from __future__ import annotations

import datetime as dt
import hashlib
import json
import os
from pathlib import Path
from typing import Any

from app.db import PROJECT_ROOT, connect, load_sources, prune_audio
from ingest.fetch_audio import download_audio
from ingest.fetch_feeds import fetch_source, is_reserve_source
from ingest.fetch_text import body_for_entry, clean_text, word_count
from ingest.phrases import generate_phrases, store_phrases
from ingest.picker import choose_picks
from ingest.pool import hydrate_db, load_pool, writeback_db
from ingest.readability import CATEGORIES, KINDS, LEVELS, level_for_source
from ingest.reserve import generate_reserves
from ingest.state import record_picks, used_hashes


def _guid_hash(entry: dict[str, Any]) -> str:
    seed = ":".join(
        str(entry.get(key) or "") for key in ("source_id", "source_kind", "guid", "url", "title")
    )
    return hashlib.sha1(seed.encode("utf-8", "ignore")).hexdigest()


def _insert_fresh_items(
    conn: Any,
    day: str,
    config: dict[str, Any],
    items_added: int,
    duplicates: int,
    audios_kept: int,
    sources_report: dict[str, str],
    errors: dict[str, str],
) -> tuple[int, int, int]:
    cutoff = (
        dt.date.fromisoformat(day) - dt.timedelta(days=int(config["lookback_days"]))
    ).isoformat()
    text_low = int(config["text_hard_min_words"])
    text_high = int(config["text_hard_max_words"])
    for source in load_sources():
        if not source.get("enabled", True) or is_reserve_source(source):
            continue
        name = str(source.get("name") or source["id"])
        source_items = 0
        license_name = str(source.get("license") or "proprietary")
        attribution = source.get("attribution") or None
        try:
            entries = fetch_source(source, config, day)
            for entry in entries:
                entry["source_kind"] = str(source["kind"])
                published = str(entry.get("published_at") or "")[:10]
                if published and published < cutoff:
                    continue
                guid_hash = _guid_hash(entry)
                exists = conn.execute(
                    "SELECT 1 FROM items WHERE guid_hash=?", (guid_hash,)
                ).fetchone()
                if exists:
                    duplicates += 1
                    continue

                body = body_for_entry(entry, config)
                words = word_count(body)
                kind = str(source["kind"])
                if kind == "text" and not text_low <= words <= text_high:
                    continue

                low = str(source.get("level_min") or "computed")
                high = str(source.get("level_max") or "computed")
                text_for_score = body if kind == "text" else clean_text(entry.get("summary"))
                minimum_words = 120 if kind == "text" else 60
                values, level, method = level_for_source(
                    text_for_score, low, high, config["level_thresholds"], minimum_words
                )

                audio_info: dict[str, Any] | None = None
                if kind == "audio":
                    audio_info = download_audio(entry, source, config, day, guid_hash)
                    if audio_info is None:
                        continue

                conn.execute(
                    """INSERT OR IGNORE INTO items
                       (guid_hash, source_id, kind, category, title, url, summary,
                        published_at, fetched_at, body_text, word_count, duration_sec,
                        audio_path, audio_bytes, fk_grade, avg_sentence_len,
                        rare_word_ratio, score, level, level_method,
                        audio_remote_url, license, attribution, origin)
                       VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?, 'fresh')""",
                    (
                        guid_hash,
                        str(source["id"]),
                        kind,
                        str(source["category"]),
                        clean_text(entry.get("title")),
                        entry.get("url"),
                        clean_text(entry.get("summary"))[:2000],
                        entry.get("published_at"),
                        dt.datetime.now().isoformat(timespec="seconds"),
                        body if kind == "text" else None,
                        words if kind == "text" else word_count(entry.get("summary")),
                        audio_info["duration_sec"] if audio_info else None,
                        audio_info["audio_path"] if audio_info else None,
                        audio_info["audio_bytes"] if audio_info else None,
                        values["fk_grade"],
                        values["avg_sentence_len"],
                        values["rare_word_ratio"],
                        values["score"],
                        level,
                        method,
                        audio_info["audio_remote_url"] if audio_info else None,
                        license_name,
                        attribution,
                    ),
                )
                source_items += 1
                items_added += 1
                if audio_info:
                    audios_kept += 1
            conn.commit()
            sources_report[name] = f"{source_items} item(s) stored"
        except Exception as exc:
            errors[name] = f"{type(exc).__name__}: {exc}"
            sources_report[name] = "ERROR"
    return items_added, duplicates, audios_kept


def _candidates(conn: Any) -> list[dict[str, Any]]:
    rows = conn.execute(
        """SELECT i.*, s.name AS source_name
           FROM items i LEFT JOIN sources s ON s.id=i.source_id
           WHERE i.category IN ('news','culture','history')"""
    ).fetchall()
    candidates: list[dict[str, Any]] = []
    for row in rows:
        candidate = dict(row)
        origin = str(candidate.get("origin") or "fresh")
        candidate["origin_kind"] = origin if origin in {"reserve", "archive"} else "fresh"
        candidates.append(candidate)
    return candidates


