"""Narration for the demo recorded on the Vultr VM.

Each segment's speech is synthesized first, so the recording can hold every shot
for as long as its voiceover needs. Wording describes only what the footage shows.

    python tools/video/narration_vultr.py     # -> dist/vo/<id>.mp3, dist/vo/durations.json
"""

from __future__ import annotations

import asyncio
import json
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "dist" / "vo"
VOICE = "en-US-GuyNeural"
RATE = "+8%"

# `text` is the caption; `speech` is what the voice reads when the two must differ.
SEGMENTS = [
    {
        "id": "hook",
        "text": (
            "This is Cage, live on a Vultr virtual machine at this public address. "
            "A coding agent runs here on Vultr Serverless Inference, and every action "
            "it takes happens inside a throwaway Docker container. "
            "Nothing in this video is mocked."
        ),
    },
    {
        "id": "deploy",
        "text": (
            "This is the VM itself. Vultr's metadata service reports the region and "
            "this public IP. Three services are up: the app, Caddy, and sandboxd, the "
            "only one holding the Docker socket. The readiness check passes."
        ),
        "speech": (
            "This is the VM itself. Vultr's metadata service reports the region and "
            "this public I P. Three services are up: the app, Caddy, and sandbox D, the "
            "only one holding the Docker socket. The readiness check passes."
        ),
    },
    {
        "id": "task",
        "text": (
            "Now a real task: I ask for a chart. The panel on the right shows live CPU "
            "and memory from this container. Qwen 3.8 on Vultr Serverless Inference "
            "calls write_file through a mediated tool, then run_command executes it, "
            "and the real exit code and output come back."
        ),
        "speech": (
            "Now a real task: I ask for a chart. The panel on the right shows live CPU "
            "and memory from this container. Qwen three point eight on Vultr Serverless "
            "Inference calls write file through a mediated tool, then run command "
            "executes it, and the real exit code and output come back."
        ),
    },
    {
        "id": "boundary",
        "text": (
            "Every run gets a new container: no host mount, no network, no IPC sharing, "
            "and no API key. One CPU, 512 megabytes, 128 processes, a read-only root, "
            "and user 1000. The workspace is a 64 megabyte tmpfs, so a runaway writer "
            "cannot fill the VM disk."
        ),
        "speech": (
            "Every run gets a new container: no host mount, no network, no I P C sharing, "
            "and no A P I key. One CPU, 512 megabytes, 128 processes, a read-only root, "
            "and user one thousand. The workspace is a 64 megabyte temp F S, so a runaway "
            "writer cannot fill the VM disk."
        ),
    },
    {
        "id": "agent",
        "text": (
            "Now the agent itself tries something destructive through that same tool: "
            "rm /etc/hostname. The read-only root refuses, and the failure comes back as "
            "a tool result with exit code 1. The agent doesn't have to behave. "
            "Every tool call has a receipt."
        ),
        "speech": (
            "Now the agent itself tries something destructive through that same tool: "
            "R M, slash E T C, slash hostname. The read-only root refuses, and the failure "
            "comes back as a tool result with exit code 1. The agent doesn't have to "
            "behave. Every tool call has a receipt."
        ),
    },
    {
        "id": "drills1",
        "text": (
            "Next, direct drills, each against a fresh sandbox. "
            "rm -rf / --no-preserve-root: the read-only root rejects it. "
            "The read-only canary is world-writable in the image, so it fails if the root "
            "filesystem is writable, independent of UID 1000. The cross-task drill checks "
            "the peer is alive before asserting isolation."
        ),
        "speech": (
            "Next, direct drills, each against a fresh sandbox. "
            "R M dash R F on the root, with no preserve root: the read-only root rejects it. "
            "The read-only canary is world-writable in the image, so it fails if the root "
            "filesystem is writable, independent of U I D one thousand. The cross-task drill "
            "checks the peer is alive before asserting isolation."
        ),
    },
    {
        "id": "drills2",
        "text": (
            "A fork bomb hits the resource limits. The secret probe finds no secret-like "
            "variables, the network probe finds no route, and a write to /etc is rejected."
        ),
        "speech": (
            "A fork bomb hits the resource limits. The secret probe finds no secret-like "
            "variables, the network probe finds no route, and a write to slash E T C is "
            "rejected."
        ),
    },
    {
        "id": "usecase",
        "text": (
            "Last, an infinite loop. While it burns its one CPU: Cage is for small teams "
            "who want a coding agent on their own VM, without betting the machine on the "
            "model behaving."
        ),
    },
    {
        "id": "drills3",
        "text": "The timeout kills it. All eight drills: contained.",
    },
    {
        "id": "host",
        "text": (
            "Back on the VM: /etc/hostname is still here, and no sandbox containers are "
            "left behind. Docker shares the host kernel, and kernel escapes are out of "
            "scope. This is container-scoped containment."
        ),
        "speech": (
            "Back on the VM: slash E T C slash hostname is still here, and no sandbox "
            "containers are left behind. Docker shares the host kernel, and kernel escapes "
            "are out of scope. This is container-scoped containment."
        ),
    },
    {
        "id": "evidence",
        "text": (
            "Each run is sealed when it finishes. The pack holds the task, every event, an "
            "Ed25519 signature, the public key, and its fingerprint. The owner field is "
            "excluded. The signature proves this control plane produced the pack, "
            "not that the host is honest."
        ),
        "speech": (
            "Each run is sealed when it finishes. The pack holds the task, every event, an "
            "E D 25519 signature, the public key, and its fingerprint. The owner field is "
            "excluded. The signature proves this control plane produced the pack, "
            "not that the host is honest."
        ),
    },
    {
        "id": "close",
        "text": (
            "Cage: container-scoped blast radius zero, on Vultr. "
            "Every tool call has a receipt."
        ),
    },
]


async def synth(text: str, out: Path) -> None:
    import edge_tts

    await edge_tts.Communicate(text, VOICE, rate=RATE).save(str(out))


def duration(path: Path) -> float:
    raw = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "default=nw=1:nk=1", str(path)],
        capture_output=True, text=True, check=True,
    ).stdout
    return float(raw.strip())


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    durations = {}
    for seg in SEGMENTS:
        path = OUT / f"{seg['id']}.mp3"
        asyncio.run(synth(seg.get("speech", seg["text"]), path))
        durations[seg["id"]] = round(duration(path), 2)
        print(f"{seg['id']:10s} {durations[seg['id']]:6.2f}s  {len(seg['text'].split())} words")
    (OUT / "durations.json").write_text(json.dumps(durations, indent=1), encoding="utf-8")
    print(f"total speech {sum(durations.values()):.1f}s")


if __name__ == "__main__":
    main()
