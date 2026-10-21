# Cage architecture

## One-sentence model

The **control plane** decides what to do; **sandboxd** decides where it is allowed to happen; the **sandbox** is a disposable container that cannot reach the host, the network, a secret, or another task through the mediated tool surface.

This is a **container-scoped** claim. Docker shares the host kernel; kernel/runc escapes are out of scope. See "Boundary statement" below.

## Components

### 1. Control plane (`app/`)

- FastAPI app with server-rendered UI and SSE.
- Native tool-calling agent loop (`app/agent.py`).
- Tools: `run_command`, `read_file`, `write_file`, `list_files`, `finish`.
- SQLite evidence store (`app/store.py`).
- Event bus for SSE (`app/events.py`).
- Vultr Serverless Inference client (`app/llm.py`).
- Ed25519 evidence signer (`app/evidence.py`).
- Rate limits, concurrency cap, demo pause, per-task token budget.
- No Docker socket, no host shell, no direct workspace access.

### 2. sandboxd (`sandboxd/`)

- FastAPI service with the only Docker socket.
- Creates one container per task; no host workspace mount.
- Pinned `SANDBOX_IMAGE`; the create API does not accept a caller-supplied image.
- Bearer-token auth (`SANDBOXD_TOKEN`).
- Narrow API: create, exec, read/write/list files, stats, destroy.
- Path confinement to `/workspace` for file tools, including symlink resolution inside the container; file ops are timeout-bounded and writes are capped at 1MB. This is defense-in-depth, not the boundary for `run_command`.
- Max concurrent sandboxes.
- Reaps orphan containers after `TTL_SECONDS`.
- Runs blocking docker-py calls in worker threads so one long exec cannot stall health, stats, destroy, or a sibling task.

### 3. Sandbox image (`sandbox_image/`)

- Python 3.11 + pandas/numpy/matplotlib/scipy/scikit-learn/pytest.
- Non-root user `sandbox` (UID 1000).
- `/workspace` is overlaid by a 64MB tmpfs at runtime, so the image directory is only a mount point.
- `/cage-readonly-canary` is a world-writable, root-owned file used to prove `read_only=True` independently of UID 1000.
- `MPLBACKEND=Agg` and `MPLCONFIGDIR=/tmp/matplotlib` so plotting works with a read-only root.

## Request lifecycle

```
POST /api/tasks
  ├─ demo enabled? rate limit? concurrency cap? token budget available?
  └─ create task (SQLite, status=queued)
  └─ background AgentRunner.run(task_id)

AgentRunner
  ├─ sandboxd.create(task_id)
  │    └─ docker run ... network=none, ipc=none, read_only,
  │       user=1000, cap-drop, 512MB/1CPU/128PIDs,
  │       /workspace=64MB tmpfs
  ├─ loop:
  │    ├─ Vultr Serverless Inference chat.completions(tools=...)
  │    ├─ tool call → sandboxd.exec / files
  │    ├─ persist event + publish SSE
  │    ├─ token usage checked against MAX_TASK_TOKENS
  │    ├─ cancellation checked at each step
  │    └─ finish → summary
  ├─ sandboxd.destroy(sandbox_id)
  │    └─ docker rm -f
  └─ task status=completed/failed, evidence retained
```

## Isolation flags

```text
network_mode=none
ipc_mode=none
read_only=True
tmpfs=/tmp:rw,noexec,nosuid,size=64m
tmpfs=/workspace:rw,nosuid,size=64m,uid=1000,gid=1000
mem_limit=512m
memswap_limit=512m
nano_cpus=1_000_000_000
pids_limit=128
cap_drop=ALL
security_opt=no-new-privileges
user=1000:1000
```

The inner command is wrapped in `timeout --signal=KILL <seconds> sh -lc <command>`. GNU timeout runs the command in its own process group and sends SIGKILL to the group. After the exec, sandboxd compares the cgroup `oom_kill` counter before/after and also reads Docker `State.OOMKilled`, so a child OOM is not mislabeled as a timeout.

## Boundary statement

**In scope:** the agent cannot use a mediated tool to touch the host filesystem, host processes, host network, LLM API key, or another task's workspace.

**Out of scope:** a kernel local-privilege-escalation, a runc/daemon exploit, or a Docker socket compromise. Those are platform-level risks; the mitigation path is a dedicated Vultr VM, a minimal sandboxd API with a bearer token, and optionally rootless Docker/gVisor/Firecracker.

**Why not claim VM-level isolation:** it would be false. The README and UI say "container-scoped blast radius zero" and the cheatsheet keeps the same boundary.

## Threat model

