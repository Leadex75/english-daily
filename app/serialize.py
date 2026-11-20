from __future__ import annotations

import re
from pathlib import Path
from typing import Any

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
        "url": row["url"],
        "published_at": row["published_at"],
        "level": row["level"],
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
    }


def serialize_day(
    conn: Any,
    day: str,
    level: str,
    config: dict[str, Any],
    public_mode: bool = False,
    audio_base: str | None = None,
) -> dict[str, Any]:
    rows = conn.execute(
        """SELECT p.category, p.kind, i.*, s.name AS source_name
           FROM daily_picks p
           JOIN items i ON i.id = p.item_id
           LEFT JOIN sources s ON s.id = i.source_id
           WHERE p.date=? AND p.level=?""",
        (day, level),
    ).fetchall()
    slots: dict[str, dict[str, Any]] = {
        "news": {"text": None, "audio": None},
        "culture": {"text": None, "audio": None},
    }
    for row in rows:
        category = str(row["category"])
        kind = str(row["kind"])
        if category not in slots or kind not in slots[category]:
            continue
        slots[category][kind] = serialize_item(
            row, kind, day, config, public_mode=public_mode, audio_base=audio_base
        )
    return {"date": day, "level": level, "slots": slots}
