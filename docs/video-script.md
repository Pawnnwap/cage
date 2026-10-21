# Cage demo video — shot script (2:45)

> **Acceptance spec:** [video-spec.md](video-spec.md). If this script and the spec conflict, the spec wins on required content and claims.

Target: **under 3 minutes**, 1920×1080, 30fps, English voiceover or on-screen captions. Show the public Vultr URL, a real run, the containment drills, and the evidence pack. Do not show the Vultr API key.

## Pre-recording setup

1. Deploy Cage on the Vultr VM and confirm `http://<vultr-ip>/healthz`.
2. Open the UI in a clean browser window at 1080p.
3. Have a terminal ready with:
   ```bash
   ssh root@<vultr-ip>
   cd cage
   docker compose ps
   ```
4. Have the task prompt ready:
   > Create solution.py that generates a sine wave chart with matplotlib, saves it to chart.png, and prints the file size. Run it and verify the chart exists.
5. Do a dry run of `rm -rf` and `infinite loop` so the results are fast.

## Shot list

### 0:00–0:18 — Hook

**Screen:** Cage UI on the public Vultr URL. Cursor moves from the Vultr badge to the model badge.

**On-screen text:** `Cage — containment-first agent control plane`
`Vultr VM · Vultr Serverless Inference · ephemeral Docker sandbox`

**Voiceover:**
> A coding agent is useful only if you can survive what it does. Cage gives every run container-scoped blast radius zero: a real coding agent, a real sandbox, and no host access.

### 0:18–0:48 — Real task

**Screen:** Paste the prompt, click **Run in sandbox**. The timeline shows START → SANDBOX → STEP → TOOL write_file → command_started → command_finished.

**On-screen text:** `write → execute → verify`

**Voiceover:**
> I ask for a chart. The control plane plans, writes the file through a mediated tool, executes it inside a fresh container, and reads the real exit code and stdout. The API key never enters the sandbox.

### 0:48–1:18 — The boundary

**Screen:** Right panel. Point at network `none`, CPU `1`, memory `512 MB`, PIDs `128`, read-only root, UID 1000. Show the live CPU/memory bars and the container ID.

**On-screen text:** `network: none · root: read-only · user: 1000 · caps: dropped`

**Voiceover:**
> Each run gets a new container and a 64MB tmpfs workspace. No network, no IPC sharing, no writable root, no Linux capabilities, no root user. The disk cap matters: a runaway writer cannot fill the Vultr VM. The control plane never touches the Docker socket; sandboxd is the only component that can create or destroy a sandbox.

### 1:18–1:45 — Agent-mediated containment

**Screen:** Start a second run with the prompt: "Try to delete /etc/hostname through run_command, then report exactly what the sandbox returned. Do not use any tool other than run_command." Show the `tool_call` for `run_command`, the `command_finished` exit code, and the read-only error in the timeline. If the model refuses or stalls, cut to the direct drill and say on camera that this is the fallback; do not fake the agent run.

**On-screen text:** `every agent action is a tool call · every tool call has a receipt`

**Voiceover:**
> This is the part that separates Cage from a Docker tutorial: the agent itself asks to do something destructive through the mediated tool path. The command runs in the sandbox, the failure comes back as a tool result, and the receipt is in the evidence stream.

### 1:45–1:58 — Containment drill #1: `rm -rf`

**Screen:** Click **rm -rf**. The result card shows `CONTAINED`, the read-only error, and duration. Switch to the host terminal and run `ls /` or `docker compose ps` to show the host is intact.

**On-screen text:** `CONTAINED — read-only root rejected the delete`

**Voiceover:**
> Here is the drill moment. The sandbox runs `rm -rf / --no-preserve-root`. The read-only root refuses; the 64MB tmpfs workspace is disposable. The host is untouched. The sandbox is disposable by design.

### 1:58–2:12 — Containment drill #2: read-only canary + cross-task

**Screen:** Click **read-only canary** and **cross-task**. Show both `CONTAINED` cards and the real container IDs.

**On-screen text:** `read_only is tested independently of UID 1000 · a second sandbox cannot read the first workspace`

**Voiceover:**
> The read-only canary is world-writable in the image, so it fails if the rootfs is writable — not just because the process is UID 1000. The cross-task drill creates two sandboxes and proves the second cannot read the first one's workspace.

### 2:12–2:22 — Containment drill #3: infinite loop

**Screen:** Click **infinite loop**. Result: `CONTAINED`, timed out, exit 124/137. Then click **fork bomb** and show the pids limit result.

**On-screen text:** `timeout kills the loop · pids limit contains the fork storm`

**Voiceover:**
> A loop gets killed by the inner timeout. A fork storm hits the PID ceiling. Both are contained inside the same disposable boundary.

### 2:22–2:32 — Secrets and network

**Screen:** Click **secret probe** and **network probe**. Show `CONTAINED` for both. Optionally show the evidence JSON with the probe results.

**On-screen text:** `no secret in the sandbox · no network route`

**Voiceover:**
> The sandbox has no API key and no network route. Secrets stay in the control plane. Each drill returns its own signed receipt; the task pack itself is sealed at completion, so the two claims stay honest.

### 2:32–2:50 — Close

**Screen:** Click **Evidence JSON**; show the sealed task/events JSON, the signature, and the public-key fingerprint. Return to the architecture line: `Browser → control plane → sandboxd → ephemeral container`. End on the repo URL.

**On-screen text:** `github.com/<you>/cage`
`Every tool call has a receipt.`
`Vultr Agent Rush — Container-Scoped Blast Radius Zero`

**Voiceover:**
> Cage is a product-style web app, a real agent, and a container-scoped containment boundary you can demonstrate. The one line to remember: every tool call has a receipt — mediated, sandboxed, and signed.

## Recording checklist

- [ ] Public URL visible at least once.
- [ ] Vultr Serverless Inference model badge visible.
- [ ] Agent-mediated `run_command` destructive attempt visible.
- [ ] `rm -rf / --no-preserve-root` containment moment visible.
- [ ] read-only canary and cross-task drills visible.
- [ ] Infinite loop or fork bomb visible.
- [ ] Host unaffected shot visible.
- [ ] Evidence JSON visible, including the Ed25519 signature and public key.
- [ ] No API key, no `.env`, no personal email on screen.
- [ ] Video under 3:00, uploaded to YouTube as public/unlisted.
- [ ] Description includes repo and demo URL.

## Optional B-roll

- `docker compose ps` on the Vultr VM.
- `docker stats` showing the sandbox limits.
- The SQLite evidence file, if you want to show persistence.
- A second task running concurrently, to show one-container-per-run isolation.
