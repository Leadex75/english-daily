from __future__ import annotations

import datetime as dt
import os
import shutil
import sqlite3
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import yaml

PROJECT_ROOT = Path(__file__).resolve().parent.parent
CONFIG_PATH = PROJECT_ROOT / "config.yaml"
SOURCES_PATH = PROJECT_ROOT / "sources.yaml"

DEFAULTS: dict[str, Any] = {
    "languages": {"en": {"brand": "English Daily", "label": "English"}},
    "default_language": "en",
    "online_site_url": "https://leadex75.github.io/english-daily/",
    "data_dir": "./data",
    "host": "127.0.0.1",
    "port": 8000,
    "audio_pref_min_sec": 180,
    "audio_pref_max_sec": 1200,
    "audio_hard_min_sec": 30,
    "audio_hard_max_sec": 5400,
    "verify_audio_download": False,
    "text_pref_min_words": 120,
    "text_pref_max_words": 1500,
    "text_hard_min_words": 40,
    "text_hard_max_words": 4000,
    "lookback_days": 7,
    "retention_days": 90,
    "archive_days": 90,
    "reencode_audio": False,
    "audio_bitrate_kbps": 48,
    "auto_ingest_on_start": True,
    "user_agent": "english-daily/1.0 (+https://github.com/Leadex75/english-daily)",
    "request_timeout_sec": 30,
    "max_entries_per_source": 10,
    "timezone": "Europe/Paris",
    "audio_mode": "local",
    "public_mode": True,
    "excerpt_words": 60,
    "excerpt_min_sentence_words": 8,
    "text_cleaning": {
        "patterns": [
            r"\bSign up for our email newsletter\b.*$",
            r"\bFollow us on social media\b.*$",
            r"\bWatch this podcast here\b.*$",
            r"\bGet a free worksheet for this episode here:\b.*$",
            r"\bLet us know what you think\b.*$",
            r"\bWant more analysis\b.*$",
            r"\bSubscribe to\b.*?\bnewsletter\b.*$",
            r"\bSupport public media with NPR\+.*$",
            r"\bThis show.s perks include sponsor-free listening\b.*$",
            r"\bLearn more at plus\.npr\.org\b.*$",
            r"\bToday.s episode of\b.*$",
            r"\bSee pcm\.adswizz\.com\b.*$",
            r"\bNPR Privacy Policy\b.*$",
            r"\bLearn more about the standards of our journalism\b.*$",
            r"\bContinue reading\s*(?:\.{3,}|…)?\s*$",
            r"^\s*[-–—]?\s*Published\s+",
        ]
    },
    "static_retention_days": 365,
    "noindex": True,
    "pool_cap_per_bucket": 12,
    "pool_min_per_bucket": 4,
    "reserve_time_budget_sec": 420,
    "reserve_max_requests": 400,
    "reserve_offline": False,
    "ingest_offline": False,
    "new_books_per_run": 25,
    "weekly_goal_default": 5,
    "history_keywords": [],
    "history_categories": [],
    "history_periods": {},
    "history_themes": {},
    "word_bands": {},
    "levels": {},
    "phrase_history_days": 400,
    "phrase_offline": False,
    "content_blocklist": [],
    "level_thresholds": {"A1": 0.15, "A2": 0.28, "B1": 0.42, "B2": 0.58, "C1": 0.75},
}

CREATE_SOURCES = """CREATE TABLE sources (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    feed_url TEXT NOT NULL,
    category TEXT NOT NULL CHECK (category IN ('news','culture','history','phrase')),
    kind TEXT NOT NULL CHECK (kind IN ('text','audio')),
    level_min TEXT NOT NULL,
    level_max TEXT NOT NULL,
    max_duration_sec INTEGER NULL,
    enabled INTEGER DEFAULT 1,
    lang TEXT NOT NULL DEFAULT 'en'
)"""

