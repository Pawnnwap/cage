"""Minimal Chrome DevTools Protocol client using only the standard library.

No playwright, no websocket package: raw socket + RFC 6455 framing. Enough to
drive a real Chrome window (click, type, navigate, evaluate) for recording.
"""

from __future__ import annotations

import base64
import json
import os
import socket
import struct
import time
import urllib.request

_OP_TEXT = 0x1
_OP_CLOSE = 0x8
_OP_PING = 0x9
_OP_PONG = 0xA


class _WS:
    def __init__(self, url: str, timeout: float = 20.0):
        assert url.startswith("ws://")
        rest = url[5:]
        hostport, path = rest.split("/", 1)
        path = "/" + path
        host, port = hostport.split(":")
        self.sock = socket.create_connection((host, int(port)), timeout=timeout)
        key = base64.b64encode(os.urandom(16)).decode()
        req = (
            f"GET {path} HTTP/1.1\r\n"
            f"Host: {hostport}\r\n"
            "Upgrade: websocket\r\n"
            "Connection: Upgrade\r\n"
            f"Sec-WebSocket-Key: {key}\r\n"
            "Sec-WebSocket-Version: 13\r\n\r\n"
        )
        self.sock.sendall(req.encode())
        buf = b""
        while b"\r\n\r\n" not in buf:
            buf += self.sock.recv(4096)
        if b"101" not in buf.split(b"\r\n", 1)[0]:
            raise RuntimeError("websocket upgrade failed: " + buf[:200].decode("latin-1"))
        self.buf = buf.split(b"\r\n\r\n", 1)[1]
        self.sock.settimeout(timeout)

    def _recv(self, n: int) -> bytes:
        while len(self.buf) < n:
            chunk = self.sock.recv(65536)
            if not chunk:
                raise RuntimeError("socket closed")
            self.buf += chunk
        out, self.buf = self.buf[:n], self.buf[n:]
        return out

    def send_text(self, payload: str) -> None:
        data = payload.encode()
        header = bytes([0x80 | 0x1])
        length = len(data)
        mask = os.urandom(4)
        if length < 126:
            header += bytes([0x80 | length])
        elif length < (1 << 16):
            header += bytes([0x80 | 126]) + struct.pack(">H", length)
        else:
            header += bytes([0x80 | 127]) + struct.pack(">Q", length)
        masked = bytes(b ^ mask[i % 4] for i, b in enumerate(data))
        self.sock.sendall(header + mask + masked)

    def recv_text(self) -> str:
        while True:
            b0, b1 = self._recv(2)
            opcode = b0 & 0x0F
            masked = b1 & 0x80
            length = b1 & 0x7F
            if length == 126:
                length = struct.unpack(">H", self._recv(2))[0]
            elif length == 127:
                length = struct.unpack(">Q", self._recv(8))[0]
            if masked:
                mask = self._recv(4)
            payload = self._recv(length) if length else b""
            if masked:
                payload = bytes(b ^ mask[i % 4] for i, b in enumerate(payload))
            if opcode == _OP_TEXT:
                return payload.decode("utf-8", "replace")
            if opcode == _OP_PING:
                self.sock.sendall(bytes([0x80 | _OP_PONG]) + bytes([0]) )
            elif opcode == _OP_CLOSE:
                raise RuntimeError("websocket closed by peer")

    def close(self):
        try:
            self.sock.sendall(bytes([0x80 | _OP_CLOSE, 0]))
        except Exception:
            pass
        self.sock.close()


class CDP:
    def __init__(self, ws_url: str):
        self._ws = _WS(ws_url)
        self._id = 0

    def call(self, method: str, params: dict | None = None, timeout: float = 30.0) -> dict:
        self._id += 1
        msg_id = self._id
        self._ws.send_text(json.dumps({"id": msg_id, "method": method, "params": params or {}}))
        self._ws.sock.settimeout(timeout)
        deadline = time.time() + timeout
        while time.time() < deadline:
            raw = self._ws.recv_text()
            msg = json.loads(raw)
            if msg.get("id") == msg_id:
                if "error" in msg:
                    raise RuntimeError(f"{method}: {msg['error']}")
                return msg.get("result", {})
        raise TimeoutError(f"{method} timed out")

    def evaluate(self, expr: str) -> str:
        res = self.call("Runtime.evaluate", {"expression": expr, "returnByValue": True, "awaitPromise": False})
        if "exceptionDetails" in res:
            raise RuntimeError(str(res["exceptionDetails"])[:300])
        return res.get("result", {}).get("value")

    def navigate(self, url: str) -> None:
        self.call("Page.navigate", {"url": url})

    def click(self, x: float, y: float) -> None:
        for kind in ("mousePressed", "mouseReleased"):
            self.call(
                "Input.dispatchMouseEvent",
                {"type": kind, "x": x, "y": y, "button": "left", "clickCount": 1},
            )

    def type_text(self, text: str) -> None:
        self.call("Input.insertText", {"text": text})

    def close(self):
        self._ws.close()


def first_page_ws(port: int = 9222, timeout: float = 30.0) -> str:
    """Wait for Chrome's debugging endpoint and return the first page's ws url."""
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            with opener.open(f"http://127.0.0.1:{port}/json/list", timeout=3) as r:
                targets = json.loads(r.read())
            for t in targets:
                if t.get("type") == "page" and t.get("webSocketDebuggerUrl"):
                    return t["webSocketDebuggerUrl"]
        except Exception:
            pass
        time.sleep(0.4)
    raise TimeoutError("no chrome page target")
