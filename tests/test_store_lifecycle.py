from __future__ import annotations

import time

from app.models import ContainmentReport, ProbeResult
from app.store import Store


def test_reconcile_running_marks_interrupted(tmp_path):
    store = Store(tmp_path / "cage.sqlite3")
    task = store.create_task("hello", model="qwen3.8-27b")
    store.update_task(task.id, status="running", started_at=1.0)

    ids = store.reconcile_running()

    assert ids == [task.id]
    updated = store.get_task(task.id)
    assert updated is not None
    assert updated.status == "interrupted"
    assert "restarted" in (updated.error or "")
    assert updated.model == "qwen3.8-27b"


def test_probe_reports_are_persisted(tmp_path):
    store = Store(tmp_path / "cage.sqlite3")
    task = store.create_task("hello")
    report = ContainmentReport(
        sandbox_id="ephemeral-1",
        probes=[
            ProbeResult(
                name="rm_rf",
                passed=True,
                detail="read-only root rejected the delete",
                output="permission denied",
                duration_ms=12,
            )
        ],
        host_canary_intact=True,
        generated_at=time.time(),
    )

    store.add_probe_report(report, task_id=task.id)
    reports = store.list_probe_reports(task_id=task.id)

    assert len(reports) == 1
    assert reports[0]["probe"] == "rm_rf"
    assert reports[0]["passed"] == 1
    evidence = store.evidence(task.id)
    assert evidence["probe_reports"]
