import sqlite3
import tempfile
import unittest
from collections import Counter
from pathlib import Path

from app.db import DEFAULTS, connect, data_dir, db_path, init_db, load_config, upsert_sources
from ingest.export_static import export_static
from ingest.phrases import generate_phrases, load_bank
from ingest.picker import choose_picks
from ingest.pipeline import run_ingest
from ingest.readability import band_center


class BankTests(unittest.TestCase):
    def test_bank_counts_and_shape(self):
        words = load_bank("words")
        expressions = load_bank("expressions")
        expected_words = {"A1": 20, "A2": 20, "B1": 23, "B2": 20, "C1": 20, "C2": 21}
        expected_expressions = {level: 30 for level in expected_words}
        self.assertEqual(dict(Counter(item["level"] for item in words)), expected_words)
        self.assertEqual(dict(Counter(item["level"] for item in expressions)), expected_expressions)
        word_texts = [str(item["text"]).lower() for item in words]
        expression_texts = [str(item["expression"]).lower() for item in expressions]
        self.assertEqual(len(word_texts), len(set(word_texts)))
        self.assertEqual(len(expression_texts), len(set(expression_texts)))
        for item in words:
            self.assertTrue(str(item.get("meaning_fr") or "").strip())
        for item in expressions:
            self.assertTrue(str(item.get("meaning_fr") or "").strip())

    def test_phrases_are_deterministic_and_offline(self):
        config = {"phrase_offline": True, "phrase_history_days": 400}
        day = "2026-11-21"
        with tempfile.TemporaryDirectory() as first_dir, tempfile.TemporaryDirectory() as second_dir:
            first = generate_phrases(config, day, first_dir, offline=True)
            second = generate_phrases(config, day, second_dir, offline=True)
        self.assertEqual(set(first), {"A1", "A2", "B1", "B2", "C1", "C2"})
        for level in first:
            self.assertEqual(first[level]["word"]["key"], second[level]["word"]["key"])
            self.assertEqual(first[level]["expression"]["key"], second[level]["expression"]["key"])
            self.assertEqual(first[level]["word"]["dictionary"], {})
            self.assertEqual(first[level]["expression"]["audio"], None)


class PickerTests(unittest.TestCase):
    def test_adjacent_level_fallback_is_tagged(self):
        config = dict(DEFAULTS)
        day = "2026-11-21"
        body = "word " * 200
        candidates = []
        for suffix, level in (("1", "B1"), ("2", "B1"), ("3", "B1")):
            candidates.append({
                "guid_hash": f"adjacent-{suffix}",
                "source_id": f"source-{suffix}",
                "source_name": f"Source {suffix}",
                "kind": "text",
                "category": "news",
                "title": "A test article",
                "url": "https://example.org/article",
                "published_at": day,
                "body_text": body,
                "word_count": 200,
                "score": band_center(level, config["level_thresholds"]),
                "level": level,
                "origin": "fresh",
            })
        picks, filled, empty = choose_picks(candidates, day, config)
        self.assertEqual(len(filled), 3)
        self.assertEqual(len(empty), 33)
        chosen = picks[("B2", "news", "text")]
        self.assertEqual(chosen["level"], "B1")
        self.assertEqual(chosen["slot_level"], "B2")
        self.assertIn("Closest level: B1", chosen["badges"])


