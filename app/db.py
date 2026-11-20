from __future__ import annotations

import datetime as dt
import os
import sqlite3
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import yaml

PROJECT_ROOT = Path(__file__).resolve().parent.parent
CONFIG_PATH = PROJECT_ROOT / "config.yaml"
SOURCES_PATH = PROJECT_ROOT / "sources.yaml"

DEFAULTS: dict[str, Any] = {
    "data_dir": "./data",
    "host": "127.0.0.1",
    "port": 8000,
    "audio_min_sec": 180,
    "audio_max_sec": 1200,
    "lookback_days": 7,
    "retention_days": 90,
    "reencode_audio": False,
    "audio_bitrate_kbps": 48,
    "auto_ingest_on_start": True,
    "user_agent": "english-daily/1.0 (personal use)",
    "request_timeout_sec": 30,
    "max_entries_per_source": 10,
    "timezone": "Europe/Paris",
    "audio_mode": "local",
    "public_mode": True,
    "excerpt_words": 60,
    "static_retention_days": 365,
    "noindex": True,
    "level_thresholds": {"A1": 0.15, "A2": 0.28, "B1": 0.42, "B2": 0.58, "C1": 0.75},
}


def load_config() -> dict[str, Any]:
    raw: dict[str, Any] = {}
    if CONFIG_PATH.exists():
        with CONFIG_PATH.open("r", encoding="utf-8") as handle:
            raw = yaml.safe_load(handle) or {}
    config = {**DEFAULTS, **raw}
    config["level_thresholds"] = {**DEFAULTS["level_thresholds"], **(raw.get("level_thresholds") or {})}
    env_data_dir = os.environ.get("ENGLISH_DAILY_DATA_DIR")
    if env_data_dir:
        config["data_dir"] = env_data_dir
    env_audio_mode = os.environ.get("ENGLISH_DAILY_AUDIO_MODE")
    if env_audio_mode:
        config["audio_mode"] = env_audio_mode
    audio_mode = str(config.get("audio_mode") or "local").strip().lower()
    config["audio_mode"] = audio_mode if audio_mode in {"local", "hotlink"} else "local"
    return config


def today(config: dict[str, Any]) -> str:
    try:
        zone = ZoneInfo(str(config.get("timezone") or "Europe/Paris"))
    except Exception:
        zone = dt.datetime.now().astimezone().tzinfo
    return dt.datetime.now(zone).date().isoformat()


def load_sources() -> list[dict[str, Any]]:
    with SOURCES_PATH.open("r", encoding="utf-8") as handle:
        data = yaml.safe_load(handle) or {}
    return list(data.get("sources") or [])


def data_dir(config: dict[str, Any]) -> Path:
    path = Path(str(config["data_dir"]))
    return path if path.is_absolute() else PROJECT_ROOT / path


def db_path(config: dict[str, Any]) -> Path:
    return data_dir(config) / "english-daily.sqlite3"


