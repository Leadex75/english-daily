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
    data_dir,
    init_db,
    load_config,
    load_sources,
    successful_ingest_exists,
    today,
    upsert_sources,
)
from app.serialize import serialize_day
from ingest.pipeline import run_ingest
from ingest.readability import LEVELS

app = FastAPI(title="english-daily", docs_url=None, redoc_url=None)
_ingest_lock = threading.Lock()


def _auto_ingest() -> None:
    config = load_config()
    day = today(config)
    if not config.get("auto_ingest_on_start") or successful_ingest_exists(day, config):
        return
    with _ingest_lock:
        if not successful_ingest_exists(day, config):
            run_ingest(day, config)


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
def health() -> dict[str, Any]:
    config = load_config()
    conn = connect(config)
    try:
        sources = int(conn.execute("SELECT COUNT(*) FROM sources WHERE enabled=1").fetchone()[0])
    finally:
        conn.close()
    return {"status": "ok", "name": "english-daily", "enabled_sources": sources, "ffmpeg": bool(shutil.which("ffmpeg"))}


@app.get("/api/days")
def days() -> list[str]:
    conn = connect(load_config())
    try:
        rows = conn.execute("SELECT DISTINCT date FROM ingest_runs ORDER BY date DESC").fetchall()
        return [str(row[0]) for row in rows]
    finally:
        conn.close()


@app.get("/api/day/{day}")
def day(day: str, level: str = "B1") -> dict[str, Any]:
    day = _valid_day(day)
    if level not in LEVELS:
        raise HTTPException(status_code=400, detail=f"level must be one of {', '.join(LEVELS)}")
    config = load_config()
    conn = connect(config)
    try:
        return serialize_day(conn, day, level, config)
    finally:
        conn.close()


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