CREATE_ITEMS = """CREATE TABLE items (
    id INTEGER PRIMARY KEY,
    guid_hash TEXT UNIQUE NOT NULL,
    source_id TEXT REFERENCES sources(id),
    kind TEXT NOT NULL,
    category TEXT NOT NULL CHECK (category IN ('news','culture','history','phrase')),
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
    level_method TEXT,
    audio_remote_url TEXT,
    license TEXT,
    attribution TEXT,
    origin TEXT DEFAULT 'fresh',
    lang TEXT NOT NULL DEFAULT 'en',
    periods TEXT DEFAULT '[]',
    themes TEXT DEFAULT '[]',
    history_terms TEXT DEFAULT '[]',
    transcript_url TEXT,
    transcript_text TEXT
)"""

CREATE_PICKS = """CREATE TABLE daily_picks (
    date TEXT NOT NULL,
    level TEXT NOT NULL,
    category TEXT NOT NULL,
    kind TEXT NOT NULL,
    item_id INTEGER REFERENCES items(id),
    origin TEXT,
    badges TEXT,
    reconstructed INTEGER DEFAULT 0,
    lang TEXT NOT NULL DEFAULT 'en',
    PRIMARY KEY (lang, date, level, category, kind)
)"""

CREATE_PHRASES = """CREATE TABLE phrases (
    lang TEXT NOT NULL DEFAULT 'en', date TEXT NOT NULL, level TEXT NOT NULL,
    payload TEXT NOT NULL, PRIMARY KEY (lang, date, level))"""

CREATE_EXTRA = [
    """CREATE TABLE IF NOT EXISTS ingest_runs (
        id INTEGER PRIMARY KEY, date TEXT NOT NULL, lang TEXT NOT NULL DEFAULT 'en',
        started_at TEXT NOT NULL, finished_at TEXT, status TEXT NOT NULL, log TEXT)""",
    """CREATE TABLE IF NOT EXISTS phrases (
        lang TEXT NOT NULL DEFAULT 'en', date TEXT NOT NULL, level TEXT NOT NULL,
        payload TEXT NOT NULL, PRIMARY KEY (lang, date, level))""",
    """CREATE TABLE IF NOT EXISTS books (
        librivox_id TEXT PRIMARY KEY, lang TEXT NOT NULL DEFAULT 'en', title TEXT,
        author TEXT, gutenberg_id TEXT, genre TEXT, level TEXT, score REAL,
        url_rss TEXT, fetched_at TEXT)""",
]


def load_config() -> dict[str, Any]:
    raw: dict[str, Any] = {}
    if CONFIG_PATH.exists():
        with CONFIG_PATH.open("r", encoding="utf-8") as handle:
            raw = yaml.safe_load(handle) or {}
    config = {**DEFAULTS, **raw}
    config["level_thresholds"] = {**DEFAULTS["level_thresholds"], **(raw.get("level_thresholds") or {})}
    config["word_bands"] = {**DEFAULTS.get("word_bands", {}), **(raw.get("word_bands") or {})}
    text_cleaning = {**DEFAULTS["text_cleaning"], **(raw.get("text_cleaning") or {})}
    text_cleaning["patterns"] = list(
        text_cleaning.get("patterns") or DEFAULTS["text_cleaning"]["patterns"]
    )
    config["text_cleaning"] = text_cleaning
    levels = dict(DEFAULTS.get("levels") or {})
    for language, values in (raw.get("levels") or {}).items():
        if isinstance(values, dict):
            levels[str(language)] = {
                **levels.get(str(language), {}),
                **values,
            }
    config["levels"] = levels
    env_data_dir = os.environ.get("ENGLISH_DAILY_DATA_DIR")
    if env_data_dir:
        config["data_dir"] = env_data_dir
    env_audio_mode = os.environ.get("ENGLISH_DAILY_AUDIO_MODE")
    if env_audio_mode:
        config["audio_mode"] = env_audio_mode
    audio_mode = str(config.get("audio_mode") or "local").strip().lower()
    config["audio_mode"] = audio_mode if audio_mode in {"local", "hotlink"} else "local"
    return config


