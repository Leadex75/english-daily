from __future__ import annotations

import argparse
import datetime as dt
import sys
from typing import Any

from app.db import connect, init_db, load_config, load_sources, prune_audio, today, upsert_sources
from ingest.export_static import export_static
from ingest.pipeline import run_ingest
from ingest.readability import LEVELS
from ingest.state import import_site_state


def _stats(config: dict[str, Any], days: int) -> dict[str, Any]:
    conn = connect(config)
    try:
        rows = conn.execute(
            """SELECT level, COUNT(*) AS total, COUNT(DISTINCT date) AS day_count
               FROM daily_picks WHERE date >= date('now', ?) GROUP BY level""",
            (f"-{days} days",),
        ).fetchall()
        by_level = {
            str(level): {"picks": 0, "days": 0, "capacity": 6 * days} for level in LEVELS
        }
        for row in rows:
            level = str(row["level"])
            if level in by_level:
                by_level[level] = {
                    "picks": int(row["total"]),
                    "days": int(row["day_count"]),
                    "capacity": 6 * days,
                }
        return {
            "days": days,
            "weekly_goal": int(config.get("weekly_goal_default", 5)),
            "by_level": by_level,
            "phrase_days": int(conn.execute("SELECT COUNT(DISTINCT date) FROM phrases").fetchone()[0]),
            "items": int(conn.execute("SELECT COUNT(*) FROM items").fetchone()[0]),
            "days_published": int(conn.execute("SELECT COUNT(DISTINCT date) FROM daily_picks").fetchone()[0]),
        }
    finally:
        conn.close()


def _stats_markdown(summary: dict[str, Any]) -> str:
    lines = [
        f"## english-daily stats ({summary['days']} days)",
        "",
        "| Level | Picks | Days with content | Capacity |",
        "| --- | ---: | ---: | ---: |",
    ]
    for level, values in summary["by_level"].items():
        lines.append(f"| {level} | {values['picks']} | {values['days']} | {values['capacity']} |")
    lines += [
        "",
        f"- Phrase days: {summary['phrase_days']}",
        f"- Items in database: {summary['items']}",
        f"- Published days: {summary['days_published']}",
        f"- Weekly goal: {summary['weekly_goal']}",
    ]
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="english-daily")
    sub = parser.add_subparsers(dest="command")

    serve = sub.add_parser("serve", help="start the web app (default command)")
    serve.add_argument("--host", default=None)
    serve.add_argument("--port", type=int, default=None)

    ingest = sub.add_parser("ingest", help="fetch content for a date")
    ingest.add_argument("--date", default=None, help="YYYY-MM-DD (default: today)")
    ingest.add_argument("--state-dir", default=None, help="commit-friendly dedup state folder")

    backfill = sub.add_parser("backfill", help="re-pick recent days from the local database")
    backfill.add_argument("--days", type=int, default=90)
    backfill.add_argument("--state-dir", default=None)

    export = sub.add_parser("export-static", help="write a GitHub-Pages-ready site")
    export.add_argument("--out", default="site")
    visibility = export.add_mutually_exclusive_group()
    visibility.add_argument("--public", dest="public_mode", action="store_true", default=None)
    visibility.add_argument("--private", dest="public_mode", action="store_false")

    import_state_cmd = sub.add_parser("import-state", help="rebuild state/used.json from exported data")
    import_state_cmd.add_argument("--site-dir", default="site")
    import_state_cmd.add_argument("--state-dir", default="state")

    stats_cmd = sub.add_parser("stats", help="print content coverage")
    stats_cmd.add_argument("--days", type=int, default=90)

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
        if summary["filled"] == 0:
            print("No slots were filled; failing the ingestion run.", file=sys.stderr)
            return 1
        return 0

    if command == "backfill":
        offline = dict(config)
        offline["ingest_offline"] = True
        offline["reserve_offline"] = True
        offline["phrase_offline"] = True
        count = max(1, int(args.days))
        end = dt.date.fromisoformat(today(config))
        total_filled = 0
        for offset in range(count - 1, -1, -1):
            day = (end - dt.timedelta(days=offset)).isoformat()
            summary = run_ingest(day, offline, state_dir=args.state_dir)
            total_filled += int(summary["filled"])
            print(summary["report"])
        print(f"Backfill complete: {total_filled} slot(s) filled across {count} day(s).")
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

    if command == "stats":
        print(_stats_markdown(_stats(config, int(args.days))))
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
