from __future__ import annotations

import datetime as dt
import hashlib
from typing import Any

from app.db import connect, load_sources, prune_audio
from ingest.fetch_audio import download_audio
from ingest.fetch_feeds import fetch_source
from ingest.fetch_text import body_for_entry, clean_text, word_count
from ingest.picker import fill_picks
from ingest.readability import LEVELS, level_for_source
from ingest.state import record_picks, used_hashes


def _guid_hash(entry: dict[str, Any]) -> str:
    # Include source and kind so a text article and its audio version stay distinct.
    seed = ":".join(
        str(entry.get(key) or "") for key in ("source_id", "source_kind", "guid", "url", "title")
    )
    return hashlib.sha1(seed.encode("utf-8", "ignore")).hexdigest()


def run_ingest(day: str, config: dict[str, Any], state_dir: str | None = None) -> dict[str, Any]:
    """Fetch all enabled sources for `day`, store items, download audios and pick."""
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

    for source in load_sources():
        if not source.get("enabled", True):
            continue
        name = str(source.get("name") or source["id"])
        source_items = 0
        license_name = str(source.get("license") or "proprietary")
        attribution = source.get("attribution") or None
        try:
            entries = fetch_source(source, config, day)
            cutoff = (
                dt.date.fromisoformat(day) - dt.timedelta(days=int(config["lookback_days"]))
            ).isoformat()
            conn = connect(config)
            try:
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
                    if kind == "text" and not 120 <= words <= 1500:
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
                            audio_remote_url, license, attribution)
                           VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
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
            finally:
                conn.close()
            sources_report[name] = f"{source_items} item(s) stored"
        except Exception as exc:  # one bad source must never stop the run
            errors[name] = f"{type(exc).__name__}: {exc}"
            sources_report[name] = "ERROR"

    excluded_hashes = used_hashes(state_dir, config)
    filled, empty = fill_picks(day, config, excluded_hashes=excluded_hashes)
    conn = connect(config)
    try:
        picked_hashes = [
            str(row[0])
            for row in conn.execute(
                """SELECT DISTINCT i.guid_hash
                   FROM daily_picks p JOIN items i ON i.id = p.item_id
                   WHERE p.date=? AND i.guid_hash IS NOT NULL""",
                (day,),
            ).fetchall()
        ]
    finally:
        conn.close()
    state_entries = record_picks(state_dir, config, day, picked_hashes)
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
            f"Slots filled: {len(filled)}/24",
            "Empty slots: " + (", ".join(empty) if empty else "none"),
            "Levels with no slot: " + (", ".join(empty_levels) if empty_levels else "none"),
            f"Audio files pruned: {pruned}",
            f"State entries: {state_entries}",
            "Errors per source: " + (", ".join(f"{k}={v}" for k, v in errors.items()) if errors else "none"),
        ]
    )
    return {
        "date": day,
        "status": status,
        "items": items_added,
        "audios": audios_kept,
        "filled": len(filled),
        "empty": empty,
        "empty_levels": empty_levels,
        "state_entries": state_entries,
        "errors": errors,
        "report": report,
    }
