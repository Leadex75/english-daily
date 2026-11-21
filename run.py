from __future__ import annotations

import argparse
import datetime as dt
import json
import sys
from pathlib import Path
from typing import Any

from app.db import (
    PROJECT_ROOT,
    available_languages,
    connect,
    default_language,
    init_db,
    load_config,
    load_sources,
    normalize_language,
    prune_audio,
    successful_ingest_exists,
    today,
    upsert_sources,
)
from ingest.export_static import export_static
from ingest.fetch_text import clean_text, word_count
from ingest.picker import choose_picks
from ingest.pipeline import _candidates, run_ingest
from ingest.pool import pool_dir, write_json
from ingest.readability import CATEGORIES, KINDS, LEVELS
from ingest.state import import_site_state, load_entries


def _languages(config: dict[str, Any], lang: str | None) -> list[str]:
    if lang:
        return [normalize_language(config, lang)]
    return available_languages(config)


def _backfill(
    config: dict[str, Any],
    days: int,
    state_dir: str | None,
    lang: str | None,
    force: bool = False,
) -> dict[str, int]:
    offline = dict(config)
    offline["ingest_offline"] = True
    offline["reserve_offline"] = True
    offline["phrase_offline"] = True
    languages = _languages(config, lang)
    end = dt.date.fromisoformat(today(config))
    total_filled = 0
    skipped = 0
    processed = 0
    for offset in range(max(1, int(days)) - 1, -1, -1):
        day = (end - dt.timedelta(days=offset)).isoformat()
        for language in languages:
            if not force and successful_ingest_exists(day, config, language):
                skipped += 1
                continue
            summary = run_ingest(day, offline, state_dir=state_dir, lang=language)
            total_filled += int(summary["filled"])
            processed += 1
            print(summary["report"])
    return {"days": max(1, int(days)), "processed": processed, "skipped": skipped, "filled": total_filled}


def _reconstruct(
    config: dict[str, Any],
    day: str,
    lang: str | None = None,
    state_dir: str | None = None,
    write: bool = False,
) -> dict[str, Any]:
    language = normalize_language(config, lang)
    root = Path(state_dir) if state_dir else PROJECT_ROOT / "state"
    entries = load_entries(root, config, language)
    try:
        cutoff = (dt.date.fromisoformat(day) - dt.timedelta(days=30)).isoformat()
    except ValueError:
        cutoff = ""
    excluded = {
        str(entry["guid_hash"])
        for entry in entries
        if cutoff <= str(entry.get("date") or "")[:10] < day
    }
    conn = connect(config)
    try:
        candidates = _candidates(conn, language)
        scoring_config = dict(config)
        scoring_config["_lang"] = language
        trace: list[dict[str, Any]] = []
        picks, _, _ = choose_picks(
            candidates, day, scoring_config, excluded_hashes=excluded, trace=trace
        )
        rows = conn.execute(
            """SELECT dp.level, dp.category, dp.kind, dp.item_id, dp.origin, dp.badges,
                      i.guid_hash
               FROM daily_picks dp LEFT JOIN items i ON i.id=dp.item_id
               WHERE dp.date=? AND dp.lang=?""",
            (day, language),
        ).fetchall()
        stored = {
            (str(row["level"]), str(row["category"]), str(row["kind"])): dict(row)
            for row in rows
        }
        details: list[dict[str, Any]] = []
        matched = mismatched = missing = 0
        for level in LEVELS:
            for category in CATEGORIES:
                for kind in KINDS:
                    key = (level, category, kind)
                    expected = str(picks[key]["guid_hash"]) if key in picks else ""
                    actual = str(stored[key]["guid_hash"] or "") if key in stored else ""
                    if expected and actual and expected == actual:
                        status = "matched"
                        matched += 1
                    elif expected and actual:
                        status = "mismatched"
                        mismatched += 1
                    elif expected:
                        status = "missing"
                        missing += 1
                    elif actual:
                        status = "extra"
                    else:
                        status = "empty"
                    details.append({
                        "level": level,
                        "category": category,
                        "kind": kind,
                        "status": status,
                        "expected_guid_hash": expected or None,
                        "actual_guid_hash": actual or None,
                    })
        if write:
            conn.execute("DELETE FROM daily_picks WHERE date=? AND lang=?", (day, language))
            for (level, category, kind), item in picks.items():
                conn.execute(
                    """INSERT INTO daily_picks
                       (date, level, category, kind, item_id, origin, badges, reconstructed, lang)
                       VALUES (?,?,?,?,?,?,?,1,?)""",
                    (
                        day,
                        level,
                        category,
                        kind,
                        int(item["id"]),
                        str(item.get("origin") or "fresh"),
                        json.dumps(item.get("badges") or [], ensure_ascii=False),
                        language,
                    ),
                )
            conn.commit()
    finally:
        conn.close()
    return {
        "date": day,
        "lang": language,
        "written": bool(write),
        "total_slots": len(LEVELS) * len(CATEGORIES) * len(KINDS),
        "matched": matched,
        "mismatched": mismatched,
        "missing": missing,
        "reconstructed_filled": len(picks),
        "stored_picks": len(stored),
        "excluded_prior_hashes": len(excluded),
        "details": details,
        "trace": trace,
    }


