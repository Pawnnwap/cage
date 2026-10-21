"""Render the Cage demo video frame by frame and pipe it into ffmpeg.

Usage:
    python tools/video/render.py                 # full render -> dist/cage-demo-animatic.mp4
    python tools/video/render.py --preview 26.0  # single frame -> dist/preview.png
"""

from __future__ import annotations

import argparse
import json
import math
import subprocess
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter

sys.path.insert(0, str(Path(__file__).resolve().parent))

import content as C  # noqa: E402
import kit as K  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
DIST = ROOT / "dist"
NARRATION = ROOT / "docs" / "video_narration.json"

FPS = 30
TOTAL = 165.0

# --------------------------------------------------------------------------
# static background (radial glow baked once)
# --------------------------------------------------------------------------


def build_base():
    img = Image.new("RGB", (K.W, K.CONTENT_H), K.INK)
    glow = Image.new("RGBA", (K.W, K.CONTENT_H), (0, 0, 0, 0))
    gd = ImageDraw.Draw(glow)
    gd.ellipse([-260, -420, K.W * 0.6, 520], fill=(184, 242, 91, 20))
    gd.ellipse([K.W * 0.5, -320, K.W * 1.3, 440], fill=(99, 230, 255, 14))
    glow = glow.filter(ImageFilter.GaussianBlur(100))
    return Image.alpha_composite(img.convert("RGBA"), glow).convert("RGB")


BASE = build_base()

# --------------------------------------------------------------------------
# narration
# --------------------------------------------------------------------------

FALLBACK_NARRATION = {
    "segments": [
        {"id": "hook", "start": 0.0, "end": 18.0, "onscreen": "Cage \u2014 containment-first agent control plane", "captions": []},
        {"id": "real_task", "start": 18.0, "end": 48.0, "onscreen": "write \u2192 execute \u2192 verify", "captions": []},
        {"id": "boundary", "start": 48.0, "end": 70.0, "onscreen": "network: none \u00b7 root: read-only \u00b7 user: 1000", "captions": []},
        {"id": "agent_mediated", "start": 70.0, "end": 95.0, "onscreen": "every tool call has a receipt", "captions": []},
        {"id": "drills_a", "start": 95.0, "end": 120.0, "onscreen": "rm -rf \u00b7 read-only canary \u00b7 cross-task", "captions": []},
        {"id": "drills_b_host", "start": 120.0, "end": 140.0, "onscreen": "loop \u00b7 fork bomb \u00b7 secret \u00b7 network \u00b7 host intact", "captions": []},
        {"id": "evidence_close", "start": 140.0, "end": TOTAL, "onscreen": "sealed \u00b7 signed \u00b7 verifiable", "captions": []},
    ]
}


def load_narration():
    if NARRATION.exists():
        try:
            data = json.loads(NARRATION.read_text(encoding="utf-8"))
            if data.get("segments"):
                return data
        except Exception as exc:  # pragma: no cover
            print(f"[warn] narration json unusable ({exc}); using fallback labels")
    return FALLBACK_NARRATION


NARR = load_narration()
CAPTIONS = sorted(
    [cap for seg in NARR["segments"] for cap in seg.get("captions", [])],
    key=lambda c: c["t"],
)


def caption_at(t):
    for cap in CAPTIONS:
        if cap["t"] <= t < cap["t"] + cap["d"]:
            raw = cap["text"]
            if isinstance(raw, list):
                raw = " ".join(str(x) for x in raw)
            lines = [ln.strip() for ln in str(raw).split("\n") if ln.strip()]
            return lines[:2]
    return []


def onscreen_at(t):
    for seg in NARR["segments"]:
        if seg["start"] <= t < seg["end"]:
            return seg.get("onscreen", "")
    return ""


# --------------------------------------------------------------------------
# helpers
# --------------------------------------------------------------------------

FULL = (0.0, 0.0, float(K.W), float(K.CONTENT_H))


def base_state():
    return {
        "title": "No run selected",
        "meta": "Select a run or start a new one.",
        "status": "idle",
        "cards": [],
        "scroll": 0.0,
        "alpha": {},
        "limits": C.LIMITS,
        "container_id": "\u2014",
        "image_id": C.IMAGE_ID_19,
        "key_fp": C.KEY_FP,
        "sandbox_mode": "docker",
        "cpu": 0.0,
        "mem": 0.0,
        "active_drill": None,
        "probe_results": [],
        "probe_running": None,
        "footer_hint": "No active sandbox.",
        "prompt": "",
        "cursor_on": False,
        "btn_pressed": False,
        "btn_label": "Run in sandbox",
        "runs": [],
        "evidence_pressed": False,
    }