| Threat | Control |
|---|---|
| Agent deletes host files | No host bind mount; read-only root; tmpfs workspace |
| Agent fills the VM disk | `/workspace` is a 64MB tmpfs; no host volume |
| Agent exfiltrates API keys | Key exists only in the control plane; sandbox has no key and no network |
| Agent forks/loops forever | PIDs limit + inner `timeout --signal=KILL` + task timeout |
| Agent writes outside workspace | sandboxd path confinement rejects `..`, absolute paths outside `/workspace`, and symlinks that resolve outside `/workspace` for file tools; file ops have a 5s timeout and 1MB write cap |
| Agent keeps state between tasks | One container per task; tmpfs disappears with the container; cross-task drill verifies a second sandbox cannot read the first workspace |
| Caller asks sandboxd for an arbitrary image | Image is pinned server-side; create API accepts only `task_id` |
| Caller reaches sandboxd | Bearer token required; port 8090 is not published |
| Public demo abuse | Per-IP rate limit, global concurrency cap, per-task token budget, demo pause |
| Evidence edited after the fact | Evidence is sealed at task completion and Ed25519-signed; pre-seal GETs return 409; the fingerprint is exposed for out-of-band pinning |
| Owner cookie leaks through evidence | The sealed pack excludes `task.owner`; drill reports require an owned task query |
| Stale sandboxes | TTL reaper removes orphan containers |

## Failure handling

- **LLM endpoint does not support tools**: `LLMClient` retries with a strict JSON protocol.
- **Command timeout**: `timed_out=true`, exit code 124/137, UI shows the result.
- **OOM**: `oom_killed=true`, `timed_out=false`; the UI does not merge the two. Detection uses both `State.OOMKilled` and a before/after cgroup `oom_kill` counter for exec'd children.
- **Container missing**: sandboxd returns 404; the task fails with a visible error.
- **Task timeout**: control plane cancels the loop and destroys the sandbox in `finally`.
- **Operator cancel**: `/api/tasks/{id}/destroy` marks the task cancelled and deletes the container directly; the runner records any tokens already spent and skips the final status overwrite.
- **Control plane restart**: startup reconciliation marks `running` tasks `interrupted` and records a `task_finished` event.
- **Public demo abuse**: per-IP rate limit using the last `X-Forwarded-For` hop (Caddy overwrites the header), global task/probe concurrency, daily task/token budgets, and a boot-time `DEMO_ENABLED` pause.
- **sandboxd restart**: in-memory records are lost; the TTL reaper removes orphan containers labeled `cage.sandbox=1`.
- **Caddy health**: Caddy uses `/healthz` (SQLite liveness) as its active health URI so the evidence viewer stays up if sandboxd is down; `/readyz` is the operator-facing sandbox/Docker/image readiness check.
- **sandboxd image readiness**: sandboxd health reports `image_ok`; `/readyz` is false when the sandbox image is missing.

## Evidence

`app/evidence.py` uses Ed25519:

- private key at `EVIDENCE_KEY_PATH` (generated on first run, mode 600);
- canonical JSON: sorted keys, compact separators, UTF-8;
- `signature` is base64 Ed25519 over the pack without signature fields;
- `public_key` and `key_fingerprint` are returned with the pack;
- `EvidenceSigner.verify()` is the reference verifier;
- probe reports are task-scoped when a `task_id` is supplied, retained to a bounded row count, and returned as signed drill responses.
- task evidence is sealed at completion; repeated GETs return the same signed bytes; unsealed tasks return 409.
- the sandbox event includes a sanitized `host_config` snapshot read back from Docker, not just the requested kwargs.
- the public key is served by the same host, so the key fingerprint should be pinned in the submission/README as an out-of-band anchor.

The signature proves the control plane produced the pack; it does not prove the model's behavior outside the recorded events. The event stream is the evidence for what happened inside the sandbox.

## Extension points

- **Codex / pi-style runner**: implement the same `ToolExecutor` interface or a new runner that still sends every action through `sandboxd`. The containment boundary does not depend on the agent harness.
- **Browser-use (Pattern B)**: add a `browser_*` tool family and run Playwright inside the same sandbox; keep screenshots as evidence.
- **Approval gate**: pause before a command matching a policy and require an operator click in the UI.
- **Multi-tenant auth**: put an identity-aware proxy in front of the control plane; add per-user quotas and sandbox labels.
- **Package access without egress**: add a signed package mirror or a Vultr-local artifact proxy; never reopen general egress.

## Non-goals

- Cage is not a general-purpose container platform.
- Cage does not claim kernel-level isolation.
- Cage does not implement browser automation in this version.
- Cage is not multi-tenant in this version. Anonymous cookie ownership prevents casual cross-visitor access but is not authentication.
