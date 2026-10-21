from __future__ import annotations

from app.drills import evaluate_cross_task, evaluate_probe
from app.models import ExecResult


def result(
    exit_code=0,
    stdout="",
    stderr="",
    timed_out=False,
    oom_killed=False,
):
    return ExecResult(
        exit_code=exit_code,
        stdout=stdout,
        stderr=stderr,
        duration_ms=1,
        timed_out=timed_out,
        oom_killed=oom_killed,
    )


def test_rm_rf_pass_and_fail():
    passed, _ = evaluate_probe("rm_rf", result(exit_code=1), result(exit_code=0))
    assert passed is True
    failed, _ = evaluate_probe("rm_rf", result(exit_code=0), result(exit_code=0))
    assert failed is False


def test_readonly_canary_distinguishes_writable_root():
    passed, _ = evaluate_probe(
        "readonly_canary",
        result(exit_code=1, stderr="read-only file system"),
        result(exit_code=0, stdout="unmodified\n"),
    )
    assert passed is True
    failed, _ = evaluate_probe(
        "readonly_canary",
        result(exit_code=0),
        result(exit_code=0, stdout="unmodifiedx\n"),
    )
    assert failed is False


def test_fork_bomb_requires_signature_not_timeout():
    timeout_only, _ = evaluate_probe(
        "fork_bomb", result(exit_code=137, timed_out=True)
    )
    assert timeout_only is False
    passed, _ = evaluate_probe(
        "fork_bomb",
        result(exit_code=1, stderr="BlockingIOError: resource temporarily unavailable"),
    )
    assert passed is True


def test_network_probe_requires_network_failure():
    passed, _ = evaluate_probe(
        "network_probe", result(exit_code=1, stderr="Network is unreachable")
    )
    assert passed is True
    failed, _ = evaluate_probe(
        "network_probe", result(exit_code=1, stderr="something else")
    )
    assert failed is False


def test_secret_probe_detects_a_leak():
    passed, _ = evaluate_probe("secret_probe", result(exit_code=0, stdout="PATH=/bin"))
    assert passed is True
    failed, _ = evaluate_probe(
        "secret_probe", result(exit_code=0, stdout="API_KEY=sk-test")
    )
    assert failed is False


def test_cross_task_requires_a_live_peer_and_a_failed_read():
    passed, _ = evaluate_cross_task(
        result(exit_code=0),
        result(exit_code=0),
        result(exit_code=0, stdout="peer-alive\n"),
        result(exit_code=1),
    )
    assert passed is True

    dead_peer, _ = evaluate_cross_task(
        result(exit_code=0),
        result(exit_code=1),
        result(exit_code=1),
        result(exit_code=1),
    )
    assert dead_peer is False

    leaked, _ = evaluate_cross_task(
        result(exit_code=0),
        result(exit_code=0),
        result(exit_code=0, stdout="peer-alive\n"),
        result(exit_code=0, stdout="cage-canary"),
    )
    assert leaked is False


def test_infinite_loop_requires_timeout_not_oom():
    passed, _ = evaluate_probe(
        "infinite_loop", result(exit_code=137, timed_out=True)
    )
    assert passed is True
    failed, _ = evaluate_probe(
        "infinite_loop",
        result(exit_code=137, timed_out=True, oom_killed=True),
    )
    assert failed is False
