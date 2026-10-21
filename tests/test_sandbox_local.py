from __future__ import annotations

import pytest

from app.config import Settings
from app.sandbox_client import LocalSandbox, SandboxError


def _settings(tmp_path):
    return Settings(
        data_dir=tmp_path,
        workspace_root=tmp_path / "workspaces",
        sandbox_mode="local",
        command_timeout_s=5,
    )


@pytest.mark.asyncio
async def test_roundtrip_and_workspace_paths(tmp_path):
    sandbox = LocalSandbox("roundtrip", _settings(tmp_path))
    await sandbox.start()
    try:
        await sandbox.write_file("notes/hello.txt", "hello cage")
        assert await sandbox.read_file("notes/hello.txt") == "hello cage"
        assert await sandbox.read_file("/workspace/notes/hello.txt") == "hello cage"
        assert "notes/hello.txt" in await sandbox.list_files()

        result = await sandbox.exec("python -c \"print('ok')\"")
        assert result.exit_code == 0
        assert "ok" in result.stdout
    finally:
        await sandbox.destroy()


@pytest.mark.asyncio
async def test_large_file_read_has_explicit_truncation_marker(tmp_path):
    sandbox = LocalSandbox("large", _settings(tmp_path))
    await sandbox.start()
    try:
        content = "HEADER\n" + ("x" * 50000) + "\nFOOTER"
        await sandbox.write_file("large.txt", content)
        read = await sandbox.read_file("large.txt")
        assert read.startswith("HEADER")
        assert "Cage truncated" in read
        assert read.endswith("FOOTER")
    finally:
        await sandbox.destroy()


@pytest.mark.asyncio
async def test_rejects_path_escape(tmp_path):
    sandbox = LocalSandbox("escape", _settings(tmp_path))
    await sandbox.start()
    try:
        with pytest.raises(SandboxError):
            await sandbox.read_file("../secret.txt")
        with pytest.raises(SandboxError):
            await sandbox.read_file("/etc/passwd")
    finally:
        await sandbox.destroy()


@pytest.mark.asyncio
async def test_timeout_is_reported(tmp_path):
    sandbox = LocalSandbox("timeout", _settings(tmp_path))
    await sandbox.start()
    try:
        result = await sandbox.exec(
            "python -c \"import time; time.sleep(3)\"", timeout_s=1
        )
        assert result.timed_out is True
        assert result.exit_code == 124
    finally:
        await sandbox.destroy()
