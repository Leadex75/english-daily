from __future__ import annotations

import json
import re
from typing import Any

from app.serialize import excerpt
from ingest.phrases import load_phrases

_TOKEN_RE = re.compile(r"[\wÀ-ÿ’'-]+", re.UNICODE)


def _tokens(value: str) -> list[str]:
    return [token.strip("’'-") for token in _TOKEN_RE.findall(str(value or "").lower()) if token.strip("’'-")]


def _json_list(value: Any) -> list[Any]:
    try:
        payload = json.loads(str(value or "[]"))
    except (TypeError, ValueError):
        return []
    return payload if isinstance(payload, list) else []


def _rows(conn: Any, language: str, day: str | None) -> list[Any]:
    sql = """SELECT p.date AS pick_date, p.level AS slot_level, p.category AS pick_category,
                    p.kind AS pick_kind, i.*, s.name AS source_name
             FROM daily_picks p
             JOIN items i ON i.id=p.item_id
             LEFT JOIN sources s ON s.id=i.source_id
             WHERE p.lang=?"""
    params: list[Any] = [language]
    if day:
        sql += " AND p.date=?"
        params.append(day)
    sql += " ORDER BY p.date DESC, i.id"
    return conn.execute(sql, tuple(params)).fetchall()


def _phrase_days(conn: Any, language: str, day: str | None) -> list[str]:
    if day:
        return [day]
    rows = conn.execute(
        "SELECT DISTINCT date FROM phrases WHERE lang=? ORDER BY date DESC", (language,)
    ).fetchall()
    return [str(row[0]) for row in rows]


def build_search_index(
    conn: Any,
    config: dict[str, Any],
    lang: str | None = None,
    day: str | None = None,
    public_mode: bool = False,
) -> dict[str, Any]:
    language = str(lang or "en")
    items: list[dict[str, Any]] = []
    open_licenses = {"cc_by", "cc_by_sa", "public_domain", "public_domain_us_gov"}
    for row in _rows(conn, language, day):
        license_name = str(row["license"] or "proprietary")
        body = str(row["body_text"] or "") if str(row["kind"]) == "text" else str(row["summary"] or "")
        if public_mode and license_name not in open_licenses:
            body = excerpt(body, int(config.get("excerpt_words", 120)), config)
        terms = [str(term.get("text") or term) for term in _json_list(row["history_terms"]) if isinstance(term, dict)]
        items.append({
            "id": int(row["id"]),
            "guid_hash": row["guid_hash"],
            "date": str(row["pick_date"]),
            "level": str(row["slot_level"]),
            "category": str(row["pick_category"]),
            "kind": str(row["pick_kind"]),
            "title": str(row["title"] or ""),
            "source": str(row["source_name"] or row["source_id"] or ""),
            "url": row["url"],
            "summary": str(row["summary"] or ""),
            "body": body[:3000],
            "periods": _json_list(row["periods"] if "periods" in row.keys() else "[]"),
            "themes": _json_list(row["themes"] if "themes" in row.keys() else "[]"),
            "history_terms": terms,
        })

    for phrase_day in _phrase_days(conn, language, day):
        payloads = load_phrases(conn, phrase_day, language)
        for level, payload in payloads.items():
            for kind in ("word", "expression", "history"):
                item = payload.get(kind) or {}
                text = str(item.get("text") or item.get("expression") or "")
                if not text:
                    continue
                items.append({
                    "id": 0,
                    "guid_hash": str(item.get("key") or f"phrase:{phrase_day}:{level}:{kind}"),
                    "date": phrase_day,
                    "level": str(level),
                    "category": "phrase",
                    "kind": f"phrase:{kind}",
                    "title": text,
                    "source": "Phrase of the day",
                    "url": None,
                    "summary": str(item.get("meaning") or ""),
                    "body": " ".join(
                        str(item.get(key) or "")
                        for key in ("meaning", "meaning_fr", "example")
                    ).strip(),
                    "periods": [],
                    "themes": [],
                    "history_terms": [],
                })
    return {
        "lang": language,
        "day": day,
        "public_mode": bool(public_mode),
        "items": items,
    }


def search_index(
    index: dict[str, Any],
    query: str,
    day: str | None = None,
    level: str | None = None,
    limit: int = 20,
) -> list[dict[str, Any]]:
    terms = _tokens(query)
    if not terms:
        return []
    results: list[dict[str, Any]] = []
    for item in index.get("items") or []:
        if day and str(item.get("date")) != day:
            continue
        if level and str(item.get("level")) != level:
            continue
        title = str(item.get("title") or "")
        body = str(item.get("body") or "")
        summary = str(item.get("summary") or "")
        source = str(item.get("source") or "")
        terms_list = [str(value) for value in (item.get("history_terms") or [])]
        score = 0
        matched: list[str] = []
        for term in terms:
            weight = 0
            if term in _tokens(title):
                weight += 6
            if term in _tokens(" ".join(terms_list)):
                weight += 4
            if term in _tokens(summary):
                weight += 2
            if term in _tokens(body):
                weight += 1
            if term in _tokens(source):
                weight += 1
            if weight:
                score += weight
                if term not in matched:
                    matched.append(term)
        if not score:
            continue
        snippet = body or summary or title
        snippet = " ".join(snippet.split())[:240]
        results.append({
            "score": score,
            "matched_terms": matched,
            "date": item.get("date"),
            "level": item.get("level"),
            "category": item.get("category"),
            "kind": item.get("kind"),
            "title": title,
            "source": item.get("source"),
            "url": item.get("url"),
            "guid_hash": item.get("guid_hash"),
            "snippet": snippet,
        })
    results.sort(key=lambda item: (-int(item["score"]), str(item["date"]), str(item["title"])))
    limit = max(1, min(100, int(limit)))
    return results[:limit]