def _reconstruct_report(summary: dict[str, Any]) -> str:
    lines = [
        f"Reconstruction {summary['date']} ({summary['lang']})",
        f"Slots: {summary['reconstructed_filled']}/{summary['total_slots']} reconstructed, "
        f"{summary['stored_picks']} stored, {summary['excluded_prior_hashes']} prior hash(es) excluded",
        f"Comparison: {summary['matched']} matched, {summary['mismatched']} mismatched, "
        f"{summary['missing']} missing",
        f"Mode: {'write' if summary['written'] else 'dry run'}",
    ]
    problems = [item for item in summary["details"] if item["status"] in {"mismatched", "missing"}]
    lines.append(
        "Problem slots: " + (
            ", ".join(
                f"{item['level']}/{item['category']}/{item['kind']}"
                for item in problems
            )
            if problems else "none"
        )
    )
    return "\n".join(lines)


def _stats(config: dict[str, Any], days: int, lang: str | None = None) -> dict[str, Any]:
    language = normalize_language(config, lang)
    conn = connect(config)
    try:
        rows = conn.execute(
            """SELECT level, COUNT(*) AS total, COUNT(DISTINCT date) AS day_count
               FROM daily_picks WHERE date >= date('now', ?) AND lang=? GROUP BY level""",
            (f"-{days} days", language),
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
            "lang": language,
            "weekly_goal": int(config.get("weekly_goal_default", 5)),
            "by_level": by_level,
            "phrase_days": int(conn.execute(
                "SELECT COUNT(DISTINCT date) FROM phrases WHERE lang=?", (language,)
            ).fetchone()[0]),
            "items": int(conn.execute(
                "SELECT COUNT(*) FROM items WHERE lang=?", (language,)
            ).fetchone()[0]),
            "days_published": int(conn.execute(
                "SELECT COUNT(DISTINCT date) FROM daily_picks WHERE lang=?", (language,)
            ).fetchone()[0]),
        }
    finally:
        conn.close()


