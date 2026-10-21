# Cage defense cheatsheet

> **How to use:** memorize §0 before the demo. When asked, give the one-line answer first; expand only if the judge pushes. ⚠️ means "say this honestly; do not bluff." Source: three rounds of simulated technical/platform/originality review plus 15 final Q&A.
>
> **One-line pitch:** Cage is a self-hosted, containment-first coding-agent control plane for Vultr: every tool call is mediated, every sandbox is ephemeral, and every run has a signed receipt.

## 0. Core data card

| Number / fact | Meaning | What it is NOT |
|---|---|---|
| **29 tests passing** | Unit/API tests: local sandbox, agent loop, cancellation, rate limits, signed evidence, path checks, Docker flags, OOM, drill logic, probe persistence, reconciliation | Not 27 Docker integration tests; no Docker on the build machine |
| **8 drills** | `rm -rf /`, infinite loop, fork bomb, secret probe, network probe, host write, read-only canary, cross-task isolation | Logic-tested; not yet executed on a real Docker daemon |
| **64 MB tmpfs** | `/workspace` disk/RAM cap; `/tmp` also 64 MB `noexec,nosuid` | Not an unbounded host volume |
| **1 CPU / 512 MB / 128 PIDs** | Per-sandbox cgroup limits; `memswap_limit=512m` | Not a VM; Docker shares the host kernel |
| **network none / ipc none** | No egress, no shared IPC namespace | Does not prevent kernel/runc escapes |
| **UID 1000 / cap-drop ALL / no-new-privileges** | Non-root, no capabilities, no escalation | Not a substitute for a VM boundary |
| **30 s command / 600 s task / 24 steps / 200k tokens** | Per-run caps | Not a global cap; daily budgets are separate |
| **6/min per IP, 2 concurrent tasks, 1 probe, 4 sandboxes** | Public demo quotas | Rate buckets are in-memory and reset on restart |
| **100 tasks/day / 2M tokens/day** | Daily budgets queried from SQLite | Failed-run tokens are recorded, but no dollar estimate exists |
| **Ed25519, 409 before seal** | Evidence is sealed at completion; repeated GETs return identical signed bytes | Signature proves the control plane produced the pack, not host honesty |
| **8, 27, 64, 512, 128** | The numbers to remember | Do not say "six drills" |
| **1,053 participants / $9k + $5k credits** | Vultr Agent Rush field and prize | Not a probability estimate |
| **Deadline: 2026-11-08 23:00 UTC** | Submission deadline (2026-11-09 07:00 SST) | Do not miss it |

**Red lines — do not say:**
- "Kernel-level blast radius zero." Say **container-scoped**.
- "The Docker drills are verified." Say **logic-tested; on-VM run pending**.
- "We have a real Vultr run / video." Say **deployment and video are pending**.
- "The image is pinned." Say **server-chosen tag; resolved image ID is recorded; digest pinning is next**.
- "The signature proves what happened." Say **it proves this control plane produced this intact pack**.
- "The public key is the trust anchor." Say **the fingerprint must be pinned out-of-band because the key is served by the same host**.
- "The cookie is authentication." Say **anonymous ownership scoping, not auth**.
- "Path confinement is the boundary." Say **defense-in-depth; the container is the boundary**.
- "Production-ready SaaS." Say **hardened single-node demo**.

## 1. Claim and evidence

### Q1. You say "blast radius zero," but Docker shares the host kernel. Which claim are you actually making?
**One-line:** Container-scoped zero for the mediated tool surface, not kernel isolation.
- No host mount; `network=none`; `ipc=none`; read-only root; UID 1000; `cap_drop=ALL` plus `no-new-privileges`; 1 CPU/512MB/128 PIDs; 64MB tmpfs workspace.
- The sandbox cannot reach the host filesystem, host network, LLM key, or another task through the mediated tools.
- ⚠️ Kernel/runc/daemon escapes are out of scope and stated in README/ARCHITECTURE.
- Validation path: run all eight drills on a Vultr VM; repeat under gVisor/Firecracker if a VM-grade boundary is required.

