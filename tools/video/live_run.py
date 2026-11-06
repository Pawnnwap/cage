"""Drive a REAL Cage run against the live control plane and capture the events.

    python tools/video/live_run.py "<prompt>" <out.json> [timeout_s]

Talks to the running app over HTTP exactly like the browser UI does, then dumps
the task + every event to JSON so the video can be built from real data.
"""

from __future__ import annotations

import http.cookiejar
import json
import os
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

BASE = os.environ.get("CAGE_BASE", "http://127.0.0.1:8080")

# the sandbox exports an HTTP proxy; localhost must never go through it.
# the cookie jar keeps the cage_owner cookie so scoped reads succeed.
_JAR = http.cookiejar.CookieJar()
_OPENER = urllib.request.build_opener(
    urllib.request.ProxyHandler({}), urllib.request.HTTPCookieProcessor(_JAR)
)


def get(path: str, timeout: int = 30):
    with _OPENER.open(BASE + path, timeout=timeout) as r:
        return json.loads(r.read())


def post(path: str, body: dict, timeout: int = 60):
    req = urllib.request.Request(
        BASE + path,
        data=json.dumps(body).encode(),
        headers={"Content-Type": "application/json"},
    )
    with _OPENER.open(req, timeout=timeout) as r:
        return json.loads(r.read())


def main():
    prompt = sys.argv[1]
    out = Path(sys.argv[2])
    limit = int(sys.argv[3]) if len(sys.argv) > 3 else 300

    task = post("/api/tasks", {"prompt": prompt})
    tid = task["id"]
    print(f"task {tid}  status={task.get('status')}  title={task.get('title')}")

    deadline = time.time() + limit
    payload = None
    while time.time() < deadline:
        payload = get(f"/api/tasks/{tid}")
        status = payload["task"]["status"]
        if status in ("completed", "failed", "cancelled"):
            break
        time.sleep(2.0)

    payload = payload or get(f"/api/tasks/{tid}")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    # pull the sealed evidence pack for the same task (owner cookie is live here)
    if payload["task"]["status"] in ("completed", "failed", "cancelled"):
        ev_path = out.with_name(out.stem + "_evidence.json")
        try:
            pack = get(f"/api/tasks/{tid}/evidence")
            ev_path.write_text(json.dumps(pack, indent=2), encoding="utf-8")
            print(f"evidence keys: {sorted(pack.keys())}")
            print(f"fingerprint:   {pack.get('key_fingerprint')}")
            print(f"owner in pack: {'owner' in pack}")
            print(f"evidence -> {ev_path}")
        except urllib.error.HTTPError as exc:
            print("evidence HTTP", exc.code, exc.read()[:200].decode("utf-8", "replace"))

    print(f"status: {payload['task']['status']}")
    print(f"events: {len(payload['events'])}")
    for ev in payload["events"]:
        kind = ev["kind"]
        p = ev["payload"]
        extra = ""
        if kind == "tool_call":
            extra = f"{p.get('tool')} {json.dumps(p.get('arguments'))[:90]}"
        elif kind == "command_started":
            extra = f"$ {p.get('command')[:90]}"
        elif kind == "command_finished":
            extra = f"exit={p.get('exit_code')} {(p.get('stdout') or '')[:90]!r} {(p.get('stderr') or '')[:60]!r}"
        elif kind == "file_written":
            extra = f"{p.get('path')} {p.get('chars')} chars"
        elif kind == "task_summary":
            extra = (p.get("summary") or "")[:120]
        elif kind == "task_finished":
            extra = str(p.get("summary") or p.get("error") or p.get("status"))[:120]
        print(f"  {ev['id']:3d} {kind:18s} {extra}")
    print(f"saved -> {out}")


if __name__ == "__main__":
    try:
        main()
    except urllib.error.HTTPError as exc:
        print("HTTP", exc.code, exc.read()[:400].decode("utf-8", "replace"))
        sys.exit(1)