MEASURE = ImageDraw.Draw(Image.new("RGB", (8, 8)))
CARD_W = K.CW - 40
CARD_GAP = 10
VIEW_H = (K.MAIN_BOT - 40) - (K.MAIN_Y + 66)


def heights_for(cards):
    return [K.card_height(MEASURE, card, CARD_W) for card in cards]


def typed(text, t, t0, cps=34):
    return text[: int(max(0.0, t - t0) * cps)]


def scroll_for(marks, cards, t, lead=0.35, pad=22):
    """Follow the newest card with a short lag so the feed scrolls smoothly."""
    visible = [c for i, c in enumerate(cards) if marks[i] <= t - lead]
    if not visible:
        return 0.0
    hs = heights_for(visible)
    total = sum(hs) + CARD_GAP * max(0, len(hs) - 1)
    return max(0.0, total - VIEW_H + pad)


def drill_result(key):
    d = C.DRILL_BY_KEY[key]
    return {
        "passed": d["passed"],
        "detail": d["detail"],
        "duration_ms": d["duration_ms"],
        "ids": d["ids"],
        "output": d["output"],
    }


def zoom_to(target, t, t0, dur=0.6, direction="in"):
    k = K.ease((t - t0) / dur)
    if direction == "out":
        k = 1.0 - k
    k = max(0.0, min(1.0, k))
    return tuple(FULL[i] + (target[i] - FULL[i]) * k for i in range(4))


def _drill_phase(t, slots):
    active = running = None
    results = []
    for press, run, res, key in slots:
        if t >= res:
            results.append(drill_result(key))
        elif t >= run:
            running = active = key
        elif t >= press:
            active = key
    return active, running, results[-2:]


MARKERS = [5.6, 7.0, 8.2, 9.6, 10.8, 12.0, 13.6, 15.4, 16.6]
MARKERS_2 = [5.0, 6.2, 7.8, 9.2, 10.8, 12.8, 14.8]

# --------------------------------------------------------------------------
# scenes
# --------------------------------------------------------------------------


def scene_hook(t):
    """0 - 18: public URL, one-liner, badges, deployment proof."""
    s = base_state()
    s["title"] = "An agent with a container-scoped blast radius of zero"
    s["meta"] = "Start a run to watch every tool call, command, and drill."
    opts = dict(
        focus_vultr=K.appear(t, 0.7, 0.7),
        focus_model=K.appear(t, 3.6, 0.7),
    )
    if 1.4 <= t < 3.4:
        k = K.ease((t - 1.4) / 2.0)
        opts["cursor"] = (int(K.lerp(1552, 1818, k)), 22)
    if t >= 8.4:
        opts["term"] = (C.DEPLOY_LINES, 8.5, (1030, 145, 810, 380), "root@cage-vm \u2014 ~/cage", 62)
    return s, None, opts


def scene_real_task(t):
    """18 - 48: a real model run through the mediated tool path."""
    s = base_state()
    s["runs"] = [("sine wave chart \u00b7 run it and verify", "running", "09:14:02", True)]
    s["title"] = "sine wave chart \u00b7 run it and verify"
    s["meta"] = C.PROMPT_1
    s["prompt"] = typed(C.PROMPT_1, t, 0.4, 34)
    s["cursor_on"] = t < 4.4
    s["btn_pressed"] = 4.6 <= t < 4.95
    s["btn_label"] = "Starting\u2026" if 4.6 <= t < 5.2 else "Run in sandbox"

    cards, alphas = [], {}
    for i, m in enumerate(MARKERS):
        if t >= m:
            cards.append(C.CARDS_TASK1[i])
            alphas[len(cards) - 1] = K.appear(t, m, 0.3)
    s["cards"] = cards
    s["alpha"] = alphas
    s["status"] = "running" if t < 16.6 else "completed"
    s["scroll"] = scroll_for(MARKERS, C.CARDS_TASK1, t)

    if t >= 7.0:
        s["container_id"] = C.CID1
        s["footer_hint"] = (
            f"sandbox {C.SANDBOX1_ID[:26]} \u00b7 running" if t < 16.6
            else "sandbox destroyed \u00b7 no residual process"
        )
    if 12.0 <= t < 14.5:
        s["cpu"] = K.lerp(12.0, 64.0, K.ease((t - 12.0) / 2.0))
        s["mem"] = K.lerp(84.0, 218.0, K.ease((t - 12.0) / 2.0))
    elif 14.5 <= t < 16.6:
        s["cpu"] = K.lerp(64.0, 24.0, K.ease((t - 14.5) / 2.0))
        s["mem"] = 218.0
    return s, None, dict()


