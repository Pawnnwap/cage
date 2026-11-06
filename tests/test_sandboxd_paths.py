from __future__ import annotations

import base64
from types import SimpleNamespace

import pytest

from sandboxd.manager import _WRITE_SCRIPT, SandboxManager, _container_path


class WritableFakeContainer:
    """Mirrors a read-only rootfs: the archive API is refused, exec is not."""

    def __init__(self, write_exit: int = 0, escape: bool = False):
        self.files: dict[str, bytes] = {}
        self.write_args: list[str] = []
        self.write_exit = write_exit
        self.escape = escape

    def put_archive(self, path, data):
        raise AssertionError("container rootfs is marked read-only")

    def exec_run(self, command, demux=True):
        if command[0] == "mkdir":
            return SimpleNamespace(exit_code=0, output=(b"", b""))
        script = command[4]
        if script == _WRITE_SCRIPT:
            target, mode, chunk = command[5:]
            self.write_args.append(chunk)
            if self.write_exit:
                return SimpleNamespace(exit_code=self.write_exit, output=(b"", b"disk full"))
            previous = self.files.get(target, b"") if mode == "ab" else b""
            self.files[target] = previous + base64.b64decode(chunk)
            return SimpleNamespace(exit_code=0, output=(b"", b""))
        if self.escape:
            return SimpleNamespace(exit_code=3, output=(b"/etc/passwd\n", b""))
        return SimpleNamespace(exit_code=0, output=(f"{command[5]}\n".encode(), b""))


def _manager(container) -> SandboxManager:
    manager = SandboxManager.__new__(SandboxManager)
    manager._record = lambda sandbox_id: SimpleNamespace(container=container)
    return manager


def test_write_file_round_trips_large_content_through_exec():
    container = WritableFakeContainer()
    content = "é" * 450_000
    _manager(container).write_file("sbx", "notes/big.txt", content)
    assert container.files["/workspace/notes/big.txt"] == content.encode("utf-8")
    assert len(container.write_args) > 1
    assert max(len(arg) for arg in container.write_args) < 131_072


def test_write_file_creates_empty_file():
    container = WritableFakeContainer()
    _manager(container).write_file("sbx", "empty.txt", "")
    assert container.files["/workspace/empty.txt"] == b""


def test_write_file_replaces_existing_content():
    container = WritableFakeContainer()
    manager = _manager(container)
    manager.write_file("sbx", "a.txt", "first version")
    manager.write_file("sbx", "a.txt", "second")
    assert container.files["/workspace/a.txt"] == b"second"


def test_write_file_surfaces_sandbox_failure():
    container = WritableFakeContainer(write_exit=1)
    with pytest.raises(OSError, match="disk full"):
        _manager(container).write_file("sbx", "a.txt", "x")


def test_write_file_rejects_symlink_escape_before_writing():
    container = WritableFakeContainer(escape=True)
    with pytest.raises(ValueError):
        _manager(container).write_file("sbx", "link.txt", "x")
    assert container.write_args == []


def test_write_file_enforces_size_cap():
    container = WritableFakeContainer()
    with pytest.raises(ValueError):
        _manager(container).write_file("sbx", "a.txt", "x" * 1_048_577)
    assert container.write_args == []


def test_maps_relative_and_absolute_workspace_paths():
    assert _container_path(".") == "/workspace"
    assert _container_path("notes/a.txt") == "/workspace/notes/a.txt"
    assert _container_path("/workspace/notes/a.txt") == "/workspace/notes/a.txt"
    assert _container_path("notes/../a.txt") == "/workspace/a.txt"


@pytest.mark.parametrize("path", ["../secret", "/etc/passwd", "/workspace/../../etc"])
def test_rejects_escape(path):
    with pytest.raises(ValueError):
        _container_path(path)
