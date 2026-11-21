from __future__ import annotations

import datetime as dt
import json
from pathlib import Path
from typing import Any, Iterable

from app.db import default_language, today
from ingest.paths import migrate_legacy_state, state_lang_dir

STATE_FILE = "used.json"
PRUNE_DAYS = 30


def state_path(
    state_dir: str | Path, config: dict[str, Any] | None = None, lang: str | None = None
) -> Path:
    root = Path(state_dir)
    language = str(lang or (default_language(config) if config else "en"))
    migrate_legacy_state(root, language)
    return state_lang_dir(root, language) / STATE_FILE


def load_entries(
    state_dir: str | Path, config: dict[str, Any] | None = None, lang: str | None = None
) -> list[dict[str, str]]:
    path = state_path(state_dir, config, lang)
    if not path.is_file():
        return []
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
        guid_hash = str(raw.get("guid_hash") or "")
        date = str(raw.get("date") or "")
        if guid_hash and date:
            entries.append({"guid_hash": guid_hash, "date": date})
    return entries


def prune_entries(entries: Iterable[dict[str, str]], config: dict[str, Any]) -> list[dict[str, str]]:
    try:
        cutoff = dt.date.fromisoformat(today(config)).toordinal() - PRUNE_DAYS
    except Exception:
        return list(entries)
    unique: dict[str, dict[str, str]] = {}
    for entry in entries:
        try:
            day = dt.date.fromisoformat(str(entry["date"])[:10]).toordinal()
        except Exception:
            continue
        if day < cutoff:
            continue
        current = unique.get(entry["guid_hash"])
        if current is None or day >= dt.date.fromisoformat(current["date"]).toordinal():
            unique[entry["guid_hash"]] = {"guid_hash": entry["guid_hash"], "date": str(entry["date"])[:10]}
    return [unique[key] for key in sorted(unique)]


def save_entries(
    state_dir: str | Path,
    entries: Iterable[dict[str, str]],
    config: dict[str, Any],
    lang: str | None = None,
) -> int:
    cleaned = prune_entries(entries, config)
    path = state_path(state_dir, config, lang)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(cleaned, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    temporary.replace(path)
    return len(cleaned)


def used_hashes(
    state_dir: str | Path | None,
    config: dict[str, Any],
    lang: str | None = None,
) -> set[str]:
    if not state_dir:
        return set()
    return {
        str(entry["guid_hash"])
        for entry in prune_entries(load_entries(state_dir, config, lang), config)
    }


def record_picks(
    state_dir: str | Path | None,
    config: dict[str, Any],
    day: str,
    hashes: Iterable[str],
    lang: str | None = None,
) -> int:
    if not state_dir:
        return 0
    entries = load_entries(state_dir, config, lang)
    known = {(str(entry["guid_hash"]), str(entry["date"])[:10]) for entry in entries}
    for guid_hash in hashes:
        pair = (str(guid_hash), str(day)[:10])
        if pair not in known:
            entries.append({"guid_hash": pair[0], "date": pair[1]})
            known.add(pair)
    return save_entries(state_dir, entries, config, lang)


def import_site_state(
    site_dir: str | Path,
    state_dir: str | Path,
    config: dict[str, Any],
    lang: str | None = None,
) -> tuple[int, int]:
    from ingest.paths import site_lang_dir

    language = str(lang or default_language(config))
    entries = load_entries(state_dir, config, language)
    known = {(str(entry["guid_hash"]), str(entry["date"])[:10]) for entry in entries}
    added = 0
    for path in sorted((site_lang_dir(site_dir, language)).glob("*/*.json")):
        if path.name == "index.json":
            continue
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if not isinstance(payload, dict):
            continue
        date = str(payload.get("date") or path.parent.name)[:10]
        for category in ("news", "culture", "history"):
            for kind in ("text", "audio"):
                item = ((payload.get("slots") or {}).get(category) or {}).get(kind)
                if not isinstance(item, dict):
                    continue
                guid_hash = str(item.get("guid_hash") or "")
                pair = (guid_hash, date)
                if guid_hash and pair not in known:
                    entries.append({"guid_hash": guid_hash, "date": date})
                    known.add(pair)
                    added += 1
    return added, save_entries(state_dir, entries, config, language)