class MigrationAndExportTests(unittest.TestCase):
    def test_old_database_migrates_with_backup(self):
        with tempfile.TemporaryDirectory() as temp:
            config = dict(DEFAULTS)
            config["data_dir"] = temp
            root = data_dir(config)
            path = db_path(config)
            conn = sqlite3.connect(str(path))
            conn.executescript(
                """
                CREATE TABLE sources (
                    id TEXT PRIMARY KEY, name TEXT NOT NULL, feed_url TEXT NOT NULL,
                    category TEXT NOT NULL, kind TEXT NOT NULL, level_min TEXT NOT NULL,
                    level_max TEXT NOT NULL, max_duration_sec INTEGER NULL, enabled INTEGER DEFAULT 1
                );
                CREATE TABLE items (
                    id INTEGER PRIMARY KEY, guid_hash TEXT UNIQUE NOT NULL, source_id TEXT,
                    kind TEXT NOT NULL, category TEXT NOT NULL, title TEXT NOT NULL, url TEXT,
                    summary TEXT, published_at TEXT, fetched_at TEXT, body_text TEXT,
                    word_count INTEGER, duration_sec INTEGER, audio_path TEXT, audio_bytes INTEGER,
                    fk_grade REAL, avg_sentence_len REAL, rare_word_ratio REAL, score REAL,
                    level TEXT, level_method TEXT
                );
                CREATE TABLE daily_picks (
                    date TEXT NOT NULL, level TEXT NOT NULL, category TEXT NOT NULL,
                    kind TEXT NOT NULL, item_id INTEGER,
                    PRIMARY KEY (date, level, category, kind)
                );
                INSERT INTO sources VALUES ('old', 'Old', 'https://example.org', 'news', 'text', 'B1', 'B1', NULL, 1);
                INSERT INTO items (guid_hash, source_id, kind, category, title, level)
                    VALUES ('old-1', 'old', 'text', 'news', 'Old item', 'B1');
                INSERT INTO daily_picks VALUES ('2026-11-20', 'B1', 'news', 'text', 1);
                """
            )
            conn.commit()
            conn.close()

            init_db(config)
            check = connect(config)
            try:
                item_columns = {row["name"] for row in check.execute("PRAGMA table_info(items)")}
                pick_columns = {row["name"] for row in check.execute("PRAGMA table_info(daily_picks)")}
                self.assertIn("origin", item_columns)
                source_sql = check.execute(
                    "SELECT sql FROM sqlite_master WHERE type='table' AND name='sources'"
                ).fetchone()[0]
                self.assertIn("'phrase'", source_sql)
                self.assertIn("origin", pick_columns)
                self.assertIn("badges", pick_columns)
                self.assertEqual(check.execute("SELECT COUNT(*) FROM items").fetchone()[0], 1)
                self.assertEqual(check.execute("SELECT COUNT(*) FROM daily_picks").fetchone()[0], 1)
            finally:
                check.close()
            self.assertTrue(list(root.glob("english.db.bak-*")))

    def test_offline_ingest_writes_picks_phrases_and_static_site(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            config = dict(load_config())
            config["data_dir"] = str(root / "data")
            config["ingest_offline"] = True
            config["reserve_offline"] = True
            config["phrase_offline"] = True
            day = "2026-11-21"
            init_db(config)
            upsert_sources(
                [{"id": "test_source", "name": "Test Source", "feed_url": "generated",
                  "category": "history", "kind": "text", "level_min": "B1", "level_max": "B1",
                  "enabled": True}],
                config,
            )
            conn = connect(config)
            try:
                conn.execute(
                    """INSERT INTO items
                       (guid_hash, source_id, kind, category, title, url, published_at,
                        fetched_at, body_text, word_count, score, level, level_method, origin)
                       VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                    ("test-1", "test_source", "text", "history", "A test article",
                     "https://example.org/article", day, day, "word " * 200, 200, 0.5,
                     "B1", "computed", "fresh"),
                )
                conn.commit()
            finally:
                conn.close()

            summary = run_ingest(day, config, state_dir=str(root / "state"))
            self.assertGreaterEqual(summary["filled"], 1)
            self.assertEqual(summary["phrases"], 6)
            conn = connect(config)
            try:
                self.assertEqual(conn.execute("SELECT COUNT(*) FROM phrases").fetchone()[0], 6)
                self.assertGreaterEqual(conn.execute("SELECT COUNT(*) FROM daily_picks").fetchone()[0], 1)
            finally:
                conn.close()

            out = root / "site"
            result = export_static(out, config, public_mode=True)
            self.assertIn(day, result["days"])
            self.assertTrue((out / "data" / day / "B1.json").is_file())
            self.assertTrue((out / "data" / day / "phrases.json").is_file())
            self.assertTrue((out / "index.html").is_file())
            self.assertTrue((out / "manifest.webmanifest").is_file())
            self.assertTrue((out / "sw.js").is_file())


if __name__ == "__main__":
    unittest.main()
