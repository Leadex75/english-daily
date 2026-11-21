import argparse
import functools
import http.server
import sys
import threading
import webbrowser
from pathlib import Path

APP_ROOT = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parents[1]))
if str(APP_ROOT) not in sys.path:
    sys.path.insert(0, str(APP_ROOT))


def resolve_site_dir(root, explicit=None):
    root = Path(root)
    site = Path(explicit) if explicit else (root / "site")
    if site.is_dir() and (site / "index.html").is_file():
        return site
    return None


def parse_args(argv=None):
    parser = argparse.ArgumentParser(prog="english-daily-desktop")
    parser.add_argument("--site", default=None, help="serve an exported static site instead of the API")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--no-browser", action="store_true")
    return parser.parse_args(argv)


def serve_site(site, host, port):
    handler = functools.partial(
        http.server.SimpleHTTPRequestHandler,
        directory=str(site),
    )
    with http.server.ThreadingHTTPServer((host, port), handler) as server:
        server.serve_forever()


def serve_app(host, port):
    import uvicorn
    from app.main import app
    uvicorn.run(app, host=host, port=port, log_level="info")


def main(argv=None):
    args = parse_args(argv)
    site = resolve_site_dir(APP_ROOT, args.site)
    url = f"http://{args.host}:{args.port}/"
    if not args.no_browser:
        threading.Timer(0.6, lambda: webbrowser.open(url)).start()
    print(f"english-daily running at {url}")
    print("Press Ctrl+C to quit.")
    try:
        if site:
            serve_site(site, args.host, args.port)
        else:
            serve_app(args.host, args.port)
    except KeyboardInterrupt:
        print("Stopped.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
