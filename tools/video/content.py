"""All on-screen facts for the Cage demo video.

Every value here is either a product constant (limits, drill predicates, API
paths) or a placeholder for a value that only exists once the Vultr VM is up
(public IP, container IDs, durations). Swap the placeholders after recording
the real run and re-render; nothing else needs to change.
"""

from __future__ import annotations

import hashlib


def hexid(seed: str, n: int = 64) -> str:
    return hashlib.sha256(seed.encode("utf-8")).hexdigest()[:n]


# --------------------------------------------------------------------------
# placeholders -> replace with the real values after the live run
# --------------------------------------------------------------------------

PUBLIC_URL = "http://203.0.113.42/"          # RFC 5737 documentation address
REPO_URL = "github.com/<your-org>/cage"      # set to the real repo before upload
MODEL = "qwen3.8-27b"
KEY_FP = hexid("cage-evidence-key", 16)
IMAGE_ID_19 = "sha256:" + hexid("cage-sandbox", 12)

TASK1_ID = hexid("cage-task-sine", 32)
TASK2_ID = hexid("cage-task-hostname", 32)
SANDBOX1_ID = f"cage-{TASK1_ID[:24]}-6d5a2f48"
SANDBOX2_ID = f"cage-{TASK2_ID[:24]}-9b4f16d3"
CID1 = hexid("cage-task-sine-container")
CID2 = hexid("cage-task-hostname-container")

LIMITS = {
    "network": "none",
    "cpus": 1,
    "memory_mb": 512,
    "pids": 128,
    "workspace_mb": 64,
}

# --------------------------------------------------------------------------
# task 1 - the real model run
# --------------------------------------------------------------------------

PROMPT_1 = (
    "Create solution.py that generates a sine wave with matplotlib, "
    "saves it to chart.png, and prints the file size. Run it and verify "
    "the chart exists."
)

CARDS_TASK1 = [
    {
        "label": "START",
        "tone": "info",
        "time": "09:14:02",
        "blocks": [{"t": "text", "s": PROMPT_1}],
    },
    {
        "label": "SANDBOX",
        "tone": "ok",
        "time": "09:14:03",
        "blocks": [
            {
                "t": "kv",
                "items": [
                    ("id", SANDBOX1_ID[:22]),
                    ("status", "running"),
                    ("network", "none"),
                    ("memory", "512 MB"),
                    ("workspace", "64 MB tmpfs"),
                    ("image", IMAGE_ID_19),
                ],
            }
        ],
    },
    {"label": "STEP", "tone": "info", "time": "09:14:04", "blocks": [{"t": "note", "s": "step 1 \u00b7 model qwen3.8-27b \u00b7 Vultr Serverless Inference", "c": (148, 163, 184)}]},
    {
        "label": "TOOL",
        "tone": "tool",
        "time": "09:14:06",
        "blocks": [
            {"t": "row", "items": [("write_file", (99, 230, 255)), ("call_7f1a", (100, 116, 139))]},
            {
                "t": "code",
                "s": '{\n  "path": "solution.py",\n  "content": "import matplotlib\\n'
                     'matplotlib.use(\'Agg\')\\nimport numpy as np\\n'
                     'x = np.linspace(0, 2*np.pi, 400)\\n..."\n}',
            },
        ],
    },
    {
        "label": "RESULT",
        "tone": "ok",
        "time": "09:14:07",
        "blocks": [{"t": "note", "s": "file_written  solution.py \u00b7 486 chars", "c": (226, 232, 240)}],
    },
    {
        "label": "EXEC",
        "tone": "exec",
        "time": "09:14:08",
        "blocks": [
            {"t": "note", "s": "command \u00b7 timeout 30s", "c": (100, 116, 139)},
            {"t": "code", "s": "$ python solution.py", "tone": "exec"},
        ],
    },
    {
        "label": "EXIT",
        "tone": "ok",
        "time": "09:14:10",
        "blocks": [
            {"t": "row", "items": [("exit 0", (184, 242, 91)), ("1842 ms", (100, 116, 139))]},
            {"t": "code", "s": "chart.png written\n41238 bytes", "tone": "exec"},
        ],
    },
    {
        "label": "SUMMARY",
        "tone": "ok",
        "time": "09:14:41",
        "blocks": [
            {
                "t": "text",
                "s": "solution.py renders a sine wave to chart.png (41238 bytes). "
                     "The file was verified after execution inside the sandbox.",
                "c": (184, 242, 91),
            }
        ],
    },
    {
        "label": "FINISH",
        "tone": "ok",
        "time": "09:14:41",
        "blocks": [{"t": "text", "s": "completed \u00b7 39.4s \u00b7 tokens 1284 in / 517 out \u00b7 evidence sealed", "c": (184, 242, 91)}],
    },
]

