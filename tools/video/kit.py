"""Drawing primitives for the Cage demo video.

Everything here is deterministic: given a time value, the same frame comes out.
The page is drawn in a 1920x1004 logical space with a font boost so the UI
stays readable when the video is watched at 1080p (or downscaled to 720p).
"""

from __future__ import annotations

from functools import lru_cache

from PIL import Image, ImageDraw, ImageFont

# --------------------------------------------------------------------------
# theme
# --------------------------------------------------------------------------

W, H = 1920, 1080
CHROME_H = 76
CONTENT_H = H - CHROME_H  # 1004

INK = (8, 11, 14)
PANEL = (13, 18, 23)
PANEL_2 = (17, 23, 30)
LINE = (30, 40, 52)
CODE_BG = (7, 10, 13)
ACID = (184, 242, 91)
CYAN = (99, 230, 255)
DANGER = (255, 107, 107)
AMBER = (255, 190, 92)
WHITE = (255, 255, 255)
TEXT = (228, 234, 242)
MUTED = (156, 170, 190)
DIM = (110, 126, 145)
FAINT = (78, 92, 110)

F_SANS = "C:/Windows/Fonts/segoeui.ttf"
F_SANS_B = "C:/Windows/Fonts/segoeuib.ttf"
F_MONO = "C:/Windows/Fonts/consola.ttf"
F_MONO_B = "C:/Windows/Fonts/consolab.ttf"

# the app renders 10-12px UI text; at video scale that is unreadable, so every
# font size goes through this multiplier
BOOST = 1.42

TEXT_LH = 22
CODE_LH = 19


@lru_cache(maxsize=2048)
def font(path: str, size: int):
    return ImageFont.truetype(path, int(size))


def sans(size: float, bold: bool = False):
    return font(F_SANS_B if bold else F_SANS, max(9, round(size * BOOST)))


def mono(size: float, bold: bool = False):
    return font(F_MONO_B if bold else F_MONO, max(9, round(size * BOOST)))


# --------------------------------------------------------------------------
# primitives
# --------------------------------------------------------------------------


def rr(d, box, radius=10, fill=None, outline=None, width=1):
    d.rounded_rectangle([int(v) for v in box], radius=radius, fill=fill, outline=outline, width=width)


def txt(d, xy, s, f, fill, anchor="la"):
    d.text((int(xy[0]), int(xy[1])), s, font=f, fill=fill, anchor=anchor)


def tw(d, s, f):
    return int(d.textlength(s, font=f))


def wrap(d, s, f, max_w):
    words = s.split(" ")
    lines, cur = [], ""
    for word in words:
        trial = word if not cur else cur + " " + word
        if tw(d, trial, f) <= max_w or not cur:
            cur = trial
        else:
            lines.append(cur)
            cur = word
    if cur:
        lines.append(cur)
    return lines


def clip(s, n):
    s = str(s)
    return s if len(s) <= n else s[: n - 1] + "\u2026"


def clip_w(d, s, f, max_w):
    s = str(s)
    if tw(d, s, f) <= max_w:
        return s
    while s and tw(d, s + "\u2026", f) > max_w:
        s = s[:-1]
    return s + "\u2026"


def lerp(a, b, t):
    t = max(0.0, min(1.0, t))
    return a + (b - a) * t


def ease(t):
    t = max(0.0, min(1.0, t))
    return t * t * (3 - 2 * t)


def appear(t, start, dur=0.35):
    return ease((t - start) / dur) if dur > 0 else 1.0


def mix(c1, c2, t):
    t = max(0.0, min(1.0, t))
    return tuple(int(lerp(c1[i], c2[i], t)) for i in range(3))


def dim(c, amount):
    return mix(INK, c, amount)


# --------------------------------------------------------------------------
# browser chrome
# --------------------------------------------------------------------------


