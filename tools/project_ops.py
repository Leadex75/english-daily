from __future__ import annotations

import datetime as dt
import shutil
from pathlib import Path
from typing import Any

import yaml

from app.db import (
    available_languages,
    connect,
    data_dir,
    db_path,
    default_language,
    init_db,
    language_metadata,
    load_sources,
    normalize_language,
    today,
    upsert_sources,
)
from ingest.export_static import export_static
from ingest.pipeline import run_ingest
from ingest.readability import LEVELS

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def _resolve_path(value: str | Path) -> Path:
    path = Path(value)
    return path if path.is_absolute() else PROJECT_ROOT / path


def validate_config(config: dict[str, Any]) -> dict[str, Any]:
    issues: list[str] = []
    for key in ("data_dir", "default_language", "languages", "levels"):
        if not config.get(key):
            issues.append(f"missing required config key: {key}")

    languages = available_languages(config)
    fallback = default_language(config)
    if fallback not in languages:
        issues.append(f"default_language is not available: {fallback}")

    raw_languages = config.get("languages")
    for language in languages:
        entry = raw_languages.get(language) or {} if isinstance(raw_languages, dict) else {}
        for field in ("brand", "label", "tagline"):
            if not str(entry.get(field) or "").strip():
                issues.append(f"{language}: missing {field} metadata")
        levels = (config.get("levels") or {}).get(language) or {}
        thresholds = levels.get("thresholds") or config.get("level_thresholds") or {}
        missing_thresholds = [level for level in LEVELS[:-1] if level not in thresholds]
        if missing_thresholds:
            issues.append(f"{language}: missing thresholds for {', '.join(missing_thresholds)}")
        word_bands = levels.get("word_bands") or config.get("word_bands") or {}
        missing_bands = [level for level in LEVELS if level not in word_bands]
        if missing_bands:
            issues.append(f"{language}: missing word bands for {', '.join(missing_bands)}")

    if config.get("audio_mode") not in {"local", "hotlink"}:
        issues.append("audio_mode must be local or hotlink")
    try:
        if float(config.get("request_timeout_sec", 0)) <= 0:
            issues.append("request_timeout_sec must be positive")
    except (TypeError, ValueError):
        issues.append("request_timeout_sec must be numeric")
    if "/english-daily" not in str(config.get("online_site_url", "")):
        issues.append("online_site_url must point at the english-daily site")
    if "github.com/Leadex75/english-daily" not in str(config.get("user_agent", "")):
        issues.append("user_agent must include the repository URL")

    return {
        "ok": not issues,
        "issues": issues,
        "languages": languages,
        "default_language": fallback,
    }


def _demo_sources(languages: list[str]) -> list[dict[str, Any]]:
    sources: list[dict[str, Any]] = []
    for language in languages:
        for kind in ("text", "audio"):
            sources.append({
                "id": f"demo_{language}_{kind}",
                "name": f"Demo {language} {kind}",
                "feed_url": "generated",
                "category": "news",
                "kind": kind,
                "level_min": "B1",
                "level_max": "B1",
                "enabled": True,
                "lang": language,
            })
    return sources


def default_demo_dates(config: dict[str, Any]) -> list[str]:
    current = dt.date.fromisoformat(today(config))
    return [current.isoformat(), (current - dt.timedelta(days=1)).isoformat()]


