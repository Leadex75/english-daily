from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from ingest.fetch_text import clean_text
from ingest.phrases import load_phrases
from ingest.readability import CATEGORIES, KINDS, LEVELS

_SENTENCE_END_RE = re.compile(r"(?:[.!?]|…)(?=\s|$)")
_CLAUSE_END_RE = re.compile(r"[,;:—–](?=\s|$)")
_CLOZE_STOPWORDS = {"a", "an", "and", "be", "for", "in", "is", "of", "on", "the", "to", "with"}
_TOUR_STEPS = (
    {"id": "level", "title": "Choose your level", "body": "Start with a CEFR level, then switch any time.", "target": "[data-eds-level]"},
    {"id": "tabs", "title": "Browse the day", "body": "Read news, culture and history in both text and audio.", "target": "[data-eds-tabs]"},
    {"id": "phrase", "title": "Learn the phrase", "body": "Each level has one word, expression and history term.", "target": "[data-eds-phrase]"},
    {"id": "exercises", "title": "Practise actively", "body": "Answer three short exercises to review what you learned.", "target": "[data-eds-exercises]"},
    {"id": "glossary", "title": "Build your glossary", "body": "Star items, export them to Anki, and keep your progress.", "target": "[data-eds-glossary]"},
)


def _duration(seconds: Any) -> str:
    try:
        value = max(0, int(seconds or 0))
    except (TypeError, ValueError):
        return ""
    return f"{value // 60}:{value % 60:02d}"


def _choices(values: list[str], answer: str, count: int = 4) -> list[str]:
    options = [answer] + [value for value in values if value and value != answer]
    unique: list[str] = []
    for value in sorted(set(options)):
        if value not in unique:
            unique.append(value)
    return unique[:count]


def _cloze(expression: str) -> tuple[str, str]:
    tokens = re.findall(r"[\wÀ-ÿ’'-]+", expression)
    candidates = [
        token for token in tokens
        if len(token.strip("’'-")) > 2 and token.lower().strip("’'-") not in _CLOZE_STOPWORDS
    ]
    if not candidates:
        candidates = tokens
    target = max(candidates, key=lambda token: (len(token), token))
    prompt = re.sub(rf"\b{re.escape(target)}\b", "____", expression, count=1)
    return prompt, target