def draw_chrome(d, url: str):
    d.rectangle([0, 0, W, 40], fill=(32, 33, 36))
    d.rounded_rectangle([16, 6, 336, 40], radius=10, fill=(53, 54, 58))
    d.rectangle([16, 30, 336, 40], fill=(53, 54, 58))
    d.ellipse([32, 14, 46, 28], fill=(28, 42, 24))
    txt(d, (52, 19), "Cage - containment-first agent control plane", sans(12), (207, 210, 214))
    txt(d, (316, 15), "\u00d7", sans(14), (150, 152, 156))

    d.rectangle([0, 40, W, CHROME_H], fill=(53, 54, 58))
    for i, cx in enumerate((32, 66, 100)):
        c = (168, 171, 176) if i < 2 else (126, 129, 134)
        d.ellipse([cx - 8, 50, cx + 8, 66], outline=c, width=2)
    rr(d, [124, 45, 1660, 71], radius=13, fill=(32, 33, 36))
    d.ellipse([140, 51, 154, 65], outline=(120, 200, 130), width=2)
    d.line([147, 58, 147, 62], fill=(120, 200, 130), width=2)
    txt(d, (164, 47), url, sans(15), (220, 224, 228))
    txt(d, (1636, 46), "\u2606", sans(15), (168, 171, 176))
    for cx in (1700, 1736, 1772):
        d.ellipse([cx - 2, 56, cx + 2, 60], fill=(168, 171, 176))
    d.ellipse([1822, 51, 1850, 79], fill=(110, 150, 235))
    txt(d, (1836, 55), "V", sans(13, True), (255, 255, 255), anchor="mm")
    d.line([0, CHROME_H - 1, W, CHROME_H - 1], fill=(0, 0, 0), width=1)


# --------------------------------------------------------------------------
# page layout (content coordinates)
# --------------------------------------------------------------------------

HEAD_H = 62
FOOT_H = 34
MAIN_Y = HEAD_H
MAIN_BOT = CONTENT_H - FOOT_H

LX, LW = 24, 470
CX, CW = 510, 900
RX, RW = 1426, 470

LEFT_BOX = (LX, MAIN_Y, LX + LW, MAIN_Y + 336)
RUNS_BOX = (LX, MAIN_Y + 352, LX + LW, MAIN_BOT)
CENTER_BOX = (CX, MAIN_Y, CX + CW, MAIN_BOT)
RIGHT_BOX = (RX, MAIN_Y, RX + RW, MAIN_Y + 440)
DRILL_BOX = (RX, MAIN_Y + 456, RX + RW, MAIN_BOT)


def draw_header(d, model: str, focus_vultr: float = 0.0, focus_model: float = 0.0):
    x0, x1 = 20, W - 20
    d.line([x0, HEAD_H - 1, x1, HEAD_H - 1], fill=LINE, width=1)

    bx, by = 24, 9
    rr(d, [bx, by, bx + 44, by + 44], radius=13, fill=(22, 32, 18), outline=(74, 100, 44), width=1)
    d.polygon(
        [(bx + 22, by + 11), (bx + 36, by + 18), (bx + 36, by + 28), (bx + 22, by + 35), (bx + 8, by + 28), (bx + 8, by + 18)],
        outline=ACID,
        width=3,
    )
    d.line([(bx + 16, by + 25), (bx + 21, by + 30), (bx + 29, by + 21)], fill=ACID, width=3, joint="curve")

    txt(d, (bx + 56, 6), "Cage", sans(17, True), WHITE)
    pill_x = bx + 56 + tw(d, "Cage", sans(17, True)) + 12
    rr(d, [pill_x, 10, pill_x + 148, 32], radius=10, fill=(22, 32, 18), outline=(74, 100, 44), width=1)
    txt(d, (pill_x + 11, 12), "VULTR AGENT RUSH", sans(10, True), ACID)
    txt(d, (bx + 56, 34), "Containment-first agent control plane \u00b7 container-scoped blast radius zero", sans(11), MUTED)

    chips = [
        ("Vultr Serverless Inference", ACID, focus_vultr),
        ("Docker sandbox", CYAN, 0.0),
        (model, MUTED, focus_model),
    ]
    cx = W - 26
    for label, colour, glow in reversed(chips):
        f = mono(10)
        w = tw(d, label, f) + 40
        x = cx - w
        rr(d, [x, 15, cx, 43], radius=14, fill=mix((30, 42, 26), (48, 68, 34), glow), outline=mix(LINE, colour, 0.3 + 0.55 * glow), width=1)
        d.ellipse([x + 11, 24, x + 20, 33], fill=colour)
        txt(d, (x + 28, 20), label, f, mix(MUTED, colour, 0.3 + 0.65 * glow))
        cx = x - 9