### Q2. Has any of this actually run on Docker, or is it a unit test asserting its own kwargs?
**One-line:** The flags are API-surface tested; the live Docker run is the remaining gap.
- `tests/test_sandbox_flags.py` uses a fake Docker client and asserts `network_mode=none`, `ipc_mode=none`, `read_only`, `cap_drop`, `no-new-privileges`, UID 1000, PIDs, CPU, memory, 64MB tmpfs, no volumes, and absence of `privileged`, `pid_mode`, `mounts`, `devices`, `userns_mode`.
- `SandboxManager.create` reads back a sanitized `HostConfig` snapshot (`NetworkMode`, `ReadonlyRootfs`, `CapDrop`, `Binds`, `Privileged`, `PidsLimit`, etc.) into the sandbox event and drill report, so the demo shows what Docker reports, not just what we requested.
- ⚠️ No Docker on the build machine and no Vultr run yet; 29 tests are unit/API tests.
- Validation path: `docker inspect` the recorded container ID, diff against `host_config` in the sealed report, and let the read-only canary fail the drill if `read_only` did not land.

### Q3. Why should I believe the agent cannot reach the host when `sandboxd` holds the Docker socket?
**One-line:** The agent never talks to sandboxd with Docker authority; the control plane does, through a narrow authenticated API.
- Create schema has only `task_id`; image is server-side; there is no wire field for `image`, `privileged`, `binds`, or `devices`.
- `sandboxd` requires a bearer token and fails closed (503) when `SANDBOXD_TOKEN` is unset; port 8090 is not published.
- ⚠️ A stolen token or sandboxd compromise is host-root; the token is static, not constant-time, and not per-task scoped.
- ⚠️ `cage-sandbox:latest` is mutable; evidence records the resolved `image_id`; digest pinning is next.
- Validation path: dedicated VM, unpublished 8090, rotate the token via the runbook.

## 2. Isolation and drills

### Q4. `run_command` is unrestricted inside the sandbox, so what does the symlink-aware file path check actually buy?
**One-line:** Defense-in-depth against accidental escapes, not the containment boundary.
- `_realpath` runs inside the container under a 5s timeout and rejects resolutions outside `/workspace`; `write_file` resolves the parent and caps bodies at 1MB; reads/list are timeout-bounded, and reads over 40KB return an explicit head+tail truncation marker.
- ⚠️ Check and write are separate syscalls; a concurrent symlink race is possible. The container is what contains the shell.
- Validation path: on Docker, `ln -s /etc/passwd /workspace/x` must be refused; `host_config.Binds` must be null and the read-only canary must stay unchanged.

### Q5. Fork bomb, OOM, and timeout all look like 137. How do I know the drills are not green for the wrong reason?
**One-line:** The drills use different pass predicates, and OOM is read from Docker state.
- `timeout --signal=KILL` runs the command in its own process group; `pids_limit=128` is the fork-bomb control.
- `oom_killed` is derived from a before/after cgroup `oom_kill` counter plus Docker `State.OOMKilled`; `timed_out` is not set for an OOM kill.
- Infinity loop requires timeout without OOM; fork bomb requires a resource-limit signature; a bare timeout explicitly fails it.
- ⚠️ `timed_out` is still inferred from exit 124/137 when OOM is false; raw exit code and flags are kept for audit.
- Validation path: run the fork bomb on the VM and show the resource signature, not just a red exit.

