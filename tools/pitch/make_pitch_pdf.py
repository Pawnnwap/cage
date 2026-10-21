"""Generate the 16:9 project pitch PDF for the lablab submission.

Usage:
    .venv/Scripts/python.exe tools/pitch/make_pitch_pdf.py
"""

from __future__ import annotations

from pathlib import Path

from fpdf import FPDF

W, H = 960, 540
BG = (11, 15, 19)
PANEL = (17, 24, 31)
LINE = (30, 42, 52)
TEXT = (222, 231, 240)
MUTED = (140, 156, 172)
ACCENT = (184, 242, 91)
CYAN = (99, 230, 255)
RED = (255, 107, 107)

REPO = "github.com/Pawnnwap/cage"


class Slide(FPDF):
    def __init__(self) -> None:
        super().__init__(orientation="L", unit="pt", format=(W, H))
        self.set_auto_page_break(auto=False)
        self.set_margins(0, 0, 0)
        self.set_title("Cage - container-scoped blast radius zero")

    def slide(self, kicker: str, title: str) -> None:
        self.add_page()
        self.set_fill_color(*BG)
        self.rect(0, 0, W, H, style="F")
        self.set_fill_color(*ACCENT)
        self.rect(56, 62, 4, 18, style="F")
        self.set_font("Helvetica", "B", 11)
        self.set_text_color(*ACCENT)
        self.cell(0, 12, kicker.upper(), new_x="LMARGIN", new_y="NEXT", align="L")
        self.set_xy(56, 86)
        self.set_font("Helvetica", "B", 30)
        self.set_text_color(*TEXT)
        self.multi_cell(W - 112, 36, title)
        self.set_draw_color(*LINE)
        self.set_line_width(1)
        self.line(56, H - 74, W - 56, H - 74)
        self.set_xy(56, H - 62)
        self.set_font("Helvetica", "", 9)
        self.set_text_color(*MUTED)
        self.cell(0, 12, f"Cage  |  containment-first agent control plane  |  {REPO}")

    def bullets(self, items: list[tuple[str, str]], top: int = 186, gap: int = 34) -> None:
        self.set_y(top)
        for head, body in items:
            self.set_x(56)
            self.set_font("Helvetica", "B", 13)
            self.set_text_color(*ACCENT)
            self.cell(300, 16, head, align="L")
            self.set_x(56)
            self.set_font("Helvetica", "", 11.5)
            self.set_text_color(*TEXT)
            self.multi_cell(W - 112, 15, body)
            self.set_y(self.get_y() + gap - 24)

    def panel(self, x: int, y: int, w: int, h: int, heading: str, lines: list[str],
              accent: tuple[int, int, int] = CYAN) -> None:
        self.set_fill_color(*PANEL)
        self.set_draw_color(*LINE)
        self.rect(x, y, w, h, style="DF")
        self.set_xy(x + 18, y + 16)
        self.set_font("Helvetica", "B", 12)
        self.set_text_color(*accent)
        self.cell(w - 36, 15, heading, align="L")
        self.set_xy(x + 18, y + 38)
        self.set_font("Helvetica", "", 10.5)
        self.set_text_color(*TEXT)
        for line in lines:
            self.set_x(x + 18)
            self.multi_cell(w - 36, 13.5, line)
            self.set_y(self.get_y() + 2)


