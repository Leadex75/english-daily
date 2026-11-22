from __future__ import annotations

import argparse
import json
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

FIELDS = ["Front", "Back", "Example", "Source", "Level", "Language", "Date", "Guid"]
MODES = ("ok", "origin-not-allowed", "not-running", "slow", "permission-denied", "duplicate notes")


class Handler(BaseHTTPRequestHandler):
    server_version = "FakeAnkiConnect/1.0"
    mode = "ok"
    allowed_origins: tuple[str, ...] = ()
    slow_seconds = 10.0

    def log_message(self, format: str, *args: Any) -> None:
        return

    def _allowed_origin(self) -> str | None:
        origin = str(self.headers.get("Origin") or "")
        if not self.allowed_origins:
            return origin or None
        return origin if origin in self.allowed_origins else None

    def _send(self, payload: dict[str, Any], status: int = 200) -> None:
        body = json.dumps(payload, separators=(",", ":")).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        allowed = self._allowed_origin()
        if allowed and self.mode != "origin-not-allowed":
            self.send_header("Access-Control-Allow-Origin", allowed)
            self.send_header("Vary", "Origin")
        self.end_headers()
        self.wfile.write(body)

    def do_OPTIONS(self) -> None:
        self.send_response(204)
        self.send_header("Allow", "POST, OPTIONS")
        self.send_header("Access-Control-Allow-Methods", "POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        allowed = self._allowed_origin()
        if allowed:
            self.send_header("Access-Control-Allow-Origin", allowed)
            self.send_header("Vary", "Origin")
        self.end_headers()

    def do_POST(self) -> None:
        try:
            length = int(self.headers.get("Content-Length") or "0")
        except ValueError:
            self._send({"result": None, "error": "invalid content length"}, 400)
            return
        if length <= 0 or length > 65536:
            self._send({"result": None, "error": "invalid request body"}, 413)
            return
        try:
            payload = json.loads(self.rfile.read(length).decode("utf-8"))
        except (UnicodeDecodeError, ValueError):
            self._send({"result": None, "error": "invalid JSON"}, 400)
            return
        if self.mode == "slow":
            time.sleep(self.slow_seconds)
        if self.mode == "origin-not-allowed" and self.headers.get("Origin"):
            self._send({"result": None, "error": "origin is not in webCorsOriginList"}, 403)
            return
        action = str(payload.get("action") or "")
        params = payload.get("params") or {}
        if action == "version":
            self._send({"result": 6, "error": None})
        elif action == "requestPermission":
            self._send({"result": None, "error": None})
        elif action == "modelFieldNames":
            if params.get("modelName") == "English Daily Cloze":
                self._send({"result": ["Text", "Extra", "Source", "Level", "Language", "Date", "Guid"], "error": None})
            else:
                self._send({"result": FIELDS, "error": None})
        elif action == "createModel":
            self._send({"result": {"name": params.get("modelName")}, "error": None})
        elif action == "addNotes":
            if self.mode == "permission-denied":
                self._send({"result": None, "error": "AnkiConnect permission not granted for this origin"})
            elif self.mode == "duplicate notes":
                notes = params.get("notes") or []
                self._send({"result": [None for _ in notes], "error": None})
            else:
                notes = params.get("notes") or []
                self._send({"result": list(range(1, len(notes) + 1)), "error": None})
        else:
            self._send({"result": None, "error": f"unknown action: {action}"})


def build_server(mode: str, port: int, origins: tuple[str, ...] = (), slow_seconds: float = 10.0) -> ThreadingHTTPServer:
    handler = type(
        "ConfiguredHandler",
        (Handler,),
        {"mode": mode, "allowed_origins": tuple(origins), "slow_seconds": slow_seconds},
    )
    return ThreadingHTTPServer(("127.0.0.1", port), handler)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="fake-ankiconnect")
    parser.add_argument("--mode", choices=MODES, default="ok")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--origin", action="append", default=[], help="allowed browser origin; repeatable")
    parser.add_argument("--slow-seconds", type=float, default=10.0)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    if args.mode == "not-running":
        print("Fake AnkiConnect mode 'not-running' intentionally did not start")
        return 0
    server = build_server(args.mode, args.port, tuple(args.origin), args.slow_seconds)
    print(f"Fake AnkiConnect {args.mode} listening on http://127.0.0.1:{args.port}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("Stopped.")
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
