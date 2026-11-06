"""Burn the captions onto the REAL recording and mux the voiceover.

    python tools/video/assemble_live.py

Produces dist/cage-demo-live.mp4 from dist/raw_final.mp4 (gdigrab capture) and
dist/voiceover_live.wav (edge-tts). Only a subtitle track and an audio track are
added; the video frames are the captured ones.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DIST = ROOT / "dist"
NARR = ROOT / "docs" / "video_narration_live.json"
VIDEO = DIST / "raw_final.mp4"
AUDIO = DIST / "voiceover_live.wav"
OUT = DIST / "cage-demo-live.mp4"

W, H = 1920, 1080


def ts(seconds: float) -> str:
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = seconds % 60
    return f"{h:d}:{m:02d}:{s:05.2f}"


def build_ass(data: dict) -> str:
    head = f"""[Script Info]
ScriptType: v4.00+
PlayResX: {W}
PlayResY: {H}
WrapStyle: 0
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Cap,Segoe UI,30,&H00FFFFFF,&H00FFFFFF,&H99000000,&H8C000000,1,0,0,0,100,100,0,0,3,14,0,2,140,140,104,1
Style: Tag,Segoe UI Semibold,15,&H005BF2B8,&H005BF2B8,&H00000000,&H00000000,0,0,0,0,100,100,1,0,1,1.2,0,7,44,44,34,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    lines = []

    # captions
    for seg in data["segments"]:
        for cap in seg.get("captions", []):
            text = cap["text"].replace("\n", r"\N")
            lines.append(
                f"Dialogue: 0,{ts(cap['t'])},{ts(cap['t'] + cap['d'])},Cap,,0,0,0,,{text}"
            )
    return head + "\n".join(lines) + "\n"


def main() -> None:
    data = json.loads(NARR.read_text(encoding="utf-8"))
    ass = DIST / "captions.ass"
    ass.write_text(build_ass(data), encoding="utf-8")
    print(f"captions -> {ass}")

    # escape the path for the filtergraph
    esc = str(ass).replace("\\", "/").replace(":", r"\:")
    cmd = [
        "ffmpeg", "-y",
        "-i", str(VIDEO),
        "-i", str(AUDIO),
        "-vf", f"subtitles='{esc}'",
        "-c:v", "libx264", "-preset", "medium", "-crf", "19", "-pix_fmt", "yuv420p",
        "-r", "30",
        "-c:a", "aac", "-b:a", "192k",
        "-shortest", "-movflags", "+faststart",
        str(OUT),
    ]
    subprocess.run(cmd, check=True, capture_output=True)
    print(f"video -> {OUT}")


if __name__ == "__main__":
    main()
