"""Generate the English voiceover and mix it onto the timeline.

For every narration segment we synthesize speech with edge-tts, fit it into the
segment window by nudging the speaking rate, then place it at the segment start
and mix everything into a single 48 kHz track.

    python tools/video/tts.py            # -> dist/voiceover.wav
"""

from __future__ import annotations

import asyncio
import json
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DIST = ROOT / "dist"
NARRATION = ROOT / "docs" / "video_narration.json"
VOICE = "en-US-GuyNeural"
TOTAL = 165.0
LEAD = 0.35      # speech starts this long after the segment boundary
TAIL = 0.45      # and must end this long before the next one


def ffprobe_duration(path: Path) -> float:
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of",
         "default=nw=1:nk=1", str(path)],
        capture_output=True, text=True, check=True,
    ).stdout.strip()
    return float(out)


async def synth(text: str, out: Path, rate: str = "+0%"):
    import edge_tts

    communicate = edge_tts.Communicate(text, VOICE, rate=rate)
    await communicate.save(str(out))


def speak(text: str, out: Path, target: float) -> float:
    """Synthesize `text` so it fits roughly in `target` seconds."""
    asyncio.run(synth(text, out, "+0%"))
    dur = ffprobe_duration(out)
    rate = 0
    for _ in range(4):
        if dur <= target:
            break
        # each iteration closes ~80% of the gap
        need = (dur / target - 1.0) * 100.0
        rate = int(round(rate + need * 0.9))
        rate = max(-10, min(45, rate))
        asyncio.run(synth(text, out, f"+{rate}%"))
        dur = ffprobe_duration(out)
    return dur


def main():
    data = json.loads(NARRATION.read_text(encoding="utf-8"))
    DIST.mkdir(parents=True, exist_ok=True)
    tmp = Path(tempfile.mkdtemp(prefix="cage-vo-"))

    inputs, filters, labels = [], [], []
    for i, seg in enumerate(data["segments"]):
        window = seg["end"] - seg["start"]
        target = window - LEAD - TAIL
        wav = tmp / f"seg_{i:02d}.mp3"
        dur = speak(seg["text"], wav, target)
        delay_ms = int(round((seg["start"] + LEAD) * 1000))
        inputs += ["-i", str(wav)]
        filters.append(f"[{i}:a]adelay={delay_ms}|{delay_ms},volume=1.0[a{i}]")
        labels.append(f"[a{i}]")
        print(f"{seg['id']:16s} window {window:5.1f}s  speech {dur:5.2f}s  start {seg['start']:6.2f}s")

    n = len(labels)
    mix = "".join(labels) + f"amix=inputs={n}:duration=longest:normalize=0,"
    mix += f"apad=whole_dur={TOTAL},atrim=0:{TOTAL},loudnorm=I=-16:TP=-1.5:LRA=11"

    cmd = ["ffmpeg", "-y", *inputs, "-filter_complex", ";".join(filters) + ";" + mix,
           "-ar", "48000", "-ac", "1", str(DIST / "voiceover.wav")]
    subprocess.run(cmd, check=True, capture_output=True)
    print("audio ->", DIST / "voiceover.wav")


if __name__ == "__main__":
    main()
