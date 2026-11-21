from __future__ import annotations

import datetime as dt
import json
import re
import shutil
from pathlib import Path
from typing import Any

from app.db import PROJECT_ROOT, load_sources

_DAY_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def available_languages(config: dict[str, Any] | None = None) -> list[str]:
    config = config or {}
    languages = [str(value) for value in (config.get("languages") or []) if str(value).strip()]
    if not languages:
        source_languages = {str(src.get("lang") or "en") for src in load_sources()}
        languages = sorted(source_languages) or ["en"]
    return list(dict.fromkeys(languages))


def default_language(config: dict[str, Any] | None = None) -> str:
    config = config or {}
    default = str(config.get("default_language") or "en")
    languages = available_languages(config)
    return default if default in languages else (languages[0] if languages else "en")


def normalize_language(config: dict[str, Any] | None, lang: str | None) -> str:
    value = str(lang or default_language(config))
    languages = available_languages(config)
    return value if value in languages else default_language(config)


def state_lang_dir(state_dir: str | Path, lang: str | None = None) -> Path:
    root = Path(state_dir)
    language = str(lang or "en")
    return root / language


def site_lang_dir(site_dir: str | Path, lang: str | None = None) -> Path:
    root = Path(site_dir) / "data"
    language = str(lang or "en")
    return root / language


def site_index_path(site_dir: str | Path, lang: str | None = None) -> Path:
    return site_lang_dir(site_dir, lang) / "index.json"


def site_day_dir(site_dir: str | Path, day: str, lang: str | None = None) -> Path:
    return site_lang_dir(site_dir, lang) / day


def site_level_path(site_dir: str | Path, day: str, level: str, lang: str | None = None) -> Path:
    return site_day_dir(site_dir, day, lang) / f"{level}.json"


def site_phrase_path(site_dir: str | Path, day: str, lang: str | None = None) -> Path:
    return site_day_dir(site_dir, day, lang) / "phrases.json"


def site_search_dir(site_dir: str | Path, lang: str | None = None) -> Path:
    return site_lang_dir(site_dir, lang) / "search"


def languages_path(site_dir: str | Path) -> Path:
    return Path(site_dir) / "data" / "languages.json"


def _move(source: Path, target: Path) -> None:
    if not source.exists() or target.exists():
        return
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.move(str(source), str(target))


def migrate_legacy_state(state_dir: str | Path, lang: str | None = None) -> list[str]:
    root = Path(state_dir)
    language = str(lang or "en")
    target_root = state_lang_dir(root, language)
    moved: list[str] = []
    for name in ("used.json", "phrase_used.json", "books.json", "wiki_cache.json"):
        source = root / name
        if source.exists():
            _move(source, target_root / name)
            moved.append(name)
    source_pool = root / "pool"
    if source_pool.is_dir() and not (target_root / "pool").exists():
        target_root.mkdir(parents=True, exist_ok=True)
        shutil.move(str(source_pool), str(target_root / "pool"))
        moved.append("pool")
    return moved


def migrate_legacy_site(site_dir: str | Path, lang: str | None = None) -> list[str]:
    root = Path(site_dir) / "data"
    language = str(lang or "en")
    target_root = site_lang_dir(site_dir, language)
    moved: list[str] = []
    if not root.is_dir():
        return moved
    for child in sorted(root.iterdir()):
        if child.name == language or child.name == "languages.json":
            continue
        if child.is_dir() and not _DAY_RE.fullmatch(child.name):
            continue
        if child.is_file() and child.suffix != ".json":
            continue
        _move(child, target_root / child.name)
        moved.append(child.name)
    return moved


def write_languages(site_dir: str | Path, config: dict[str, Any]) -> Path:
    path = languages_path(site_dir)
    languages = available_languages(config)
    payload = {
        "generated_at": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z"),
        "default": default_language(config),
        "languages": languages,
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    temporary.replace(path)
    return path


def project_state_dir() -> Path:
    return PROJECT_ROOT / "state"