def build(path: Path) -> None:
    pdf = Slide()

    # 1 - title
    pdf.add_page()
    pdf.set_fill_color(*BG)
    pdf.rect(0, 0, W, H, style="F")
    pdf.set_fill_color(*ACCENT)
    pdf.rect(56, 150, 5, 46, style="F")
    pdf.set_xy(76, 146)
    pdf.set_font("Helvetica", "B", 44)
    pdf.set_text_color(*TEXT)
    pdf.multi_cell(W - 132, 50, "Cage")
    pdf.set_xy(76, 206)
    pdf.set_font("Helvetica", "", 21)
    pdf.set_text_color(*ACCENT)
    pdf.multi_cell(W - 132, 27, "Container-scoped blast radius zero for coding agents")
    pdf.set_xy(76, 258)
    pdf.set_font("Helvetica", "", 13)
    pdf.set_text_color(*MUTED)
    pdf.multi_cell(W - 176, 19, "A self-hosted, containment-first control plane for agents that write and run real code:")
    pdf.multi_cell(W - 176, 19, "mediated tool calls, ephemeral Docker sandboxes on Vultr, and signed evidence of every run.")
    pdf.set_xy(76, 340)
    pdf.set_font("Helvetica", "B", 12)
    pdf.set_text_color(*TEXT)
    pdf.cell(0, 16, f"Repository: {REPO}")
    pdf.set_xy(76, 362)
    pdf.set_font("Helvetica", "", 11)
    pdf.set_text_color(*MUTED)
    pdf.cell(0, 15, "Vultr Agent Rush  |  Challenge 1: Blast Radius Zero  |  Pattern A: sandboxed code execution")
    pdf.set_xy(76, 400)
    pdf.set_font("Helvetica", "", 10.5)
    pdf.set_text_color(*MUTED)
    pdf.cell(0, 14, "Scope statement: container-scoped containment, not kernel-level isolation. Docker shares the host kernel; we say so up front.")

    # 2 - problem
    pdf.slide("01 / problem", "Agent demos avoid danger. Production agents must execute.")
    pdf.bullets([
        ("The dilemma",
         "A coding agent that only chats is not useful. An agent that writes and executes code is dangerous. "
         "Most agent platforms resolve this by trusting the operator and hoping the model behaves."),
        ("The cost of that trust",
         "One prompt injection turns a helper into a process that can read secrets, fill a disk, or reach the network. "
         "Nobody can prove afterwards what the agent actually did."),
        ("Our bet",
         "Make the blast radius a property of the execution environment instead of a property of the model's manners. "
         "Let the agent attempt anything; the container decides what survives."),
    ])

    # 3 - architecture
    pdf.slide("02 / architecture", "One control plane, one sandbox authority, one ephemeral container per task.")
    pdf.panel(56, 180, 400, 250, "Control plane  (FastAPI + SSE)", [
        "- Plans tasks, dispatches tools, verifies results",
        "- Holds the Vultr Serverless Inference key",
        "- Never touches Docker, never gets host shell",
        "- SQLite evidence store, per-IP rate limits,",
        "  concurrency cap, per-task token budget",
    ], CYAN)
    pdf.panel(488, 180, 416, 250, "sandboxd  (the only Docker authority)", [
        "- Creates one container + one workspace per task",
        "- network=none, ipc=none, read-only rootfs",
        "- UID 1000, cap-drop=ALL, no-new-privileges",
        "- 1 CPU / 512MB / 128 PIDs / 64MB tmpfs workspace",
        "- Bearer token between app and sandboxd",
    ], ACCENT)
    pdf.set_xy(56, 448)
    pdf.set_font("Helvetica", "", 11)
    pdf.set_text_color(*MUTED)
    pdf.cell(0, 14, "Vultr: the VM hosts the control plane, sandboxd and Caddy; Serverless Inference serves every agent LLM call, host-side only.")

    # 4 - containment model
    pdf.slide("03 / containment", "What the container guarantees, and what it does not.")
    pdf.bullets([
        ("Enforced by the runtime",
         "network=none  |  ipc=none  |  read-only rootfs  |  user 1000:1000  |  cap_drop=ALL  |  "
         "no-new-privileges  |  mem=512m  |  pids=128  |  1 CPU  |  /workspace = 64MB tmpfs  |  "
         "inner timeout --signal=KILL"),
        ("Also enforced",
         "No API key or credential is ever placed in the sandbox. Tool file paths are confined to /workspace and "
         "symlink-resolved inside the container. The workspace is tmpfs, so a runaway writer hits ENOSPC instead of the VM disk."),
        ("Not claimed",
         "Docker shares the host kernel. A kernel or runc escape, a hostile host, or a compromised sandboxd are out of scope; "
         "the mitigation is a dedicated Vultr VM, a minimal authenticated API, and optionally rootless Docker or gVisor."),
    ], top=176, gap=30)

    # 5 - drills
    pdf.slide("04 / proof", "Eight drills. A green card has to be earned.")
    pdf.panel(56, 176, 416, 250, "What each drill proves", [
        "- rm -rf / --no-preserve-root  -> rootfs is read-only",
        "- read-only canary  -> fails if read_only=False, even as UID 1000",
        "- infinite loop  -> killed by the inner timeout, not by OOM",
        "- fork bomb  -> PID limit produces a resource-limit failure",
        "- secret probe  -> no secret-like env vars in the sandbox",
        "- network probe  -> no network route out of the container",
        "- host write  -> no write outside the workspace",
        "- cross-task  -> a second sandbox cannot read the first one",
    ], ACCENT)
    pdf.panel(488, 176, 416, 250, "Why the drills are not theatre", [
        "- Each drill runs against a fresh container and",
        "  reports the real container ID and image ID",
        "- Pass predicates require a specific failure signature",
        "  (EROFS, timeout, EAGAIN, EACCES), not just",
        "  'something went wrong'",
        "- 27 tests cover the drill logic, including cases",
        "  that must fail",
        "- The same drill runs live from the web UI, so the",
        "  demo is the system under test",
    ], CYAN)

    # 6 - evidence
    pdf.slide("05 / evidence", "Signed receipts, not screenshots.")
    pdf.bullets([
        ("Sealed at completion",
         "When a task finishes, the control plane canonicalises the event log (tool calls, commands, exit codes, stdout/stderr, "
         "timeout/OOM flags, resolved image ID) and signs it with Ed25519. Repeated fetches return identical bytes; before sealing "
         "the endpoint returns 409 instead of signing on demand."),
        ("Independently verifiable",
         "scripts/verify_evidence.py re-computes the canonical payload and checks the signature against the published public key. "
         "The evidence pack deliberately excludes the session cookie, so it can be shared without granting access."),
        ("The honest part",
         "The signature proves this control plane produced this intact record. It does not prove the host was honest, and the key is "
         "host-side, so the fingerprint has to be pinned out of band."),
    ], top=176, gap=30)

    # 7 - deployment
    pdf.slide("06 / deployment", "One command on a Vultr VM, and nothing to configure by hand.")
    pdf.bullets([
        ("Deployment",
         "docker build -t cage-sandbox:latest sandbox_image, then docker compose up -d --build: app + sandboxd + Caddy on one VM. "
         "Caddy serves the app on 80/443; the app port stays on loopback and sandboxd is never published."),
        ("Model",
         "All agent calls go to Vultr Serverless Inference (OpenAI-compatible). Default qwen3.8-27b, which supports tool calling; "
         "Nemotron 3 Nano Omni is the open-weight alternative. The key never leaves the control plane."),
        ("Operability",
         "/healthz for liveness, /readyz for sandboxd + Docker + image readiness, a per-IP rate limit, a global task and probe cap, "
         "daily task and token budgets, and a boot-time DEMO_ENABLED kill switch for a public demo."),
    ], top=176, gap=30)

    # 8 - status
    pdf.slide("07 / status", "Where it stands, and what comes next.")
    pdf.panel(56, 180, 416, 230, "Demonstrated", [
        "- 27 automated tests pass (agent loop, cancellation,",
        "  rate limits, evidence signing, drill logic,",
        "  Docker flag construction, OOM classification)",
        "- Agent loop, SSE UI, evidence sealing and verifier",
        "  exercised end to end on a local build",
        "- Public repository with setup, architecture and",
        "  video spec, MIT licensed",
    ], ACCENT)
    pdf.panel(488, 180, 416, 230, "In progress during the build window", [
        "- Vultr VM deployment with the real Serverless",
        "  Inference key and a public demo URL",
        "- Live run of all eight drills on the VM, with the",
        "  host-unaffected proof recorded",
        "- Container image pinned by digest; evidence key",
        "  fingerprint published out of band",
    ], CYAN)
    pdf.set_xy(56, 430)
    pdf.set_font("Helvetica", "B", 12)
    pdf.set_text_color(*TEXT)
    pdf.cell(0, 16, "Every tool call has a receipt.")
    pdf.set_xy(56, 452)
    pdf.set_font("Helvetica", "", 10.5)
    pdf.set_text_color(*MUTED)
    pdf.cell(0, 14, f"Repository: {REPO}   |   Container-scoped containment, stated precisely, with evidence.")

    path.parent.mkdir(parents=True, exist_ok=True)
    pdf.output(str(path))
    print(f"wrote {path}")


if __name__ == "__main__":
    root = Path(__file__).resolve().parents[2]
    build(root / "dist" / "cage-pitch.pdf")
