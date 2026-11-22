import argparse
import functools
import http.server
import json
import socket
import sys
import threading
import webbrowser
from pathlib import Path

APP_ROOT = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parents[1]))
if str(APP_ROOT) not in sys.path:
    sys.path.insert(0, str(APP_ROOT))

from app.anki_connect import MAX_BODY_BYTES, AnkiConnectError, parse_body, proxy_request

DEFAULT_PORT = 8731
PORT_TRIES = 20


def resolve_site_dir(root, explicit=None):
    root = Path(root)
    site = Path(explicit) if explicit else (root / "site")
    if site.is_dir() and (site / "index.html").is_file():
        return site
    return None


def choose_port(host, port):
    for candidate in range(port, port + PORT_TRIES):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            try:
                sock.bind((host, candidate))
                return candidate
            except OSError:
                continue
    raise RuntimeError(f"no free port in range {port}-{port + PORT_TRIES - 1}")


def parse_args(argv=None):
    parser = argparse.ArgumentParser(prog="English Daily Desktop")
    parser.add_argument("--site", default=None, help="serve an exported static site instead of the API")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    parser.add_argument(
        "--anki-url",
        default="http://127.0.0.1:8765",
        help="local AnkiConnect endpoint used by the built-in proxy",
    )
    parser.add_argument("--no-browser", action="store_true")
    return parser.parse_args(argv)


def build_handler(site, endpoint, expected_origin):
    class Handler(http.server.SimpleHTTPRequestHandler):
        anki_endpoint = endpoint
        expected_origin = expected_origin

        def log_message(self, format, *args):
            return

        def do_POST(self):
            if self.path.split("?", 1)[0] != "/api/ankiconnect":
                self.send_error(404, "Not Found")
                return
            try:
                length = int(self.headers.get("Content-Length") or "0")
            except ValueError:
                self._send_json({"error": "invalid content length", "kind": "validation"}, 400)
                return
            if length < 0 or length > MAX_BODY_BYTES:
                self._send_json({"error": "request body is too large", "kind": "validation"}, 413)
                return
            raw = self.rfile.read(length)
            try:
                payload = parse_body(raw)
                result = proxy_request(
                    payload,
                    dict(self.headers),
                    expected_origin=self.expected_origin,
                    endpoint=self.anki_endpoint,
                )
                self._send_json(result)
            except AnkiConnectError as exc:
                self._send_json({"error": exc.message, "kind": exc.kind}, exc.status)

        def _send_json(self, payload, status=200):
            body = json.dumps(payload, separators=(",", ":")).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

    if site is not None:
        return functools.partial(Handler, directory=str(site))
    return Handler


def serve_site(site, host, port, endpoint):
    expected_origin = f"http://{host}:{port}"
    handler = build_handler(site, endpoint, expected_origin)
    with http.server.ThreadingHTTPServer((host, port), handler) as server:
        server.serve_forever()


def serve_app(host, port):
    import uvicorn
    from app.main import app
    uvicorn.run(app, host=host, port=port, log_level="info")


def main(argv=None):
    args = parse_args(argv)
    site = resolve_site_dir(APP_ROOT, args.site)
    port = choose_port(args.host, args.port)
    url = f"http://{args.host}:{port}/"
    if not args.no_browser:
        threading.Timer(0.6, lambda: webbrowser.open(url)).start()
    print(f"English Daily running at {url}")
    print(f"AnkiConnect proxy uses {args.anki_url}")
    print("Press Ctrl+C to quit.")
    try:
        if site:
            serve_site(site, args.host, port, args.anki_url)
        else:
            serve_app(args.host, port)
    except KeyboardInterrupt:
        print("Stopped.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
