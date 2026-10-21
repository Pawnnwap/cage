from __future__ import annotations

import json
import time
from typing import Any

from app.events import EventBus
from app.sandbox_client import Sandbox, SandboxError
from app.store import Store


TOOL_SCHEMAS: list[dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "run_command",
            "description": (
                "Run a shell command inside the isolated sandbox. The sandbox has "
                "no network access and a read-only root filesystem. Use /workspace."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "command": {"type": "string"},
                    "timeout_s": {"type": "integer", "minimum": 1, "maximum": 120},
                },
                "required": ["command"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "read_file",
            "description": "Read a UTF-8 text file from the sandbox workspace.",
            "parameters": {
                "type": "object",
                "properties": {"path": {"type": "string"}},
                "required": ["path"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "write_file",
            "description": "Create or overwrite a UTF-8 text file in the sandbox workspace.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string"},
                    "content": {"type": "string"},
                },
                "required": ["path", "content"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_files",
            "description": "List files in the sandbox workspace.",
            "parameters": {
                "type": "object",
                "properties": {"path": {"type": "string", "default": "."}},
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "finish",
            "description": "Finish the task and return a concise summary of what was done.",
            "parameters": {
                "type": "object",
                "properties": {"summary": {"type": "string"}},
                "required": ["summary"],
            },
        },
    },
]


class ToolExecutor:
    def __init__(
        self,
        task_id: str,
        sandbox: Sandbox,
        store: Store,
        bus: EventBus,
        default_timeout_s: int = 30,
    ):
        self.task_id = task_id
        self.sandbox = sandbox
        self.store = store
        self.bus = bus
        self.default_timeout_s = default_timeout_s

    async def emit(self, kind: str, payload: dict[str, Any]) -> None:
        event = self.store.add_event(self.task_id, kind, payload)
        await self.bus.publish(event)

    async def execute(
        self, name: str, arguments: dict[str, Any], call_id: str
    ) -> tuple[str, bool, str | None]:
        started = time.perf_counter()
        try:
            if name == "run_command":
                return await self._run_command(arguments, call_id, started)
            if name == "read_file":
                return await self._read_file(arguments, call_id, started)
            if name == "write_file":
                return await self._write_file(arguments, call_id, started)
            if name == "list_files":
                return await self._list_files(arguments, call_id, started)
            if name == "finish":
                summary = str(arguments.get("summary", "Task finished."))
                await self.emit(
                    "task_summary",
                    {"call_id": call_id, "summary": summary},
                )
                return summary, True, summary
            return f"error: unknown tool {name}", False, None
        except SandboxError as exc:
            await self.emit(
                "tool_error",
                {"call_id": call_id, "tool": name, "error": str(exc)},
            )
            return f"error: {exc}", False, None
        except Exception as exc:  # noqa: BLE001 - surface tool errors to the model
            await self.emit(
                "tool_error",
                {"call_id": call_id, "tool": name, "error": repr(exc)},
            )
            return f"error: {exc!r}", False, None

    async def _run_command(
        self, arguments: dict[str, Any], call_id: str, started: float
    ) -> tuple[str, bool, str | None]:
        command = str(arguments.get("command", "")).strip()
        if not command:
            return "error: empty command", False, None
        timeout_s = int(arguments.get("timeout_s") or self.default_timeout_s)
        await self.emit(
            "command_started",
            {"call_id": call_id, "command": command, "timeout_s": timeout_s},
        )
        result = await self.sandbox.exec(command, timeout_s=timeout_s)
        await self.emit(
            "command_finished",
            {
                "call_id": call_id,
                "command": command,
                "exit_code": result.exit_code,
                "timed_out": result.timed_out,
                "oom_killed": result.oom_killed,
                "duration_ms": result.duration_ms,
                "stdout": result.stdout[-8000:],
                "stderr": result.stderr[-4000:],
            },
        )
        observation = (
            f"exit_code: {result.exit_code}\n"
            f"timed_out: {result.timed_out}\n"
            f"oom_killed: {result.oom_killed}\n"
            f"duration_ms: {result.duration_ms}\n"
            f"stdout:\n{result.stdout[-8000:]}\n"
            f"stderr:\n{result.stderr[-4000:]}"
        )
        return observation, False, None

    async def _read_file(
        self, arguments: dict[str, Any], call_id: str, started: float
    ) -> tuple[str, bool, str | None]:
        path = str(arguments.get("path", "")).strip()
        content = await self.sandbox.read_file(path)
        await self.emit(
            "file_read",
            {"call_id": call_id, "path": path, "chars": len(content)},
        )
        return content, False, None

    async def _write_file(
        self, arguments: dict[str, Any], call_id: str, started: float
    ) -> tuple[str, bool, str | None]:
        path = str(arguments.get("path", "")).strip()
        content = str(arguments.get("content", ""))
        await self.sandbox.write_file(path, content)
        await self.emit(
            "file_written",
            {"call_id": call_id, "path": path, "chars": len(content)},
        )
        return f"wrote {len(content)} chars to {path}", False, None

    async def _list_files(
        self, arguments: dict[str, Any], call_id: str, started: float
    ) -> tuple[str, bool, str | None]:
        path = str(arguments.get("path", ".") or ".")
        files = await self.sandbox.list_files(path)
        await self.emit(
            "files_listed",
            {"call_id": call_id, "path": path, "count": len(files)},
        )
        return json.dumps(files, ensure_ascii=False), False, None
