from __future__ import annotations

import asyncio
import time

import pytest

from app.agent import AgentRunner
from app.config import Settings
from app.events import EventBus
from app.llm import FakeLLM, LLMResponse, ToolCall
from app.store import Store


def _settings(tmp_path):
    return Settings(
        data_dir=tmp_path,
        workspace_root=tmp_path / "workspaces",
        sandbox_mode="local",
        llm_mode="fake",
        max_steps=6,
        command_timeout_s=10,
        task_timeout_s=30,
    )


def _script():
    return [
        LLMResponse(
            tool_calls=[
                ToolCall(
                    id="w1",
                    name="write_file",
                    arguments={
                        "path": "solution.py",
                        "content": "print('hello from cage')\n",
                    },
                )
            ]
        ),
        LLMResponse(
            tool_calls=[
                ToolCall(
                    id="r1",
                    name="run_command",
                    arguments={"command": "python solution.py"},
                )
            ]
        ),
        LLMResponse(
            tool_calls=[
                ToolCall(
                    id="f1",
                    name="finish",
                    arguments={"summary": "wrote and ran solution.py"},
                )
            ]
        ),
    ]


@pytest.mark.asyncio
async def test_agent_writes_runs_and_finishes(tmp_path):
    settings = _settings(tmp_path)
    store = Store(tmp_path / "cage.sqlite3")
    runner = AgentRunner(settings, store, EventBus(), FakeLLM(_script()))
    task = store.create_task("write and run solution.py")

    await runner.run(task.id)

    updated = store.get_task(task.id)
    assert updated is not None
    assert updated.status == "completed"
    assert updated.summary == "wrote and ran solution.py"

    events = store.get_events(task.id)
    kinds = [event.kind for event in events]
    assert "sandbox_started" in kinds
    assert "command_finished" in kinds
    assert "task_finished" in kinds
    command_events = [e for e in events if e.kind == "command_finished"]
    assert command_events
    assert command_events[-1].payload["exit_code"] == 0
    assert "hello from cage" in command_events[-1].payload["stdout"]


class BlockingLLM:
    def __init__(self):
        self.started = asyncio.Event()
        self.release = asyncio.Event()

    async def chat(self, messages, tools):
        self.started.set()
        await self.release.wait()
        return LLMResponse(
            tool_calls=[
                ToolCall(
                    id="finish-after-cancel",
                    name="finish",
                    arguments={"summary": "late finish"},
                )
            ]
        )


@pytest.mark.asyncio
async def test_cancel_is_not_overwritten_by_runner(tmp_path):
    settings = _settings(tmp_path)
    store = Store(tmp_path / "cage.sqlite3")
    llm = BlockingLLM()
    runner = AgentRunner(settings, store, EventBus(), llm)
    task = store.create_task("cancel me")

    job = asyncio.create_task(runner.run(task.id))
    await asyncio.wait_for(llm.started.wait(), timeout=2)
    store.update_task(
        task.id,
        status="cancelled",
        finished_at=time.time(),
        error="cancelled by operator",
    )
    store.add_event(
        task.id,
        "task_finished",
        {
            "status": "cancelled",
            "summary": None,
            "error": "cancelled by operator",
        },
    )
    llm.release.set()
    await asyncio.wait_for(job, timeout=5)

    updated = store.get_task(task.id)
    assert updated is not None
    assert updated.status == "cancelled"
    finished = [
        event
        for event in store.get_events(task.id)
        if event.kind == "task_finished"
    ]
    assert len(finished) == 1
