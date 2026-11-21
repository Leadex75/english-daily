from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from ingest.phrases import load_phrases
from ingest.readability import CATEGORIES, KINDS

_SENTENCE_END_RE = re.compile(r"(?<=[.!?])\s+")


def excerpt(text: str, limit: int) -> str:
    words = (text or "").split()
    if not words or limit <= 0:
        return ""
    prefix = " ".join(words[:limit])
    parts = _SENTENCE_END_RE.split(prefix)
    if len(parts) > 1 and len(parts[0].split()) >= max(3, min(limit, limit // 2)):
        prefix = parts[0]
    return prefix.rstrip(" ,;:") + "…"


def _badges(row: Any) -> list[str]:
    try:
        value = json.loads(str(row["pick_badges"] or "[]"))
    except (TypeError, ValueError):
        return []
    return [str(item) for item in value] if isinstance(value, list) else []


def _json_array(value: Any) -> list[Any]:
    try:
        payload = json.loads(str(value or "[]"))
    except (TypeError, ValueError):
        return []
    return payload if isinstance(payload, list) else []


def serialize_item(
    row: Any,
    kind: str,
    day: str,
    config: dict[str, Any],
    public_mode: bool = False,
    audio_base: str | None = None,
) -> dict[str, Any]:
    license_name = str(row["license"] or "proprietary")
    attribution = row["attribution"] or None
    body_text = row["body_text"] if kind == "text" else None
    truncated = False
    if kind == "text" and public_mode and license_name == "proprietary":
        body_text = excerpt(str(body_text or ""), int(config["excerpt_words"]))
        truncated = True

    audio_remote_url = row["audio_remote_url"] or None
    audio_path = row["audio_path"] or None
    if kind == "audio":
        if audio_remote_url:
            audio_url = audio_remote_url
        elif audio_path:
            name = Path(str(audio_path)).name
            audio_url = f"{audio_base}{day}/{name}" if audio_base is not None else f"/audio/{day}/{name}"
        else:
            audio_url = None
        description = str(row["summary"] or "")
    else:
        audio_url = None
        description = None

    return {
        "id": int(row["id"]),
        "title": str(row["title"]),
        "source": str(row["source_name"] or row["source_id"]),
        "source_id": row["source_id"],
        "category": row["category"],
        "url": row["url"],
        "published_at": row["published_at"],
        "level": row["slot_level"] or row["level"],
        "slot_level": row["slot_level"] or row["level"],
        "source_level": row["level"],
        "word_count": row["word_count"],
        "duration_sec": row["duration_sec"],
        "body_text": body_text,
        "audio_url": audio_url,
        "description": description,
        "license": license_name,
        "attribution": attribution,
        "truncated": truncated,
        "guid_hash": row["guid_hash"],
        "summary": row["summary"],
        "origin": row["pick_origin"] or row["origin"] or "fresh",
        "badges": _badges(row),
        "periods": _json_array(row["periods"] if "periods" in row.keys() else "[]"),
        "themes": _json_array(row["themes"] if "themes" in row.keys() else "[]"),
        "history_terms": _json_array(row["history_terms"] if "history_terms" in row.keys() else "[]"),
    }


def serialize_day(
    conn: Any,
    day: str,
    level: str,
    config: dict[str, Any],
    public_mode: bool = False,
    audio_base: str | None = None,
    lang: str | None = None,
) -> dict[str, Any]:
    from app.db import default_language

    language = str(lang or default_language(config))
    rows = conn.execute(
        """SELECT p.category AS pick_category, p.kind AS pick_kind, p.level AS slot_level,
                  p.origin AS pick_origin, p.badges AS pick_badges,
                  i.*, s.name AS source_name
           FROM daily_picks p
           JOIN items i ON i.id = p.item_id
           LEFT JOIN sources s ON s.id = i.source_id
           WHERE p.date=? AND p.level=? AND p.lang=?""",
        (day, level, language),
    ).fetchall()
    slots: dict[str, dict[str, Any]] = {
        category: {"text": None, "audio": None} for category in CATEGORIES
    }
    origins: dict[str, int] = {}
    for row in rows:
        category = str(row["pick_category"])
        kind = str(row["pick_kind"])
        if category not in slots or kind not in slots[category]:
            continue
        item = serialize_item(
            row, kind, day, config, public_mode=public_mode, audio_base=audio_base
        )
        slots[category][kind] = item
        origin = str(item["origin"])
        origins[origin] = origins.get(origin, 0) + 1

    filled = sum(
        1 for category in CATEGORIES for kind in KINDS if slots[category][kind] is not None
    )
    return {
        "date": day,
        "lang": language,
        "level": level,
        "slots": slots,
        "phrase": load_phrases(conn, day, language).get(level),
        "meta": {
            "filled": filled,
            "total": len(CATEGORIES) * len(KINDS),
            "origins": origins,
        },
    }