### Q6. Two containers on one kernel: what do they still share, and what stops a `dd` loop or 200 forks from hurting the VM?
**One-line:** They share the kernel; the cgroup and tmpfs cap everything else we claim.
- Shared: kernel (out of scope). Not shared: host FS, network, IPC, PID namespace, host privileges.
- 512MB memory = 512MB swap; 1 CPU; 128 PIDs; 64MB workspace tmpfs (shmem charged to the cgroup); 64MB `/tmp` `noexec,nosuid`.
- Cross-task drill requires a live peer to write/read its own file, A's write to succeed, and B's read of A's canary to fail.
- ⚠️ The operator must fit `MAX_CONCURRENT_TASKS × 512MB` plus the control plane into the Vultr plan.
- Validation path: live `memory_usage_mb`, `cpu_percent`, `pids` in `/sandbox`; `host_config.Binds` and host canary in the report.

### Q7. Eight green CONTAINED cards — what makes them worth anything?
**One-line:** Each is a real container with real IDs and a control that can turn red.
- Reports include real `container_id`, resolved `image_id`, `task_id`, duration, output, and `host_canary_intact`.
- Read-only canary is a world-writable, root-owned file; it fails if `read_only=False`, independent of UID 1000.
- Cross-task verifies the peer is alive before asserting isolation.
- ⚠️ The on-VM Docker execution is still pending; logic is unit-tested with deliberate FAILED cases.
- Validation path: run all eight on the VM, keep signed receipts, cross-check container IDs against `docker ps`.

## 3. Evidence

### Q8. The evidence is signed by the same control plane that ran the agent. What does the signature prove?
**One-line:** It proves this control plane produced this intact pack — not that the sandbox behaved or the host is honest.
- Evidence is sealed at completion; GET before seal returns 409; repeated GETs return identical bytes.
- Ed25519 over canonical JSON; public key and 16-hex fingerprint returned; `scripts/verify_evidence.py` is the reference verifier.
- The sealed pack excludes `owner`; drill receipts are signed separately and not retro-injected into a sealed task pack.
- ⚠️ Private key is on the same `/data` disk; no external timestamp/transparency log; root can forge. Public key is same-host.
- Validation path: pin the fingerprint in the submission/README; verify the exported pack against the pinned value; back up the key.

### Q9. Is the sealed pack truly immutable, and does it prove task ownership?
**One-line:** Sealed bytes are stable; ownership is a cookie scope, not authentication.
- `task_evidence` returns 409 until sealed; normal completion seals; cancelled/interrupted startup paths seal as well.
- The pack excludes `owner`; drill reports require an owned `task_id`.
- ⚠️ A task cancelled while the runner is mid-LLM call is sealed by the runner after it stops; until then GET returns 409.
- ⚠️ Anonymous `cage_owner` cookie is a bearer identifier; copying it grants access. No accounts, no per-user quotas.
- Validation path: two browser profiles must not see each other's runs; pin the key fingerprint.

## 4. Public demo and ops

### Q10. A public, login-less demo with your Vultr key behind it: what stops a visitor from running up the bill or reading another visitor's evidence?
**One-line:** Layered caps plus cookie scoping; it is a demo guard, not multi-tenant auth.
- 6/min per IP using the last `X-Forwarded-For` hop; Caddy overwrites the header; 2 concurrent tasks, 1 probe, 4 sandboxes.
- 100 tasks/day, 2M tokens/day, 200k tokens/task, 24 steps, 600s/run; probe report table keeps 200 rows.
- List/read/SSE/cancel/evidence scoped by anonymous `cage_owner` cookie; mismatch returns 404; owner excluded from evidence.
- ⚠️ Cookie is not auth; rate buckets reset on restart; no cost-per-run estimate.
- Validation path: two browsers, restart test, k6/locust burst, then publish 429/p95 numbers.

