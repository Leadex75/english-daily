from __future__ import annotations

import datetime as dt
import re
import shutil
import threading
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.db import (
    PROJECT_ROOT,
    connect,
    available_languages,
    data_dir,
    default_language,
    init_db,
    load_config,
    load_sources,
    normalize_language,
    source_registry,
    successful_ingest_exists,
    today,
    upsert_sources,
)
from app.serialize import serialize_day
from ingest.phrases import load_phrases
from ingest.pipeline import run_ingest
from ingest.readability import CATEGORIES, KINDS, LEVELS

app = FastAPI(title="english-daily", docs_url=None, redoc_url=None)
_ingest_lock = threading.Lock()


def _language(config: dict[str, Any], lang: str | None = None) -> str:
    return normalize_language(config, lang)


def _auto_ingest() -> None:
    config = load_config()
    day = today(config)
    if not config.get("auto_ingest_on_start") or all(
        successful_ingest_exists(day, config, language)
        for language in available_languages(config)
    ):
        return
    with _ingest_lock:
        for language in available_languages(config):
            if not successful_ingest_exists(day, config, language):
                run_ingest(day, config, lang=language)


@app.on_event("startup")
def startup() -> None:
    config = load_config()
    init_db(config)
    upsert_sources(load_sources(), config)
    if config.get("auto_ingest_on_start"):
        threading.Thread(target=_auto_ingest, name="auto-ingest", daemon=True).start()


def _valid_day(day: str) -> str:
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", day):
        raise HTTPException(status_code=400, detail="date must be YYYY-MM-DD")
    try:
        dt.date.fromisoformat(day)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="invalid date") from exc
    return day


@app.get("/api/health")
def health(lang: str | None = None) -> dict[str, Any]:
    config = load_config()
    language = _language(config, lang)
    conn = connect(config)
    try:
        sources = int(conn.execute(
            "SELECT COUNT(*) FROM sources WHERE enabled=1 AND lang=?", (language,)
        ).fetchone()[0])
    finally:
        conn.close()
    return {
        "status": "ok",
        "name": "english-daily",
        "lang": language,
        "languages": available_languages(config),
        "enabled_sources": sources,
        "ffmpeg": bool(shutil.which("ffmpeg")),
    }


@app.get("/api/days")
def days(lang: str | None = None) -> list[str]:
    config = load_config()
    language = _language(config, lang)
    conn = connect(config)
    try:
        rows = conn.execute(
            """SELECT date FROM (
                 SELECT date FROM ingest_runs WHERE lang=?
                 UNION SELECT date FROM phrases WHERE lang=?
               ) ORDER BY date DESC""",
            (language, language),
        ).fetchall()
        return [str(row[0]) for row in rows]
    finally:
        conn.close()


@app.get("/api/languages")
def languages() -> dict[str, Any]:
    config = load_config()
    return {
        "default": default_language(config),
        "languages": available_languages(config),
    }


@app.get("/api/sources")
def sources(lang: str | None = None) -> dict[str, Any]:
    config = load_config()
    language = _language(config, lang)
    return {
        "lang": language,
        "languages": available_languages(config),
        "sources": source_registry(config, language),
    }


@app.get("/api/day/{day}")
def day(day: str, level: str = "B1", lang: str | None = None) -> dict[str, Any]:
    day = _valid_day(day)
    if level not in LEVELS:
        raise HTTPException(status_code=400, detail=f"level must be one of {', '.join(LEVELS)}")
    config = load_config()
    language = _language(config, lang)
    conn = connect(config)
    try:
        return serialize_day(conn, day, level, config, lang=language)
    finally:
        conn.close()


@app.get("/api/phrase/{day}")
def phrase(day: str, level: str = "B1", lang: str | None = None) -> dict[str, Any]:
    day = _valid_day(day)
    if level not in LEVELS:
        raise HTTPException(status_code=400, detail=f"level must be one of {', '.join(LEVELS)}")
    config = load_config()
    language = _language(config, lang)
    conn = connect(config)
    try:
        payload = load_phrases(conn, day, language).get(level)
    finally:
        conn.close()
    if not payload:
        raise HTTPException(status_code=404, detail="no phrase for this date and level")
    return payload


@app.get("/api/stats")
def stats(days: int = 30, lang: str | None = None) -> dict[str, Any]:
    days = max(1, min(365, int(days)))
    config = load_config()
    language = _language(config, lang)
    conn = connect(config)
    try:
        rows = conn.execute(
            """SELECT level, category, kind, COUNT(*) AS total
               FROM daily_picks WHERE date >= date('now', ?) AND lang=?
               GROUP BY level, category, kind""",
            (f"-{days} days", language),
        ).fetchall()
        by_level: dict[str, dict[str, int]] = {
            level: {"filled": 0, "total": len(CATEGORIES) * len(KINDS)} for level in LEVELS
        }
        for row in rows:
            level = str(row["level"])
            if level in by_level:
                by_level[level]["filled"] += int(row["total"])
        phrase_days = int(conn.execute(
            "SELECT COUNT(DISTINCT date) FROM phrases WHERE lang=?", (language,)
        ).fetchone()[0])
        item_total = int(conn.execute(
            "SELECT COUNT(*) FROM items WHERE lang=?", (language,)
        ).fetchone()[0])
    finally:
        conn.close()
    return {
        "days": days,
        "lang": language,
        "weekly_goal": int(config.get("weekly_goal_default", 5)),
        "by_level": by_level,
        "phrase_days": phrase_days,
        "items": item_total,
    }


@app.get("/audio/{day}/{filename}")
def audio(day: str, filename: str) -> FileResponse:
    day = _valid_day(day)
    if not re.fullmatch(r"[0-9a-f]{40}\.mp3", filename):
        raise HTTPException(status_code=404, detail="not found")
    root = (data_dir(load_config()) / "audio" / day).resolve()
    target = (root / filename).resolve()
    try:
        target.relative_to(root)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail="not found") from exc
    if not target.is_file():
        raise HTTPException(status_code=404, detail="not found")
    return FileResponse(target, media_type="audio/mpeg")


app.mount("/", StaticFiles(directory=str(PROJECT_ROOT / "static"), html=True), name="static")