def scene_boundary(t):
    """48 - 70: configured limits, live stat, container + image id, host config."""
    s = base_state()
    s["runs"] = [("sine wave chart \u00b7 run it and verify", "completed", "09:14:02", True)]
    s["title"] = "sine wave chart \u00b7 run it and verify"
    s["meta"] = C.PROMPT_1
    s["status"] = "completed"
    s["cards"] = C.CARDS_TASK1
    s["container_id"] = C.CID1
    s["footer_hint"] = f"sandbox {C.SANDBOX1_ID[:26]} \u00b7 running"
    s["scroll"] = scroll_for(MARKERS, C.CARDS_TASK1, 30.0)
    s["cpu"] = 18.0 + 13.0 * (0.5 + 0.5 * math.sin(t * 1.6))
    s["mem"] = 196.0 + 24.0 * (0.5 + 0.5 * math.sin(t * 0.9 + 1.0))

    opts = {"sandbox_focus": 1.0}
    if t < 9.4:
        opts["term"] = (C.INSPECT_LINES, 0.4, (900, 145, 980, 470), "root@cage-vm \u2014 docker inspect", 80)
        focus = None
    elif t < 14.8:
        opts["invariants"] = K.appear(t, 9.6, 0.8)
        focus = None
    else:
        focus = zoom_to((1404, 196, 512, 250), t, 14.8, 0.7)
    return s, focus, opts


def scene_agent_mediated(t):
    """70 - 95: the agent asks to delete /etc/hostname through run_command."""
    s = base_state()
    s["runs"] = [
        ("delete /etc/hostname through run_command", "running" if t < 14.8 else "completed", "09:16:11", True),
        ("sine wave chart \u00b7 run it and verify", "completed", "09:14:02", False),
    ]
    s["title"] = "delete /etc/hostname through run_command"
    s["meta"] = C.PROMPT_2
    s["prompt"] = typed(C.PROMPT_2, t, 0.3, 42)
    s["cursor_on"] = t < 3.8
    s["btn_pressed"] = 4.0 <= t < 4.35
    s["btn_label"] = "Starting\u2026" if 4.0 <= t < 4.6 else "Run in sandbox"

    cards, alphas = [], {}
    for i, m in enumerate(MARKERS_2):
        if t >= m:
            cards.append(C.CARDS_TASK2[i])
            alphas[len(cards) - 1] = K.appear(t, m, 0.3)
    s["cards"] = cards
    s["alpha"] = alphas
    s["status"] = "running" if t < 14.8 else "completed"
    s["scroll"] = scroll_for(MARKERS_2, C.CARDS_TASK2, t)
    if t >= 6.2:
        s["container_id"] = C.CID2
        s["footer_hint"] = f"sandbox {C.SANDBOX2_ID[:26]} \u00b7 running"
    if 9.2 <= t < 11.0:
        s["cpu"] = K.lerp(8.0, 31.0, K.ease((t - 9.2) / 1.6))
        s["mem"] = K.lerp(96.0, 164.0, K.ease((t - 9.2) / 1.6))

    focus = zoom_to((K.CX + 10, K.MAIN_Y + 150, 760, 560), t, 16.2, 0.7) if t >= 16.2 else None
    return s, focus, dict()


def scene_drills_a(t):
    """95 - 120: rm -rf, read-only canary, cross-task."""
    slots = [
        (0.4, 1.1, 2.4, "rm_rf"),
        (8.0, 8.7, 10.0, "readonly_canary"),
        (15.6, 16.4, 18.0, "cross_task"),
    ]
    active, running, results = _drill_phase(t, slots)
    s = base_state()
    s["runs"] = [
        ("delete /etc/hostname through run_command", "completed", "09:16:11", False),
        ("sine wave chart \u00b7 run it and verify", "completed", "09:14:02", True),
    ]
    s["title"] = "sine wave chart \u00b7 run it and verify"
    s["meta"] = C.PROMPT_1
    s["status"] = "completed"
    s["cards"] = C.CARDS_TASK1
    s["scroll"] = scroll_for(MARKERS, C.CARDS_TASK1, 30.0)
    s["container_id"] = C.CID1
    s["active_drill"] = active
    s["probe_running"] = running
    s["probe_results"] = results
    s["cpu"] = 11.0
    s["mem"] = 188.0
    s["footer_hint"] = f"sandbox {C.SANDBOX1_ID[:26]} \u00b7 running"
    focus = zoom_to((1398, 500, 524, 470), t, 1.6, 0.7) if t >= 1.6 else None
    return s, focus, dict()


