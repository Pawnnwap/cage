# Provenance

## Relationship to super-opencode

Cage is an independent implementation built for Vultr Agent Rush. It shares
high-level ideas with [super-opencode](https://github.com/Pawnnwap/super-opencode)
(Apache-2.0), but no source code from that repository is included here.

| Concept | super-opencode | Cage |
|---|---|---|
| Supervisor loop | `supervisor/core/loop.py` | `app/agent.py` — a native tool-calling loop, no shared code |
| Evidence-grounded judging | `supervisor/core/judge_harness.py` | not used; Cage records deterministic command receipts instead |
| Goal guard | `supervisor/core/goal_guard.py` | not used; Cage uses a finish tool plus token/step limits |
| Loop detection | `supervisor/analyzers/loop_detector.py` | `app/agent.py` repeated-command counter, independently written |
| Desktop UI | NiceGUI pages under `services/webui/` | FastAPI + server-rendered HTML + SSE, new |
| Containment | not present | `sandboxd/`, `sandbox_image/`, `app/drills.py`, `app/evidence.py` — all new |

## What is original to Cage

- The separate `sandboxd` service as the only Docker authority.
- The ephemeral 64MB tmpfs workspace and read-only canary.
- The eight containment drills, including the cross-task liveness check.
- The sealed Ed25519 evidence pack and `scripts/verify_evidence.py`.
- The public-demo quota model, owner-cookie scoping, and incident runbook.
- The Vultr Compose deployment and Caddy health split.

## Attribution

See [NOTICE](../NOTICE). If any file is later found to contain adapted
Apache-2.0 code, add the upstream copyright header and a NOTICE entry before
submission.
