"""Assemble the final demo: the VM capture + the narration + burned captions.

    python tools/video/assemble_vultr.py

Inputs:  dist/rec/final.mp4, dist/rec/marks_final.json, dist/vo/*.mp3
Output:  dist/cage-demo-vultr.mp4 (1920x1080, 30fps, AAC audio, hard subtitles)
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DIST = ROOT / "dist"
VIDEO = DIST / "rec" / "final3.mp4"
MARKS = DIST / "rec" / "marks_final3.json"
VO_DIR = DIST / "vo"
OUT = DIST / "cage-demo-vultr.mp4"

W, H = 1920, 1080
VIDEO_LEAD = 0.6   # capture starts this long before the recorder's own clock
GAP = 0.7          # same silence as the recorder
FADE_OUT = 0.9

BS = chr(92)        # one backslash, composed so this file stays escape-free
NL = BS + "N"       # ASS hard line break
OV = BS + "fs34"    # ASS font-size override

sys.path.insert(0, str(Path(__file__).resolve().parent))
from narration_vultr import SEGMENTS  # noqa: E402  (text + ids, not audio)


def ts(seconds: float) -> str:
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = seconds % 60
    return f"{h:d}:{m:02d}:{s:05.2f}"


def chunks(text: str, max_words: int = 11) -> list[str]:
    """Split narration into short captions, breaking after punctuation when possible."""
    groups, cur = [], []
    for word in text.split():
        cur.append(word)
        if len(cur) >= max_words - 3 and word.endswith((",", ".", ":", ";")):
            groups.append(" ".join(cur))
            cur = []
        elif len(cur) >= max_words:
            groups.append(" ".join(cur))
            cur = []
    if cur:
        groups.append(" ".join(cur))
    return groups


def mix_audio(marks: list[dict], total: float) -> None:
    inputs, filters, labels = [], [], []
    for i, seg in enumerate(SEGMENTS):
        mark = next(m for m in marks if m["id"] == seg["id"])
        delay = int(round((VIDEO_LEAD + mark["t"]) * 1000))
        inputs += ["-i", str(VO_DIR / f"{seg['id']}.mp3")]
        filters.append(f"[{i}:a]adelay={delay}|{delay},volume=1.0[a{i}]")
        labels.append(f"[a{i}]")
    chain = "".join(labels)
    chain += f"amix=inputs={len(labels)}:duration=longest:normalize=0,"
    chain += f"apad=whole_dur={total + 0.5},atrim=0:{total + 0.5},"
    chain += "loudnorm=I=-16:TP=-1.5:LRA=11[aout]"
    subprocess.run(
        ["ffmpeg", "-y", "-loglevel", "error", *inputs, "-filter_complex", chain,
         "-map", "[aout]", "-ar", "48000", "-ac", "1", str(DIST / "vo_mix.wav")],
        check=True,
    )


def build_ass(marks: list[dict], total: float, durations: dict[str, float]) -> str:
    head = f"""[Script Info]
ScriptType: v4.00+
PlayResX: {W}
PlayResY: {H}
WrapStyle: 0
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Cap,Arial,32,&H00FFFFFF,&H00FFFFFF,&H30000000,&H30000000,1,0,0,0,100,100,0,0,3,9,0,2,120,120,26,1
Style: End,Arial,46,&H00FFFFFF,&H00FFFFFF,&H18000000,&H18000000,1,0,0,0,100,100,0,0,3,24,0,5,120,120,0,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    lines = []
    for seg in SEGMENTS:
        mark = next(m for m in marks if m["id"] == seg["id"])
        start = VIDEO_LEAD + mark["t"]
        if seg["id"] == "close":
            lines.append(
                f"Dialogue: 1,{ts(start + 0.3)},{ts(total)},End,,0,0,0,,"
                + f"Every tool call has a receipt.{NL}{{{OV}}}github.com/Pawnnwap/cage{NL}https://139-180-191-46.sslip.io"
            )
            continue
        groups = chunks(seg["text"])
        words = sum(len(g.split()) for g in groups)
        t = start
        for group in groups:
            d = durations[seg["id"]] * len(group.split()) / words
            lines.append(f"Dialogue: 0,{ts(t)},{ts(t + d)},Cap,,0,0,0,,{group}")
            t += d
    return head + chr(10).join(lines) + chr(10)


def main() -> None:
    data = json.loads(MARKS.read_text(encoding="utf-8"))
    marks, total = data["marks"], data["total"]

    mix_audio(marks, total)
    print(f"audio -> {DIST / 'vo_mix.wav'}")

    ass = DIST / "captions_vultr.ass"
    durations = json.loads((VO_DIR / "durations.json").read_text(encoding="utf-8"))
    ass.write_text(build_ass(marks, total, durations), encoding="utf-8")
    print(f"captions -> {ass}")

    esc = str(ass).replace("\\", "/").replace(":", r"\:")
    vf = f"subtitles='{esc}',fade=t=out:st={total - FADE_OUT:.2f}:d={FADE_OUT}"
    subprocess.run(
        ["ffmpeg", "-y", "-loglevel", "error",
         "-i", str(VIDEO), "-i", str(DIST / "vo_mix.wav"),
         "-vf", vf, "-r", "30",
         "-c:v", "libx264", "-preset", "medium", "-crf", "19", "-pix_fmt", "yuv420p",
         "-c:a", "aac", "-b:a", "192k",
         "-shortest", "-movflags", "+faststart", str(OUT)],
        check=True,
    )
    probe = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration,size",
         "-of", "default=nw=1:nk=1", str(OUT)],
        capture_output=True, text=True, check=True,
    ).stdout.split()
    print(f"video -> {OUT}  {float(probe[0]):.1f}s  {int(probe[1]) / 1e6:.1f} MB")


if __name__ == "__main__":
    main()