def scene_drills_b_host(t):
    """120 - 140: loop, fork bomb, secret, network, then the host is intact."""
    slots = [
        (0.2, 0.8, 1.8, "infinite_loop"),
        (3.4, 4.0, 5.0, "fork_bomb"),
        (6.4, 7.0, 7.8, "secret_probe"),
        (8.8, 9.4, 10.2, "network_probe"),
    ]
    active, running, results = _drill_phase(t, slots)
    s = base_state()
    s["runs"] = [
        ("delete /etc/hostname through run_command", "completed", "09:16:11", False),
        ("sine wave chart \u00b7 run it and verify", "completed", "09:14:02", True),
    ]
    s["title"] = "sine wave chart \u00b7 run it and verify"
    s["meta"] = C.PROMPT_1
    s["status"] = "completed"
    s["cards"] = C.CARDS_TASK1
    s["scroll"] = scroll_for(MARKERS, C.CARDS_TASK1, 30.0)
    s["container_id"] = C.CID1
    s["active_drill"] = active
    s["probe_running"] = running
    s["probe_results"] = results
    s["cpu"] = 11.0
    s["mem"] = 188.0
    s["footer_hint"] = "sandbox destroyed \u00b7 no residual process"

    target = (1398, 500, 524, 470)
    if t >= 10.4:
        focus = zoom_to(target, t, 10.4, 0.5, direction="out")
        return s, focus, dict(term=(C.HOST_LINES, 11.1, (400, 150, 880, 340), "root@cage-vm \u2014 host, after the drills", 44))
    focus = zoom_to(target, 0.0, 0.0)
    return s, focus, dict()


INVARIANTS = [
    "network: none",
    "ipc: none",
    "root filesystem: read-only",
    "user: UID 1000",
    "capabilities: dropped (ALL)",
    "1 CPU \u00b7 512 MB \u00b7 128 PIDs",
    "workspace: 64 MB tmpfs",
    "no host bind mount",
    "no API key in the sandbox",
]


def draw_check(d, x, y, colour, size=11):
    d.line([(x, y + size * 0.55), (x + size * 0.38, y + size)], fill=colour, width=3, joint="curve")
    d.line([(x + size * 0.38, y + size), (x + size * 1.15, y - size * 0.55)], fill=colour, width=3, joint="curve")


def draw_invariant_list(d, alpha):
    if alpha <= 0.01:
        return
    x, y = 34, 148
    w = 566
    h = 58 + 34 * len(INVARIANTS)
    K.rr(d, [x, y, x + w, y + h], radius=14, fill=(6, 9, 12))
    K.rr(d, [x, y, x + w, y + h], radius=14, outline=K.mix(K.LINE, K.ACID, 0.45 * alpha), width=1)
    K.txt(d, (x + 22, y + 18), "CONFIGURED INVARIANTS", K.sans(13, True), K.dim(K.ACID, alpha))
    cy = y + 54
    for item in INVARIANTS:
        draw_check(d, x + 24, cy + 4, K.dim(K.ACID, alpha))
        K.txt(d, (x + 54, cy), item, K.mono(12), K.dim(K.TEXT, alpha))
        cy += 34


