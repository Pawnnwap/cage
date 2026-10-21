from __future__ import annotations

from types import SimpleNamespace

import pytest

from sandboxd.manager import SandboxManager


class FakeContainer:
    def __init__(self):
        self.id = "container-id"
        self.image = SimpleNamespace(id="sha256:image-id")
        self.attrs = {
            "State": {"OOMKilled": False},
            "HostConfig": {
                "NetworkMode": "none",
                "IpcMode": "none",
                "ReadonlyRootfs": True,
                "CapDrop": ["ALL"],
                "SecurityOpt": ["no-new-privileges"],
                "Memory": 536870912,
                "NanoCpus": 1_000_000_000,
                "PidsLimit": 128,
                "Privileged": False,
                "Binds": None,
                "Devices": [],
                "PidMode": "",
                "UsernsMode": "",
                "Tmpfs": {"/workspace": "rw,nosuid,size=64m"},
            },
        }
        self.removed = False

    def remove(self, force=False):
        self.removed = True

    def reload(self):
        return None

    def exec_run(self, command, demux=True, workdir=None):
        if command[:3] == ["cat", "/workspace/x"]:
            return SimpleNamespace(exit_code=0, output=(b"ok", b""))
        if command[0] == "find":
            return SimpleNamespace(exit_code=0, output=(b"/workspace/a.txt\n", b""))
        return SimpleNamespace(exit_code=0, output=(b"", b""))


class FakeContainers:
    def __init__(self):
        self.kwargs = None
        self.container = FakeContainer()

    def run(self, image, **kwargs):
        self.kwargs = kwargs
        return self.container


class FakeClient:
    def __init__(self):
        self.containers = FakeContainers()
        self.volumes = SimpleNamespace(create=lambda **kwargs: None)


def _manager(monkeypatch, max_sandboxes=4):
    fake = FakeClient()
    monkeypatch.setattr("sandboxd.manager.docker.from_env", lambda: fake)
    manager = SandboxManager(
        "cage-sandbox:latest",
        max_sandboxes=max_sandboxes,
        workspace_limit_mb=64,
    )
    return manager, fake


def test_docker_run_flags_are_pinned(monkeypatch):
    manager, fake = _manager(monkeypatch, max_sandboxes=1)
    info = manager.create("task-1")
    kwargs = fake.containers.kwargs

    assert kwargs["network_mode"] == "none"
    assert kwargs["ipc_mode"] == "none"
    assert kwargs["read_only"] is True
    assert kwargs["cap_drop"] == ["ALL"]
    assert kwargs["security_opt"] == ["no-new-privileges"]
    assert kwargs["user"] == "1000:1000"
    assert kwargs["pids_limit"] == 128
    assert kwargs["nano_cpus"] == 1_000_000_000
    assert kwargs["mem_limit"] == "512m"
    assert kwargs["memswap_limit"] == "512m"
    assert "size=64m" in kwargs["tmpfs"]["/workspace"]
    assert "uid=1000" in kwargs["tmpfs"]["/workspace"]
    assert "volumes" not in kwargs
    assert kwargs.get("privileged") is not True
    assert "pid_mode" not in kwargs
    assert "mounts" not in kwargs
    assert "devices" not in kwargs
    assert "userns_mode" not in kwargs
    assert info["image_id"] == "sha256:image-id"
    assert info["host_config"]["NetworkMode"] == "none"
    assert info["host_config"]["ReadonlyRootfs"] is True
    assert info["limits"]["network"] == "none"
    assert info["limits"]["workspace"] == "64MB tmpfs"

    manager.destroy(info["id"])
    assert fake.containers.container.removed is True


def test_sandbox_capacity_is_enforced(monkeypatch):
    manager, _ = _manager(monkeypatch, max_sandboxes=1)
    manager.create("task-1")
    with pytest.raises(RuntimeError, match="capacity"):
        manager.create("task-2")


def test_oom_is_not_reported_as_timeout(monkeypatch):
    manager, fake = _manager(monkeypatch)
    info = manager.create("task-oom")
    container = fake.containers.container

    def exec_run(command, demux=True, workdir=None):
        return SimpleNamespace(exit_code=137, output=(b"", b"killed"))

    container.exec_run = exec_run
    container.attrs = {"State": {"OOMKilled": True}}

    result = manager.exec(info["id"], "python -c 'x'", 5)
    assert result["exit_code"] == 137
    assert result["oom_killed"] is True
    assert result["timed_out"] is False


def test_child_oom_is_detected_from_cgroup_counter(monkeypatch):
    manager, fake = _manager(monkeypatch)
    info = manager.create("task-child-oom")
    container = fake.containers.container
    calls = {"oom": 0}

    def exec_run(command, demux=True, workdir=None):
        joined = " ".join(command)
        if "memory.events" in joined:
            calls["oom"] += 1
            return SimpleNamespace(
                exit_code=0,
                output=(f"{calls['oom'] - 1}\n".encode(), b""),
            )
        return SimpleNamespace(exit_code=137, output=(b"", b"killed"))

    container.exec_run = exec_run
    container.attrs = {"State": {"OOMKilled": False}}

    result = manager.exec(info["id"], "python -c 'x'", 5)
    assert result["exit_code"] == 137
    assert result["oom_killed"] is True
    assert result["timed_out"] is False


def test_symlink_escape_is_rejected(monkeypatch):
    manager, fake = _manager(monkeypatch)
    info = manager.create("task-symlink")
    container = fake.containers.container

    def exec_run(command, demux=True, workdir=None):
        if "python" in command and "-c" in command:
            return SimpleNamespace(exit_code=3, output=(b"", b"outside"))
        return SimpleNamespace(exit_code=0, output=(b"/workspace/x", b""))

    container.exec_run = exec_run

    with pytest.raises(ValueError, match="symlink|escapes"):
        manager.read_file(info["id"], "root/etc/passwd")
