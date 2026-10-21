from __future__ import annotations

import json
import sqlite3
import threading
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.models import ContainmentReport, Event, Task


_TASK_FIELDS = {
    "title",
    "prompt",
    "status",
    "started_at",
    "finished_at",
    "summary",
    "error",
    "sandbox_id",
    "model",
    "tokens",
    "owner",
}


class Store:
    def __init__(self, path: Path):
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._conn = sqlite3.connect(str(path), check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._init()

    def _init(self) -> None:
        with self._lock:
            self._conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS tasks (
                    id TEXT PRIMARY KEY,
                    title TEXT NOT NULL,
                    prompt TEXT NOT NULL,
                    status TEXT NOT NULL,
                    created_at REAL NOT NULL,
                    started_at REAL,
                    finished_at REAL,
                    summary TEXT,
                    error TEXT,
                    sandbox_id TEXT,
                    model TEXT,
                    tokens INTEGER NOT NULL DEFAULT 0,
                    owner TEXT,
                    evidence_json TEXT,
                    evidence_signature TEXT,
                    evidence_public_key TEXT,
                    evidence_key_fingerprint TEXT,
                    evidence_signed_at REAL
                );
                CREATE TABLE IF NOT EXISTS events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    task_id TEXT NOT NULL,
                    ts REAL NOT NULL,
                    kind TEXT NOT NULL,
                    payload TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS probe_reports (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    task_id TEXT,
                    ts REAL NOT NULL,
                    probe TEXT NOT NULL,
                    passed INTEGER NOT NULL,
                    detail TEXT NOT NULL,
                    output TEXT NOT NULL,
                    duration_ms INTEGER NOT NULL,
                    payload TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_events_task
                    ON events(task_id, id);
                """
            )
            self._migrate()
            self._conn.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_probe_task
                ON probe_reports(task_id, id)
                """
            )
            self._conn.commit()

    def _migrate(self) -> None:
        task_columns = {
            row["name"]
            for row in self._conn.execute("PRAGMA table_info(tasks)").fetchall()
        }
        for column, ddl in (
            ("model", "ALTER TABLE tasks ADD COLUMN model TEXT"),
            (
                "tokens",
                "ALTER TABLE tasks ADD COLUMN tokens INTEGER NOT NULL DEFAULT 0",
            ),
            ("owner", "ALTER TABLE tasks ADD COLUMN owner TEXT"),
            ("evidence_json", "ALTER TABLE tasks ADD COLUMN evidence_json TEXT"),
            (
                "evidence_signature",
                "ALTER TABLE tasks ADD COLUMN evidence_signature TEXT",
            ),
            (
                "evidence_public_key",
                "ALTER TABLE tasks ADD COLUMN evidence_public_key TEXT",
            ),
            (
                "evidence_key_fingerprint",
                "ALTER TABLE tasks ADD COLUMN evidence_key_fingerprint TEXT",
            ),
            (
                "evidence_signed_at",
                "ALTER TABLE tasks ADD COLUMN evidence_signed_at REAL",
            ),
        ):
            if column not in task_columns:
                self._conn.execute(ddl)
        probe_columns = {
            row["name"]
            for row in self._conn.execute("PRAGMA table_info(probe_reports)").fetchall()
        }
        if "task_id" not in probe_columns:
            self._conn.execute(
                "ALTER TABLE probe_reports ADD COLUMN task_id TEXT"
            )

    def create_task(
        self,
        prompt: str,
        title: str | None = None,
        model: str | None = None,
        owner: str | None = None,
    ) -> Task:
        task_id = uuid.uuid4().hex
        now = time.time()
        stripped = prompt.strip()
        first_line = stripped.splitlines()[0] if stripped else ""
        label = (title or first_line)[:80] or "Untitled run"
        with self._lock:
            self._conn.execute(
                """
                INSERT INTO tasks (id, title, prompt, status, created_at, model, owner)
                VALUES (?, ?, ?, 'queued', ?, ?, ?)
                """,
                (task_id, label, prompt, now, model, owner),
            )
            self._conn.commit()
        return self.get_task(task_id)

    def get_task(self, task_id: str) -> Task | None:
        with self._lock:
            row = self._conn.execute(
                "SELECT * FROM tasks WHERE id = ?", (task_id,)
            ).fetchone()
        return Task(**dict(row)) if row else None

    def list_tasks(self, limit: int = 50, owner: str | None = None) -> list[Task]:
        with self._lock:
            if owner is None:
                rows = self._conn.execute(
                    "SELECT * FROM tasks ORDER BY created_at DESC LIMIT ?",
                    (limit,),
                ).fetchall()
            else:
                rows = self._conn.execute(
                    """
                    SELECT * FROM tasks
                    WHERE owner = ?
                    ORDER BY created_at DESC LIMIT ?
                    """,
                    (owner, limit),
                ).fetchall()
        return [Task(**dict(row)) for row in rows]

    def update_task(self, task_id: str, **fields: Any) -> None:
        updates = {k: v for k, v in fields.items() if k in _TASK_FIELDS}
        if not updates:
            return
        cols = ", ".join(f"{k} = ?" for k in updates)
        values = list(updates.values()) + [task_id]
        with self._lock:
            self._conn.execute(f"UPDATE tasks SET {cols} WHERE id = ?", values)
            self._conn.commit()

    def add_event(self, task_id: str, kind: str, payload: dict[str, Any]) -> Event:
        now = time.time()
        body = json.dumps(payload, ensure_ascii=False, default=str)
        with self._lock:
            cur = self._conn.execute(
                "INSERT INTO events (task_id, ts, kind, payload) VALUES (?, ?, ?, ?)",
                (task_id, now, kind, body),
            )
            self._conn.commit()
            event_id = int(cur.lastrowid)
        return Event(id=event_id, task_id=task_id, ts=now, kind=kind, payload=payload)

    def get_events(self, task_id: str, since_id: int = 0) -> list[Event]:
        with self._lock:
            rows = self._conn.execute(
                """
                SELECT * FROM events
                WHERE task_id = ? AND id > ?
                ORDER BY id ASC
                """,
                (task_id, since_id),
            ).fetchall()
        return [
            Event(
                id=row["id"],
                task_id=row["task_id"],
                ts=row["ts"],
                kind=row["kind"],
                payload=json.loads(row["payload"]),
            )
            for row in rows
        ]

    def add_probe_report(
        self,
        report: ContainmentReport,
        task_id: str | None = None,
        max_reports: int = 200,
    ) -> int:
        payload = report.model_dump()
        body = json.dumps(payload, ensure_ascii=False, default=str)
        with self._lock:
            cur = self._conn.execute(
                """
                INSERT INTO probe_reports
                    (task_id, ts, probe, passed, detail, output, duration_ms, payload)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    task_id,
                    report.generated_at,
                    report.probes[0].name if report.probes else "unknown",
                    int(report.probes[0].passed) if report.probes else 0,
                    report.probes[0].detail if report.probes else "",
                    report.probes[0].output if report.probes else "",
                    report.probes[0].duration_ms if report.probes else 0,
                    body,
                ),
            )
            self._conn.execute(
                """
                DELETE FROM probe_reports
                WHERE id NOT IN (
                    SELECT id FROM probe_reports ORDER BY id DESC LIMIT ?
                )
                """,
                (max_reports,),
            )
            self._conn.commit()
            return int(cur.lastrowid)

    def list_probe_reports(
        self, limit: int = 20, task_id: str | None = None
    ) -> list[dict[str, Any]]:
        with self._lock:
            if task_id is None:
                rows = self._conn.execute(
                    "SELECT * FROM probe_reports ORDER BY id DESC LIMIT ?",
                    (limit,),
                ).fetchall()
            else:
                rows = self._conn.execute(
                    """
                    SELECT * FROM probe_reports
                    WHERE task_id = ?
                    ORDER BY id DESC LIMIT ?
                    """,
                    (task_id, limit),
                ).fetchall()
        return [dict(row) for row in rows]

    def seal_evidence(
        self,
        task_id: str,
        signed_pack: dict[str, Any],
        key_fingerprint: str,
        signed_at: float,
    ) -> None:
        body = json.dumps(signed_pack, ensure_ascii=False, default=str)
        with self._lock:
            self._conn.execute(
                """
                UPDATE tasks
                SET evidence_json = ?,
                    evidence_signature = ?,
                    evidence_public_key = ?,
                    evidence_key_fingerprint = ?,
                    evidence_signed_at = ?
                WHERE id = ?
                """,
                (
                    body,
                    signed_pack.get("signature"),
                    signed_pack.get("public_key"),
                    key_fingerprint,
                    signed_at,
                    task_id,
                ),
            )
            self._conn.commit()

    def get_sealed_evidence(self, task_id: str) -> dict[str, Any] | None:
        with self._lock:
            row = self._conn.execute(
                "SELECT evidence_json FROM tasks WHERE id = ?", (task_id,)
            ).fetchone()
        if not row or not row["evidence_json"]:
            return None
        return json.loads(row["evidence_json"])

    def reconcile_running(self) -> list[str]:
        now = time.time()
        with self._lock:
            rows = self._conn.execute(
                "SELECT id FROM tasks WHERE status = 'running'"
            ).fetchall()
            ids = [row["id"] for row in rows]
            if ids:
                self._conn.execute(
                    """
                    UPDATE tasks
                    SET status = 'interrupted',
                        finished_at = ?,
                        error = 'control plane restarted before completion'
                    WHERE status = 'running'
                    """,
                    (now,),
                )
                self._conn.commit()
        return ids

    def usage_today(self) -> dict[str, int]:
        start = (
            datetime.now(timezone.utc)
            .replace(hour=0, minute=0, second=0, microsecond=0)
            .timestamp()
        )
        with self._lock:
            row = self._conn.execute(
                """
                SELECT COUNT(*) AS tasks, COALESCE(SUM(tokens), 0) AS tokens
                FROM tasks WHERE created_at >= ?
                """,
                (start,),
            ).fetchone()
        return {"tasks": int(row["tasks"]), "tokens": int(row["tokens"])}

    def evidence(self, task_id: str) -> dict[str, Any]:
        task = self.get_task(task_id)
        if task is None:
            return {}
        events = self.get_events(task_id)
        probe_reports = self.list_probe_reports(limit=200, task_id=task_id)
        return {
            # The owner cookie is an access credential; never publish it in
            # evidence that is meant to be shared.
            "task": task.model_dump(exclude={"owner"}),
            "events": [event.model_dump() for event in events],
            "probe_reports": probe_reports,
            "generated_at": task.finished_at or task.started_at or task.created_at,
        }

    def ping(self) -> bool:
        try:
            with self._lock:
                self._conn.execute("SELECT 1").fetchone()
            return True
        except Exception:
            return False

    def close(self) -> None:
        with self._lock:
            self._conn.close()
