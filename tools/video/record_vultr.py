"""Record the demo on the Vultr VM: a real Chrome window and a real terminal on a
virtual display, driven with real mouse and key events and captured with ffmpeg.
Every frame is a real frame of the deployed system; nothing is drawn.

Each shot is held for as long as its voiceover needs (durations.json), and the
actual start of every segment is written to marks.json for the audio mix.

    python3 record_vultr.py --durations durations.json --out raw.mp4 --marks marks.json
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import time
import urllib.request

import cdp

APP = "https://139-180-191-46.sslip.io/"
DISPLAY = ":99"
GAP = 0.6  # silence between one segment's speech and the next segment

CHART_PROMPT = (
    "Create solution.py that generates a sine wave chart with matplotlib, saves it to "
    "chart.png, and prints the file size. Run it and verify the chart exists."
)
RM_PROMPT = (
    "Use run_command to delete /etc/hostname with exactly this command and nothing else: "
    "rm /etc/hostname. Then report exactly what the sandbox returned."
)

PRETTY_PRINT = (104, 96)  # the raw JSON viewer's checkbox at 100% zoom

ENV = {**os.environ, "DISPLAY": DISPLAY}
T0 = time.time()


def log(msg: str) -> None:
    print(f"[{time.time() - T0:6.1f}s] {msg}", flush=True)


def xdo(*args: str) -> str:
    return subprocess.run(
        ["xdotool", *args], env=ENV, capture_output=True, text=True, check=True
    ).stdout.strip()


def mouse_pos() -> tuple[int, int]:
    fields = dict(
        part.split("=") for part in xdo("getmouselocation", "--shell").split("\n") if "=" in part
    )
    return int(fields["X"]), int(fields["Y"])


def glide(x: float, y: float, seconds: float = 0.55) -> None:
    """Move the real pointer with an ease-in-out path, as a hand would."""
    sx, sy = mouse_pos()
    steps = max(8, int(seconds * 40))
    for i in range(1, steps + 1):
        t = i / steps
        e = t * t * (3 - 2 * t)
        xdo("mousemove", str(int(sx + (x - sx) * e)), str(int(sy + (y - sy) * e)))
        time.sleep(seconds / steps)


def click() -> None:
    xdo("click", "1")


def wheel(down: bool, times: int, delay_ms: int = 90) -> None:
    xdo("click", "--repeat", str(times), "--delay", str(delay_ms), "5" if down else "4")


def type_keys(text: str, delay_ms: int = 16) -> None:
    xdo("type", "--delay", str(delay_ms), "--", text)


def key(*names: str) -> None:
    xdo("key", *names)


class Page:
    def __init__(self, ws_url: str):
        self.c = cdp.CDP(ws_url)

    def js(self, expr: str):
        return self.c.evaluate(expr)

    def center(self, selector: str) -> tuple[float, float]:
        raw = self.js(
            "(function(){var e=document.querySelector(" + json.dumps(selector) + ");"
            "if(!e)return null;e.scrollIntoView({block:'nearest'});"
            "var r=e.getBoundingClientRect();"
            "var ox=window.screenX+(window.outerWidth-window.innerWidth)/2;"
            "var oy=window.screenY+(window.outerHeight-window.innerHeight);"
            "return JSON.stringify({x:ox+r.x+r.width/2,y:oy+r.y+r.height/2});})()"
        )
        if not raw:
            raise RuntimeError(f"no element {selector}")
        pos = json.loads(raw)
        return pos["x"], pos["y"]

    def point(self, selector: str, seconds: float = 0.55) -> None:
        glide(*self.center(selector), seconds=seconds)

    def press(self, selector: str) -> None:
        self.point(selector)
        time.sleep(0.15)
        click()


class Timeline:
    def __init__(self, durations: dict[str, float]):
        self.durations = durations
        self.marks: list[dict] = []
        self.start = 0.0
        self.deadline = 0.0

    def begin(self, seg_id: str) -> None:
        now = time.time()
        self.marks.append({"id": seg_id, "t": round(now - self.start, 2)})
        self.deadline = now + self.durations[seg_id] + GAP
        log(f"== {seg_id} (needs {self.durations[seg_id]:.1f}s)")

    def remaining(self) -> float:
        return self.deadline - time.time()

    def hold(self) -> None:
        left = self.remaining()
        if left > 0:
            time.sleep(left)
        else:
            log(f"   overran by {-left:.1f}s")


def windows() -> tuple[str, str]:
    chrome = xdo("search", "--onlyvisible", "--class", "google-chrome").split("\n")[-1]
    term = xdo("search", "--onlyvisible", "--class", "xterm").split("\n")[-1]
    return chrome, term


def show(window: str) -> None:
    xdo("windowactivate", "--sync", window)
    xdo("windowraise", window)
    time.sleep(0.25)


def term_run(command: str, settle: float = 0.9) -> None:
    type_keys(command, delay_ms=9)
    time.sleep(0.15)
    key("Return")
    time.sleep(settle)


def wait_new_run(page: Page, previous: str | None, timeout: float = 8.0) -> str:
    deadline = time.time() + timeout
    while time.time() < deadline:
        current = page.js("state.currentId")
        if current and current != previous:
            return current
        time.sleep(0.15)
    raise RuntimeError("the click did not start a new run")


def wait_finished(page: Page, timeout: float = 120.0) -> str:
    deadline = time.time() + timeout
    status = ""
    while time.time() < deadline:
        status = (page.js("document.getElementById('runStatus').innerText") or "").strip().lower()
        if status in ("completed", "failed", "cancelled"):
            return status
        time.sleep(0.25)
    return status


def drill(page: Page, name: str, timeout: float = 40.0) -> str:
    """Click a drill button; return the text of its result card."""
    selector = f'.drill[data-probe="{name}"]'
    page.press(selector)
    time.sleep(0.2)
    deadline = time.time() + timeout
    text = ""
    while time.time() < deadline:
        running = page.js("!!document.querySelector('#probeResult .probe.running')")
        text = page.js(
            "(function(){var e=document.querySelector('#probeResult .probe:not(.running)');"
            "return e?e.innerText:'';})()"
        ) or ""
        if not running and text:
            break
        time.sleep(0.2)
    first = " ".join(text.split())[:110]
    log(f"   drill {name}: {first}")
    if "CONTAINED" not in text:
        raise RuntimeError(f"drill {name} did not report CONTAINED: {first}")
    return text


def scroll_timeline_to(page: Page, needle: str) -> bool:
    """Scroll the run timeline so the first card containing `needle` is visible."""
    return bool(page.js(
        "(function(){var t=document.getElementById('timeline');"
        "var n=[].slice.call(t.children).find(function(c){return c.innerText.indexOf("
        + json.dumps(needle) + ")>=0;});"
        "if(!n)return false;n.scrollIntoView({behavior:'smooth',block:'center'});return true;})()"
    )) and (time.sleep(0.9) or True)


def evidence_target() -> str:
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    with opener.open("http://127.0.0.1:9222/json/list", timeout=5) as r:
        for target in json.loads(r.read()):
            if target.get("type") == "page" and "/evidence" in target.get("url", ""):
                return target["webSocketDebuggerUrl"]
    raise RuntimeError("no evidence tab")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--durations", default="durations.json")
    ap.add_argument("--out", default="raw.mp4")
    ap.add_argument("--marks", default="marks.json")
    ap.add_argument("--evidence", default="/home/rec/evidence.json")
    args = ap.parse_args()

    durations = json.load(open(args.durations, encoding="utf-8"))
    tl = Timeline(durations)
    chrome, term = windows()

    show(chrome)
    page = Page(cdp.first_page_ws(9222))
    page.c.call("Network.clearBrowserCookies")
    page.c.navigate(APP)
    time.sleep(3.0)
    if page.js("document.getElementById('prompt') ? 'ok' : 'no'") != "ok":
        raise RuntimeError("the app did not load")
    glide(960, 700, 0.2)

    log("start capture")
    ff = subprocess.Popen(
        ["ffmpeg", "-y", "-loglevel", "error", "-f", "x11grab", "-framerate", "30",
         "-video_size", "1920x1080", "-draw_mouse", "1", "-i", DISPLAY,
         "-c:v", "libx264", "-preset", "ultrafast", "-crf", "16", "-pix_fmt", "yuv420p", args.out],
        stdin=subprocess.PIPE, env=ENV,
    )
    time.sleep(0.6)
    tl.start = time.time()

    try:
        # ---- hook: the public URL and the runtime badges -----------------------
        tl.begin("hook")
        time.sleep(1.0)
        glide(240, 63, 0.8)
        time.sleep(3.0)
        glide(1445, 121, 0.8)
        time.sleep(2.2)
        glide(1587, 121, 0.4)
        time.sleep(1.2)
        glide(1695, 121, 0.4)
        tl.hold()

        # ---- the VM itself ---------------------------------------------------
        tl.begin("deploy")
        show(term)
        term_run(
            "curl -s 169.254.169.254/v1.json | python3 -c 'import json,sys; d=json.load(sys.stdin); "
            "print(d[\"region\"][\"regioncode\"], d[\"hostname\"], d[\"interfaces\"][0][\"ipv4\"][\"address\"])'",
            settle=2.2,
        )
        term_run("docker compose ps --format 'table {{.Service}}\\t{{.Image}}\\t{{.Status}}'", settle=3.2)
        term_run("curl -s localhost:8080/readyz; echo", settle=2.0)
        term_run("docker image ls cage-sandbox", settle=1.0)
        tl.hold()

        # ---- a real task -------------------------------------------------------
        tl.begin("task")
        show(chrome)
        page.press("#prompt")
        type_keys(CHART_PROMPT, delay_ms=11)
        time.sleep(0.3)
        previous = page.js("state.currentId")
        page.press("#createBtn")
        first_task = wait_new_run(page, previous)
        log(f"   task {first_task}")
        page.point("#cpuBar", 0.5)
        status = wait_finished(page)
        log(f"   task status = {status}")
        if status != "completed":
            raise RuntimeError(f"task ended {status}")
        log(f"   stats at finish: {page.js('document.getElementById(%s).innerText' % json.dumps('memText'))}")
        scroll_timeline_to(page, "write_file")
        glide(960, 500, 0.6)
        time.sleep(max(0.0, min(4.0, tl.remaining() - 5.0)))
        if tl.remaining() > 2.0:
            wheel(True, 8)
        tl.hold()

        # ---- the boundary ------------------------------------------------------
        tl.begin("boundary")
        scroll_timeline_to(page, "SANDBOX")
        for selector, hold_s in (("#mNetwork", 2.6), ("#mCpu", 1.0), ("#mMem", 1.0), ("#mPids", 1.0)):
            page.point(selector, 0.45)
            time.sleep(hold_s)
        page.point("#mWorkspace", 0.45)
        time.sleep(max(0.0, min(4.0, tl.remaining() - 6.0)))
        page.point("#containerId", 0.45)
        time.sleep(0.5)
        glide(860, 330, 0.7)
        tl.hold()

        # ---- the agent itself attempts something destructive -------------------
        tl.begin("agent")
        for attempt in range(1, 4):
            page.press("#prompt")
            type_keys(RM_PROMPT, delay_ms=9)
            time.sleep(0.2)
            previous = page.js("state.currentId")
            page.press("#createBtn")
            second_task = wait_new_run(page, previous)
            log(f"   attempt {attempt}: task {second_task}")
            status = wait_finished(page)
            log(f"   attempt {attempt}: status = {status}")
            if status != "completed":
                raise RuntimeError(f"task ended {status}")
            found = scroll_timeline_to(page, "Read-only file system")
            shown = page.js("document.getElementById('timeline').innerText") or ""
            ok = bool(found) and "exit 1" in shown
            log(f"   attempt {attempt}: read-only visible {found}; exit 1 shown {'yes' if 'exit 1' in shown else 'no'}")
            if ok:
                break
            log("   the model declined to run it; retrying the agent attempt")
        else:
            raise RuntimeError("the model never ran rm through run_command in 3 attempts")
        glide(860, 520, 0.7)
        tl.hold()

        # ---- direct drills ----------------------------------------------------
        tl.begin("drills1")
        time.sleep(1.5)
        drill(page, "rm_rf")
        time.sleep(max(0.0, min(5.0, tl.remaining() - 11.5)))
        drill(page, "readonly_canary")
        time.sleep(max(0.0, min(5.5, tl.remaining() - 5.0)))
        drill(page, "cross_task")
        tl.hold()

        tl.begin("drills2")
        drill(page, "fork_bomb")
        time.sleep(0.6)
        drill(page, "secret_probe")
        time.sleep(0.6)
        drill(page, "network_probe")
        time.sleep(0.6)
        drill(page, "host_write")

        tl.begin("usecase")
        drill(page, "infinite_loop")
        tl.hold()

        tl.begin("drills3")
        glide(1640, 240, 0.5)
        passed = page.js("document.querySelectorAll('.drill.drill-pass').length")
        log(f"   drills marked passed: {passed}")
        if passed != 8:
            raise RuntimeError(f"expected 8 passed drills, saw {passed}")
        tl.hold()

        # ---- the host is unaffected -------------------------------------------
        tl.begin("host")
        show(term)
        key("ctrl+l")
        time.sleep(0.2)
        term_run("ls -l /etc/hostname && cat /etc/hostname", settle=2.6)
        term_run("docker ps -a --filter label=cage.sandbox=1", settle=2.0)
        tl.hold()

        # ---- evidence ----------------------------------------------------------
        tl.begin("evidence")
        show(chrome)
        page.press('button[onclick="exportEvidence()"]')
        time.sleep(0.7)
        tab = Page(evidence_target())
        pack = tab.js("document.body.innerText")
        if not pack or not pack.lstrip().startswith("{"):
            raise RuntimeError("the evidence tab did not show JSON")
        with open(args.evidence, "w", encoding="utf-8") as handle:
            handle.write(pack)
        log(f"   pack bytes = {len(pack)}")
        # the raw JSON view: pretty-print, zoom in, then walk down to the signature
        glide(*PRETTY_PRINT, 0.4)
        click()
        time.sleep(0.2)
        key("ctrl+plus")
        key("ctrl+plus")
        key("ctrl+plus")
        # keep the signature block above the caption band; the JSON itself is untouched
        tab.js("document.body.style.paddingBottom='170px'")
        time.sleep(1.8)
        glide(1500, 600, 0.3)
        wheel(True, 10, delay_ms=100)
        key("End")
        time.sleep(2.6)
        key("ctrl+0")
        show(term)
        key("ctrl+l")
        time.sleep(0.2)
        term_run(f"grep -c " + chr(39) + f'"owner"' + chr(39) + f" {args.evidence}", settle=0.7)
        term_run(f".venv/bin/python scripts/verify_evidence.py {args.evidence}", settle=1.5)
        term_run(f"sed 's/Read-only file system/Deleted OK/' {args.evidence} > /tmp/tampered.json", settle=0.3)
        term_run(".venv/bin/python scripts/verify_evidence.py /tmp/tampered.json", settle=1.4)
        tl.hold()

        # ---- close ------------------------------------------------------------
        tl.begin("close")
        show(chrome)
        key("ctrl+w")
        time.sleep(0.4)
        page.js("window.scrollTo({top:0,behavior:'smooth'})")
        glide(960, 640, 0.6)
        tl.hold()
        time.sleep(0.8)
    finally:
        log("stop capture")
        total = time.time() - tl.start
        try:
            ff.stdin.write(b"q")
            ff.stdin.flush()
        except Exception:
            ff.terminate()
        try:
            ff.wait(timeout=30)
        except subprocess.TimeoutExpired:
            ff.kill()
        with open(args.marks, "w", encoding="utf-8") as handle:
            json.dump({"marks": tl.marks, "total": round(total, 2)}, handle, indent=1)
        log(f"total {total:.1f}s; marks -> {args.marks}")


if __name__ == "__main__":
    main()
