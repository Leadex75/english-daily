from __future__ import annotations

import datetime as dt
import hashlib
import json
import os
import random
import re
from pathlib import Path
from typing import Any, Iterable
from urllib.parse import quote

import feedparser
import yaml

from app.db import PROJECT_ROOT, default_language, language_setting
from ingest.paths import state_lang_dir
from ingest.fetch_feeds import http_get, plain_text

BANK_DIR = PROJECT_ROOT / "bank"
PHRASE_STATE_FILE = "phrase_used.json"
LEVELS = ["A1", "A2", "B1", "B2", "C1", "C2"]


def phrase_state_path(
    state_dir: str | Path, config: dict[str, Any] | None = None, lang: str | None = None
) -> Path:
    language = str(lang or (default_language(config) if config else "en"))
    return state_lang_dir(state_dir, language) / PHRASE_STATE_FILE


def bank_dir(lang: str | None = None) -> Path:
    return BANK_DIR / str(lang or "en")


def load_bank(name: str, lang: str | None = None) -> list[dict[str, Any]]:
    path = bank_dir(lang) / f"{name}.yaml"
    with path.open("r", encoding="utf-8") as handle:
        data = yaml.safe_load(handle) or {}
    return [dict(item) for item in (data.get(name) or []) if isinstance(item, dict)]


def load_history_terms(lang: str | None = None) -> list[dict[str, Any]]:
    path = bank_dir(lang) / "history_terms.yaml"
    if not path.is_file():
        return []
    with path.open("r", encoding="utf-8") as handle:
        data = yaml.safe_load(handle) or {}
    return [dict(item) for item in (data.get("terms") or []) if isinstance(item, dict)]


def _history_label(value: str, config: dict[str, Any], key: str, lang: str | None) -> str:
    raw = str(value or "").strip()
    if not raw:
        return ""
    configured = language_setting(config, key, lang) or {}
    if isinstance(configured, dict):
        for label in configured:
            if str(label).strip().lower() == raw.lower():
                return str(label)
    return raw


def annotate_history(
    item: dict[str, Any], config: dict[str, Any], lang: str | None = None
) -> dict[str, Any]:
    payload = dict(item)
    if str(payload.get("category") or "") != "history":
        return payload
    haystack = " ".join(
        str(payload.get(key) or "")
        for key in ("title", "summary", "body_text")
    ).lower()
    if not haystack.strip():
        return payload
    matched: list[dict[str, Any]] = []
    periods: list[str] = []
    themes: list[str] = []
    for term in load_history_terms(lang):
        aliases = list(term.get("aliases") or [])
        aliases.append(str(term.get("text") or ""))
        patterns = [
            rf"\b{re.escape(str(alias).lower())}\b"
            for alias in aliases if str(alias).strip()
        ]
        if not any(re.search(pattern, haystack) for pattern in patterns):
            continue
        matched.append(dict(term))
        period = _history_label(term.get("period"), config, "history_periods", lang)
        theme = _history_label(term.get("theme"), config, "history_themes", lang)
        if period and period not in periods:
            periods.append(period)
        if theme and theme not in themes:
            themes.append(theme)
    if matched:
        payload["history_terms"] = matched[:8]
        payload["periods"] = list(dict.fromkeys(list(payload.get("periods") or []) + periods))
        payload["themes"] = list(dict.fromkeys(list(payload.get("themes") or []) + themes))
    return payload


def phrase_key(item: dict[str, Any], kind: str) -> str:
    value = str(item.get("text") or item.get("expression") or "")
    return hashlib.sha1(f"{kind}:{value}".encode("utf-8")).hexdigest()


def load_phrase_state(
    state_dir: str | Path, config: dict[str, Any] | None = None, lang: str | None = None
) -> list[dict[str, str]]:
    path = phrase_state_path(state_dir, config, lang)
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    if not isinstance(payload, list):
        return []
    entries: list[dict[str, str]] = []
    for raw in payload:
        if not isinstance(raw, dict):
            continue
        key = str(raw.get("key") or "")
        date = str(raw.get("date") or "")[:10]
        if key and date:
            entries.append({"key": key, "date": date})
    return entries


