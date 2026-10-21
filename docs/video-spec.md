# Cage demo video specification

This is the **acceptance spec** for the Vultr Agent Rush submission video. The shot-by-shot narration is in [video-script.md](video-script.md). If the two conflict, this spec wins on required content and claims.

## 1. Purpose

A judge should understand, without reading the repo:

1. what Cage does;
2. why the sandbox boundary matters;
3. what was actually contained;
4. what evidence exists;
5. what is explicitly **not** claimed.

The video must show a **real Vultr deployment** and a **real model run**. It must not be recorded against the local fake LLM.

## 2. Hard constraints

| Item | Requirement |
|---|---|
| Duration | **≤ 3:00**, target **2:45** |
| Resolution / frame rate | 1920×1080, 30 fps |
| Format | MP4, H.264 video, AAC audio |
| Audio | English voiceover, or English captions burned in / uploaded |
| Visibility | YouTube public or unlisted; link must work without login |
| Browser | 100% zoom, bookmarks bar hidden, notifications off |
| Secrets | No API key, `.env`, password, token, or private email on screen |
| Claims | Say **container-scoped**, never kernel-level isolation |
| Demo integrity | No fake agent run, no staged terminal output, no unverified "passed" cards |
| Recording gate | Record only after all eight drills pass on the Vultr VM |

## 3. Mandatory proof shots

Every item below must be visible at least once. A shot that only shows a label is not enough; the proof must show the mechanism or the result.

### 3.1 Deployment proof

- [ ] Public Vultr URL visible in the address bar.
- [ ] `docker compose ps` on the Vultr VM showing `app`, `sandboxd`, and `caddy` running.
- [ ] `curl /readyz` returns ready **after** the sandbox image is built.
- [ ] The sandbox image is built as a separate pre-step; show `docker images | grep cage-sandbox` if space allows.

### 3.2 Real model proof

- [ ] Header shows **Vultr Serverless Inference** and the model badge (`qwen3.8-27b`, or the model actually used).
- [ ] A real task run, not the fake LLM: prompt → `tool_call` → `command_finished` with a real exit code and stdout.
- [ ] If the model ID was changed, show the `/api/config` model value or the Vultr console/model list.

### 3.3 Sandbox boundary proof

Show the sandbox panel with the **configured limits** and at least one **live** stat:

- [ ] `network: none`
- [ ] `ipc: none`
- [ ] `1 CPU`
- [ ] `512 MB`
- [ ] `128 PIDs`
- [ ] `64 MB tmpfs workspace`
- [ ] `read-only` root / UID 1000 (from the panel or the event card)
- [ ] Real container ID and resolved image ID from the `sandbox_started` event.
- [ ] Live CPU or memory stat (not only typed-in labels).

### 3.4 Agent-mediated containment proof

This is the shot that separates Cage from a Docker tutorial.

- [ ] Start a second run with a prompt that asks the agent to use `run_command` to delete `/etc/hostname`.
- [ ] Show the `run_command` tool call itself, not just a button.
- [ ] Show the resulting exit code and the read-only error.
- [ ] If the model refuses, stalls, or calls a different tool: cut to the direct drill and **say on camera that this is the fallback**. Do not fake the agent run.
- [ ] On-screen text: `every tool call has a receipt`.

### 3.5 Direct containment drills

Run these against a fresh sandbox. Show the result card, the drill name, and the real container/image ID.

- [ ] `rm -rf / --no-preserve-root` → `CONTAINED`; read-only root rejected the delete.
- [ ] `read-only canary` → `CONTAINED`; the world-writable root file is unchanged (this is the control that fails if `read_only=False`).
- [ ] `cross-task` → `CONTAINED`; the peer sandbox is alive and cannot read the first workspace.
- [ ] `infinite loop` → `CONTAINED`; timed out, not OOM.
- [ ] `fork bomb` → `CONTAINED`; resource-limit signature or OOM, not a bare timeout.
- [ ] `secret probe` → `CONTAINED`; no secret-like env vars.
- [ ] `network probe` → `CONTAINED`; a specific network failure.
- [ ] `host write` → `CONTAINED`; root write rejected and read-only canary unchanged.

If time is tight, the **minimum** set is: `rm -rf`, `read-only canary`, `cross-task`, `infinite loop`, `fork bomb`, `secret probe`, `network probe`. Do not cut `read-only canary` or `cross-task`; they are the controls that make the others credible.

### 3.6 Host-unaffected proof

- [ ] On the Vultr VM terminal, show `/etc/hostname` still exists after `rm -rf / --no-preserve-root`.
- [ ] Show `docker ps -a --filter label=cage.sandbox=1` is empty after the drills/task cleanup, or show the TTL reaper removing the last container.
- [ ] Do not show a host path that the sandbox never had; explain that the absence of a host bind mount is the control.