def draw_footer(d):
    s = "No network egress \u00b7 64MB tmpfs workspace \u00b7 no API keys in the sandbox \u00b7 one ephemeral container per run \u00b7 signed evidence"
    txt(d, (W // 2, CONTENT_H - FOOT_H + 9), s, sans(10), FAINT, anchor="ma")
    d.line([0, CONTENT_H - FOOT_H, W, CONTENT_H - FOOT_H], fill=LINE, width=1)


# --------------------------------------------------------------------------
# small widgets
# --------------------------------------------------------------------------


def chip(d, x, y, label, colour=DIM, bg=(24, 32, 40)):
    f = sans(10)
    w = tw(d, label, f) + 22
    rr(d, [x, y, x + w, y + 28], radius=8, fill=bg, outline=LINE, width=1)
    txt(d, (x + 11, y + 5), label, f, colour)
    return w


def badge(d, x, y, label, colour, right=None):
    f = sans(10, True)
    w = tw(d, label, f) + 22
    bx = (right - w) if right else x
    rr(d, [bx, y, bx + w, y + 26], radius=13, fill=mix(INK, colour, 0.18), outline=mix(LINE, colour, 0.55), width=1)
    txt(d, (bx + 11, y + 5), label, f, colour)
    return w


def metric(d, x, y, w, h, label, value, value_colour=TEXT):
    rr(d, [x, y, x + w, y + h], radius=9, fill=PANEL_2, outline=LINE, width=1)
    txt(d, (x + 12, y + 5), label, sans(10), DIM)
    txt(d, (x + 12, y + 20), clip_w(d, value, sans(13, True), w - 24), sans(13, True), value_colour)


def bar(d, x, y, w, label, value_text, frac, colour):
    txt(d, (x, y), label, sans(10), DIM)
    txt(d, (x + w, y), value_text, mono(10), MUTED, anchor="ra")
    rr(d, [x, y + 19, x + w, y + 29], radius=5, fill=(22, 30, 38))
    if frac > 0.001:
        rr(d, [x, y + 19, x + max(6, int(w * min(1.0, frac))), y + 29], radius=5, fill=colour)


def button(d, x, y, w, h, label, tone="ghost", pressed=False, disabled=False, icon=None):
    if tone == "primary":
        fill = (152, 202, 62) if pressed else ACID
        fg, outline = (10, 14, 8), None
    elif tone == "drill":
        fill = (40, 54, 30) if pressed else (20, 28, 36)
        fg = ACID if not disabled else FAINT
        outline = (72, 96, 54)
    else:
        fill = (32, 44, 56) if pressed else (20, 28, 36)
        fg = TEXT if not disabled else FAINT
        outline = LINE
    rr(d, [x, y, x + w, y + h], radius=9, fill=fill, outline=outline, width=1)
    f = sans(12, True)
    if icon:
        txt(d, (x + 14, y + h // 2), icon, f, fg, anchor="lm")
        txt(d, (x + w // 2 + 9, y + h // 2), label, f, fg, anchor="mm")
    else:
        txt(d, (x + w // 2, y + h // 2), label, f, fg, anchor="mm")


def cursor(d, x, y):
    d.polygon(
        [(x, y), (x, y + 24), (x + 7, y + 17), (x + 14, y + 26), (x + 19, y + 22), (x + 12, y + 13), (x + 20, y + 12)],
        fill=WHITE, outline=(18, 18, 18),
    )


# --------------------------------------------------------------------------
# left column
# --------------------------------------------------------------------------


def draw_new_run(d, prompt, cursor_on=False, btn_pressed=False, btn_label="Run in sandbox"):
    x, y, x2, y2 = LEFT_BOX
    rr(d, LEFT_BOX, radius=14, fill=PANEL, outline=LINE, width=1)
    txt(d, (x + 18, y + 16), "New run", sans(14, True), WHITE)
    txt(d, (x2 - 18, y + 19), "EPHEMERAL SANDBOX", sans(9, True), FAINT, anchor="ra")

    tx, ty = x + 18, y + 46
    tw_ = (x2 - 18) - tx
    rr(d, [tx, ty, tx + tw_, ty + 150], radius=10, fill=CODE_BG, outline=LINE, width=1)
    f = mono(11)
    lines = []
    for para in prompt.split("\n"):
        lines.extend(wrap(d, para, f, tw_ - 24))
    max_lines = int(150 / TEXT_LH)
    lines = lines[:max_lines]
    for i, line in enumerate(lines):
        txt(d, (tx + 12, ty + 12 + i * TEXT_LH), line, f, TEXT)
    if cursor_on:
        if lines:
            cx = tx + 12 + tw(d, lines[-1], f)
            cy = ty + 12 + (len(lines) - 1) * TEXT_LH
        else:
            cx, cy = tx + 12, ty + 12
        d.line([cx, cy, cx, cy + 17], fill=ACID, width=2)

    ex = tx
    for label in ("sine chart", "csv summary", "fix a test"):
        ex += chip(d, ex, ty + 162, label) + 8

    button(d, tx, ty + 202, tw_, 46, btn_label, tone="primary", pressed=btn_pressed, icon="\u2192")
    txt(d, (tx, ty + 262), "Every command is mediated by sandboxd.", sans(10), FAINT)
    txt(d, (tx, ty + 280), "No host shell, no network, no secrets.", sans(10), FAINT)


def draw_runs(d, runs):
    x, y, x2, y2 = RUNS_BOX
    rr(d, RUNS_BOX, radius=14, fill=PANEL, outline=LINE, width=1)
    txt(d, (x + 18, y + 16), "Runs", sans(14, True), WHITE)
    txt(d, (x2 - 18, y + 19), "REFRESH", sans(9, True), FAINT, anchor="ra")
    iy = y + 46
    for title, status, ts, active in runs:
        h = 54
        if iy + h > y2 - 14:
            break
        rr(d, [x + 14, iy, x2 - 14, iy + h], radius=10, fill=(26, 36, 44) if active else PANEL_2,
           outline=mix(LINE, ACID, 0.5) if active else LINE, width=1)
        colour = {"running": ACID, "completed": ACID, "failed": DANGER}.get(status, DIM)
        d.ellipse([x + 28, iy + 23, x + 38, iy + 33], fill=colour)
        txt(d, (x + 50, iy + 9), clip_w(d, title, sans(11, True), (x2 - x) - 80), sans(11, True), TEXT)
        txt(d, (x + 50, iy + 29), f"{status} \u00b7 {ts}", sans(10), DIM)
        iy += h + 8


# --------------------------------------------------------------------------
# centre column: timeline
# --------------------------------------------------------------------------

TONES = {
    "ok": ACID,
    "fail": DANGER,
    "exec": CYAN,
    "tool": AMBER,
    "agent": (186, 166, 255),
    "info": MUTED,
}


def card_height(d, card, width):
    f_body = sans(11)
    h = 36
    for block in card["blocks"]:
        if block["t"] == "text":
            h += 8 + TEXT_LH * len(wrap(d, block["s"], f_body, width - 34))
        elif block["t"] == "code":
            h += 12 + CODE_LH * len(block["s"].split("\n"))
        elif block["t"] == "kv":
            h += 8 + TEXT_LH * ((len(block["items"]) + 1) // 2)
        elif block["t"] == "row":
            h += 8 + 22
        elif block["t"] == "note":
            h += 8 + 20
    return h + 14


def draw_card(d, x, y, w, card, alpha=1.0):
    tone = TONES.get(card.get("tone", "info"), MUTED)
    h = card_height(d, card, w)
    rr(d, [x, y, x + w, y + h], radius=11, fill=mix(INK, PANEL, alpha), outline=mix(LINE, tone, 0.3 * alpha), width=1)
    d.rounded_rectangle([x, y + 2, x + 4, y + h - 2], radius=2, fill=dim(tone, alpha))
    txt(d, (x + 18, y + 9), card["label"], mono(10, True), dim(tone, alpha))
    txt(d, (x + w - 16, y + 9), card.get("time", ""), mono(10), dim(FAINT, alpha), anchor="ra")

    cy = y + 34
    f_body = sans(11)
    f_code = mono(11)
    for block in card["blocks"]:
        t = block["t"]
        if t == "text":
            for line in wrap(d, block["s"], f_body, w - 34):
                txt(d, (x + 18, cy), line, f_body, dim(block.get("c", TEXT), alpha))
                cy += TEXT_LH
            cy += 6
        elif t == "code":
            lines = block["s"].split("\n")
            bh = CODE_LH * len(lines) + 14
            rr(d, [x + 16, cy, x + w - 16, cy + bh], radius=7, fill=CODE_BG, outline=dim(LINE, alpha), width=1)
            colour = dim({"exec": CYAN, "danger": DANGER}.get(block.get("tone", ""), TEXT), alpha)
            for i, line in enumerate(lines):
                txt(d, (x + 26, cy + 7 + i * CODE_LH), clip_w(d, line, f_code, w - 60), f_code, colour)
            cy += bh + 8
        elif t == "kv":
            col_w = (w - 36) // 2
            for i, (k, v) in enumerate(block["items"]):
                cxx = x + 18 + (i % 2) * col_w
                cyy = cy + (i // 2) * TEXT_LH + TEXT_LH // 2
                txt(d, (cxx, cyy), k, sans(10), dim(DIM, alpha), anchor="lm")
                txt(d, (cxx + 78, cyy), clip_w(d, v, mono(11), col_w - 84), mono(11), dim(block.get("c", TEXT), alpha), anchor="lm")
            cy += TEXT_LH * ((len(block["items"]) + 1) // 2) + 6
        elif t == "row":
            cx2 = x + 18
            for label, colour in block["items"]:
                txt(d, (cx2, cy), label, mono(11, True), dim(colour, alpha))
                cx2 += tw(d, label, mono(11, True)) + 18
            cy += 24
        elif t == "note":
            txt(d, (x + 18, cy), block["s"], sans(10), dim(block.get("c", MUTED), alpha))
            cy += 22
    return h


def draw_center(d, state):
    x, y, x2, y2 = CENTER_BOX
    rr(d, CENTER_BOX, radius=14, fill=PANEL, outline=LINE, width=1)
    txt(d, (x + 18, y + 14), clip_w(d, state.get("title", "No run selected"), sans(14, True), CW - 260), sans(14, True), WHITE)
    status = state.get("status", "idle")
    badge(d, 0, y + 14, status, TONES.get("ok" if status == "completed" else ("exec" if status == "running" else "info"), MUTED), right=x2 - 18)
    txt(d, (x + 18, y + 38), clip_w(d, state.get("meta", ""), sans(11), CW - 40), sans(11), DIM)
    ty = y + 64
    d.line([x, ty, x2, ty], fill=LINE, width=1)

    clip_top = ty + 2
    clip_bot = y2 - 40
    cards = state.get("cards", [])
    gap = 10
    heights = [card_height(d, c, CW - 40) for c in cards]
    total = sum(heights) + gap * max(0, len(cards) - 1)
    view = clip_bot - clip_top
    scroll = state.get("scroll", 0.0)
    scroll = max(0.0, min(max(0.0, total - view + 12), scroll))

    d.rectangle([x + 1, clip_top, x2 - 1, clip_bot], fill=PANEL)
    cy_pos = clip_top + 10 - scroll
    for i, card in enumerate(cards):
        h = heights[i]
        if cy_pos + h < clip_top - 60 or cy_pos > clip_bot + 60:
            cy_pos += h + gap
            continue
        draw_card(d, x + 20, cy_pos, CW - 40, card, alpha=state.get("alpha", {}).get(i, 1.0))
        cy_pos += h + gap

    txt(d, (x + 18, y2 - 28), clip_w(d, state.get("footer_hint", "No active sandbox."), sans(10), CW - 200), sans(10), FAINT)
    txt(d, (x2 - 18, y2 - 28), "SSE \u00b7 live", mono(10), FAINT, anchor="ra")


# --------------------------------------------------------------------------
# right column: sandbox + drills
# --------------------------------------------------------------------------

DRILLS = [
    ("rm_rf", "rm -rf"),
    ("infinite_loop", "infinite loop"),
    ("fork_bomb", "fork bomb"),
    ("secret_probe", "secret probe"),
    ("network_probe", "network probe"),
    ("host_write", "host write"),
    ("readonly_canary", "read-only canary"),
    ("cross_task", "cross-task"),
]


def draw_sandbox_panel(d, state, focus=0.0):
    x, y, x2, y2 = RIGHT_BOX
    rr(d, RIGHT_BOX, radius=14, fill=PANEL, outline=mix(LINE, ACID, focus * 0.75), width=1)
    txt(d, (x + 18, y + 16), "Sandbox", sans(14, True), WHITE)
    badge(d, 0, y + 14, state.get("sandbox_mode", "docker"), CYAN, right=x2 - 18)
    txt(d, (x + 18, y + 44), "CONFIGURED LIMITS \u00b7 LIVE STATS BELOW", sans(9, True), FAINT)

    ix = x + 18
    iw = (x2 - 18) - ix
    cw = (iw - 10) // 2
    gy = y + 64
    lim = state.get("limits", {})
    cells = [
        ("Network", lim.get("network", "\u2014"), ACID),
        ("vCPU", str(lim.get("cpus", "\u2014")), TEXT),
        ("Memory", f"{lim.get('memory_mb', '-')} MB", TEXT),
        ("PIDs", str(lim.get("pids", "\u2014")), TEXT),
    ]
    for i, (k, v, c) in enumerate(cells):
        metric(d, ix + (i % 2) * (cw + 10), gy + (i // 2) * 48, cw, 40, k, v, c)
    metric(d, ix, gy + 96, iw, 40, "Workspace tmpfs \u00b7 disk-capped", f"{lim.get('workspace_mb', 64)} MB", CYAN)

    by = gy + 148
    rr(d, [ix, by, x2 - 18, by + 92], radius=10, fill=CODE_BG, outline=LINE, width=1)
    txt(d, (ix + 12, by + 8), "CONTAINER", sans(9, True), FAINT)
    txt(d, (ix + 12, by + 26), clip_w(d, state.get("container_id", "\u2014"), mono(11), iw - 24), mono(11), TEXT)
    txt(d, (ix + 12, by + 46), "image " + state.get("image_id", ""), mono(10), MUTED)
    txt(d, (ix + 12, by + 66), "key " + state.get("key_fp", "\u2014"), mono(10), ACID)

    sb = by + 104
    bar(d, ix, sb, iw, "CPU \u00b7 live", f"{state.get('cpu', 0.0):.1f}%", state.get("cpu", 0.0) / 100.0, ACID)
    mx = float(lim.get("memory_mb", 512) or 512)
    bar(d, ix, sb + 46, iw, "Memory \u00b7 live", f"{state.get('mem', 0.0):.1f} / {int(mx)} MB", state.get("mem", 0.0) / mx, CYAN)

    fb = sb + 88
    button(d, ix, fb, (iw - 10) // 2, 36, "Evidence JSON", pressed=state.get("evidence_pressed", False))
    button(d, ix + (iw - 10) // 2 + 10, fb, (iw - 10) // 2, 36, "Stats")


def draw_drill_panel(d, state):
    x, y, x2, y2 = DRILL_BOX
    rr(d, DRILL_BOX, radius=14, fill=PANEL, outline=LINE, width=1)
    txt(d, (x + 18, y + 16), "Containment drills", sans(14, True), WHITE)
    txt(d, (x2 - 18, y + 19), "LIVE PROOF", sans(9, True), FAINT, anchor="ra")
    txt(d, (x + 18, y + 44), "Run hostile commands against a disposable sandbox.", sans(10), DIM)
    txt(d, (x + 18, y + 62), "A pass means the container-scoped blast radius held.", sans(10), DIM)

    ix = x + 18
    iw = (x2 - 18) - ix
    cw = (iw - 10) // 2
    gy = y + 88
    active = state.get("active_drill")
    for i, (key, label) in enumerate(DRILLS):
        bx = ix + (i % 2) * (cw + 10)
        by = gy + (i // 2) * 42
        button(d, bx, by, cw, 34, label, tone="drill", pressed=(key == active))

    ry = gy + 176
    for res in state.get("probe_results", [])[:2]:
        h = draw_probe_result(d, ix, ry, iw, res)
        ry += h + 10
        if ry > y2 - 40:
            break
    if state.get("probe_running"):
        rr(d, [ix, ry, x2 - 18, ry + 30], radius=8, fill=(22, 32, 20), outline=(64, 86, 48), width=1)
        d.ellipse([ix + 12, ry + 12, ix + 20, ry + 20], fill=ACID)
        txt(d, (ix + 28, ry + 7), f"Running {state['probe_running']} against a fresh sandbox\u2026", sans(10), TEXT)


def draw_probe_result(d, x, y, w, res):
    passed = res["passed"]
    colour = ACID if passed else DANGER
    lines = wrap(d, res["detail"], sans(11), w - 28)
    h = 34 + TEXT_LH * len(lines) + 22 + 20
    if res.get("output"):
        h += CODE_LH * len(res["output"].split("\n")) + 14
    rr(d, [x, y, x + w, y + h], radius=9, fill=mix(INK, (18, 30, 16) if passed else (36, 16, 16), 1.0),
       outline=mix(LINE, colour, 0.6), width=1)
    txt(d, (x + 14, y + 8), "CONTAINED" if passed else "FAILED", sans(12, True), colour)
    txt(d, (x + w - 14, y + 9), f"{res['duration_ms']} ms", mono(10), MUTED, anchor="ra")
    cy = y + 34
    for line in lines:
        txt(d, (x + 14, cy), line, sans(11), TEXT)
        cy += TEXT_LH
    txt(d, (x + 14, cy + 2), clip_w(d, res["ids"], mono(9), w - 28), mono(9), FAINT)
    cy += 20
    txt(d, (x + 14, cy + 2), "\u2713 host canary intact", sans(9), ACID)
    cy += 22
    if res.get("output"):
        out = res["output"].split("\n")
        bh = CODE_LH * len(out) + 12
        rr(d, [x + 12, cy, x + w - 12, cy + bh], radius=7, fill=CODE_BG, outline=LINE, width=1)
        for i, line in enumerate(out):
            txt(d, (x + 20, cy + 6 + i * CODE_LH), clip_w(d, line, mono(10), w - 44), mono(10), DANGER if not passed else MUTED)
    return h


# --------------------------------------------------------------------------
# overlays: terminal
# --------------------------------------------------------------------------

TERM_BG = (10, 14, 18)
TERM_BAR = (24, 31, 39)
PROMPT = "root@cage-vm:~/cage#"


def term_lines(lines, t, t0, cps=34):
    out = []
    cur = t0
    for line in lines:
        text = line["s"]
        dur = len(text) / cps
        if t < cur:
            break
        local = t - cur
        if local >= dur:
            out.append((text, line.get("k", "out"), False))
        else:
            out.append((text[: int(local * cps)], line.get("k", "out"), True))
            break
        cur += dur + line.get("p", 0.28)
    return out


def draw_terminal(d, box, title, lines, t, t0=0.0, cps=34, font_size=15):
    x, y, w, h = box
    rr(d, [x, y, x + w, y + h], radius=13, fill=TERM_BG, outline=(48, 60, 72), width=1)
    rr(d, [x, y, x + w, y + 42], radius=13, fill=TERM_BAR)
    d.rectangle([x, y + 28, x + w, y + 42], fill=TERM_BAR)
    for i, c in enumerate(((255, 95, 86), (255, 189, 46), (39, 201, 63))):
        d.ellipse([x + 18 + i * 20, y + 15, x + 31 + i * 20, y + 28], fill=c)
    txt(d, (x + w // 2, y + 21), title, font(F_MONO, 12), MUTED, anchor="mm")
    d.line([x, y + 42, x + w, y + 42], fill=(42, 52, 64), width=1)

    f = font(F_MONO, font_size)
    lh = int(font_size * 1.55)
    pw = tw(d, PROMPT, f) + 9
    cy = y + 56
    for text, style, is_cursor in term_lines(lines, t, t0, cps):
        if cy > y + h - 10:
            break
        if style == "cmd":
            txt(d, (x + 20, cy), PROMPT, f, ACID)
            txt(d, (x + 20 + pw, cy), text, f, WHITE)
            if is_cursor:
                cxx = x + 20 + pw + tw(d, text, f)
                d.rectangle([cxx, cy + 2, cxx + 10, cy + int(font_size * 1.1)], fill=ACID)
        else:
            colour = {"out": TEXT, "dim": DIM, "ok": ACID, "err": DANGER, "cy": CYAN}.get(style, TEXT)
            txt(d, (x + 20, cy), text, f, colour)
            if is_cursor:
                cxx = x + 20 + tw(d, text, f)
                d.rectangle([cxx, cy + 2, cxx + 10, cy + int(font_size * 1.1)], fill=ACID)
        cy += lh


# --------------------------------------------------------------------------
# overlays: JSON viewer
# --------------------------------------------------------------------------


def draw_json(d, box, title, rows, font_size=15, highlight=()):
    x, y, w, h = box
    rr(d, [x, y, x + w, y + h], radius=13, fill=(10, 14, 18), outline=(48, 60, 72), width=1)
    rr(d, [x, y, x + w, y + 44], radius=13, fill=TERM_BAR)
    d.rectangle([x, y + 30, x + w, y + 44], fill=TERM_BAR)
    txt(d, (x + 20, y + 12), title, font(F_MONO, 13), MUTED)
    txt(d, (x + w - 20, y + 12), "evidence.json \u00b7 sealed at completion", font(F_MONO, 13), ACID, anchor="ra")
    d.line([x, y + 44, x + w, y + 44], fill=(42, 52, 64), width=1)

    f = font(F_MONO, font_size)
    lh = int(font_size * 1.6)
    cy = y + 58
    for idx, (text, colour) in enumerate(rows):
        if cy > y + h - 12:
            break
        if idx in highlight:
            rr(d, [x + 12, cy - 4, x + w - 12, cy + lh - 6], radius=6, fill=(30, 50, 24))
            txt(d, (x + 22, cy), text, f, ACID)
        else:
            txt(d, (x + 22, cy), text, f, colour)
        cy += lh


# --------------------------------------------------------------------------
# overlays: captions / lower third
# --------------------------------------------------------------------------


def draw_caption(d, lines):
    if not lines:
        return
    f = sans(30, True)
    lh = 40
    pad_x, pad_y = 34, 16
    bw = max(tw(d, s, f) for s in lines) + pad_x * 2
    bh = lh * len(lines) + pad_y * 2 - 6
    bx = (W - bw) // 2
    by = 1006 - bh
    rr(d, [bx, by, bx + bw, by + bh], radius=14, fill=(4, 6, 8))
    rr(d, [bx, by, bx + bw, by + bh], radius=14, outline=(44, 56, 70), width=1)
    for i, s in enumerate(lines):
        txt(d, (W // 2, by + pad_y - 5 + i * lh), s, f, WHITE, anchor="ma")


def draw_lower_third(d, label, alpha=1.0):
    if not label:
        return
    f = sans(17, True)
    pad_x, pad_y = 22, 13
    bw = tw(d, label, f) + pad_x * 2 + 14
    bh = 52
    bx, by = 40, 898 - bh
    rr(d, [bx, by, bx + bw, by + bh], radius=11, fill=(6, 9, 12))
    rr(d, [bx, by, bx + bw, by + bh], radius=11, outline=mix(LINE, ACID, 0.45 * alpha), width=1)
    d.rounded_rectangle([bx, by + 2, bx + 5, by + bh - 2], radius=3, fill=dim(ACID, alpha))
    txt(d, (bx + pad_x + 10, by + pad_y - 2), label, f, dim(ACID, alpha))
