from __future__ import annotations

import re

from app.models import ExecResult


NETWORK_SIGNATURES = (
    "network is unreachable",
    "temporary failure in name resolution",
    "name or service not known",
    "connection refused",
    "network is down",
)

FORK_SIGNATURES = (
    "blockingioerror",
    "resource temporarily unavailable",
    "cannot allocate memory",
)


def _output(execution: ExecResult) -> str:
    return (execution.stdout + execution.stderr).lower()


def evaluate_probe(
    name: str,
    execution: ExecResult,
    followup: ExecResult | None = None,
) -> tuple[bool, str]:
    output = _output(execution)

    if name == "rm_rf":
        passed = (
            execution.exit_code not in (0, 127)
            and followup is not None
            and followup.exit_code == 0
        )
        return passed, (
            "read-only root rejected the delete; /etc/hostname still exists"
            if passed
            else "root filesystem was modified or rm did not fail cleanly"
        )

    if name == "readonly_canary":
        passed = (
            execution.exit_code not in (0, 127)
            and followup is not None
            and followup.stdout.strip() == "unmodified"
        )
        return passed, (
            "world-writable root canary stayed unchanged"
            if passed
            else "root filesystem accepted a write; read_only is not effective"
        )

    if name == "infinite_loop":
        passed = execution.timed_out and not execution.oom_killed
        return passed, (
            "command killed by the sandbox timeout"
            if passed
            else "infinite loop did not hit the timeout"
        )

    if name == "fork_bomb":
        hit = any(signature in output for signature in FORK_SIGNATURES)
        passed = execution.exit_code not in (0, 127) and hit
        return passed, (
            "pids/memory limits produced a resource-limit failure"
            if passed
            else "fork bomb did not show a resource-limit signature"
        )

    if name == "secret_probe":
        leaked = re.search(
            r"(?i)(api[_-]?key|token|secret|password)\s*[=:]",
            _output(execution),
        )
        passed = execution.exit_code == 0 and leaked is None
        return passed, (
            "no secret-like environment variables found"
            if passed
            else (
                f"possible secret exposed: {leaked.group(0)}"
                if leaked
                else "secret probe did not run cleanly"
            )
        )

    if name == "network_probe":
        hit = any(signature in output for signature in NETWORK_SIGNATURES)
        passed = execution.exit_code not in (0, 127) and hit
        return passed, (
            "no network route from the sandbox"
            if passed
            else "network probe did not show a network failure"
        )

    if name == "host_write":
        passed = (
            execution.exit_code not in (0, 127)
            and followup is not None
            and followup.exit_code != 0
        )
        return passed, (
            "read-only root rejected the write to /etc"
            if passed
            else "sandbox wrote to the root filesystem"
        )

    return False, f"unknown probe: {name}"


def evaluate_cross_task(
    write_a: ExecResult,
    peer_write: ExecResult,
    peer_read: ExecResult,
    read_a: ExecResult,
) -> tuple[bool, str]:
    peer_alive = (
        peer_write.exit_code == 0
        and peer_read.exit_code == 0
        and "peer-alive" in peer_read.stdout
    )
    passed = (
        peer_alive
        and write_a.exit_code == 0
        and read_a.exit_code != 0
    )
    return passed, (
        "second sandbox was alive and could not read the first workspace"
        if passed
        else "cross-task isolation check failed (peer dead or read succeeded)"
    )
