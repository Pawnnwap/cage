"""Build the narration for the REAL recording.

The wording is deliberately literal: it describes only what the footage shows.
Container isolation, the eight drills, and the Vultr deployment are named as
pending, because they are not running in this session.

    python tools/video/build_narration_live.py
"""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "docs" / "video_narration_live.json"

FINGERPRINT = "8d408402fb391d6c"

SEGMENTS = [
    {
        "id": "hook",
        "start": 0.0,
        "end": 17.0,
        "onscreen": "live run \u00b7 real model \u00b7 real tool calls",
        "text": (
            "This is Cage, a containment-first control plane for a coding agent. "
            "Everything in this video is a live run: a real model, real tool calls, "
            "and a real command executing."
        ),
    },
    {
        "id": "run",
        "start": 17.0,
        "end": 48.0,
        "onscreen": "prompt \u2192 tool call \u2192 real exit code",
        "text": (
            "I type a task and press Run in sandbox. The control plane plans, then "
            "calls write file through a mediated tool. Then run command executes it "
            "and returns the real exit code and the real standard output. The model "
            "is a self hosted Qwen three point eight, twenty seven billion, behind "
            "an OpenAI compatible endpoint."
        ),
    },
    {
        "id": "output",
        "start": 48.0,
        "end": 64.0,
        "onscreen": "exit 0 \u00b7 real stdout \u00b7 local fallback, not a container",
        "text": (
            "Exit zero, and the chart file is twenty eight thousand bytes. One "
            "caveat: this laptop has no Docker, so the sandbox runs the local "
            "fallback. That is not a security boundary."
        ),
    },
    {
        "id": "evidence",
        "start": 64.0,
        "end": 95.0,
        "onscreen": "sealed evidence \u00b7 Ed25519 \u00b7 owner excluded",
        "text": (
            "Every action is in the timeline, and the run is sealed when it "
            "finishes. This is the real pack: fifty eight events, an Ed25519 "
            "signature, the public key, and the key fingerprint. The owner field is "
            "deliberately excluded. The signature proves this control plane produced "
            "the pack, not that the host is honest."
        ),
    },
    {
        "id": "config",
        "start": 95.0,
        "end": 113.0,
        "onscreen": "runtime config \u00b7 limits \u00b7 fingerprint",
        "text": (
            "The runtime config returns the model, the configured limits, and the "
            "fingerprint eight d four zero eight four zero two. The limits are what "
            "a Docker sandbox would enforce: one CPU, five hundred twelve megabytes, "
            "one hundred twenty eight PIDs, a sixty four megabyte workspace, no network."
        ),
    },
    {
        "id": "verify",
        "start": 113.0,
        "end": 144.0,
        "onscreen": "verifier VALID \u00b7 Docker drills and Vultr deploy still pending",
        "text": (
            "The control plane reports ready, and warns in the same payload that the "
            "local fallback is not a security boundary. The verifier reads the "
            "exported pack and prints VALID. What is still pending: running the eight "
            "containment drills under Docker, and deploying on Vultr. Every tool call "
            "has a receipt."
        ),
    },
]


def chunk(text: str, start: float, end: float, max_words: int = 8) -> list[dict]:
    words = text.split()
    groups, cur = [], []
    for w in words:
        cur.append(w)
        if len(cur) >= max_words and w.endswith((",", ".", ";", ":")):
            groups.append(" ".join(cur))
            cur = []
        elif len(cur) >= max_words + 4:
            groups.append(" ".join(cur))
            cur = []
    if cur:
        groups.append(" ".join(cur))

    # proportional timing by word count, with a small tail beat
    total = sum(len(g.split()) for g in groups) or 1
    span = max(1.0, (end - start) - 0.5)
    t = start + 0.3
    out = []
    for g in groups:
        share = len(g.split()) / total
        dur = max(1.0, span * share)
        out.append({"t": round(t, 2), "d": round(dur, 2), "text": _wrap(g)})
        t += dur
    return out


def _wrap(s: str, width: int = 40) -> str:
    words, lines, cur = s.split(), [], ""
    for w in words:
        trial = w if not cur else cur + " " + w
        if len(trial) <= width:
            cur = trial
        else:
            if cur:
                lines.append(cur)
            cur = w
    if cur:
        lines.append(cur)
    if len(lines) > 2:  # rebalance into two lines
        mid = len(" ".join(lines)) // 2
        joined = " ".join(lines)
        cut = joined.rfind(" ", 0, mid + 10)
        lines = [joined[:cut], joined[cut + 1 :]]
    return "\n".join(lines)


def main() -> None:
    segs = []
    for seg in SEGMENTS:
        caps = chunk(seg["text"], seg["start"], seg["end"])
        segs.append({
            "id": seg["id"],
            "start": seg["start"],
            "end": seg["end"],
            "onscreen": seg["onscreen"],
            "text": seg["text"],
            "captions": caps,
        })
    data = {
        "title": "Cage \u2014 live run, container boundary pending",
        "voice": "en-US-GuyNeural",
        "segments": segs,
    }
    OUT.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    total = sum(len(s["text"].split()) for s in segs)
    print(f"wrote {OUT}  segments={len(segs)}  words={total}")
    for s in segs:
        print(f"  {s['id']:10s} {s['start']:5.0f}-{s['end']:5.0f}s  {len(s['text'].split()):3d} words  {len(s['captions'])} caps")


if __name__ == "__main__":
    main()
