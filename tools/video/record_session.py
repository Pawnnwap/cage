"""Record a REAL Cage session: real Chrome, real control plane, real model.

Drives the live app over CDP while ffmpeg captures the Windows desktop with
gdigrab (1920x1080, 30 fps). Every frame is a real frame; nothing is drawn.

    python tools/video/record_session.py [--out dist/raw_desktop.mp4]
"""

from __future__ import annotations

import argparse
import ctypes
import ctypes.wintypes as wt
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import cdp  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
DIST = ROOT / "dist"
APP = "http://127.0.0.1:8080/"

PROMPT = (
    "Create solution.py that generates a sine wave chart with matplotlib, "
    "saves it to chart.png, and prints the file size. Run it and verify "
    "the chart exists."
)

T0 = time.time()


def log(msg: str) -> None:
    print(f"[{time.time() - T0:6.1f}s] {msg}", flush=True)


def hold(seconds: float, label: str = "") -> None:
    if label:
        log(label)
    time.sleep(seconds)


# --------------------------------------------------------------------------
# window helpers (stdlib ctypes only)
# --------------------------------------------------------------------------

user32 = ctypes.WinDLL("user32", use_last_error=True)
SW_MAXIMIZE, SW_MINIMIZE = 3, 6
EnumWindowsProc = ctypes.WINFUNCTYPE(ctypes.c_bool, wt.HWND, wt.LPARAM)


def _find_windows(needle: str):
    found = []

    @EnumWindowsProc
    def _cb(hwnd, _lparam):
        if not user32.IsWindowVisible(hwnd):
            return True
        length = user32.GetWindowTextLengthW(hwnd)
        if length:
            buf = ctypes.create_unicode_buffer(length + 1)
            user32.GetWindowTextW(hwnd, buf, length + 1)
            if needle.lower() in buf.value.lower():
                found.append(hwnd)
        return True

    user32.EnumWindows(_cb, 0)
    return found


def maximize(title_part: str) -> bool:
    for hwnd in _find_windows(title_part):
        user32.ShowWindow(hwnd, SW_MAXIMIZE)
        user32.SetForegroundWindow(hwnd)
        return True
    return False


def place(title_part: str, x: int, y: int, w: int, h: int) -> bool:
    """Move/resize a top-level window to an exact rect (more reliable than MAXIMIZE)."""
    SWP_SHOWWINDOW = 0x0040
    ok = False
    for hwnd in _find_windows(title_part):
        user32.SetWindowPos(hwnd, 0, x, y, w, h, SWP_SHOWWINDOW)
        user32.SetForegroundWindow(hwnd)
        ok = True
    return ok


def foreground_title() -> str:
    hwnd = user32.GetForegroundWindow()
    n = user32.GetWindowTextLengthW(hwnd)
    buf = ctypes.create_unicode_buffer(n + 1)
    user32.GetWindowTextW(hwnd, buf, n + 1)
    return buf.value


def ensure_front(title_part: str) -> str:
    """Maximise + focus the browser and refuse to record if it is not in front."""
    for hwnd in _find_windows(title_part):
        user32.ShowWindow(hwnd, SW_MAXIMIZE)
        user32.SetForegroundWindow(hwnd)
        time.sleep(1.2)
        title = foreground_title()
        if title_part.lower() in title.lower():
            return title
    raise RuntimeError(
        f"cannot bring '{title_part}' to the foreground; foreground is '{foreground_title()}'"
    )


def minimize(title_part: str) -> bool:
    ok = False
    for hwnd in _find_windows(title_part):
        user32.ShowWindow(hwnd, SW_MINIMIZE)
        ok = True
    return ok


# --------------------------------------------------------------------------


def wait_status(c: cdp.CDP, want: str, timeout: float = 200.0) -> str:
    deadline = time.time() + timeout
    status = ""
    while time.time() < deadline:
        status = c.evaluate("document.getElementById('runStatus').innerText.trim()")
        if status.lower() == want.lower():
            return status
        time.sleep(1.0)
    return status