### Q11. The app dies mid-run while sandboxd keeps running. What happens to the container, task, and evidence?
**One-line:** The task is reconciled to interrupted and sealed; the container is TTL-reaped or killed via the runbook.
- Runner destroys its container in `finally`; cancel deletes via sandboxd immediately; tokens spent are recorded.
- Boot reconciliation marks `running` rows `interrupted`, appends `task_finished`, seals the partial trail.
- Orphan containers are removed by the TTL reaper (7200s, 60s sweep) or the runbook's `label=cage.sandbox=1` kill.
- Caddy health is `/healthz` (SQLite), so the evidence viewer stays up; `/readyz` checks sandboxd/Docker/image and new tasks get 503 until recovery.
- ⚠️ Single-node SQLite; no HA; SSE drops; in-flight model call is lost.

## 5. Product, originality, and demo

### Q12. There is no real Vultr key, no VM deployment, and no video. Why is this not just a local demo with Vultr branding?
**One-line:** The Vultr-specific mechanisms are real; the live demonstration is the remaining deliverable.
- Every model call goes through `https://api.vultrinference.com/v1`; the key stays in the control plane; default model `qwen3.8-27b` (tools supported), Nemotron alternative.
- `sandboxd` is the only socket holder; the app is loopback-only; Caddy owns 80/443; sandbox image is a pre-build step.
- 29 tests and a fake-LLM UI loop are verified locally.
- ⚠️ Real inference, Compose deployment, all eight Docker drills, public URL, and video are pending.
- Validation path: deploy on Vultr, run the real task and eight drills, record the host-unaffected shot, update the verification table.

### Q13. What breaks first if this becomes a real product?
**One-line:** Image reproducibility first, then single-node state; cost visibility third.
- First trust failure: `cage-sandbox:latest` is mutable; pin by digest and record it in deployment config.
- First scaling failure: one SQLite file, one app replica, in-memory rate buckets; move to shared DB/limiter before a second replica.
- Cost: tokens/model are recorded, but there is no dollar estimate; add a price table and reconcile with the Vultr invoice.
- ⚠️ "Production-ready" here means hardened single-node demo, not SaaS; no accounts/pricing/load test.

### Q14. What is actually yours, and why is this not a Docker tutorial with nicer UI plus borrowed ideas?
**One-line:** The containment layer, sandboxd, evidence sealing, drills, quotas, and Vultr deployment are new; the concept map is explicit.
- `docs/provenance.md` maps supervisor loop, judge harness, goal guard, loop detection, and UI to the files; upstream judge/goal-guard are not used.
- `NOTICE` discloses the Apache-2.0 inspiration and states no source code is included; Cage is MIT.
- Differentiation is self-hosted control + signed evidence + drills, not a hypervisor; E2B/Daytona can also be self-hosted.
- ⚠️ "Independent implementation" is asserted by the concept map, not a formal code-diff/plagiarism audit; run ScanCode and a diff.

### Q15. The script's only proof of mediation is an agent-mediated destructive attempt that needs a live model. What if the model refuses or stalls?
**One-line:** Cut to the direct drill and say so on camera; the fallback is disclosed, not faked.
- The centerpiece prompt asks the agent to run a destructive command through `run_command`; the failure becomes a tool result and a receipt.
- If the model refuses/stalls, the script explicitly switches to the direct drill and states it is the fallback.
- The recording checklist requires the public URL, Vultr model badge, agent-mediated attempt, `rm -rf /` containment, host-unaffected shot, and sealed evidence.
- ⚠️ No real model run or video exists yet; the verification table marks it pending.
- The memorable frame: **every tool call has a receipt** — mediated, sandboxed, signed.

## 30-second close

> "Cage is container-scoped, not kernel-scoped: every agent action is a mediated tool call inside an ephemeral Docker sandbox with no host mount, no network, no secrets, and a 64MB tmpfs workspace. We have 29 passing tests, eight drill predicates with deliberate FAILED cases, and sealed Ed25519 evidence. What we do **not** claim yet: the Docker drills and the live Vultr run are still pending; the shared kernel is out of scope. If you support us, the next 48 hours are: deploy on the Vultr VM, run all eight drills, pin the image digest and evidence fingerprint, then record the three-minute demo. The one line to remember is: every tool call has a receipt."
