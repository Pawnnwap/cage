from __future__ import annotations

import asyncio
import shutil
import time
from pathlib import Path
from typing import Protocol

import httpx

from app.config import Settings
from app.models import ExecResult, SandboxInfo


class SandboxError(RuntimeError):
    pass


class Sandbox(Protocol):
    async def start(self) -> SandboxInfo: ...
    async def exec(self, command: str, timeout_s: int | None = None) -> ExecResult: ...
    async def read_file(self, path: str) -> str: ...
    async def write_file(self, path: str, content: str) -> None: ...
    async def list_files(self, path: str = ".") -> list[str]: ...
    async def stats(self) -> dict: ...
    async def destroy(self) -> None: ...


def _truncate_file_content(content: str, limit: int = 40000) -> str:
    if len(content) <= limit:
        return content
    head = content[: limit - 4000]
    tail = content[-4000:]
    dropped = len(content) - len(head) - len(tail)
    return (
        head
        + f"\n...[Cage truncated {dropped} chars; use run_command to "
        "inspect a specific range]...\n"
        + tail
    )


def _resolve_workspace_path(root: Path, raw: str) -> Path:
    cleaned = raw.strip().replace("\\", "/")
    if cleaned.startswith("/workspace/"):
        cleaned = cleaned[len("/workspace/") :]
    elif cleaned == "/workspace":
        cleaned = "."
    cleaned = cleaned.lstrip("/")
    candidate = (root / cleaned).resolve()
    root_resolved = root.resolve()
    if candidate != root_resolved and root_resolved not in candidate.parents:
        raise SandboxError(f"path escapes workspace: {raw}")
    return candidate


class LocalSandbox:
    """Development-only fallback. It is NOT a security boundary.

    The Vultr submission must run with SANDBOX_MODE=docker. This class exists
    so the control plane and tests work on a Windows laptop without Docker.
    """

    def __init__(self, task_id: str, settings: Settings):
        self.task_id = task_id
        self.root = (settings.workspace_root / task_id).resolve()
        self._default_timeout = settings.command_timeout_s
        self._id = f"local-{task_id[:12]}"
        self._started = False

    async def start(self) -> SandboxInfo:
        self.root.mkdir(parents=True, exist_ok=True)
        self._started = True
        return SandboxInfo(
            id=self._id,
            task_id=self.task_id,
            container_id=self._id,
            status="running",
            limits={
                "mode": "local",
                "network": "host",
                "note": "development fallback; not a security boundary",
            },
        )

    async def exec(self, command: str, timeout_s: int | None = None) -> ExecResult:
        if not self._started:
            raise SandboxError("sandbox not started")
        timeout = timeout_s or self._default_timeout
        started = time.perf_counter()
        proc = await asyncio.create_subprocess_shell(
            command,
            cwd=str(self.root),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        timed_out = False
        try:
            stdout_b, stderr_b = await asyncio.wait_for(
                proc.communicate(), timeout=timeout
            )
        except asyncio.TimeoutError:
            timed_out = True
            proc.kill()
            stdout_b, stderr_b = await proc.communicate()
        duration_ms = int((time.perf_counter() - started) * 1000)
        return ExecResult(
            exit_code=124 if timed_out else int(proc.returncode or 0),
            stdout=stdout_b.decode("utf-8", errors="replace")[-20000:],
            stderr=stderr_b.decode("utf-8", errors="replace")[-8000:],
            duration_ms=duration_ms,
            timed_out=timed_out,
            oom_killed=False,
        )

    async def read_file(self, path: str) -> str:
        target = _resolve_workspace_path(self.root, path)
        if not target.is_file():
            raise SandboxError(f"not a file: {path}")
        return _truncate_file_content(
            target.read_text(encoding="utf-8", errors="replace")
        )

    async def write_file(self, path: str, content: str) -> None:
        target = _resolve_workspace_path(self.root, path)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")

    async def list_files(self, path: str = ".") -> list[str]:
        base = _resolve_workspace_path(self.root, path)
        if not base.exists():
            return []
        files = [
            str(p.relative_to(self.root)).replace("\\", "/")
            for p in base.rglob("*")
            if p.is_file()
        ]
        return sorted(files)[:300]

    async def stats(self) -> dict:
        return {
            "mode": "local",
            "cpu_percent": None,
            "memory_usage_mb": None,
            "memory_limit_mb": None,
            "pids": None,
        }

    async def destroy(self) -> None:
        self._started = False
        shutil.rmtree(self.root, ignore_errors=True)


class DockerSandbox:
    """Talks to sandboxd, which owns the Docker socket and the container."""

    def __init__(self, task_id: str, settings: Settings):
        self.task_id = task_id
        self.base_url = settings.sandboxd_url.rstrip("/")
        self._default_timeout = settings.command_timeout_s
        headers = (
            {"Authorization": f"Bearer {settings.sandboxd_token}"}
            if settings.sandboxd_token
            else {}
        )
        self._client = httpx.AsyncClient(
            base_url=self.base_url, timeout=60.0, headers=headers
        )
        self._info: SandboxInfo | None = None

    async def start(self) -> SandboxInfo:
        response = await self._client.post(
            "/v1/sandboxes",
            json={"task_id": self.task_id},
        )
        response.raise_for_status()
        self._info = SandboxInfo(**response.json())
        return self._info

    @property
    def sandbox_id(self) -> str:
        if self._info is None:
            raise SandboxError("sandbox not started")
        return self._info.id

    async def exec(self, command: str, timeout_s: int | None = None) -> ExecResult:
        effective_timeout = int(timeout_s or self._default_timeout)
        response = await self._client.post(
            f"/v1/sandboxes/{self.sandbox_id}/exec",
            json={
                "command": command,
                "timeout_s": effective_timeout,
            },
            # Must exceed the sandbox-side timeout; otherwise a valid
            # 61-120s command fails client-side while it is still running.
            timeout=float(effective_timeout) + 20.0,
        )
        response.raise_for_status()
        return ExecResult(**response.json())

    async def read_file(self, path: str) -> str:
        response = await self._client.get(
            f"/v1/sandboxes/{self.sandbox_id}/files", params={"path": path}
        )
        response.raise_for_status()
        return response.json()["content"]

    async def write_file(self, path: str, content: str) -> None:
        response = await self._client.put(
            f"/v1/sandboxes/{self.sandbox_id}/files",
            json={"path": path, "content": content},
        )
        response.raise_for_status()

    async def list_files(self, path: str = ".") -> list[str]:
        response = await self._client.get(
            f"/v1/sandboxes/{self.sandbox_id}/files/list", params={"path": path}
        )
        response.raise_for_status()
        return list(response.json()["files"])

    async def stats(self) -> dict:
        response = await self._client.get(
            f"/v1/sandboxes/{self.sandbox_id}/stats"
        )
        response.raise_for_status()
        return response.json()

    async def destroy(self) -> None:
        try:
            if self._info is not None:
                await self._client.delete(f"/v1/sandboxes/{self.sandbox_id}")
        finally:
            await self._client.aclose()
            self._info = None


def make_sandbox(task_id: str, settings: Settings) -> Sandbox:
    if settings.sandbox_mode == "docker":
        return DockerSandbox(task_id, settings)
    return LocalSandbox(task_id, settings)