def save_phrase_state(
    state_dir: str | Path,
    entries: Iterable[dict[str, str]],
    config: dict[str, Any],
    lang: str | None = None,
) -> int:
    history_days = int(config.get("phrase_history_days", 400))
    try:
        cutoff = dt.date.fromisoformat(str(config.get("_day") or dt.date.today().isoformat())) - dt.timedelta(days=history_days)
    except ValueError:
        cutoff = dt.date.today() - dt.timedelta(days=history_days)
    unique: dict[str, str] = {}
    for entry in entries:
        try:
            day = dt.date.fromisoformat(str(entry["date"])[:10])
        except (KeyError, ValueError):
            continue
        if day >= cutoff:
            unique[str(entry["key"])] = day.isoformat()
    cleaned = [{"key": key, "date": day} for key, day in sorted(unique.items())]
    path = phrase_state_path(state_dir, config, lang)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(cleaned, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    temporary.replace(path)
    return len(cleaned)


def _choose(
    items: list[dict[str, Any]],
    kind: str,
    day: str,
    level: str,
    used: set[str],
) -> dict[str, Any]:
    available = [dict(item) for item in items if str(item.get("level")) == level]
    fresh = [item for item in available if phrase_key(item, kind) not in used]
    pool = fresh or available
    if not pool:
        raise ValueError(f"empty {kind} bank for level {level}")
    seed = "|".join(("english-daily", day, level, kind))
    chosen = random.Random(seed).choice(sorted(pool, key=lambda item: str(item.get("text") or item.get("expression"))))
    chosen["key"] = phrase_key(chosen, kind)
    chosen["kind"] = kind
    return chosen


def _definitions(payload: Any) -> list[str]:
    found: list[str] = []

    def walk(value: Any) -> None:
        if isinstance(value, dict):
            for key, child in value.items():
                if key in {"definition", "def"} and isinstance(child, str) and child.strip():
                    found.append(child.strip())
                else:
                    walk(child)
        elif isinstance(value, list):
            for child in value:
                walk(child)

    walk(payload)
    unique: list[str] = []
    for definition in found:
        if definition not in unique:
            unique.append(definition)
    return unique[:4]


def _dictionary(word: str, config: dict[str, Any], lang: str | None = None) -> dict[str, Any]:
    language = str(lang or "en")
    url = f"https://api.dictionaryapi.dev/api/v2/entries/{language}/{quote(word)}"
    try:
        response = http_get(url, config)
        if response.status_code != 200:
            return {}
        payload = response.json()
        entries = payload if isinstance(payload, list) else [payload]
        entry = entries[0] if entries and isinstance(entries[0], dict) else {}
        phonetics = [
            str(item.get("text") or "")
            for item in entry.get("phonetics") or []
            if isinstance(item, dict) and item.get("text")
        ]
        meanings: list[str] = []
        for meaning in entry.get("meanings") or []:
            if not isinstance(meaning, dict):
                continue
            for definition in meaning.get("definitions") or []:
                if isinstance(definition, dict) and definition.get("definition"):
                    meanings.append(str(definition["definition"]).strip())
        audio = next(
            (
                str(item.get("audio"))
                for item in entry.get("phonetics") or []
                if isinstance(item, dict) and str(item.get("audio") or "").startswith("https://")
            ),
            None,
        )
        return {
            "phonetic": phonetics[0] if phonetics else None,
            "definitions": meanings[:4],
            "audio_url": audio,
        }
    except Exception:
        return {}


def _wiktionary(term: str, config: dict[str, Any], lang: str | None = None) -> dict[str, Any]:
    language = str(lang or "en")
    url = f"https://{language}.wiktionary.org/api/rest_v1/page/definition/{quote(term)}"
    try:
        response = http_get(url, config, headers={"Accept": "application/json"})
        if response.status_code != 200:
            return {}
        return {"definitions": _definitions(response.json())}
    except Exception:
        return {}


def _phrase_audio(
    term: str, config: dict[str, Any], lang: str | None = None
) -> dict[str, Any] | None:
    source = next((src for src in _sources(config, lang) if str(src.get("id")) == "tews"), None)
    if not source:
        return None
    try:
        response = http_get(str(source["feed_url"]), config)
        if response.status_code != 200:
            return None
        parsed = feedparser.parse(response.content)
        needle = term.lower()
        for entry in parsed.entries:
            title = plain_text(entry.get("title"))
            if needle not in title.lower():
                continue
            audio = None
            for enclosure in entry.get("enclosures") or []:
                href = str(enclosure.get("href") or enclosure.get("url") or "")
                if href:
                    audio = href
                    break
            if audio:
                return {
                    "title": title,
                    "url": str(entry.get("link") or ""),
                    "audio_url": audio,
                }
    except Exception:
        return None
    return None


def _sources(config: dict[str, Any], lang: str | None = None) -> list[dict[str, Any]]:
    from app.db import load_sources

    return load_sources(config, lang)


def enrich(
    item: dict[str, Any], config: dict[str, Any], offline: bool = False, lang: str | None = None
) -> dict[str, Any]:
    payload = dict(item)
    payload["dictionary"] = {}
    payload["wiktionary"] = {}
    payload["audio"] = None
    if offline or bool(config.get("phrase_offline")) or os.environ.get("ENGLISH_DAILY_PHRASE_OFFLINE"):
        return payload
    term = str(payload.get("text") or payload.get("expression") or "")
    if not term:
        return payload
    if payload.get("kind") == "word":
        payload["dictionary"] = _dictionary(term, config, lang)
    payload["wiktionary"] = _wiktionary(term, config, lang)
    if payload.get("kind") == "expression":
        payload["audio"] = _phrase_audio(term, config, lang)
    return payload


def generate_phrases(
    config: dict[str, Any],
    day: str,
    state_dir: str | Path | None = None,
    offline: bool | None = None,
    lang: str | None = None,
) -> dict[str, dict[str, Any]]:
    root = Path(state_dir) if state_dir else PROJECT_ROOT / "state"
    config = dict(config)
    config["_day"] = day
    language = str(lang or default_language(config))
    state = load_phrase_state(root, config, language)
    used = {str(entry["key"]) for entry in state}
    words = load_bank("words", language)
    expressions = load_bank("expressions", language)
    history_terms = load_history_terms(language)
    if not words or not expressions or not history_terms:
        return {}
    offline_value = bool(config.get("phrase_offline")) if offline is None else bool(offline)
    result: dict[str, dict[str, Any]] = {}
    newly_used: list[dict[str, str]] = []
    for level in LEVELS:
        word = enrich(_choose(words, "word", day, level, used), config, offline_value, language)
        expression = enrich(_choose(expressions, "expression", day, level, used), config, offline_value, language)
        term = dict(_choose(history_terms, "history", day, level, used))
        term["kind"] = "history"
        newly_used.append({"key": str(word["key"]), "date": day})
        newly_used.append({"key": str(expression["key"]), "date": day})
        newly_used.append({"key": str(term["key"]), "date": day})
        used.update({str(word["key"]), str(expression["key"]), str(term["key"])})
        result[level] = {
            "date": day,
            "level": level,
            "word": word,
            "expression": expression,
            "history": term,
        }
    save_phrase_state(root, state + newly_used, config, language)
    return result


def store_phrases(
    conn: Any,
    day: str,
    payloads: dict[str, dict[str, Any]],
    lang: str | None = None,
) -> None:
    language = str(lang or "en")
    conn.execute("DELETE FROM phrases WHERE date=? AND lang=?", (day, language))
    for level, payload in payloads.items():
        conn.execute(
            "INSERT INTO phrases (lang, date, level, payload) VALUES (?,?,?,?)",
            (language, day, str(level), json.dumps(payload, ensure_ascii=False)),
        )
    conn.commit()


def load_phrases(conn: Any, day: str, lang: str | None = None) -> dict[str, dict[str, Any]]:
    language = str(lang or "en")
    payloads: dict[str, dict[str, Any]] = {}
    for row in conn.execute(
        "SELECT level, payload FROM phrases WHERE date=? AND lang=?", (day, language)
    ).fetchall():
        try:
            payloads[str(row["level"])] = json.loads(str(row["payload"]))
        except (TypeError, ValueError):
            continue
    return payloads
