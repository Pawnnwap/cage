from __future__ import annotations

import asyncio
import json
import time
from collections import Counter
from typing import Any

from app.config import Settings
from app.events import EventBus
from app.llm import LLMClient, LLMResponse
from app.sandbox_client import make_sandbox
from app.store import Store
from app.tools import TOOL_SCHEMAS, ToolExecutor


SYSTEM_PROMPT = """You are Cage, a coding agent running inside a containment-first control plane.

Operating rules:
- Every command you run is executed inside an ephemeral sandbox container.
- The sandbox has NO network access, a read-only root filesystem, and a writable /workspace.
- Never assume you can reach the internet. Use only the tools provided.
- Inspect before editing. Prefer small, verifiable steps.
- Run the code after writing it, and report the real output.
- If a command fails, read the error and change your approach instead of repeating it.
- When the task is complete, call finish with a concise summary and the evidence you observed.
"""

MAX_OBSERVATION_CHARS = 12000


class AgentRunner:
    def __init__(
        self,
        settings: Settings,
        store: Store,
        bus: EventBus,
        llm: LLMClient | Any,
        signer: Any | None = None,
    ):
        self.settings = settings
        self.store = store
        self.bus = bus
        self.llm = llm
        self.signer = signer
        self._tokens_by_task: dict[str, int] = {}

    async def emit(self, task_id: str, kind: str, payload: dict[str, Any]) -> None:
        event = self.store.add_event(task_id, kind, payload)
        await self.bus.publish(event)

    async def run(self, task_id: str) -> None:
        task = self.store.get_task(task_id)
        if task is None or task.status in {"cancelled", "interrupted"}:
            return
        self._tokens_by_task[task_id] = 0
        if hasattr(self.llm, "reset"):
            self.llm.reset()
        sandbox = make_sandbox(task_id, self.settings)
        started_at = time.time()
        self.store.update_task(task_id, status="running", started_at=started_at)
        await self.emit(
            task_id,
            "task_started",
            {"prompt": task.prompt, "model": self.settings.vultr_model},
        )

        summary: str | None = None
        error: str | None = None
        total_tokens = 0
        try:
            info = await sandbox.start()
            self.store.update_task(task_id, sandbox_id=info.id)
            await self.emit(
                task_id,
                "sandbox_started",
                info.model_dump(),
            )
            summary, total_tokens = await asyncio.wait_for(
                self._loop(task_id, task.prompt, sandbox),
                timeout=self.settings.task_timeout_s,
            )
        except asyncio.TimeoutError:
            error = f"task timed out after {self.settings.task_timeout_s}s"
        except Exception as exc:  # noqa: BLE001 - failure must be visible
            error = repr(exc)
        finally:
            total_tokens = self._tokens_by_task.pop(task_id, total_tokens)
            current = self.store.get_task(task_id)
            cancelled = bool(
                current and current.status in {"cancelled", "interrupted"}
            )
            try:
                await sandbox.destroy()
                await self.emit(task_id, "sandbox_destroyed", {})
            except Exception as exc:  # noqa: BLE001
                await self.emit(
                    task_id, "sandbox_destroy_error", {"error": repr(exc)}
                )
            if not cancelled:
                status = "failed" if error else "completed"
                self.store.update_task(
                    task_id,
                    status=status,
                    finished_at=time.time(),
                    summary=summary,
                    error=error,
                    tokens=total_tokens,
                )
                await self.emit(
                    task_id,
                    "task_finished",
                    {
                        "status": status,
                        "summary": summary,
                        "error": error,
                        "tokens": total_tokens,
                    },
                )
            else:
                # Preserve the spend trail even when the operator cancelled.
                self.store.update_task(task_id, tokens=total_tokens)
            self._seal_evidence(task_id)

    def _seal_evidence(self, task_id: str) -> None:
        if self.signer is None:
            return
        payload = self.store.evidence(task_id)
        if not payload:
            return
        signed = self.signer.signed_pack(payload)
        self.store.seal_evidence(
            task_id,
            signed,
            self.signer.fingerprint(),
            time.time(),
        )

    def _cancelled(self, task_id: str) -> bool:
        task = self.store.get_task(task_id)
        return bool(task and task.status in {"cancelled", "interrupted"})

    async def _loop(
        self, task_id: str, prompt: str, sandbox: Any
    ) -> tuple[str, int]:
        executor = ToolExecutor(
            task_id=task_id,
            sandbox=sandbox,
            store=self.store,
            bus=self.bus,
            default_timeout_s=self.settings.command_timeout_s,
        )
        messages: list[dict[str, Any]] = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": prompt},
        ]
        seen_commands: Counter[str] = Counter()
        total_tokens = 0

        for step in range(1, self.settings.max_steps + 1):
            if self._cancelled(task_id):
                return "Cancelled by operator.", total_tokens
            await self.emit(task_id, "step_started", {"step": step})
            response: LLMResponse = await asyncio.wait_for(
                self.llm.chat(messages, TOOL_SCHEMAS), timeout=180
            )
            self._tokens_by_task[task_id] = (
                self._tokens_by_task.get(task_id, 0) + response.usage_tokens
            )
            total_tokens = self._tokens_by_task[task_id]
            await self.emit(
                task_id,
                "llm_usage",
                {
                    "step": step,
                    "call_tokens": response.usage_tokens,
                    "total_tokens": total_tokens,
                    "budget": self.settings.max_task_tokens,
                },
            )
            if total_tokens > self.settings.max_task_tokens:
                raise RuntimeError(
                    f"token budget exceeded: {total_tokens} > "
                    f"{self.settings.max_task_tokens}"
                )
            await self.emit(
                task_id,
                "assistant_message",
                {"step": step, "content": response.content or ""},
            )

            if not response.tool_calls:
                if response.content:
                    messages.append(
                        {"role": "assistant", "content": response.content}
                    )
                messages.append(
                    {
                        "role": "user",
                        "content": (
                            "Continue with a tool call. If the task is complete, "
                            "call finish."
                        ),
                    }
                )
                continue

            messages.append(
                {
                    "role": "assistant",
                    "content": response.content or "",
                    "tool_calls": [
                        {
                            "id": call.id,
                            "type": "function",
                            "function": {
                                "name": call.name,
                                "arguments": json.dumps(call.arguments),
                            },
                        }
                        for call in response.tool_calls
                    ],
                }
            )

            for call in response.tool_calls:
                await self.emit(
                    task_id,
                    "tool_call",
                    {
                        "call_id": call.id,
                        "tool": call.name,
                        "arguments": call.arguments,
                    },
                )
                observation, finished, summary = await executor.execute(
                    call.name, call.arguments, call.id
                )
                await self.emit(
                    task_id,
                    "tool_result",
                    {
                        "call_id": call.id,
                        "tool": call.name,
                        "observation": observation[:MAX_OBSERVATION_CHARS],
                    },
                )
                messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": call.id,
                        "content": observation[:MAX_OBSERVATION_CHARS],
                    }
                )
                if finished:
                    return summary or "Task finished.", total_tokens

                if call.name == "run_command":
                    command = str(call.arguments.get("command", "")).strip()
                    seen_commands[command] += 1
                    count = seen_commands[command]
                    if count == 3:
                        messages.append(
                            {
                                "role": "system",
                                "content": (
                                    "You have run the same command three times. "
                                    "Stop repeating it; inspect the error or change "
                                    "your approach."
                                ),
                            }
                        )
                    elif count >= 5:
                        return (
                            "Stopped by the loop guard after repeating the same "
                            f"command {count} times.",
                            total_tokens,
                        )

        return (
            f"Stopped after reaching the {self.settings.max_steps}-step limit "
            "without a finish call.",
            total_tokens,
        )
