"""Rebuild the demo with privacy fixes. Visuals only; audio untouched.

Fixes applied to dist/raw_final.mp4:
  1. The Windows taskbar (y >= 1020 in the 1080p capture) is cropped away and
     replaced by a flat dark panel that doubles as the subtitle safe area.
  2. The terminal scene's prompt line shows the local absolute path
     E:\\pyprojects\\... -> covered with an opaque bar for its whole scene.

Canvas stays 1920x1080.

    python tools/video/assemble_live_privacy.py
"""

from __future__ import annotations

import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DIST = ROOT / "dist"
SRC = DIST / "raw_final.mp4"
AUDIO = DIST / "voiceover_live.wav"
ASS = DIST / "captions.ass"
OUT = DIST / "cage-demo-live-privacy.mp4"

W, H = 1920, 1080
# content rows kept from the capture: 0..1019 (the page + browser chrome),
# taskbar starts at y=1020
KEEP_H = 1020
PANEL_H = H - KEEP_H  # 60px subtitle band

# terminal scene (prompt visible from when cmd.exe pops up until the end)
TERM_T0 = 113.0
TERM_T1 = 144.1
# prompt line bbox in the capture (text rows 195..216, path up to x=620)
MASK_X0, MASK_Y0, MASK_X1, MASK_Y1 = 0, 190, 700, 228

# ffmpeg colour for the mask + panel: near-black #06090c
DARK = "0x06090c"


def build() -> None:
    # order: mask the prompt path first (absolute coords), crop off the taskbar,
    # append the subtitle band, scale back to 1080, then burn captions on top.
    vf = (
        f"drawbox=x={MASK_X0}:y={MASK_Y0}:w={MASK_X1 - MASK_X0}:h={MASK_Y1 - MASK_Y0}"
        f":color={DARK}:t=fill:enable='between(t,{TERM_T0},{TERM_T1})',"
        f"crop={W}:{KEEP_H}:0:0,"
        f"scale={W}:{H},"
        f"drawbox=x=0:y={KEEP_H}:w={W}:h={PANEL_H}:color={DARK}:t=fill"
    )
    esc = str(ASS).replace("\\", "/").replace(":", r"\:")
    vf_full = vf + f",subtitles='{esc}'"
    cmd = [
        "ffmpeg", "-y",
        "-i", str(SRC),
        "-i", str(AUDIO),
        "-filter_complex",
        f"[0:v]{vf_full}[v];[1:a]anull[a]",
        "-map", "[v]", "-map", "[a]",
        "-c:v", "libx264", "-preset", "medium", "-crf", "19",
        "-pix_fmt", "yuv420p", "-r", "30",
        "-c:a", "aac", "-b:a", "192k",
        "-shortest", "-movflags", "+faststart",
        str(OUT),
    ]
    subprocess.run(cmd, check=True, capture_output=True)
    print(f"video -> {OUT}")


if __name__ == "__main__":
    build()