def available_languages(config: dict[str, Any]) -> list[str]:
    raw = config.get("languages")
    languages: list[str] = []
    if isinstance(raw, dict):
        for code, settings in raw.items():
            name = str(code or "").strip()
            if not name:
                continue
            if isinstance(settings, dict) and settings.get("enabled") is False:
                continue
            languages.append(name)
    else:
        languages = [str(value) for value in (raw or []) if str(value).strip()]
    if not languages:
        languages = [str(config.get("default_language") or "en")]
    return list(dict.fromkeys(languages))


def language_metadata(config: dict[str, Any], lang: str | None = None) -> dict[str, str]:
    language = normalize_language(config, lang)
    raw = config.get("languages")
    metadata: dict[str, Any] = {}
    if isinstance(raw, dict):
        entry = raw.get(language) or {}
        if isinstance(entry, dict):
            metadata = dict(entry)
        elif entry:
            metadata = {"label": str(entry)}
    fallback_brands = {"en": "English Daily", "es": "Spanish Daily"}
    brand = str(metadata.get("brand") or (config.get("brands") or {}).get(language) or "")
    if not brand:
        brand = fallback_brands.get(language, f"{language.title()} Daily")
    return {
        "code": language,
        "brand": brand,
        "label": str(metadata.get("label") or language.upper()),
        "tagline": str(metadata.get("tagline") or f"A little {language.upper()}, every day."),
    }


def language_metadata_map(config: dict[str, Any]) -> dict[str, dict[str, str]]:
    return {language: language_metadata(config, language) for language in available_languages(config)}


def brand_for_language(config: dict[str, Any], lang: str | None = None) -> str:
    return language_metadata(config, lang)["brand"]


def default_language(config: dict[str, Any]) -> str:
    default = str(config.get("default_language") or "en")
    languages = available_languages(config)
    return default if default in languages else (languages[0] if languages else "en")


def normalize_language(config: dict[str, Any], lang: str | None) -> str:
    value = str(lang or default_language(config))
    return value if value in available_languages(config) else default_language(config)


def level_config(config: dict[str, Any], lang: str | None = None) -> tuple[dict[str, float], dict[str, Any]]:
    language = normalize_language(config, lang)
    entry = (config.get("levels") or {}).get(language) or {}
    english = (config.get("levels") or {}).get("en") or {}
    thresholds = dict(entry.get("thresholds") or english.get("thresholds") or config.get("level_thresholds") or {})
    bands = dict(entry.get("word_bands") or english.get("word_bands") or config.get("word_bands") or {})
    return thresholds, bands


def sources_for_language(
    sources: list[dict[str, Any]], config: dict[str, Any], lang: str | None = None
) -> list[dict[str, Any]]:
    language = normalize_language(config, lang)
    return [src for src in sources if str(src.get("lang") or "en") == language]


def today(config: dict[str, Any]) -> str:
    try:
        zone = ZoneInfo(str(config.get("timezone") or "Europe/Paris"))
    except Exception:
        zone = dt.datetime.now().astimezone().tzinfo
    return dt.datetime.now(zone).date().isoformat()


def load_sources(config: dict[str, Any] | None = None, lang: str | None = None) -> list[dict[str, Any]]:
    with SOURCES_PATH.open("r", encoding="utf-8") as handle:
        data = yaml.safe_load(handle) or {}
    sources = list(data.get("sources") or [])
    if config is None:
        return sources
    return sources_for_language(sources, config, lang)


def source_registry(config: dict[str, Any], lang: str | None = None) -> list[dict[str, Any]]:
    selected = load_sources() if lang is None else sources_for_language(load_sources(), config, lang)
    counts: dict[str, int] = {}
    try:
        conn = connect(config)
        try:
            for row in conn.execute("SELECT source_id, COUNT(*) AS total FROM items GROUP BY source_id"):
                counts[str(row["source_id"])] = int(row["total"])
        finally:
            conn.close()
    except sqlite3.Error:
        counts = {}
    registry: list[dict[str, Any]] = []
    for src in selected:
        item = {
            "id": str(src.get("id") or ""),
            "name": str(src.get("name") or src.get("id") or ""),
            "lang": str(src.get("lang") or "en"),
            "category": str(src.get("category") or ""),
            "kind": str(src.get("kind") or ""),
            "level_min": str(src.get("level_min") or "computed"),
            "level_max": str(src.get("level_max") or "computed"),
            "enabled": bool(src.get("enabled", True)),
            "license": str(src.get("license") or "proprietary"),
            "attribution": src.get("attribution"),
            "type": str(src.get("type") or "feed"),
            "items": counts.get(str(src.get("id") or ""), 0),
        }
        registry.append(item)
    return registry


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