def scene_evidence_close(t):
    """140 - 163: sealed pack, verifier VALID, fingerprint, repo + pitch."""
    s = base_state()
    s["runs"] = [
        ("delete /etc/hostname through run_command", "completed", "09:16:11", False),
        ("sine wave chart \u00b7 run it and verify", "completed", "09:14:02", True),
    ]
    s["title"] = "sine wave chart \u00b7 run it and verify"
    s["meta"] = C.PROMPT_1
    s["status"] = "completed"
    s["cards"] = C.CARDS_TASK1
    s["scroll"] = scroll_for(MARKERS, C.CARDS_TASK1, 30.0)
    s["container_id"] = C.CID1
    s["evidence_pressed"] = 0.2 <= t < 1.1
    s["cpu"] = 11.0
    s["mem"] = 188.0
    s["footer_hint"] = f"sandbox {C.SANDBOX1_ID[:26]} \u00b7 running"

    opts = {}
    if t < 9.4:
        n = int(K.lerp(0, len(C.EVIDENCE_ROWS), K.ease((t - 0.7) / 4.2)))
        highlight = (len(C.EVIDENCE_ROWS) - 1,) if n >= len(C.EVIDENCE_ROWS) else ()
        opts["json"] = (C.EVIDENCE_ROWS[: max(0, n)], (200, 150, 780, 580), 1.0, highlight)
    elif t < 15.8:
        opts["json"] = (C.EVIDENCE_ROWS, (200, 150, 780, 580), 1.0, (len(C.EVIDENCE_ROWS) - 1,))
        opts["term"] = (C.VERIFY_LINES, 9.7, (1000, 190, 880, 300), "root@cage-vm \u2014 verify the exported pack", 58)
    else:
        opts["close"] = K.appear(t, 15.8, 0.9)
    return s, None, opts


SCENES = [
    (0.0, 18.0, scene_hook),
    (18.0, 48.0, scene_real_task),
    (48.0, 70.0, scene_boundary),
    (70.0, 95.0, scene_agent_mediated),
    (95.0, 120.0, scene_drills_a),
    (120.0, 140.0, scene_drills_b_host),
    (140.0, TOTAL, scene_evidence_close),
]


def scene_for(t):
    for start, end, fn in SCENES:
        if start <= t < end:
            return fn, t - start
    return scene_evidence_close, t - 140.0


# --------------------------------------------------------------------------
# frame
# --------------------------------------------------------------------------


def apply_zoom(ui, focus, max_scale=2.5):
    if not focus:
        return ui
    fx, fy, fw, fh = focus
    if fw >= K.W - 2 and fh >= K.CONTENT_H - 2:
        return ui
    scale = min(K.W / fw, K.CONTENT_H / fh, max_scale)
    cw, ch = K.W / scale, K.CONTENT_H / scale
    cx, cy = fx + fw / 2.0, fy + fh / 2.0
    x0 = max(0.0, min(cx - cw / 2.0, K.W - cw))
    y0 = max(0.0, min(cy - ch / 2.0, K.CONTENT_H - ch))
    return ui.resize((K.W, K.CONTENT_H), Image.LANCZOS, box=(x0, y0, x0 + cw, y0 + ch))


def render_frame(t):
    fn, lt = scene_for(t)
    state, focus, opts = fn(lt)

    ui = BASE.copy()
    ud = ImageDraw.Draw(ui)
    K.draw_header(ud, C.MODEL, focus_vultr=opts.get("focus_vultr", 0.0), focus_model=opts.get("focus_model", 0.0))
    K.draw_new_run(ud, state["prompt"], cursor_on=state["cursor_on"], btn_pressed=state["btn_pressed"], btn_label=state["btn_label"])
    K.draw_runs(ud, state["runs"])
    K.draw_center(ud, state)
    K.draw_sandbox_panel(ud, state, focus=opts.get("sandbox_focus", 0.0))
    K.draw_drill_panel(ud, state)
    K.draw_footer(ud)
    ui = apply_zoom(ui, focus)

    img = Image.new("RGB", (K.W, K.H), K.INK)
    img.paste(ui, (0, K.CHROME_H))
    d = ImageDraw.Draw(img)
    K.draw_chrome(d, C.PUBLIC_URL)

    if opts.get("cursor"):
        K.cursor(d, opts["cursor"][0], opts["cursor"][1] + K.CHROME_H)
    if opts.get("json"):
        rows, box, alpha, highlight = opts["json"]
        overlay = Image.new("RGBA", (K.W, K.H), (0, 0, 0, 0))
        K.draw_json(ImageDraw.Draw(overlay), box, "/api/tasks/{id}/evidence", rows, highlight=highlight)
        if alpha < 1.0:
            overlay.putalpha(overlay.getchannel("A").point(lambda v: int(v * alpha)))
        img = Image.alpha_composite(img.convert("RGBA"), overlay).convert("RGB")
        d = ImageDraw.Draw(img)
    if opts.get("term"):
        lines, t0, box, title, cps = opts["term"]
        K.draw_terminal(d, box, title, lines, lt, t0=t0, cps=cps)
    if opts.get("invariants"):
        draw_invariant_list(d, opts["invariants"])
    if opts.get("close"):
        draw_close_card(d, opts["close"])
        return img

    K.draw_lower_third(d, onscreen_at(t))
    K.draw_caption(d, caption_at(t))
    return img