def build_demo_data(
    config: dict[str, Any],
    out: str | Path,
    state_dir: str | Path,
    dates: list[str] | None = None,
) -> dict[str, Any]:
    demo_config = dict(config)
    demo_config["ingest_offline"] = True
    demo_config["reserve_offline"] = True
    demo_config["phrase_offline"] = True
    demo_config["public_mode"] = True
    languages = available_languages(demo_config)
    days = dates or default_demo_dates(demo_config)
    target = _resolve_path(out)
    state = _resolve_path(state_dir)

    init_db(demo_config)
    upsert_sources(_demo_sources(languages), demo_config)
    conn = connect(demo_config)
    try:
        for day in days:
            for language in languages:
                title = (
                    "Renaissance art and reform"
                    if language == "en"
                    else "Renacimiento y reforma"
                )
                audio_title = (
                    "Museum audio guide" if language == "en" else "Guía audio del museo"
                )
                body = ("word " if language == "en" else "palabra ") * 200
                for kind, item_title, duration in (
                    ("text", title, None),
                    ("audio", audio_title, 120),
                ):
                    conn.execute(
                        """INSERT OR REPLACE INTO items
                           (guid_hash, source_id, kind, category, title, url, summary,
                            published_at, fetched_at, body_text, word_count, duration_sec,
                            audio_remote_url, score, level, level_method, origin, lang)
                           VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                        (
                            f"demo-{language}-{kind}-{day}",
                            f"demo_{language}_{kind}",
                            kind,
                            "news",
                            item_title,
                            f"https://example.org/{language}/{kind}/{day}",
                            item_title,
                            day,
                            day,
                            body,
                            200,
                            duration,
                            f"https://example.org/{language}/{day}.mp3" if kind == "audio" else None,
                            0.5,
                            "B1",
                            "computed",
                            "fresh",
                            language,
                        ),
                    )
            conn.commit()
    finally:
        conn.close()

    for language in languages:
        for day in days:
            run_ingest(day, demo_config, state_dir=str(state), lang=language)
    summary = export_static(target, demo_config, public_mode=True)
    return {
        "out": str(target),
        "state_dir": str(state),
        "languages": languages,
        "dates": days,
        "sites": summary.get("days", []),
        "level_files": summary.get("written", 0),
    }


def backup_database(config: dict[str, Any], out: str | Path | None = None) -> dict[str, Any]:
    source = db_path(config)
    if not source.is_file():
        init_db(config)
    stamp = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%d%H%M%S")
    target = _resolve_path(out) if out else source.with_name(f"{source.name}.bak-{stamp}")
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, target)
    return {
        "source": str(source),
        "backup": str(target),
        "bytes": target.stat().st_size,
    }


def restore_database(
    config: dict[str, Any], source: str | Path, force: bool = False
) -> dict[str, Any]:
    origin = _resolve_path(source)
    if not origin.is_file():
        raise FileNotFoundError(f"backup not found: {origin}")
    target = db_path(config)
    target.parent.mkdir(parents=True, exist_ok=True)
    safety: dict[str, Any] | None = None
    if target.exists():
        if not force:
            raise FileExistsError(f"database already exists: {target}")
        stamp = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%d%H%M%S")
        safety = backup_database(config, target.with_name(f"{target.name}.pre-restore-{stamp}"))
    shutil.copy2(origin, target)
    return {
        "source": str(origin),
        "target": str(target),
        "bytes": target.stat().st_size,
        "safety_backup": safety["backup"] if safety else None,
    }


def _bank_count(language: str, name: str) -> int:
    path = PROJECT_ROOT / "bank" / language / f"{name}.yaml"
    if not path.is_file():
        return 0
    payload = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    total = 0
    for value in payload.values():
        if isinstance(value, list):
            total += len(value)
    return total


def calibrate_report(config: dict[str, Any], lang: str | None = None) -> dict[str, Any]:
    languages = [normalize_language(config, lang)] if lang else available_languages(config)
    sources = load_sources()
    database = db_path(config)
    reports: dict[str, Any] = {}
    for language in languages:
        levels = (config.get("levels") or {}).get(language) or {}
        thresholds = levels.get("thresholds") or config.get("level_thresholds") or {}
        words = _bank_count(language, "words")
        expressions = _bank_count(language, "expressions")
        history = _bank_count(language, "history_terms")
        item_counts = {level: 0 for level in LEVELS}
        phrase_counts = {level: 0 for level in LEVELS}
        if database.is_file():
            conn = connect(config)
            try:
                for level in LEVELS:
                    item_counts[level] = conn.execute(
                        "SELECT COUNT(*) FROM items WHERE lang=? AND level=?",
                        (language, level),
                    ).fetchone()[0]
                    phrase_counts[level] = conn.execute(
                        "SELECT COUNT(*) FROM phrases WHERE lang=? AND level=?",
                        (language, level),
                    ).fetchone()[0]
            finally:
                conn.close()
        warnings: list[str] = []
        source_count = sum(
            1 for source in sources
            if source.get("lang") == language and source.get("enabled", True)
        )
        if source_count == 0:
            warnings.append("no enabled sources")
        if words < 120:
            warnings.append("word bank below 120 entries")
        if expressions < 120:
            warnings.append("expression bank below 120 entries")
        if history < 120:
            warnings.append("history bank below 120 entries")
        if any(level not in thresholds for level in LEVELS[:-1]):
            warnings.append("readability thresholds are incomplete")
        reports[language] = {
            "brand": language_metadata(config, language)["brand"],
            "sources": source_count,
            "bank": {"words": words, "expressions": expressions, "history_terms": history},
            "thresholds": {level: thresholds.get(level) for level in LEVELS},
            "items": item_counts,
            "phrases": phrase_counts,
            "warnings": warnings,
        }
    return {"languages": languages, "reports": reports}