def _table_sql(conn: sqlite3.Connection, name: str) -> str:
    row = conn.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name=?", (name,)).fetchone()
    return str(row[0]) if row else ""


def _columns(conn: sqlite3.Connection, name: str) -> set[str]:
    return {str(row["name"]) for row in conn.execute(f"PRAGMA table_info({name})").fetchall()}


def _rebuild(
    conn: sqlite3.Connection,
    name: str,
    create_sql: str,
    column_names: list[str],
    new_column_defaults: dict[str, str] | None = None,
) -> None:
    temporary = f"{name}__new"
    conn.execute(f"DROP TABLE IF EXISTS {temporary}")
    conn.execute(create_sql.replace(f"CREATE TABLE {name} ", f"CREATE TABLE {temporary} ", 1))
    old_columns = _columns(conn, name)
    present = [column for column in column_names if column in old_columns]
    defaults = new_column_defaults or {}
    additions = [column for column in column_names if column not in old_columns and column in defaults]
    names = present + additions
    select = [column if column in present else defaults[column] for column in names]
    conn.execute(
        f"INSERT INTO {temporary} ({', '.join(names)}) SELECT {', '.join(select)} FROM {name}"
    )
    conn.execute(f"DROP TABLE {name}")
    conn.execute(f"ALTER TABLE {temporary} RENAME TO {name}")


def _needs_migration(conn: sqlite3.Connection) -> bool:
    sources = _table_sql(conn, "sources")
    items = _table_sql(conn, "items")
    picks = _table_sql(conn, "daily_picks")
    phrases = _table_sql(conn, "phrases")
    books = _table_sql(conn, "books")
    runs = _table_sql(conn, "ingest_runs")
    if not sources or not items:
        return False
    return any(
        (
            "'phrase'" not in sources,
            "lang" not in sources.lower(),
            "'phrase'" not in items,
            "lang" not in items.lower(),
            "periods" not in items,
            "history_terms" not in items,
            "origin" not in picks,
            "lang" not in picks.lower(),
            "reconstructed" not in picks,
            bool(phrases) and "lang" not in phrases.lower(),
            bool(books) and "lang" not in books.lower(),
            bool(runs) and "lang" not in runs.lower(),
        )
    )


def _backup_before_migration(path: Path) -> None:
    if not path.exists():
        return
    stamp = dt.datetime.now().strftime("%Y%m%d")
    target = path.with_name(f"english.db.bak-{stamp}")
    suffix = 2
    while target.exists():
        target = path.with_name(f"english.db.bak-{stamp}-{suffix}")
        suffix += 1
    shutil.copy2(path, target)
    print(f"SQLite backup written to {target.name}")