def draw_close_card(d, alpha):
    a = alpha
    d.rectangle([0, 0, K.W, K.H], fill=(6, 9, 12))
    big = K.font(K.F_SANS_B, 104)
    mid = K.font(K.F_SANS, 34)
    mono_f = K.font(K.F_MONO, 27)
    pitch = K.font(K.F_SANS_B, 54)
    small = K.font(K.F_SANS, 27)
    small_b = K.font(K.F_SANS_B, 27)
    tiny = K.font(K.F_SANS, 21)

    K.txt(d, (K.W // 2, 208), "Cage", big, K.dim(K.WHITE, a), anchor="ma")
    K.txt(d, (K.W // 2, 336), "containment-first agent control plane", mid, K.dim(K.MUTED, a), anchor="ma")
    K.txt(d, (K.W // 2, 448), "Browser \u2192 control plane \u2192 sandboxd \u2192 ephemeral container", mono_f, K.dim(K.CYAN, a), anchor="ma")
    K.txt(d, (K.W // 2, 576), "Every tool call has a receipt.", pitch, K.dim(K.ACID, a), anchor="ma")
    K.txt(d, (K.W // 2, 646), "mediated \u00b7 sandboxed \u00b7 signed", small, K.dim(K.TEXT, a), anchor="ma")

    K.rr(d, [K.W // 2 - 440, 736, K.W // 2 + 440, 812], radius=13, fill=(13, 18, 23), outline=K.mix(K.LINE, K.ACID, 0.55 * a), width=1)
    K.txt(d, (K.W // 2, 759), C.REPO_URL, mono_f, K.dim(K.ACID, a), anchor="ma")

    K.txt(d, (K.W // 2, 872), "Vultr Agent Rush \u00b7 Container-Scoped Blast Radius Zero", small_b, K.dim((156, 170, 190), a), anchor="ma")
    K.txt(d, (K.W // 2, 918), "Docker shares the host kernel; kernel escapes are out of scope.", tiny, K.dim((110, 126, 145), a), anchor="ma")


# --------------------------------------------------------------------------
# main
# --------------------------------------------------------------------------


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--preview", type=float, default=None)
    ap.add_argument("--previews", default=None, help="comma separated times")
    ap.add_argument("--out", default=str(DIST / "cage-demo-animatic.mp4"))
    ap.add_argument("--audio", default=None)
    args = ap.parse_args()

    DIST.mkdir(parents=True, exist_ok=True)

    if args.previews:
        for raw in args.previews.split(","):
            t = float(raw)
            out = DIST / f"prev_{raw.strip()}.png"
            render_frame(t).save(out)
            print(f"preview {t} -> {out}")
        return

    if args.preview is not None:
        out = DIST / "preview.png"
        render_frame(args.preview).save(out)
        print(f"preview -> {out}")
        return

    audio_ok = bool(args.audio) and Path(args.audio).exists()
    cmd = [
        "ffmpeg", "-y",
        "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{K.W}x{K.H}", "-r", str(FPS),
        "-i", "-",
    ]
    if audio_ok:
        cmd += ["-i", args.audio]
    cmd += ["-c:v", "libx264", "-preset", "medium", "-crf", "17", "-pix_fmt", "yuv420p", "-movflags", "+faststart"]
    if audio_ok:
        cmd += ["-c:a", "aac", "-b:a", "192k", "-shortest"]
    cmd += ["-loglevel", "error", args.out]

    frames = int(round(TOTAL * FPS))
    # stderr must NOT be a PIPE we never drain: ffmpeg fills it and deadlocks
    err_log = DIST / "ffmpeg.err"
    err_fh = open(err_log, "w")
    proc = subprocess.Popen(cmd, stdin=subprocess.PIPE, stdout=subprocess.DEVNULL, stderr=err_fh)
    try:
        for i in range(frames):
            img = render_frame(i / FPS)
            proc.stdin.write(img.tobytes())
            if i % 300 == 0:
                print(f"frame {i}/{frames}  t={i / FPS:.1f}s", flush=True)
        proc.stdin.close()
    except BrokenPipeError:
        pass
    code = proc.wait()
    err_fh.close()
    if code != 0:
        print(err_log.read_text(encoding="utf-8", errors="replace")[-4000:])
        sys.exit(code)
    err_log.unlink(missing_ok=True)
    print(f"video -> {args.out}")


if __name__ == "__main__":
    main()
