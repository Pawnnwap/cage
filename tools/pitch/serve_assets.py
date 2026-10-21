"""Serve the dist/ folder over loopback with CORS enabled.

Used to hand a local video/PDF to the lablab upload widget, which reads the
file bytes in the page and posts them to lablab storage.

Usage:
    .venv/Scripts/python.exe tools/pitch/serve_assets.py [port]
"""

from __future__ import annotations

import http.server
import socketserver
import sys
from pathlib import Path


class CORSHandler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(ROOT), **kwargs)

    def end_headers(self) -> None:
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Headers", "*")
        self.send_header("Access-Control-Allow-Methods", "GET,POST,OPTIONS")
        super().end_headers()

    def do_OPTIONS(self) -> None:  # noqa: N802
        self.send_response(204)
        self.end_headers()

    def log_message(self, *args) -> None:  # keep the console quiet
        pass


ROOT = Path(__file__).resolve().parents[2] / "dist"


def main() -> None:
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8099
    socketserver.TCPServer.allow_reuse_address = True
    with socketserver.TCPServer(("127.0.0.1", port), CORSHandler) as httpd:
        print(f"serving {ROOT} on http://127.0.0.1:{port}")
        httpd.serve_forever()


if __name__ == "__main__":
    main()