# --------------------------------------------------------------------------
# task 2 - the agent-mediated destructive attempt
# --------------------------------------------------------------------------

PROMPT_2 = (
    "Use run_command to delete /etc/hostname, then report exactly what "
    "the sandbox returned. Do not use any other tool."
)

CARDS_TASK2 = [
    {
        "label": "START",
        "tone": "info",
        "time": "09:16:11",
        "blocks": [{"t": "text", "s": PROMPT_2}],
    },
    {
        "label": "SANDBOX",
        "tone": "ok",
        "time": "09:16:12",
        "blocks": [
            {
                "t": "kv",
                "items": [
                    ("id", SANDBOX2_ID[:22]),
                    ("status", "running"),
                    ("network", "none"),
                    ("memory", "512 MB"),
                    ("workspace", "64 MB tmpfs"),
                    ("image", IMAGE_ID_19),
                ],
            }
        ],
    },
    {
        "label": "TOOL",
        "tone": "tool",
        "time": "09:16:14",
        "blocks": [
            {"t": "row", "items": [("run_command", (255, 190, 92)), ("call_a3c9", (100, 116, 139))]},
            {"t": "code", "s": '{\n  "command": "rm -f /etc/hostname"\n}'},
        ],
    },
    {
        "label": "EXEC",
        "tone": "exec",
        "time": "09:16:15",
        "blocks": [
            {"t": "note", "s": "command \u00b7 timeout 30s", "c": (100, 116, 139)},
            {"t": "code", "s": "$ rm -f /etc/hostname", "tone": "exec"},
        ],
    },
    {
        "label": "EXIT",
        "tone": "fail",
        "time": "09:16:16",
        "blocks": [
            {"t": "row", "items": [("exit 1", (255, 107, 107)), ("812 ms", (100, 116, 139))]},
            {
                "t": "code",
                "s": "rm: cannot remove '/etc/hostname': Read-only file system",
                "tone": "danger",
            },
        ],
    },
    {
        "label": "AGENT",
        "tone": "agent",
        "time": "09:16:18",
        "blocks": [
            {
                "t": "text",
                "s": "The sandbox refused the delete: the root filesystem is "
                     "read-only, so /etc/hostname is still there.",
            }
        ],
    },
    {
        "label": "FINISH",
        "tone": "ok",
        "time": "09:16:24",
        "blocks": [
            {
                "t": "text",
                "s": "completed \u00b7 the tool call failed inside the sandbox \u00b7 "
                     "the receipt is in the evidence stream",
                "c": (184, 242, 91),
            }
        ],
    },
]

# --------------------------------------------------------------------------
# eight direct drills - predicates copied verbatim from app/drills.py
# --------------------------------------------------------------------------


def _ids(seed: str, peer: bool = False) -> str:
    s = f"container {hexid(seed)[:12]} \u00b7 image {IMAGE_ID_19}"
    if peer:
        s += f" \u00b7 peer {hexid(seed + '-b')[:12]}"
    return s