def js_click(c: cdp.CDP, selector: str) -> None:
    """A real mouse click at the element's position."""
    import json

    rect = c.evaluate(
        "(function(){var e=document.querySelector(" + repr(selector) + ");"
        "if(!e)return null;var r=e.getBoundingClientRect();"
        "return JSON.stringify({x:r.x+r.width/2,y:r.y+r.height/2});})()"
    )
    if not rect:
        raise RuntimeError(f"no element {selector}")
    pos = json.loads(rect)
    c.click(pos["x"], pos["y"])


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=str(DIST / "raw_desktop.mp4"))
    ap.add_argument("--cdp-port", type=int, default=9222)
    args = ap.parse_args()
    DIST.mkdir(parents=True, exist_ok=True)

    log("connect to chrome")
    c = cdp.CDP(cdp.first_page_ws(args.cdp_port, timeout=30))
    title = ensure_front("Cage — containment")
    log(f"foreground window: {title}")

    log("start gdigrab capture")
    ff = subprocess.Popen(
        [
            "ffmpeg", "-y", "-f", "gdigrab", "-framerate", "30", "-draw_mouse", "1",
            "-i", "desktop", "-c:v", "libx264", "-preset", "veryfast", "-crf", "18",
            "-pix_fmt", "yuv420p", args.out,
        ],
        stdin=subprocess.PIPE,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )

    try:
        hold(2.0, "recorder warm-up")
        c.navigate(APP)
        hold(7.0, "load the app")
        hold(8.0, "HOLD landing view")

        js_click(c, "#prompt")
        time.sleep(0.6)
        c.evaluate(
            "var p=document.getElementById('prompt');"
            "p.scrollIntoView({block:'center'});p.focus();"
        )
        log("type the task prompt")
        for i in range(0, len(PROMPT), 6):
            c.type_text(PROMPT[i : i + 6])
            time.sleep(0.13)
        val = c.evaluate("document.getElementById('prompt').value")
        if len(val) < 20:
            log("typing did not land; refocus and retype")
            c.evaluate("document.getElementById('prompt').focus()")
            for i in range(0, len(PROMPT), 6):
                c.type_text(PROMPT[i : i + 6])
                time.sleep(0.13)
            val = c.evaluate("document.getElementById('prompt').value")
        if not val:
            log("fallback: set the textarea value directly")
            c.evaluate("document.getElementById('prompt').value = " + repr(PROMPT))
            val = c.evaluate("document.getElementById('prompt').value")
        hold(1.5, "prompt typed")
        log(f"typed ({len(val)} chars): " + val[:70])

        prev_id = c.evaluate("state.currentId")
        c.evaluate("document.getElementById('createBtn').focus()")
        js_click(c, "#createBtn")

        # the click must produce a NEW task; if the synthetic click did not
        # register, fall back to the same handler the button calls
        deadline = time.time() + 4.0
        new_id = prev_id
        while time.time() < deadline:
            new_id = c.evaluate("state.currentId")
            if new_id and new_id != prev_id:
                break
            time.sleep(0.4)
        if not new_id or new_id == prev_id:
            log("click did not start a task; invoking createTask() directly")
            c.evaluate("createTask()")
            deadline = time.time() + 30.0
            while time.time() < deadline:
                new_id = c.evaluate("state.currentId")
                if new_id and new_id != prev_id:
                    break
                time.sleep(0.5)
        hold(1.0, "run started")
        log(f"new task id = {new_id}")
        status = wait_status(c, "completed", timeout=180.0)
        log(f"run status = {status}")
        hold(8.0, "HOLD finished timeline")
        hold(8.0, "HOLD sandbox panel")

        tid = c.evaluate("state.currentId")
        log(f"task id = {tid}")
        if tid:
            c.navigate(f"{APP}api/tasks/{tid}/evidence")
            hold(7.0, "load sealed evidence pack")
            # keep the exact bytes on screen so the verifier proves THIS pack
            pack_text = c.evaluate("document.body.innerText")
            if pack_text and pack_text.strip().startswith("{"):
                (DIST / "live_evidence.json").write_text(pack_text, encoding="utf-8")
                log(f"captured pack ({len(pack_text)} chars)")
            hold(24.0, "HOLD evidence JSON")

        c.navigate(f"{APP}api/config")
        hold(6.0, "load runtime config")
        hold(12.0, "HOLD /api/config")

        # ---- real terminal proof -------------------------------------
        log("switch to a real command prompt")
        minimize("Cage")
        time.sleep(1.0)
        cmd = (
            f'title CAGE-PROOF && cd /d {ROOT} && echo. && '
            "echo == control plane readiness == && "
            'curl -s --noproxy "*" http://127.0.0.1:8080/readyz && echo. && '
            "echo == verify the sealed evidence pack == && "
            ".venv\\Scripts\\python.exe scripts\\verify_evidence.py dist\\live_evidence.json"
        )
        subprocess.Popen(
            ["cmd.exe", "/k", cmd],
            creationflags=subprocess.CREATE_NEW_CONSOLE,
        )
        time.sleep(3.5)
        if not place("CAGE-PROOF", 0, 0, 1920, 1000):
            maximize("CAGE-PROOF")
        hold(26.0, "HOLD real terminal output")

    finally:
        log("stop recorder")
        try:
            ff.stdin.write(b"q")
            ff.stdin.flush()
        except Exception:
            ff.terminate()
        try:
            ff.wait(timeout=20)
        except subprocess.TimeoutExpired:
            ff.kill()
        c.close()
    log(f"saved -> {args.out}")


if __name__ == "__main__":
    main()
