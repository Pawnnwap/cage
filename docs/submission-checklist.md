# Vultr Agent Rush submission checklist

Event: [Vultr: Agent Rush Hackathon](https://lablab.ai/ai-hackathons/vultr-hackathon)
Online build: 3–8 November 2026
Submission deadline: **8 November 2026, 23:00 UTC** (9 November 07:00 SST)
Prize pool: $9,000 cash + $5,000 Vultr credits

## 1. Official requirements → evidence

| Requirement | Cage evidence | Status |
|---|---|---|
| GitHub repo with setup and documentation | This repo, `README.md`, `docs/` | [ ] |
| Vultr VM backend deployment | `docs/vultr-deploy.md`, Vultr VM screenshot, `docker compose ps` | [ ] |
| Agent LLM calls through Vultr Serverless Inference | `VULTR_BASE_URL=https://api.vultrinference.com/v1`, model badge in UI, `.env` (not committed) | [ ] |
| Public demo URL | `http://<vultr-ip>` or Caddy domain | [ ] |
| Recorded demo video | `docs/video-script.md`, YouTube URL | [ ] |
| One containment moment | `rm -rf` drill + infinite loop/fork bomb drill in video | [ ] |
| Clear architecture and use case | `docs/ARCHITECTURE.md`, UI architecture line, video narration | [ ] |
| Containment focus | network none, ipc none, read-only root, UID 1000, cap-drop, pids/CPU/memory limits, 64MB tmpfs workspace, read-only canary, cross-task canary, secret-free sandbox | [ ] |
| Production-style web application (single-node demo) | FastAPI UI, SSE live events, stats, cancel/destroy, signed evidence export, rate limits, concurrency cap | [ ] |
| Additional partner tracks | TBA; check the event page before submission | [ ] |

## 2. Repo readiness

- [ ] `README.md` has quick start, configuration, API, architecture, limitations.
- [ ] `LICENSE` present (MIT).
- [ ] `.env.example` present; `.env` is gitignored.
- [ ] `docker-compose.yml` builds app, sandboxd, Caddy, and the sandbox image.
- [ ] `sandbox_image/Dockerfile` builds `cage-sandbox:latest`.
- [ ] Tests pass: `.venv/Scripts/python -m pytest -q` (or Linux equivalent); expected **29 passed**.
- [ ] Local smoke works with `LLM_MODE=fake SANDBOX_MODE=local`.
- [ ] No generated data, `.venv`, `__pycache__`, SQLite, or `.env` committed.

## 3. Deployment evidence

- [ ] Vultr instance created (record region, plan, IP).
- [ ] `docker compose up -d --build` succeeds.
- [ ] `curl http://127.0.0.1:8080/healthz` returns ok.
- [ ] Public URL loads the UI.
- [ ] `docker build -t cage-sandbox:latest sandbox_image` succeeds before Compose up.
- [ ] A real task completes using Vultr Serverless Inference (not the fake LLM).
- [ ] `SANDBOXD_TOKEN` is set in `.env`; sandboxd fails closed without it.
- [ ] `TRUST_PROXY=true` is set so the per-IP limit sees visitor IPs through Caddy.
- [ ] `DEMO_ENABLED`, `MAX_CONCURRENT_TASKS`, `RATE_LIMIT_PER_MINUTE`, `MAX_TASK_TOKENS` are set.
- [ ] Screenshot of `docker compose ps` showing app, sandboxd, caddy.
- [ ] Screenshot of the UI header showing the Vultr model badge.

## 4. Containment evidence

- [ ] `rm -rf` drill returns `CONTAINED`; output shows read-only root rejection.
- [ ] `infinite loop` drill returns `CONTAINED`; output shows timeout.
- [ ] `fork bomb` drill returns `CONTAINED`; output shows pids limit.
- [ ] `secret probe` returns `CONTAINED`; no secret-like env vars.
- [ ] `network probe` returns `CONTAINED`; no route.
- [ ] `host write` returns `CONTAINED`; read-only root rejection.
- [ ] `read-only canary` returns `CONTAINED`; this fails if `read_only=False`.
- [ ] `cross-task` verifies the peer sandbox is alive before asserting isolation.
- [ ] `cross-task` returns `CONTAINED`; the second sandbox cannot read the first workspace.
- [ ] Evidence JSON exported for at least one run and one probe, with a valid Ed25519 signature; repeated GETs return the same signed bytes; pre-seal GET returns 409.
- [ ] The sealed task pack does **not** include `owner`; drill receipts include `task_id`, `container_id`, and `image_id`.
- [ ] `curl /api/evidence/public-key` returns the public key and fingerprint; the fingerprint is pinned in the submission/README.
- [ ] Video includes `rm -rf / --no-preserve-root` containment and the host-unaffected shot.

## 5. Demo video

Acceptance spec: [video-spec.md](video-spec.md). Record only after the eight Docker drills pass on the Vultr VM.

- [ ] Under 3:00.
- [ ] Public URL visible.
- [ ] Vultr Serverless Inference visible.
- [ ] Real task, not a mock.
- [ ] `rm -rf` or infinite loop containment moment.
- [ ] Host unaffected.
- [ ] Evidence JSON.
- [ ] Uploaded to YouTube (public or unlisted) and link ready.
- [ ] No API key, `.env`, email, or local path on screen.
- [ ] Task list/evidence/cancel are scoped by the `cage_owner` cookie; a second browser does not see the first visitor's run.
- [ ] The claim is "container-scoped blast radius zero", not kernel-level isolation.

## 6. Submission form

Prepare these fields:

- **Project title:** Cage — containment-first agent control plane
- **Short description:** A web-based coding agent that runs every action in an ephemeral, network-isolated Docker sandbox on Vultr, with Vultr Serverless Inference and reproducible containment evidence.
- **Long description:** Use the README “Why this fits” + architecture + containment invariants.
- **Technology tags:** agents, AI agents, sandboxing, Docker, FastAPI, Vultr, Vultr Serverless Inference, developer tools.
- **Cover image:** screenshot of the UI with the containment drill result.
- **Video presentation:** YouTube URL.
- **Slide presentation:** optional; use 5–7 slides if required.
- **GitHub repo:** public, MIT.
- **Demo URL:** public Vultr URL.
- **Team:** individual or team per lablab rules (1–6).

## 7. Pre-submit privacy audit

Run from the repo root:

```bash
git status --short
git grep -nE '(VULTR_API_KEY|sk-[A-Za-z0-9]|api[_-]?key|password|secret|token)' -- . ':!*.example' ':!docs/*'
git grep -nE '([A-Z]:\\|/home/|/Users/|C:\\Users)' -- . ':!*.example' || true
```

- [ ] No `.env`, API key, token, password, or local absolute path in the repo.
- [ ] No personal email/phone in committed files.
- [ ] `.gitignore` covers `data/`, `.venv/`, `__pycache__/`, `*.sqlite3`, `.env`.
- [ ] No Compose service other than `sandboxd` mounts the Docker socket.
- [ ] Caddy health uses `/healthz`; `/readyz` is operator-only and checks Docker + sandbox image.
- [ ] `EVIDENCE_KEY_PATH` points at a persistent path, not the repo.
- [ ] Repository is public and the license is visible in the About section.

## 8. Final dry run

- [ ] Clone the repo into a fresh directory.
- [ ] Follow `docs/vultr-deploy.md` from scratch on the Vultr VM.
- [ ] Run a real task and all eight containment drills.
- [ ] Re-record the video if any UI changed.
- [ ] Submit on lablab before 8 November 23:00 UTC.
- [ ] Record the submission receipt / project URL.

## 9. Notes

- Vultr allows Pattern A (sandboxed code execution), Pattern B (sandboxed browser), or both. Cage implements Pattern A.
- The honest boundary: Docker shares the host kernel; cage is container-scoped, not a VM. Do not claim kernel-level isolation.
- The event rules say “Submissions must be original and MIT-compliant.” Cage is MIT.
- Partner tracks were TBA at the time of writing; re-check the event page before final submission.
- The local fallback is for development only; the submitted demo must run in Docker mode on Vultr.