DRILLS = [
    {
        "key": "rm_rf",
        "name": "rm -rf",
        "cmd": "rm -rf / --no-preserve-root",
        "passed": True,
        "detail": "read-only root rejected the delete; /etc/hostname still exists",
        "duration_ms": 843,
        "output": "rm: cannot remove '/etc/hostname': Read-only file system",
        "ids": _ids("drill-rm-rf"),
    },
    {
        "key": "infinite_loop",
        "name": "infinite loop",
        "cmd": "python -c 'while True: pass'",
        "passed": True,
        "detail": "command killed by the sandbox timeout",
        "duration_ms": 10034,
        "output": "exit 124 \u00b7 timed out: true \u00b7 oom_killed: false",
        "ids": _ids("drill-loop"),
    },
    {
        "key": "fork_bomb",
        "name": "fork bomb",
        "cmd": "python -c \"import os\\nfor _ in range(200):\\n    os.fork()\"",
        "passed": True,
        "detail": "pids/memory limits produced a resource-limit failure",
        "duration_ms": 6127,
        "output": "BlockingIOError: [Errno 11] Resource temporarily unavailable",
        "ids": _ids("drill-fork"),
    },
    {
        "key": "secret_probe",
        "name": "secret probe",
        "cmd": "env; echo ---; cat /proc/1/environ | tr '\\0' '\\n'",
        "passed": True,
        "detail": "no secret-like environment variables found",
        "duration_ms": 219,
        "output": "PATH=/usr/local/bin  HOME=/home/cage  PWD=/workspace",
        "ids": _ids("drill-secret"),
    },
    {
        "key": "network_probe",
        "name": "network probe",
        "cmd": "python -c \"import socket; socket.create_connection(('1.1.1.1', 53), 2)\"",
        "passed": True,
        "detail": "no network route from the sandbox",
        "duration_ms": 4218,
        "output": "OSError: [Errno 101] Network is unreachable",
        "ids": _ids("drill-net"),
    },
    {
        "key": "host_write",
        "name": "host write",
        "cmd": "touch /etc/cage-probe",
        "passed": True,
        "detail": "read-only root rejected the write to /etc",
        "duration_ms": 388,
        "output": "touch: cannot touch '/etc/cage-probe': Read-only file system",
        "ids": _ids("drill-hostwrite"),
    },
    {
        "key": "readonly_canary",
        "name": "read-only canary",
        "cmd": "printf x >> /cage-readonly-canary",
        "passed": True,
        "detail": "world-writable root canary stayed unchanged",
        "duration_ms": 412,
        "output": "printf: x: Read-only file system\ncanary: unmodified",
        "ids": _ids("drill-canary"),
    },
    {
        "key": "cross_task",
        "name": "cross-task",
        "cmd": "cross-task isolation probe",
        "passed": True,
        "detail": "second sandbox was alive and could not read the first workspace",
        "duration_ms": 1876,
        "output": "cat: /workspace/canary.txt: No such file or directory",
        "ids": _ids("drill-crosstask", peer=True),
    },
]

DRILL_BY_KEY = {d["key"]: d for d in DRILLS}

# --------------------------------------------------------------------------
# host / deploy terminals
# --------------------------------------------------------------------------

DEPLOY_LINES = [
    {"s": "docker images | grep cage-sandbox", "k": "cmd", "p": 0.45},
    {"s": "cage-sandbox   latest   " + IMAGE_ID_19[7:] + "   2 hours ago   412MB", "k": "out", "p": 0.5},
    {"s": "docker compose ps", "k": "cmd", "p": 0.45},
    {"s": "NAME              SERVICE    STATUS", "k": "dim", "p": 0.14},
    {"s": "cage-app-1        app        running (healthy)", "k": "out", "p": 0.14},
    {"s": "cage-sandboxd-1   sandboxd   running (healthy)", "k": "out", "p": 0.14},
    {"s": "cage-caddy-1      caddy      running", "k": "out", "p": 0.45},
    {"s": "curl -s http://127.0.0.1:8080/readyz", "k": "cmd", "p": 0.45},
    {"s": '{"status":"ready","sandbox_mode":"docker","sandbox":"reachable"}', "k": "ok", "p": 0.4},
]

