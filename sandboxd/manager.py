from __future__ import annotations

import io
import posixpath
import re
import tarfile
import time
import uuid
from dataclasses import dataclass
from datetime import datetime
from typing import Any

import docker
from docker.errors import ImageNotFound, NotFound


def _container_path(raw: str) -> str:
    value = (raw or ".").strip().replace("\\", "/")
    if value.startswith("/"):
        if value == "/workspace":
            return "/workspace"
        if not value.startswith("/workspace/"):
            raise ValueError(f"path must stay inside /workspace: {raw}")
        value = value[len("/workspace/") :]
    value = value.lstrip("/")
    normalized = posixpath.normpath(value)
    if normalized in ("", "."):
        return "/workspace"
    if normalized == ".." or normalized.startswith("../"):
        raise ValueError(f"path escapes /workspace: {raw}")
    return "/workspace/" + normalized


def _decode(value: bytes | None) -> str:
    if not value:
        return ""
    return value.decode("utf-8", errors="replace")


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


@dataclass
class SandboxRecord:
    id: str
    task_id: str
    container: Any
    image_id: str
    created_at: float
    last_used: float


class SandboxManager:
    def __init__(
        self,
        image: str,
        ttl_seconds: int = 7200,
        max_sandboxes: int = 4,
        workspace_limit_mb: int = 64,
        memory_mb: int = 512,
        cpus: float = 1.0,
        pids_limit: int = 128,
    ):
        self.image = image
        self.ttl_seconds = ttl_seconds
        self.max_sandboxes = max_sandboxes
        self.workspace_limit_mb = workspace_limit_mb
        self.memory_mb = memory_mb
        self.cpus = cpus
        self.pids_limit = pids_limit
        self.client = docker.from_env()
        self._records: dict[str, SandboxRecord] = {}

    def create(self, task_id: str) -> dict[str, Any]:
        if len(self._records) >= self.max_sandboxes:
            raise RuntimeError(
                f"sandbox capacity reached ({self.max_sandboxes} concurrent)"
            )
        suffix = uuid.uuid4().hex[:8]
        name = (
            f"cage-{''.join(c for c in task_id if c.isalnum() or c in '-_')[:24]}"
            f"-{suffix}"
        )
        tmpfs = {
            "/tmp": "rw,noexec,nosuid,size=64m,uid=1000,gid=1000,mode=1777",
            "/workspace": (
                f"rw,nosuid,size={self.workspace_limit_mb}m,"
                "uid=1000,gid=1000,mode=0770"
            ),
        }
        try:
            container = self.client.containers.run(
                self.image,
                command=["sleep", "infinity"],
                detach=True,
                name=name,
                network_mode="none",
                ipc_mode="none",
                read_only=True,
                tmpfs=tmpfs,
                mem_limit=f"{self.memory_mb}m",
                memswap_limit=f"{self.memory_mb}m",
                nano_cpus=int(self.cpus * 1_000_000_000),
                pids_limit=self.pids_limit,
                cap_drop=["ALL"],
                security_opt=["no-new-privileges"],
                user="1000:1000",
                working_dir="/workspace",
                labels={
                    "cage.sandbox": "1",
                    "cage.task": task_id,
                    "cage.created_at": str(time.time()),
                },
            )
        except ImageNotFound as exc:
            raise RuntimeError(
                f"sandbox image not found: {self.image}. "
                "Build it with: docker build -t cage-sandbox:latest sandbox_image"
            ) from exc
        now = time.time()
        image_id = getattr(getattr(container, "image", None), "id", None)
        raw_host = (getattr(container, "attrs", {}) or {}).get("HostConfig", {}) or {}
        host_config = {
            key: raw_host.get(key)
            for key in (
                "NetworkMode",
                "IpcMode",
                "ReadonlyRootfs",
                "CapDrop",
                "SecurityOpt",
                "Memory",
                "NanoCpus",
                "PidsLimit",
                "Privileged",
                "Binds",
                "Devices",
                "PidMode",
                "UsernsMode",
                "Tmpfs",
            )
        }
        self._records[name] = SandboxRecord(
            id=name,
            task_id=task_id,
            container=container,
            image_id=image_id or "unknown",
            created_at=now,
            last_used=now,
        )
        return {
            "id": name,
            "task_id": task_id,
            "container_id": container.id,
            "status": "running",
            "image_id": image_id,
            "host_config": host_config,
            "limits": {
                "network": "none",
                "ipc": "none",
                "cpus": self.cpus,
                "memory_mb": self.memory_mb,
                "pids_limit": self.pids_limit,
                "rootfs": "read-only",
                "user": "1000:1000",
                "workspace": f"{self.workspace_limit_mb}MB tmpfs",
            },
        }

    def _record(self, sandbox_id: str) -> SandboxRecord:
        record = self._records.get(sandbox_id)
        if record is None:
            raise NotFound(f"sandbox not found: {sandbox_id}")
        record.last_used = time.time()
        return record

    @staticmethod
    def _oom_kills(record: SandboxRecord) -> int:
        result = record.container.exec_run(
            [
                "timeout",
                "2",
                "sh",
                "-lc",
                (
                    "cat /sys/fs/cgroup/memory.events 2>/dev/null "
                    "| awk '$1==\"oom_kill\"{print $2}'"
                ),
            ],
            demux=True,
        )
        stdout_b, _ = (
            result.output if isinstance(result.output, tuple) else (result.output, None)
        )
        values = _decode(stdout_b).strip().splitlines()
        try:
            return int(values[-1]) if values else 0
        except ValueError:
            return 0

    def exec(self, sandbox_id: str, command: str, timeout_s: int) -> dict[str, Any]:
        record = self._record(sandbox_id)
        inner = [
            "timeout",
            "--signal=KILL",
            str(max(1, int(timeout_s))),
            "sh",
            "-lc",
            command,
        ]
        oom_before = self._oom_kills(record)
        started = time.perf_counter()
        result = record.container.exec_run(inner, demux=True, workdir="/workspace")
        oom_after = self._oom_kills(record)
        duration_ms = int((time.perf_counter() - started) * 1000)
        if isinstance(result.output, tuple):
            stdout_b, stderr_b = result.output
        else:
            stdout_b, stderr_b = result.output, None
        exit_code = int(result.exit_code or 0)
        try:
            record.container.reload()
            state_oom = bool(
                (record.container.attrs.get("State") or {}).get("OOMKilled", False)
            )
        except Exception:
            state_oom = False
        # State.OOMKilled tracks the container's main process; an exec'd child
        # OOM is visible only in the cgroup counter. Check both.
        oom_killed = state_oom or oom_after > oom_before
        return {
            "exit_code": exit_code,
            "stdout": _decode(stdout_b)[-20000:],
            "stderr": _decode(stderr_b)[-8000:],
            "duration_ms": duration_ms,
            "timed_out": exit_code in (124, 137) and not oom_killed,
            "oom_killed": oom_killed,
        }

    @staticmethod
    def _realpath(record: SandboxRecord, target: str) -> str:
        script = (
            "import os,sys; p=os.path.realpath(sys.argv[1]); print(p); "
            "sys.exit(0 if p == '/workspace' or p.startswith('/workspace/') else 3)"
        )
        result = record.container.exec_run(
            ["timeout", "5", "python", "-c", script, target], demux=True
        )
        stdout_b, stderr_b = (
            result.output if isinstance(result.output, tuple) else (result.output, None)
        )
        if result.exit_code != 0:
            raise ValueError(
                f"path escapes /workspace through a symlink: {_decode(stderr_b)}"
            )
        lines = _decode(stdout_b).strip().splitlines()
        if not lines:
            raise ValueError(f"cannot resolve path in sandbox: {target}")
        resolved = lines[-1]
        if resolved != "/workspace" and not resolved.startswith("/workspace/"):
            raise ValueError(f"path escapes /workspace: {target}")
        return resolved

    def read_file(self, sandbox_id: str, path: str) -> str:
        record = self._record(sandbox_id)
        target = self._realpath(record, _container_path(path))
        result = record.container.exec_run(
            ["timeout", "5", "cat", target], demux=True
        )
        stdout_b, stderr_b = (
            result.output if isinstance(result.output, tuple) else (result.output, None)
        )
        if result.exit_code != 0:
            raise FileNotFoundError(_decode(stderr_b) or f"cannot read {path}")
        return _truncate_file_content(_decode(stdout_b))

    def write_file(self, sandbox_id: str, path: str, content: str) -> None:
        record = self._record(sandbox_id)
        if len(content.encode("utf-8")) > 1_048_576:
            raise ValueError("file content exceeds the 1MB limit")
        target = _container_path(path)
        parent = self._realpath(record, posixpath.dirname(target))
        target = posixpath.join(parent, posixpath.basename(target))
        record.container.exec_run(["mkdir", "-p", parent])
        data = content.encode("utf-8")
        buffer = io.BytesIO()
        with tarfile.open(fileobj=buffer, mode="w") as tar:
            info = tarfile.TarInfo(name=posixpath.basename(target))
            info.size = len(data)
            info.mode = 0o664
            tar.addfile(info, io.BytesIO(data))
        buffer.seek(0)
        if not record.container.put_archive(parent, buffer.getvalue()):
            raise RuntimeError(f"failed to write {path}")

    def list_files(self, sandbox_id: str, path: str = ".") -> list[str]:
        record = self._record(sandbox_id)
        base = self._realpath(record, _container_path(path))
        result = record.container.exec_run(
            ["timeout", "5", "find", base, "-maxdepth", "4", "-type", "f"],
            demux=True,
        )
        stdout_b, _ = (
            result.output if isinstance(result.output, tuple) else (result.output, None)
        )
        files: list[str] = []
        for line in _decode(stdout_b).splitlines():
            line = line.strip()
            if not line:
                continue
            if line.startswith("/workspace/"):
                line = line[len("/workspace/") :]
            files.append(line)
        return sorted(files)[:300]

    def stats(self, sandbox_id: str) -> dict[str, Any]:
        record = self._record(sandbox_id)
        stats = record.container.stats(stream=False)
        memory = stats.get("memory_stats", {}) or {}
        cpu = stats.get("cpu_stats", {}) or {}
        precpu = stats.get("precpu_stats", {}) or {}
        cpu_delta = (
            cpu.get("cpu_usage", {}).get("total_usage", 0)
            - precpu.get("cpu_usage", {}).get("total_usage", 0)
        )
        system_delta = cpu.get("system_cpu_usage", 0) - precpu.get(
            "system_cpu_usage", 0
        )
        online = cpu.get("online_cpus") or len(
            cpu.get("cpu_usage", {}).get("percpu_usage", []) or [1]
        )
        cpu_percent = (
            (cpu_delta / system_delta) * online * 100.0
            if system_delta > 0
            else 0.0
        )
        return {
            "cpu_percent": round(cpu_percent, 2),
            "memory_usage_mb": round(memory.get("usage", 0) / (1024 * 1024), 1),
            "memory_limit_mb": round(memory.get("limit", 0) / (1024 * 1024), 1),
            "pids": (stats.get("pids_stats", {}) or {}).get("current", 0),
        }

    def destroy(self, sandbox_id: str) -> None:
        record = self._records.pop(sandbox_id, None)
        if record is None:
            return
        try:
            record.container.remove(force=True)
        except NotFound:
            pass

    def count(self) -> int:
        return len(self._records)

    def reap_once(self) -> int:
        cutoff = time.time() - self.ttl_seconds
        removed = 0
        for sandbox_id, record in list(self._records.items()):
            if record.last_used < cutoff:
                self.destroy(sandbox_id)
                removed += 1
        try:
            containers = self.client.containers.list(
                all=True, filters={"label": "cage.sandbox=1"}
            )
        except Exception:
            containers = []
        for container in containers:
            try:
                created = (container.attrs.get("Created") or "").replace("Z", "+00:00")
                match = re.match(r"^(.*\.\d{6})\d*(.*)$", created)
                if match:
                    created = match.group(1) + match.group(2)
                created_at = datetime.fromisoformat(created).timestamp()
            except Exception:
                continue
            if created_at < cutoff:
                try:
                    container.remove(force=True)
                    removed += 1
                except Exception:
                    pass
        return removed
