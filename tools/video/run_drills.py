"""Run every containment drill against a live Cage deployment and save the signed reports.

    CAGE_BASE=http://<vultr-ip> python tools/video/run_drills.py dist/drills

Paced to stay under the per-IP probe rate limit. Exits non-zero unless every
drill reports passed probes and an intact host canary.
"""

from __future__ import annotations

import json
import os
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

BASE = os.environ.get("CAGE_BASE", "http://127.0.0.1:8080")
PACE_S = 11

_OPENER = urllib.request.build_opener(urllib.request.ProxyHandler({}))


def get(path: str):
    with _OPENER.open(BASE + path, timeout=30) as r:
        return json.loads(r.read())


def run_probe(name: str):
    req = urllib.request.Request(
        BASE + "/api/containment/probe",
        data=json.dumps({"probe": name}).encode(),
        headers={"Content-Type": "application/json"},
    )
    with _OPENER.open(req, timeout=120) as r:
        return json.loads(r.read())


def main() -> int:
    out = Path(sys.argv[1] if len(sys.argv) > 1 else "dist/drills")
    out.mkdir(parents=True, exist_ok=True)
    failures = 0
    for name in get("/api/containment/probes")["probes"]:
        try:
            pack = run_probe(name)
        except urllib.error.HTTPError as exc:
            failures += 1
            print(f"{name:16s} HTTP {exc.code} {exc.read()[:300].decode('utf-8', 'replace')}")
            time.sleep(PACE_S)
            continue
        (out / f"{name}.json").write_text(json.dumps(pack, indent=2), encoding="utf-8")
        contained = all(p["passed"] for p in pack["probes"]) and pack["host_canary_intact"]
        failures += 0 if contained else 1
        print(f"{name:16s} {'CONTAINED' if contained else 'NOT CONTAINED'}  canary={pack['host_canary_intact']}")
        for probe in pack["probes"]:
            detail = " ".join(probe["detail"].split())[:150]
            print(f"    [{'ok' if probe['passed'] else 'FAIL'}] {probe['name']} ({probe['duration_ms']}ms): {detail}")
        time.sleep(PACE_S)
    print(f"failures: {failures}")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