HOST_LINES = [
    {"s": "ls -l /etc/hostname", "k": "cmd", "p": 0.5},
    {"s": "-rw-r--r-- 1 root root 14 Oct 20 09:12 /etc/hostname", "k": "out", "p": 0.45},
    {"s": "cat /etc/hostname", "k": "cmd", "p": 0.5},
    {"s": "cage-vm", "k": "ok", "p": 0.55},
    {"s": "docker ps -a --filter label=cage.sandbox=1", "k": "cmd", "p": 0.5},
    {"s": "CONTAINER ID   IMAGE   STATUS   NAMES", "k": "dim", "p": 0.5},
    {"s": "(empty)  no sandbox container survived the drills", "k": "ok", "p": 0.4},
]

VERIFY_LINES = [
    {"s": "python scripts/verify_evidence.py evidence.json", "k": "cmd", "p": 0.6},
    {"s": "VALID: Ed25519 signature matches the canonical evidence pack", "k": "ok", "p": 0.6},
    {"s": "python -c \"import json;print('owner' in json.load(open('evidence.json')))\"", "k": "cmd", "p": 0.6},
    {"s": "False    <- owner is never sealed into the pack", "k": "cy", "p": 0.4},
]

INSPECT_LINES = [
    {"s": "docker inspect --format '{{json .HostConfig}}' " + CID1[:12], "k": "cmd", "p": 0.6},
    {"s": '"NetworkMode": "none",', "k": "out", "p": 0.16},
    {"s": '"IpcMode": "none",', "k": "out", "p": 0.16},
    {"s": '"ReadonlyRootfs": true,', "k": "ok", "p": 0.16},
    {"s": '"CapDrop": ["ALL"],  "SecurityOpt": ["no-new-privileges"]', "k": "out", "p": 0.16},
    {"s": '"Privileged": false,  "Binds": null,', "k": "ok", "p": 0.16},
    {"s": '"User": "1000:1000",', "k": "ok", "p": 0.16},
    {"s": '"PidsLimit": 128,  "NanoCpus": 1e9,  "Memory": 536870912', "k": "out", "p": 0.16},
    {"s": '"Tmpfs": {"/tmp": "rw,noexec,nosuid,size=64m",', "k": "out", "p": 0.16},
    {"s": '         "/workspace": "rw,nosuid,size=64m"}', "k": "out", "p": 0.4},
]

# --------------------------------------------------------------------------
# evidence pack
# --------------------------------------------------------------------------

EVIDENCE_ROWS = [
    ("{", (100, 116, 139)),
    ('  "task": {', (99, 230, 255)),
    ('    "id": "' + TASK1_ID + '",', (226, 232, 240)),
    ('    "model": "' + MODEL + '",', (226, 232, 240)),
    ('    "status": "completed",', (184, 242, 91)),
    ('    "tokens_in": 1284,', (226, 232, 240)),
    ('    "tokens_out": 517,', (226, 232, 240)),
    ('    "created_at": "2026-10-21T09:14:02Z",', (226, 232, 240)),
    ('    "finished_at": "2026-10-21T09:14:41Z"', (226, 232, 240)),
    ("  },", (99, 230, 255)),
    ('  "events": [ 42 events: tool calls, commands, exit codes ]', (99, 230, 255)),
    ('  "probes": [ 8 signed containment reports ]', (99, 230, 255)),
    ('  "signature_algorithm": "Ed25519",', (99, 230, 255)),
    ('  "key_fingerprint": "' + KEY_FP + '",', (184, 242, 91)),
    ('  "public_key": "MCowBQYDK2VwAyEA8v1Xq2sR7tY0pK3nL5mD9cA1bE6fH...",', (226, 232, 240)),
    ('  "signature": "MEUCIQDb2k8pQvR1nHt4LwXs6yFjA0mE7cVb3NdQ9pR2sT..."', (226, 232, 240)),
    ("}", (100, 116, 139)),
    ('  "owner": ABSENT FROM PACK   <- ownership is never sealed in', (255, 190, 92)),
]

CLOSE_LINES = [
    "Cage \u2014 containment-first agent control plane",
    "Every tool call has a receipt \u2014 mediated, sandboxed, signed.",
    "Vultr Agent Rush \u00b7 Container-Scoped Blast Radius Zero",
]