def _store_picks(conn: Any, day: str, picks: dict[tuple[str, str, str], dict[str, Any]]) -> None:
    conn.execute("DELETE FROM daily_picks WHERE date=?", (day,))
    for (level, category, kind), item in picks.items():
        conn.execute(
            """INSERT INTO daily_picks
               (date, level, category, kind, item_id, origin, badges)
               VALUES (?,?,?,?,?,?,?)""",
            (
                day,
                str(level),
                str(category),
                str(kind),
                int(item["id"]),
                str(item.get("origin") or "fresh"),
                json.dumps(item.get("badges") or [], ensure_ascii=False),
            ),
        )
    conn.commit()


def run_ingest(day: str, config: dict[str, Any], state_dir: str | None = None) -> dict[str, Any]:
    """Fetch, score, reserve, pick and persist one day of content."""
    root = Path(state_dir) if state_dir else PROJECT_ROOT / "state"
    conn = connect(config)
    try:
        cursor = conn.execute(
            "INSERT INTO ingest_runs (date, started_at, status) VALUES (?,?, 'running')",
            (day, dt.datetime.now().isoformat(timespec="seconds")),
        )
        run_id = int(cursor.lastrowid)
        conn.commit()
    finally:
        conn.close()

    items_added = 0
    duplicates = 0
    audios_kept = 0
    sources_report: dict[str, str] = {}
    errors: dict[str, str] = {}

    if bool(config.get("ingest_offline")):
        sources_report["fresh sources"] = "skipped (offline)"
    else:
        conn = connect(config)
        try:
            items_added, duplicates, audios_kept = _insert_fresh_items(
                conn, day, config, items_added, duplicates, audios_kept, sources_report, errors
            )
        finally:
            conn.close()

    excluded = used_hashes(root, config)
    pool = load_pool(root, config)
    reserve_before = len(pool)
    reserve_offline = bool(config.get("reserve_offline")) or bool(os.environ.get("ENGLISH_DAILY_RESERVE_OFFLINE"))
    if not reserve_offline:
        try:
            pool = generate_reserves(config, root, pool)
        except Exception as exc:
            errors["reserve pool"] = f"{type(exc).__name__}: {exc}"
            sources_report["reserve pool"] = "ERROR"
    reserves_added = max(0, len(pool) - reserve_before)
    sources_report.setdefault("reserve pool", f"{reserves_added} new candidate(s); {len(pool)} stored")

    conn = connect(config)
    try:
        hydrate_db(conn, pool)
        candidates = _candidates(conn)
    finally:
        conn.close()
    picks, filled, empty = choose_picks(candidates, day, config, excluded_hashes=excluded)

    phrases_count = 0
    try:
        phrases = generate_phrases(config, day, root)
        conn = connect(config)
        try:
            store_phrases(conn, day, phrases)
        finally:
            conn.close()
        phrases_count = len(phrases)
        sources_report["phrases"] = f"{phrases_count} level(s) stored"
    except Exception as exc:
        errors["phrases"] = f"{type(exc).__name__}: {exc}"
        sources_report["phrases"] = "ERROR"

    conn = connect(config)
    try:
        _store_picks(conn, day, picks)
        picked_hashes = {str(item["guid_hash"]) for item in picks.values()}
        writeback_db(conn, root, config, picked_hashes, excluded)
    finally:
        conn.close()
    state_entries = record_picks(root, config, day, picked_hashes)
    pruned = prune_audio(config) if int(config["retention_days"]) > 0 else 0

    status = "partial" if errors else "ok"
    log_lines = [f"{name}: {detail}" for name, detail in sources_report.items()]
    log_lines += [f"ERROR {name}: {message}" for name, message in errors.items()]
    conn = connect(config)
    try:
        conn.execute(
            "UPDATE ingest_runs SET finished_at=?, status=?, log=? WHERE id=?",
            (dt.datetime.now().isoformat(timespec="seconds"), status, "\n".join(log_lines), run_id),
        )
        conn.commit()
    finally:
        conn.close()

    filled_levels = {slot.split("/", 1)[0] for slot in filled}
    empty_levels = [level for level in LEVELS if level not in filled_levels]
    report = "\n".join(
        [
            f"Ingestion {day} ({status})",
            f"Items fetched: {items_added} (duplicates skipped: {duplicates})",
            f"Audios kept: {audios_kept}",
            f"Reserve candidates: +{reserves_added} new, {len(pool)} stored",
            f"Slots filled: {len(filled)}/36",
            "Empty slots: " + (", ".join(empty) if empty else "none"),
            "Levels with no slot: " + (", ".join(empty_levels) if empty_levels else "none"),
            f"Phrase levels: {phrases_count}/6",
            f"Audio files pruned: {pruned}",
            f"State entries: {state_entries}",
            "Errors: " + (", ".join(f"{k}={v}" for k, v in errors.items()) if errors else "none"),
        ]
    )
    return {
        "date": day,
        "status": status,
        "items": items_added,
        "duplicates": duplicates,
        "audios": audios_kept,
        "reserves_added": reserves_added,
        "reserve_total": len(pool),
        "filled": len(filled),
        "total_slots": len(CATEGORIES) * len(KINDS) * len(LEVELS),
        "empty": empty,
        "empty_levels": empty_levels,
        "phrases": phrases_count,
        "pruned": pruned,
        "state_entries": state_entries,
        "errors": errors,
        "report": report,
    }