def connect(config: dict[str, Any]) -> sqlite3.Connection:
    conn = sqlite3.connect(str(db_path(config)), timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


SCHEMA = """
CREATE TABLE IF NOT EXISTS sources (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    feed_url TEXT NOT NULL,
    category TEXT NOT NULL CHECK (category IN ('news','culture')),
    kind TEXT NOT NULL CHECK (kind IN ('text','audio')),
    level_min TEXT NOT NULL,
    level_max TEXT NOT NULL,
    max_duration_sec INTEGER NULL,
    enabled INTEGER DEFAULT 1
);
CREATE TABLE IF NOT EXISTS items (
    id INTEGER PRIMARY KEY,
    guid_hash TEXT UNIQUE NOT NULL,
    source_id TEXT REFERENCES sources(id),
    kind TEXT NOT NULL,
    category TEXT NOT NULL,
    title TEXT NOT NULL,
    url TEXT,
    summary TEXT,
    published_at TEXT,
    fetched_at TEXT,
    body_text TEXT,
    word_count INTEGER,
    duration_sec INTEGER,
    audio_path TEXT,
    audio_bytes INTEGER,
    fk_grade REAL,
    avg_sentence_len REAL,
    rare_word_ratio REAL,
    score REAL,
    level TEXT,
    level_method TEXT
);
CREATE TABLE IF NOT EXISTS daily_picks (
    date TEXT NOT NULL,
    level TEXT NOT NULL,
    category TEXT NOT NULL,
    kind TEXT NOT NULL,
    item_id INTEGER REFERENCES items(id),
    PRIMARY KEY (date, level, category, kind)
);
CREATE INDEX IF NOT EXISTS idx_daily_picks_date ON daily_picks(date);
CREATE TABLE IF NOT EXISTS ingest_runs (
    id INTEGER PRIMARY KEY,
    date TEXT NOT NULL,
    started_at TEXT NOT NULL,
    finished_at TEXT,
    status TEXT NOT NULL,
    log TEXT
);
"""


def _migrate_items(conn: sqlite3.Connection) -> None:
    columns = {str(row["name"]) for row in conn.execute("PRAGMA table_info(items)").fetchall()}
    for name in ("audio_remote_url", "license", "attribution"):
        if name not in columns:
            conn.execute(f"ALTER TABLE items ADD COLUMN {name} TEXT")


def init_db(config: dict[str, Any]) -> Path:
    root = data_dir(config)
    (root / "audio").mkdir(parents=True, exist_ok=True)
    conn = connect(config)
    try:
        conn.execute("PRAGMA journal_mode=DELETE")
        conn.executescript(SCHEMA)
        _migrate_items(conn)
        conn.commit()
    finally:
        conn.close()
    return db_path(config)


def upsert_sources(sources: list[dict[str, Any]], config: dict[str, Any]) -> None:
    conn = connect(config)
    try:
        for src in sources:
            conn.execute(
                """INSERT INTO sources
                   (id, name, feed_url, category, kind, level_min, level_max,
                    max_duration_sec, enabled)
                   VALUES (?,?,?,?,?,?,?,?,?)
                   ON CONFLICT(id) DO UPDATE SET
                     name=excluded.name, feed_url=excluded.feed_url,
                     category=excluded.category, kind=excluded.kind,
                     level_min=excluded.level_min, level_max=excluded.level_max,
                     max_duration_sec=excluded.max_duration_sec,
                     enabled=excluded.enabled""",
                (
                    str(src["id"]),
                    str(src.get("name") or src["id"]),
                    str(src["feed_url"]),
                    str(src["category"]),
                    str(src["kind"]),
                    str(src.get("level_min") or "computed"),
                    str(src.get("level_max") or "computed"),
                    src.get("max_duration_sec"),
                    int(bool(src.get("enabled", True))),
                ),
            )
        conn.commit()
    finally:
        conn.close()


def successful_ingest_exists(day: str, config: dict[str, Any]) -> bool:
    conn = connect(config)
    try:
        row = conn.execute(
            "SELECT 1 FROM ingest_runs WHERE date=? AND status IN ('ok','partial') LIMIT 1", (day,)
        ).fetchone()
        return row is not None
    finally:
        conn.close()


def prune_audio(config: dict[str, Any]) -> int:
    retention = int(config["retention_days"])
    if retention <= 0:
        return 0
    cutoff = (dt.date.fromisoformat(today(config)) - dt.timedelta(days=retention)).isoformat()
    conn = connect(config)
    removed = 0
    try:
        rows = conn.execute(
            "SELECT id, audio_path FROM items WHERE audio_path IS NOT NULL"
        ).fetchall()
        for row in rows:
            rel = str(row["audio_path"])
            day = rel.split("/", 1)[0]
            if len(day) != 10 or day >= cutoff:
                continue
            target = data_dir(config) / rel
            if target.is_file():
                try:
                    target.unlink()
                except OSError:
                    continue
            conn.execute(
                "UPDATE items SET audio_path=NULL, audio_bytes=NULL WHERE id=?", (row["id"],)
            )
            removed += 1
        conn.commit()
    finally:
        conn.close()
    return removed
