# Cage

**Container-scoped blast radius zero.** Built for [Vultr Agent Rush](https://lablab.ai/ai-hackathons/vultr-hackathon).

Cage runs a coding agent inside an ephemeral, network-isolated Docker sandbox on your Vultr VM. The control plane mediates every tool call; the sandbox has no API keys, no network, a read-only root, a 64MB tmpfs workspace, and a one-task lifetime.

> **What "zero" means:** an agent action cannot reach the host, the network, a secret, or another task through the mediated tool surface.
>
> **What it does not mean:** kernel-level isolation. Docker shares the host kernel; a kernel/runc escape is out of scope. If you need a stronger boundary, run rootless Docker, gVisor, or Firecracker in front of the same control plane. We state this explicitly because a security judge will ask.

## Why this fits Vultr Agent Rush

| Vultr requirement | Cage implementation |
|---|---|
| Web-based agent that writes/runs code | FastAPI + SSE UI; native tool-calling agent |
| Every action in a sandbox on Vultr | `sandboxd` creates a fresh Docker container per task on the Vultr VM |
| Centralized control layer | Control plane plans, dispatches tools, verifies output, records signed evidence |
| Containment-first | `network=none`, `ipc=none`, read-only root, UID 1000, cap-drop, pids/CPU/memory limits, 64MB tmpfs workspace |
| Vultr VM backend | Docker Compose deployment on a Vultr VM; Caddy on ports 80/443 |
| Vultr Serverless Inference | All LLM calls go through the OpenAI-compatible Vultr endpoint |
| Public demo + video | UI and `docs/video-script.md` |
| Containment moment | Eight drills: `rm -rf /`, infinite loop, fork bomb, secret probe, network probe, host write, read-only canary, cross-task isolation |

## Architecture

```
Browser (Tailwind + SSE)
        │
        ▼
FastAPI control plane ──── Vultr Serverless Inference
  agent loop / SQLite          (OpenAI-compatible, host-side)
  signed evidence / rate limits
        │ internal HTTP + bearer token
        ▼
sandboxd (the only component with the Docker socket)
        │
        ▼
ephemeral container
  network: none
  ipc: none
  rootfs: read-only
  user: 1000:1000
  caps: dropped
  CPU 1 / RAM 512MB / PIDs 128
  /workspace: 64MB tmpfs (disk-capped, not a host volume)
```

The control plane has no Docker socket. `sandboxd` is the only container authority, and it only exposes a narrow authenticated API. The sandbox image is pinned server-side; a caller cannot choose an arbitrary image.

## Containment invariants

- **No network egress** — `network_mode="none"`.
- **No IPC sharing** — `ipc_mode="none"`.
- **No secret in the sandbox** — the LLM API key lives only in the control plane.
- **No root** — container runs as UID 1000.
- **No privilege escalation** — `cap_drop=ALL`, `no-new-privileges`.
- **No writable rootfs** — read-only root plus a 64MB `tmpfs` for `/tmp`.
- **Disk-capped workspace** — `/workspace` is a 64MB tmpfs, not an unbounded host volume; a `dd` loop cannot fill the Vultr disk.
- **Explicit file truncation** — reads over 40KB return a head+tail view with a marker telling the agent how many chars were dropped; writes are capped at 1MB.
- **Resource caps** — 1 CPU, 512MB RAM, 128 PIDs, inner `timeout --signal=KILL` (SIGKILL to the process group).
- **OOM is distinguished from timeout** — `oom_killed` is derived from a before/after cgroup `oom_kill` counter check plus Docker `State.OOMKilled`, not inferred from exit 137 alone.
- **Ephemeral by construction** — one container per task; removed at the end; a TTL reaper cleans orphans after a crash.
- **Image pinned** — `sandboxd` uses `SANDBOX_IMAGE`; the create API does not accept an image name.
- **sandboxd authenticated** — app-to-sandboxd calls require `SANDBOXD_TOKEN`.
- **Path confinement for file tools** — `read_file`, `write_file`, and `list_files` reject `..`, absolute paths outside `/workspace`, and symlinks that resolve outside `/workspace`; file ops are timeout-bounded and writes are capped at 1MB. This is defense-in-depth, not the containment boundary: `run_command` is intentionally unrestricted *inside* the sandbox.
- **Rate limit + concurrency cap + token budget** — per-IP limits use the last `X-Forwarded-For` hop (Caddy overwrites the header), plus global task/probe concurrency, daily task/token budgets, and a boot-time demo pause.
- **Signed evidence** — task evidence is sealed and Ed25519-signed at completion; the public key and key fingerprint are returned with the pack. Pin the fingerprint in the submission/README so a verifier has an out-of-band anchor.
- **Read-only canary** — a world-writable file at `/cage-readonly-canary` lives in the image; the drill fails if the rootfs is writable, independent of UID 1000.
- **Cross-task isolation** — two sandboxes are created; the second cannot read a canary written by the first.
- **Public demo ownership** — an anonymous `cage_owner` cookie scopes task list/read/cancel/evidence; a visitor cannot enumerate or cancel another visitor's run.

## Evidence you can verify

Every task produces a JSON evidence pack:

- task metadata: model, tokens, status, timestamps;
- every event: tool call, command, exit code, stdout/stderr, timeout/OOM flags;
- probe reports from the current task window;
- an Ed25519 signature and public key.

Use the **Evidence JSON** button in the same browser session (the `cage_owner` cookie is required), or copy the cookie value and use:

```bash
curl -s -H "Cookie: cage_owner=<value>"   http://<vultr-ip>/api/tasks/<task-id>/evidence > evidence.json
curl -s http://<vultr-ip>/api/evidence/public-key
```

The evidence pack is sealed when the task finishes; repeated GETs return the same signed bytes. Before sealing, `GET /evidence` returns 409 instead of signing on demand. Drill responses are signed separately and are not retroactively injected into a sealed task pack. The signature covers the canonical JSON without `signature`, `public_key`, `signature_algorithm`, and `key_fingerprint`. `EvidenceSigner.verify()` and `scripts/verify_evidence.py` are the reference verifiers. The public key is served by the same host, so pin the fingerprint in the submission description for an out-of-band anchor.

## Quick start (local smoke, no Docker)

```bash
python -m venv .venv
# Windows
.venv\Scripts\pip install -r requirements.txt
set LLM_MODE=fake
set SANDBOX_MODE=local
.venv\Scripts\python -m uvicorn app.main:app --port 8080
```

Open http://127.0.0.1:8080. The fake LLM writes and runs `solution.py` so you can exercise the UI without an API key. The local fallback is **not** a security boundary; containment drills intentionally refuse to run in this mode.

Run the tests:

```bash
.venv\Scripts\python -m pytest -q
```

29 tests cover the local sandbox, agent loop, cancellation, API lifecycle, per-IP rate limiting (including X-Forwarded-For), signed evidence, path confinement, Docker flags, child-OOM classification, drill pass/fail logic, cross-task liveness, large-file truncation markers, probe persistence, and startup reconciliation.

## Deploy on Vultr

See [docs/vultr-deploy.md](docs/vultr-deploy.md). Short version:

```bash
cp .env.example .env
# set VULTR_API_KEY, VULTR_MODEL, SANDBOXD_TOKEN
docker build -t cage-sandbox:latest sandbox_image
docker compose up -d --build
curl http://127.0.0.1:8080/healthz
curl http://127.0.0.1:8080/readyz
```

Caddy serves the app on port 80. The app port is bound to loopback only; the public surface is Caddy.

## Configuration

| Variable | Default | Meaning |
|---|---|---|
| `SANDBOX_MODE` | `local` | `docker` on Vultr; `local` only for development |
| `LLM_MODE` | `vultr` | `vultr` or `fake` |
| `VULTR_BASE_URL` | `https://api.vultrinference.com/v1` | Vultr Serverless Inference endpoint |
| `VULTR_API_KEY` | — | Required for real runs |
| `VULTR_MODEL` | `qwen3.8-27b` | Any tool-capable Vultr model; `nemotron-3-nano-omni-30b-a3b-reasoning` is an NVIDIA alternative |
| `MAX_DAILY_TOKENS` | `2000000` | Global daily inference budget |
| `MAX_TASKS_PER_DAY` | `100` | Global daily task budget |
| `TRUST_PROXY` | `false` | Trust `X-Forwarded-For`; set `true` behind Caddy |
| `SANDBOXD_TOKEN` | — | Shared bearer token between app and sandboxd |
| `SANDBOX_IMAGE` | `cage-sandbox:latest` | Server-side image; callers cannot choose it. The tag is mutable, so evidence records the resolved image ID; pin by digest in production. |
| `MAX_STEPS` | `24` | Agent loop cap |
| `MAX_TASK_TOKENS` | `200000` | Per-task inference budget |
| `COMMAND_TIMEOUT_S` | `30` | Per-command timeout |
| `TASK_TIMEOUT_S` | `600` | Whole-run timeout |
| `PROBE_TIMEOUT_S` | `10` | Containment drill timeout |
| `WORKSPACE_LIMIT_MB` | `64` | tmpfs workspace cap |
| `MAX_CONCURRENT_TASKS` | `2` | Global task concurrency cap |
| `RATE_LIMIT_PER_MINUTE` | `6` | Per-IP task/probe rate limit |
| `DEMO_ENABLED` | `true` | Public demo kill switch |
| `MAX_SANDBOXES` | `4` | sandboxd capacity |
| `TTL_SECONDS` | `7200` | Orphan reaper TTL |
| `EVIDENCE_KEY_PATH` | `/data/evidence_key.pem` | Ed25519 signing key |

## API

| Method | Path | Purpose |
|---|---|---|
| `GET` | `/` | Web UI |
| `GET` | `/healthz` | Liveness + active task count |
| `GET` | `/readyz` | Readiness (checks sandboxd/Docker in Docker mode) |
| `GET` | `/api/config` | Runtime config and configured limits |
| `POST` | `/api/tasks` | Start a run (rate-limited, concurrency-capped) |
| `GET` | `/api/tasks` | List runs |
| `GET` | `/api/tasks/{id}` | Task + events |
| `GET` | `/api/tasks/{id}/events` | SSE live stream |
| `GET` | `/api/tasks/{id}/sandbox` | Container + live stats |
| `GET` | `/api/tasks/{id}/evidence` | Signed evidence JSON |
| `GET` | `/api/evidence/public-key` | Ed25519 public key |
| `POST` | `/api/tasks/{id}/destroy` | Cancel a run |
| `POST` | `/api/containment/probe` | Run a signed containment drill |
| `GET` | `/api/containment/reports` | Persisted drill reports |

## Why Vultr, and why not just E2B/Modal/Daytona?

E2B and Daytona also ship open-source, self-hostable components; Modal and Fly Machines are managed platforms. Cage does not claim a unique hypervisor or better isolation. It is a Vultr-native control plane plus signed evidence and drillable containment for teams that want the whole loop on their own VM.

Cage is for teams that want the control plane and the evidence plane on their own Vultr VM:

- the code and prompt path stay on infrastructure you control;
- Vultr Serverless Inference supplies the model endpoint;
- one Compose file gives you a self-hosted sandbox control plane;
- every run produces a signed, replayable evidence pack;
- containment drills are a first-class product surface, not a hidden internal test.

The differentiation is **self-hosted control + signed evidence + drillable containment**, not a new hypervisor. The target user is a solo developer or small team that wants to run and audit a coding agent on its own Vultr VM without adopting a full managed sandbox platform. The developer exports the sealed pack and publishes the key fingerprint in the repo/submission; the relying party (submission judge or internal auditor) verifies the pack against that pinned fingerprint. The public key is served by the same host, so the out-of-band fingerprint is the anchor.

## Verification status

| Claim | Status |
|---|---|
| Local agent loop + UI | Verified locally with a fake LLM |
| Unit/API tests | 29 passing |
| Effective container config | `host_config` snapshot from Docker is included in the sandbox event/drill report; unit-tested with a fake docker client |
| Sealed evidence | Repeated GETs return identical signed bytes; pre-seal requests return 409 |
| Docker isolation flags | Asserted by `tests/test_sandbox_flags.py`; not executed on this machine (no Docker) |
| Read-only canary / cross-task drill | Logic tested in `tests/test_drills.py`; Docker execution pending |
| Real Vultr inference | Pending `VULTR_API_KEY` and Vultr VM |
| Containment drills in Docker | Pending Vultr VM |
| Public demo + video | Pending deployment |

We keep this table in the README so a judge can distinguish demonstrated, designed, and aspirational claims.

## Repository layout

```
app/            FastAPI control plane, agent loop, tools, UI, evidence signer
sandboxd/       Docker sandbox service (the only Docker authority)
sandbox_image/  Preloaded Python image for the sandbox
tests/          Sandbox, agent, API, rate limit, evidence, flags, lifecycle tests
docs/           Architecture, Vultr deploy, video script, submission checklist
caddy/          Reverse proxy
docker-compose.yml
```

## Video

The acceptance spec is [docs/video-spec.md](docs/video-spec.md); the shot-by-shot narration is [docs/video-script.md](docs/video-script.md). Record only after the eight drills pass on the Vultr VM.

## Incident runbook

See [docs/runbook.md](docs/runbook.md) for pausing the demo, killing sandboxes, rotating `SANDBOXD_TOKEN`, and verifying evidence.

## Limitations

- Docker shares the host kernel; this is not a VM boundary.
- Pattern A only (code execution). Browser-use Pattern B is not implemented; Vultr allows one or both.
- The local fallback is not a containment boundary.
- Single-node deployment; anonymous cookie ownership is not real authentication; add an identity-aware proxy for multi-tenant use.
- `sandboxd` has Docker socket authority. Run it on a dedicated Vultr VM and never expose port 8090 publicly. The sandbox image is built as a separate pre-step, so no other Compose service touches the Docker socket.
- No network egress means the agent cannot `pip install` or fetch docs; the sandbox image preloads a practical Python stack. A package proxy/allowlist is the next step.
- The host canary is a secondary sanity check, not proof of host isolation; the absence of a host mount and the read-only canary are the primary controls.
- File-tool path checks are best-effort against a concurrent symlink race; the container boundary is what contains `run_command`.

## Attribution

Cage is an independent implementation for Vultr Agent Rush. Its supervisor/evidence/loop-guard concepts were inspired by [super-opencode](https://github.com/Pawnnwap/super-opencode) (Apache-2.0). The containment layer, sandboxd, signed evidence, drills, and deployment are new work. See [docs/provenance.md](docs/provenance.md) for a concept-to-file map.

## License

MIT. See [LICENSE](LICENSE).