def _build_glossary(payloads: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    glossary: list[dict[str, Any]] = []
    for level in LEVELS:
        payload = payloads.get(level) or {}
        for kind in ("word", "expression", "history"):
            item = payload.get(kind) or {}
            text = str(item.get("text") or item.get("expression") or "")
            if not text:
                continue
            glossary.append({
                "key": str(item.get("key") or f"{level}:{kind}:{text}"),
                "kind": kind,
                "level": level,
                "text": text,
                "meaning": str(item.get("meaning") or ""),
                "meaning_fr": str(item.get("meaning_fr") or ""),
                "example": str(item.get("example") or ""),
                "phonetic": str(item.get("phonetic") or ""),
                "anki_answer": str(item.get("anki_answer") or item.get("meaning_fr") or ""),
                "tags": [str(tag) for tag in (item.get("tags") or [])],
            })
    return glossary


def _build_exercises(payloads: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    words = [(level, (payloads.get(level) or {}).get("word") or {}) for level in LEVELS]
    expressions = [(level, (payloads.get(level) or {}).get("expression") or {}) for level in LEVELS]
    histories = [(level, (payloads.get(level) or {}).get("history") or {}) for level in LEVELS]
    word_choices = [str(item.get("meaning_fr") or "") for _, item in words]
    expression_choices = [
        token
        for _, item in expressions
        for token in re.findall(r"[\wÀ-ÿ’'-]+", str(item.get("expression") or ""))
        if len(token.strip("’'-")) > 2 and token.lower() not in _CLOZE_STOPWORDS
    ]
    period_choices = [str(item.get("period") or "") for _, item in histories]
    exercises: list[dict[str, Any]] = []
    for level in LEVELS:
        word = (payloads.get(level) or {}).get("word") or {}
        expression = (payloads.get(level) or {}).get("expression") or {}
        history = (payloads.get(level) or {}).get("history") or {}
        word_text = str(word.get("text") or "")
        if word_text:
            answer = str(word.get("meaning_fr") or "")
            exercises.append({
                "id": f"{level}-word", "type": "multiple-choice", "kind": "word", "level": level,
                "prompt": f"What does “{word_text}” mean?", "options": _choices(word_choices, answer),
                "answer": answer, "item_key": str(word.get("key") or ""),
            })
        expression_text = str(expression.get("expression") or "")
        if expression_text:
            prompt, answer = _cloze(expression_text)
            exercises.append({
                "id": f"{level}-expression", "type": "cloze", "kind": "expression", "level": level,
                "prompt": f"Complete the expression: {prompt}", "options": _choices(expression_choices, answer),
                "answer": answer, "item_key": str(expression.get("key") or ""),
            })
        history_text = str(history.get("text") or "")
        if history_text:
            answer = str(history.get("period") or "General")
            exercises.append({
                "id": f"{level}-history", "type": "multiple-choice", "kind": "history", "level": level,
                "prompt": f"Which period does “{history_text}” belong to?",
                "options": _choices(period_choices or ["General"], answer),
                "answer": answer, "item_key": str(history.get("key") or ""),
            })
    return exercises


def excerpt(text: str | None, limit: int, config: dict[str, Any] | None = None) -> str:
    try:
        maximum = int(limit)
    except (TypeError, ValueError):
        return ""
    if maximum <= 0:
        return ""
    value = clean_text(str(text or ""), config)
    value = re.sub(r"\s+", " ", value).strip()
    if not value:
        return ""
    words = value.split(" ")
    if len(words) <= maximum:
        return value
    prefix = " ".join(words[:maximum])
    fallback_minimum = max(4, maximum // 3)
    configured = int((config or {}).get("excerpt_min_sentence_words", fallback_minimum))
    minimum = max(4, configured)
    sentences = [
        prefix[:match.start() + 1].strip()
        for match in _SENTENCE_END_RE.finditer(prefix)
        if len(prefix[:match.start() + 1].split()) >= minimum
    ]
    if sentences:
        return sentences[-1].rstrip()
    clauses = [
        prefix[:match.start()].strip()
        for match in _CLAUSE_END_RE.finditer(prefix)
        if len(prefix[:match.start()].split()) >= minimum
    ]
    if clauses:
        return clauses[-1].rstrip(" ,;:—–") + "…"
    return prefix.rstrip(" ,;:—–") + "…"


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
        body_text = excerpt(str(body_text or ""), int(config["excerpt_words"]), config)
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
        "alt_text": f"{row['title']} — {row['source_name'] or row['source_id']}",
        "duration_formatted": _duration(row["duration_sec"]) if kind == "audio" else "",
        "source_url": row["source_feed_url"] if "source_feed_url" in row.keys() else None,
        "reading_time_min": max(1, (int(row["word_count"] or 0) + 199) // 200) if kind == "text" else 0,
    }


def serialize_day(
    conn: Any,
    day: str,
    level: str,
    config: dict[str, Any],
    public_mode: bool = False,
    audio_base: str | None = None,
    lang: str | None = None,
    data_base: str | None = None,
) -> dict[str, Any]:
    from app.db import default_language

    language = str(lang or default_language(config))
    rows = conn.execute(
        """SELECT p.category AS pick_category, p.kind AS pick_kind, p.level AS slot_level,
                  p.origin AS pick_origin, p.badges AS pick_badges,
                   i.*, s.name AS source_name, s.feed_url AS source_feed_url
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
    phrase_payloads = load_phrases(conn, day, language)
    glossary = _build_glossary(phrase_payloads)
    exercises = _build_exercises(phrase_payloads)
    periods: set[str] = set()
    themes: set[str] = set()
    source_ids: set[str] = set()
    for category in CATEGORIES:
        for kind in KINDS:
            item = slots[category][kind]
            if not item:
                continue
            if item.get("source_id"):
                source_ids.add(str(item["source_id"]))
            for period in item.get("periods") or []:
                periods.add(str(period))
            for theme in item.get("themes") or []:
                themes.add(str(theme))
    search_path = (
        f"{data_base}{language}/search/{day}.json"
        if data_base
        else f"/api/search?day={day}&lang={language}"
    )
    return {
        "date": day,
        "lang": language,
        "level": level,
        "slots": slots,
        "phrase": phrase_payloads.get(level),
        "glossary": glossary,
        "exercises": exercises,
        "tour": list(_TOUR_STEPS),
        "meta": {
            "contract_version": 2,
            "filled": filled,
            "total": len(CATEGORIES) * len(KINDS),
            "origins": origins,
            "source_count": len(source_ids),
            "phrase_count": len(phrase_payloads),
            "glossary_count": len(glossary),
            "exercise_count": len(exercises),
            "history_periods": sorted(periods),
            "history_themes": sorted(themes),
            "search_path": search_path,
        },
    }