def init_db(config: dict[str, Any]) -> Path:
    root = data_dir(config)
    root.mkdir(parents=True, exist_ok=True)
    path = db_path(config)
    if path.exists():
        conn = connect(config)
        try:
            needs = _needs_migration(conn)
        finally:
            conn.close()
        if needs:
            _backup_before_migration(path)

    conn = connect(config)
    try:
        conn.execute("PRAGMA foreign_keys=OFF")
        conn.execute("BEGIN")
        sources_sql = _table_sql(conn, "sources")
        if not sources_sql:
            conn.execute(CREATE_SOURCES)
        elif "'phrase'" not in sources_sql or "lang" not in sources_sql.lower():
            _rebuild(
                conn,
                "sources",
                CREATE_SOURCES,
                ["id", "name", "feed_url", "category", "kind", "level_min", "level_max",
                 "max_duration_sec", "enabled", "lang"],
                {"lang": "'en'"},
            )

        items_sql = _table_sql(conn, "items")
        if not items_sql:
            conn.execute(CREATE_ITEMS)
        elif any(
            column not in _columns(conn, "items")
            for column in ("origin", "lang", "periods", "themes", "history_terms", "transcript_url", "transcript_text")
        ) or "'phrase'" not in items_sql:
            _rebuild(
                conn,
                "items",
                CREATE_ITEMS,
                ["id", "guid_hash", "source_id", "kind", "category", "title", "url", "summary",
                 "published_at", "fetched_at", "body_text", "word_count", "duration_sec",
                 "audio_path", "audio_bytes", "fk_grade", "avg_sentence_len", "rare_word_ratio",
                 "score", "level", "level_method", "audio_remote_url", "license", "attribution",
                  "origin", "lang", "periods", "themes", "history_terms", "transcript_url", "transcript_text"],
                 {"origin": "'fresh'", "lang": "'en'", "periods": "'[]'", "themes": "'[]'", "history_terms": "'[]'"},
            )

        picks_sql = _table_sql(conn, "daily_picks")
        if not picks_sql:
            conn.execute(CREATE_PICKS)
        elif "lang" not in picks_sql.lower() or "reconstructed" not in picks_sql:
            _rebuild(
                conn, "daily_picks", CREATE_PICKS,
                ["date", "level", "category", "kind", "item_id", "origin", "badges",
                 "reconstructed", "lang"],
                {"origin": "'fresh'", "badges": "'[]'", "reconstructed": "0", "lang": "'en'"},
            )

        phrases_sql = _table_sql(conn, "phrases")
        if not phrases_sql:
            conn.execute(CREATE_PHRASES)
        elif "lang" not in phrases_sql.lower():
            _rebuild(
                conn, "phrases", CREATE_PHRASES,
                ["date", "level", "payload", "lang"],
                {"lang": "'en'"},
            )
        for statement in CREATE_EXTRA:
            conn.execute(statement)
        for table in ("books", "ingest_runs"):
            if table in {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}:
                columns = _columns(conn, table)
                if "lang" not in columns:
                    conn.execute(f"ALTER TABLE {table} ADD COLUMN lang TEXT NOT NULL DEFAULT 'en'")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_daily_picks_date ON daily_picks(date, lang)")
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.execute("PRAGMA foreign_keys=ON")
        conn.close()
    return path


def upsert_sources(
    sources: list[dict[str, Any]], config: dict[str, Any], lang: str | None = None
) -> None:
    selected = sources if lang is None else sources_for_language(sources, config, lang)
    conn = connect(config)
    try:
        for src in selected:
            conn.execute(
                """INSERT INTO sources
                   (id, name, feed_url, category, kind, level_min, level_max, max_duration_sec, enabled, lang)
                   VALUES (?,?,?,?,?,?,?,?,?,?)
                   ON CONFLICT(id) DO UPDATE SET
                     name=excluded.name, feed_url=excluded.feed_url,
                     category=excluded.category, kind=excluded.kind,
                     level_min=excluded.level_min, level_max=excluded.level_max,
                     max_duration_sec=excluded.max_duration_sec, enabled=excluded.enabled,
                     lang=excluded.lang""",
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
                    str(src.get("lang") or "en"),
                ),
            )
        conn.commit()
    finally:
        conn.close()


def successful_ingest_exists(day: str, config: dict[str, Any], lang: str | None = None) -> bool:
    language = normalize_language(config, lang)
    conn = connect(config)
    try:
        row = conn.execute(
            "SELECT 1 FROM ingest_runs WHERE date=? AND lang=? AND status IN ('ok','partial') LIMIT 1",
            (day, language),
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
        rows = conn.execute("SELECT id, audio_path FROM items WHERE audio_path IS NOT NULL").fetchall()
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
            conn.execute("UPDATE items SET audio_path=NULL, audio_bytes=NULL WHERE id=?", (row["id"],))
            removed += 1
        conn.commit()
    finally:
        conn.close()
    return removed