def _stats_markdown(summary: dict[str, Any]) -> str:
    lines = [
        f"## English Daily stats ({summary['days']} days, {summary['lang']})",
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


_CLEAN_TEXT_FIELDS = {
    "title", "summary", "body_text", "body", "description", "text", "snippet",
    "meaning", "example", "front", "back",
}


def _clean_scalar(value: Any, config: dict[str, Any], field: str) -> tuple[Any, bool]:
    if not isinstance(value, str):
        return value, False
    cleaned = clean_text(value, config)
    if field == "body_text":
        cleaned = cleaned.strip()
    return cleaned, cleaned != value


def _clean_payload(payload: Any, config: dict[str, Any]) -> tuple[Any, bool]:
    changed = False
    if isinstance(payload, dict):
        for key, value in list(payload.items()):
            if key in _CLEAN_TEXT_FIELDS and isinstance(value, str):
                cleaned, updated = _clean_scalar(value, config, key)
                if updated:
                    payload[key] = cleaned
                    changed = True
            else:
                cleaned, updated = _clean_payload(value, config)
                if updated:
                    payload[key] = cleaned
                    changed = True
    elif isinstance(payload, list):
        for index, value in enumerate(payload):
            cleaned, updated = _clean_payload(value, config)
            if updated:
                payload[index] = cleaned
                changed = True
    return payload, changed


def _clean_existing(
    config: dict[str, Any],
    site_dir: str | Path = "site",
    state_dir: str | Path | None = None,
    lang: str | None = None,
) -> dict[str, Any]:
    counts = {"items": 0, "pool_files": 0, "site_files": 0}
    conn = connect(config)
    try:
        rows = conn.execute(
            "SELECT id, kind, title, summary, body_text, transcript_text, word_count FROM items"
        ).fetchall()
        for row in rows:
            updates: dict[str, Any] = {}
            for field in ("title", "summary", "body_text", "transcript_text"):
                cleaned, changed = _clean_scalar(row[field], config, field)
                if changed:
                    updates[field] = cleaned
            body = updates.get("body_text", row["body_text"])
            if row["kind"] == "text" and body is not None:
                words = word_count(str(body))
                if words != row["word_count"]:
                    updates["word_count"] = words
            if updates:
                assignments = ", ".join(f"{name}=?" for name in updates)
                conn.execute(
                    f"UPDATE items SET {assignments} WHERE id=?",
                    (*updates.values(), row["id"]),
                )
                counts["items"] += 1
        conn.commit()
    finally:
        conn.close()

    root = Path(state_dir) if state_dir else PROJECT_ROOT / "state"
    for language in _languages(config, lang):
        for path in sorted(pool_dir(root, config, language).glob("*.json")):
            try:
                payload = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                continue
            cleaned, changed = _clean_payload(payload, config)
            if changed:
                write_json(path, cleaned)
                counts["pool_files"] += 1

    site = Path(site_dir)
    if not site.is_absolute():
        site = PROJECT_ROOT / site
    if site.is_dir():
        for path in sorted(site.rglob("*.json")):
            try:
                payload = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                continue
            cleaned, changed = _clean_payload(payload, config)
            if changed:
                write_json(path, cleaned)
                counts["site_files"] += 1

    summary = export_static(
        site_dir, config, public_mode=bool(config.get("public_mode", True)), lang=lang
    )
    counts["export"] = summary
    return counts


def main() -> int:
    parser = argparse.ArgumentParser(description="English Daily")
    sub = parser.add_subparsers(dest="command")

    serve = sub.add_parser("serve", help="start the web app (default command)")
    serve.add_argument("--host", default=None)
    serve.add_argument("--port", type=int, default=None)

    ingest = sub.add_parser("ingest", help="fetch content for a date")
    ingest.add_argument("--date", default=None, help="YYYY-MM-DD (default: today)")
    ingest.add_argument("--state-dir", default=None, help="commit-friendly dedup state folder")
    ingest.add_argument("--lang", default=None, help="language code (default: all configured)")

    backfill = sub.add_parser("backfill", help="re-pick recent days from the local database")
    backfill.add_argument("--days", type=int, default=90)
    backfill.add_argument("--state-dir", default=None)
    backfill.add_argument("--lang", default=None)
    backfill.add_argument("--force", action="store_true", help="re-pick days that already have an ingest run")

    reconstruct = sub.add_parser("reconstruct", help="rebuild a day from stored candidates")
    reconstruct.add_argument("--date", default=None, help="YYYY-MM-DD (default: today)")
    reconstruct.add_argument("--state-dir", default=None)
    reconstruct.add_argument("--lang", default=None)
    reconstruct.add_argument("--write", action="store_true", help="replace stored picks with reconstructed ones")
    reconstruct.add_argument("--json", dest="json_output", action="store_true")

    export = sub.add_parser("export-static", help="write a GitHub-Pages-ready site")
    export.add_argument("--out", default="site")
    export.add_argument("--lang", default=None)
    visibility = export.add_mutually_exclusive_group()
    visibility.add_argument("--public", dest="public_mode", action="store_true", default=None)
    visibility.add_argument("--private", dest="public_mode", action="store_false")

    import_state_cmd = sub.add_parser("import-state", help="rebuild language state ledgers from exported data")
    import_state_cmd.add_argument("--site-dir", default="site")
    import_state_cmd.add_argument("--state-dir", default="state")
    import_state_cmd.add_argument("--lang", default=None)

    stats_cmd = sub.add_parser("stats", help="print content coverage")
    stats_cmd.add_argument("--days", type=int, default=90)
    stats_cmd.add_argument("--lang", default=None)

    doctor_cmd = sub.add_parser("doctor", help="check all enabled sources")
    doctor_cmd.add_argument("--json", dest="json_output", action="store_true")
    doctor_cmd.add_argument("--lang", default=None)
    clean_cmd = sub.add_parser("clean-existing", help="clean stored text and rebuild the static site")
    clean_cmd.add_argument("--site-dir", default="site")
    clean_cmd.add_argument("--state-dir", default=None)
    clean_cmd.add_argument("--lang", default=None)
    sub.add_parser("prune", help="delete expired MP3 files")

    args = parser.parse_args()
    command = args.command or "serve"
    config = load_config()
    init_db(config)
    upsert_sources(load_sources(), config)

    if command == "ingest":
        day = args.date or today(config)
        total_filled = 0
        for language in _languages(config, args.lang):
            summary = run_ingest(day, config, state_dir=args.state_dir, lang=language)
            total_filled += int(summary["filled"])
            print(summary["report"])
        if total_filled == 0:
            print("No slots were filled; failing the ingestion run.", file=sys.stderr)
            return 1
        return 0

    if command == "backfill":
        summary = _backfill(config, int(args.days), args.state_dir, args.lang, force=args.force)
        print(
            f"Backfill complete: {summary['filled']} slot(s) filled across "
            f"{summary['processed']} day/language pair(s); {summary['skipped']} skipped."
        )
        return 0

    if command == "reconstruct":
        day = args.date or today(config)
        summary = _reconstruct(
            config, day, lang=args.lang, state_dir=args.state_dir, write=args.write
        )
        if args.json_output:
            print(json.dumps(summary, ensure_ascii=False, indent=2))
        else:
            print(_reconstruct_report(summary))
        return 0

    if command == "export-static":
        summary = export_static(args.out, config, public_mode=args.public_mode, lang=args.lang)
        print(f"Static site written to {summary['out']}")
        print(f"Languages: {', '.join(summary['languages'])}")
        print(f"Days: {len(summary['days'])} ({', '.join(summary['days']) or 'none'})")
        print(f"Level files: {summary['written']}; audio slots: {summary['audios']}")
        print(f"Public mode: {summary['public_mode']}; pruned days: {', '.join(summary['pruned']) or 'none'}")
        return 0

    if command == "import-state":
        total_added = 0
        total_entries = 0
        for language in _languages(config, args.lang):
            added, total = import_site_state(
                args.site_dir, args.state_dir, config, lang=language
            )
            total_added += added
            total_entries += total
        print(f"Imported {total_added} new entries; {total_entries} entries in language state ledgers.")
        return 0

    if command == "stats":
        for language in _languages(config, args.lang):
            print(_stats_markdown(_stats(config, int(args.days), language)))
        return 0

    if command == "clean-existing":
        summary = _clean_existing(config, args.site_dir, args.state_dir, args.lang)
        print(
            f"Cleaned {summary['items']} item(s), {summary['pool_files']} pool file(s), "
            f"{summary['site_files']} site JSON file(s)."
        )
        print(f"Static site written to {summary['export']['out']}")
        return 0

    if command == "prune":
        removed = prune_audio(config)
        print(f"Pruned {removed} expired audio file(s).")
        return 0

    if command == "doctor":
        from ingest.doctor import run_doctor

        return run_doctor(config, json_output=args.json_output, lang=args.lang)

    import uvicorn

    host = args.host or str(config["host"])
    port = args.port or int(config["port"])
    print(f"Starting English Daily at http://{host}:{port}/")
    uvicorn.run("app.main:app", host=host, port=port, log_level="info")
    return 0


if __name__ == "__main__":
    sys.exit(main())