### 3.7 Evidence proof

- [ ] Open a **sealed** task evidence pack: `task`, `events`, `signature`, `public_key`, `key_fingerprint`.
- [ ] Show that `owner` is **not** in the pack.
- [ ] Export the pack with the UI **Evidence JSON** button (same browser/session; owner cookie required), then run `python scripts/verify_evidence.py evidence.json` and show `VALID`.
- [ ] Show the key fingerprint visible in the UI or `/api/evidence/public-key`.
- [ ] State that the signature proves the control plane produced the pack, not that the host is honest.

### 3.8 Close

- [ ] One-line pitch: "Every tool call has a receipt."
- [ ] Repo URL (or `github.com/<you>/cage`).
- [ ] Public demo URL.
- [ ] Vultr Agent Rush / container-scoped blast radius zero.

## 4. Timing budget

| Time | Segment | Must include |
|---|---|---|
| 0:00–0:18 | Hook | public URL, product one-liner, Vultr badge |
| 0:18–0:48 | Real task | real model, tool call, command output, finish |
| 0:48–1:10 | Boundary | configured limits, live stat, container/image ID |
| 1:10–1:35 | Agent-mediated destructive attempt | `run_command`, exit code, read-only error, fallback disclosure if needed |
| 1:35–2:00 | Direct drills | `rm -rf`, read-only canary, cross-task |
| 2:00–2:20 | More drills + host proof | infinite loop/fork bomb, secret/network, host intact, no sandbox left |
| 2:20–2:45 | Evidence + close | sealed JSON, verifier VALID, fingerprint, repo/demo URL |

Target **2:45**; hard stop at **3:00**. If a shot runs long, cut the second task prompt or the optional host `docker images` shot, not the read-only canary or cross-task proof.

## 5. What the narration must say

Use the script in [video-script.md](video-script.md), with these mandatory statements:

- "Container-scoped blast radius zero" or "container-scoped containment"; never "kernel-level zero".
- "Docker shares the host kernel; kernel escapes are out of scope."
- "The sandbox has no host mount, no network, no IPC sharing, and no API key."
- "The workspace is a 64MB tmpfs, so a runaway writer cannot fill the VM disk."
- "The read-only canary fails if the rootfs is writable, independent of UID 1000."
- "The cross-task drill checks the peer is alive before asserting isolation."
- "The evidence is sealed at completion; the signature proves this control plane produced the pack, not that the host is honest."
- If the model fallback is used: "The model declined, so this is the direct drill fallback."

## 6. What the video must NOT include

- A fake LLM run presented as a real model run.
- A green `CONTAINED` card with no real container or image ID.
- "Six drills" (there are eight).
- "Kernel-level blast radius zero."
- "Production-ready SaaS" or "multi-tenant."
- "The Docker drills are verified" before they are run on the Vultr VM.
- "The image is pinned" (say server-chosen tag, resolved image ID recorded, digest pinning next).
- "The signature proves what happened" (say it proves the pack is intact and produced by this control plane).
- API keys, `.env`, personal email/phone, or local absolute paths.
- Background music that makes the narration hard to hear.
- A 3:01 runtime.

## 7. Production checklist

- [ ] Deploy on Vultr; `/readyz` returns ready.
- [ ] Build `cage-sandbox:latest`; confirm `docker images`.
- [ ] Run a real task with a real Vultr model; confirm tokens and `command_finished`.
- [ ] Run all eight drills; save the signed reports.
- [ ] Verify the sealed evidence with `scripts/verify_evidence.py`.
- [ ] Record 1920×1080 at 30 fps; hide bookmarks and notifications.
- [ ] Check audio levels; no clipping; captions match narration.
- [ ] Blur or avoid the Vultr API key and any private URLs.
- [ ] Re-watch once with sound off: can the proof shots still be understood?
- [ ] Re-watch once with sound on: does the narration match the on-screen evidence?
- [ ] Upload to YouTube; title and description include repo and demo URL.
- [ ] Paste the video URL into the lablab submission form.

## 8. Acceptance questions

After watching once, a judge should be able to answer:

1. What does Cage do?
2. What exactly is isolated, and what is not?
3. What did the agent try to do, and what happened?
4. What evidence proves the claim?
5. What is still pending or out of scope?

If any answer is unclear, the video fails the spec even if every shot is present.

## 9. Files

- Shot-by-shot narration: [video-script.md](video-script.md)
- Defense Q&A and red lines: [../pre/defense-cheatsheet.md](../pre/defense-cheatsheet.md)
- Deployment: [vultr-deploy.md](vultr-deploy.md)
- Incident/cleanup: [runbook.md](runbook.md)
- Output file: `dist/cage-demo.mp4` (not committed)
