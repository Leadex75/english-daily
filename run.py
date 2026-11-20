from __future__ import annotations

import argparse
import sys

from app.db import init_db, load_config, load_sources, prune_audio, today, upsert_sources
from ingest.export_static import export_static
from ingest.pipeline import run_ingest
from ingest.state import import_site_state


def main() -> int:
    parser = argparse.ArgumentParser(description="english-daily")
    sub = parser.add_subparsers(dest="command")

    serve = sub.add_parser("serve", help="start the web app (default command)")
    serve.add_argument("--host", default=None)
    serve.add_argument("--port", type=int, default=None)

    ingest = sub.add_parser("ingest", help="fetch content for a date")
    ingest.add_argument("--date", default=None, help="YYYY-MM-DD (default: today)")
    ingest.add_argument("--state-dir", default=None, help="commit-friendly dedup state folder")

    export = sub.add_parser("export-static", help="write a GitHub-Pages-ready site")
    export.add_argument("--out", default="site")
    visibility = export.add_mutually_exclusive_group()
    visibility.add_argument("--public", dest="public_mode", action="store_true", default=None)
    visibility.add_argument("--private", dest="public_mode", action="store_false")

    import_state_cmd = sub.add_parser("import-state", help="rebuild state/used.json from exported data")
    import_state_cmd.add_argument("--site-dir", default="site")
    import_state_cmd.add_argument("--state-dir", default="state")

    sub.add_parser("doctor", help="check all enabled sources")
    sub.add_parser("prune", help="delete expired MP3 files")

    args = parser.parse_args()
    command = args.command or "serve"
    config = load_config()
    init_db(config)
    upsert_sources(load_sources(), config)

    if command == "ingest":
        day = args.date or today(config)
        summary = run_ingest(day, config, state_dir=args.state_dir)
        print(summary["report"])
        if summary["items"] == 0:
            print("No items were fetched from any source; failing the ingestion run.", file=sys.stderr)
            return 1
        return 0

    if command == "export-static":
        summary = export_static(args.out, config, public_mode=args.public_mode)
        print(f"Static site written to {summary['out']}")
        print(f"Days: {len(summary['days'])} ({', '.join(summary['days']) or 'none'})")
        print(f"Level files: {summary['written']}; audio slots: {summary['audios']}")
        print(f"Public mode: {summary['public_mode']}; pruned days: {', '.join(summary['pruned']) or 'none'}")
        return 0

    if command == "import-state":
        added, total = import_site_state(args.site_dir, args.state_dir, config)
        print(f"Imported {added} new entries; {total} entries in {args.state_dir}/used.json.")
        return 0

    if command == "prune":
        removed = prune_audio(config)
        print(f"Pruned {removed} expired audio file(s).")
        return 0

    if command == "doctor":
        from ingest.doctor import run_doctor

        return run_doctor(config)

    import uvicorn

    host = args.host or str(config["host"])
    port = args.port or int(config["port"])
    print(f"Starting english-daily at http://{host}:{port}/")
    uvicorn.run("app.main:app", host=host, port=port, log_level="info")
    return 0


if __name__ == "__main__":
    sys.exit(main())
