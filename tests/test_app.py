import json
import sqlite3
import subprocess
import sys
import tempfile
import unittest
import zipfile
from collections import Counter
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path
from unittest.mock import patch

import yaml

from app.anki import anki_connect_note, build_note, build_notes, write_apkg
from app.db import (
    DEFAULTS,
    available_languages,
    brand_for_language,
    connect,
    data_dir,
    db_path,
    default_language,
    init_db,
    language_metadata_map,
    language_setting,
    load_config,
    load_sources,
    normalize_language,
    source_registry,
    upsert_sources,
)
from app.main import app
from app.serialize import _build_exercises, _TOUR_STEPS_BY_LANG, excerpt, serialize_day
from desktop.main import resolve_site_dir
from fastapi.testclient import TestClient

from ingest import readability
from ingest.doctor import check_sources, run_doctor
from ingest.export_static import export_static
from ingest.fetch_feeds import RESERVE_TYPES, _wikipedia_simple
from ingest.fetch_text import clean_text, extract_article, word_count
from ingest.pool import pool_dir
from tools.contrast_check import audit_css, contrast_ratio
from tools.palette_build import audit_palettes, build_css
from tools.project_ops import (
    backup_database,
    build_demo_data,
    calibrate_report,
    restore_database,
    validate_config,
)

from ingest.paths import (
    languages_path,
    migrate_legacy_site,
    migrate_legacy_state,
    site_lang_dir,
    site_level_path,
    site_phrase_path,
    site_search_path,
    state_lang_dir,
    write_languages,
)
from ingest.phrases import annotate_history, generate_phrases, load_bank, load_history_terms, store_phrases
from ingest.picker import choose_picks
from ingest.pipeline import run_ingest
from ingest.readability import band_center, is_spanish, metrics
from ingest.reserve.common import make_candidate, source_host
from ingest.reserve.wikinews import _month_category
from ingest.search import build_search_index, search_index
import run
from tools.build_desktop import build_zipapp


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
        terms = load_history_terms()
        self.assertGreaterEqual(len(terms), 120)
        self.assertEqual({str(item["level"]) for item in terms}, set(expected_words))
        for item in terms:
            self.assertTrue(str(item.get("meaning_fr") or "").strip())
            self.assertTrue(str(item.get("period") or "").strip())
            self.assertTrue(str(item.get("theme") or "").strip())
            self.assertTrue(list(item.get("aliases") or []))

    def test_spanish_and_expanded_banks_are_shape_compatible(self):
        for lang in ("en", "es"):
            words = load_bank("words", lang)
            expressions = load_bank("expressions", lang)
            terms = load_history_terms(lang)
            self.assertGreaterEqual(len(words), 120)
            self.assertGreaterEqual(len(expressions), 120)
            self.assertGreaterEqual(len(terms), 120)
            self.assertEqual(
                {str(item["level"]) for item in words},
                {"A1", "A2", "B1", "B2", "C1", "C2"},
            )
            self.assertEqual(
                {str(item["level"]) for item in expressions},
                {"A1", "A2", "B1", "B2", "C1", "C2"},
            )
            self.assertEqual(
                {str(item["level"]) for item in terms},
                {"A1", "A2", "B1", "B2", "C1", "C2"},
            )
            for item in words + expressions + terms:
                self.assertTrue(str(item.get("meaning_fr") or "").strip())
            for item in terms:
                self.assertTrue(str(item.get("period") or "").strip())
                self.assertTrue(str(item.get("theme") or "").strip())
                self.assertTrue(list(item.get("aliases") or []))

    def test_history_terms_annotate_history_items(self):
        config = dict(DEFAULTS)
        item = annotate_history({
            "category": "history",
            "title": "Renaissance art and reformation",
            "summary": "A museum exhibition about the renaissance.",
            "body_text": "The reformation changed culture.",
        }, config, "en")
        self.assertIn("Early modern", item["periods"])
        self.assertIn("Culture", item["themes"])
        self.assertIn("Religion", item["themes"])
        self.assertTrue(any(term["text"] == "renaissance" for term in item["history_terms"]))

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
            self.assertEqual(first[level]["history"]["key"], second[level]["history"]["key"])
            self.assertEqual(first[level]["history"]["level"], level)
            self.assertEqual(first[level]["word"]["dictionary"], {})
            self.assertEqual(first[level]["expression"]["audio"], None)


class ExcerptTests(unittest.TestCase):
    def test_missing_empty_and_zero_limits_return_empty(self):
        config = dict(DEFAULTS)
        self.assertEqual(excerpt(None, 60, config), "")
        self.assertEqual(excerpt("", 60, config), "")
        self.assertEqual(excerpt("Any text", 0, config), "")

    def test_short_and_exact_length_text_is_returned_unchanged(self):
        config = dict(DEFAULTS)
        text = "A short complete sentence."
        self.assertEqual(excerpt(text, 60, config), text)
        self.assertEqual(excerpt(text, 6, config), text)

    def test_boilerplate_only_text_returns_empty(self):
        config = dict(DEFAULTS)
        raw = "- Published Continue reading... Sign up for our email newsletter for tips."
        self.assertEqual(excerpt(raw, 60, config), "")

    def test_boilerplate_tail_is_removed_from_excerpt(self):
        config = dict(DEFAULTS)
        text = "The government published a short statement today. More details will follow soon. Continue reading..."
        result = excerpt(text, 60, config)
        self.assertNotIn("Continue reading", result)
        self.assertNotIn(".…", result)

    def test_long_text_breaks_at_complete_sentences(self):
        config = dict(DEFAULTS)
        text = (
            "The council approved the plan after a long meeting and several public comments. "
            "It will start next month. More details will be published soon."
        )
        result = excerpt(text, 20, config)
        self.assertTrue(result.endswith("next month."))
        self.assertNotIn("…", result)

    def test_clause_fallback_avoids_mid_word_and_dot_ellipsis(self):
        config = dict(DEFAULTS)
        text = (
            "This is a long first clause, with several words and no terminal punctuation, "
            "then it continues for much longer without stopping"
        )
        result = excerpt(text, 15, config)
        self.assertEqual(result, "This is a long first clause, with several words and no terminal punctuation…")
        self.assertNotIn(".…", result)

    def test_minimum_sentence_words_is_configurable(self):
        config = dict(DEFAULTS)
        text = (
            "The council approved the plan after a long meeting and several public comments. "
            "It will start next month with a short ceremony. More details will follow."
        )
        self.assertTrue(excerpt(text, 24, config).endswith("ceremony."))
        strict = dict(config)
        strict["excerpt_min_sentence_words"] = 50
        result = excerpt(text, 24, strict)
        self.assertTrue(result.endswith("…"))
        self.assertNotIn(".…", result)


class TextCleaningTests(unittest.TestCase):
    def test_clean_text_removes_publisher_boilerplate_and_broken_ellipses(self):
        config = dict(DEFAULTS)
        raw = "- Published The council approved the plan. Continue reading..."
        self.assertEqual(clean_text(raw, config), "The council approved the plan.")
        promotional = (
            "Food sources... but the effects are unclear. Sign up for our email newsletter "
            "for tips. Follow us on social media @bbc"
        )
        cleaned = clean_text(promotional, config)
        self.assertEqual(cleaned, "Food sources… but the effects are unclear.")
        self.assertNotIn("...", cleaned)
        self.assertNotIn(".…", cleaned)

    def test_clean_text_removes_npr_podcast_boilerplate(self):
        raw = (
            "The headlines are here. Want more analysis? Subscribe to the Up First newsletter. "
            "Support public media with NPR+ and enjoy perks for over 25 podcasts. This show’s "
            "perks include sponsor-free listening. Learn more at plus.npr.org . NPR Privacy Policy"
        )
        self.assertEqual(clean_text(raw, dict(DEFAULTS)), "The headlines are here.")

    def test_extract_article_cleans_trafilatura_output(self):
        class Response:
            text = "<html><body>article</body></html>"

            def raise_for_status(self):
                return None

        raw = "- Published The council approved the plan. Continue reading..."
        with patch("ingest.fetch_text.http_get", return_value=Response()), patch(
            "ingest.fetch_text.trafilatura.extract", return_value=raw
        ):
            cleaned = extract_article("https://example.org/article", dict(DEFAULTS))
        self.assertEqual(cleaned, "The council approved the plan.")

    def test_clean_existing_updates_database_pool_and_site(self):
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            config = dict(DEFAULTS)
            config["languages"] = ["en"]
            config["data_dir"] = str(root / "data")
            init_db(config)
            conn = connect(config)
            try:
                conn.execute(
                    """INSERT INTO sources
                       (id, name, feed_url, category, kind, level_min, level_max, enabled, lang)
                       VALUES (?,?,?,?,?,?,?,?,?)""",
                    ("source", "Source", "https://example.org/feed", "news", "text",
                     "computed", "computed", 1, "en"),
                )
                conn.execute(
                    """INSERT INTO items
                       (guid_hash, source_id, kind, category, title, url, summary, body_text,
                        word_count, level, origin, lang)
                       VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
                    (
                        "clean-hash", "source", "text", "news", "- Published Council plan",
                        "https://example.org/article", "Summary Continue reading...",
                        "- Published The council approved the plan. Continue reading...",
                        999, "B1", "fresh", "en",
                    ),
                )
                conn.commit()
            finally:
                conn.close()

            state = root / "state"
            pool = pool_dir(state, config, "en")
            pool.mkdir(parents=True, exist_ok=True)
            pool_file = pool / "clean-hash.json"
            pool_file.write_text(
                json.dumps({"guid_hash": "clean-hash", "body_text": "Old text Continue reading..."}),
                encoding="utf-8",
            )
            site = root / "site"
            site_file = site / "data" / "en" / "index.json"
            site_file.parent.mkdir(parents=True, exist_ok=True)
            site_file.write_text(
                json.dumps({"title": "- Published Council plan", "body": "Old body Continue reading..."}),
                encoding="utf-8",
            )
            with patch("run.export_static", return_value={"out": str(site)}) as export:
                summary = run._clean_existing(config, site, state)

            conn = connect(config)
            try:
                row = conn.execute(
                    "SELECT title, summary, body_text, word_count FROM items WHERE guid_hash=?",
                    ("clean-hash",),
                ).fetchone()
            finally:
                conn.close()
            self.assertEqual(row["title"], "Council plan")
            self.assertEqual(row["body_text"], "The council approved the plan.")
            self.assertEqual(row["word_count"], 5)
            self.assertEqual(
                json.loads(pool_file.read_text(encoding="utf-8"))["body_text"], "Old text"
            )
            cleaned_site = json.loads(site_file.read_text(encoding="utf-8"))
            self.assertEqual(cleaned_site["title"], "Council plan")
            self.assertEqual(cleaned_site["body"], "Old body")
            self.assertEqual(summary["items"], 1)
            export.assert_called_once()


class PickerTests(unittest.TestCase):
    def test_adjacent_level_fallback_is_tagged(self):
        config = dict(DEFAULTS)
        config["languages"] = ["en"]
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

    def test_trace_reports_explicit_cascade_stages(self):
        config = dict(DEFAULTS)
        config["languages"] = ["en"]
        day = "2026-11-21"
        center = band_center("B1", config["level_thresholds"])
        candidates = [
            {
                "guid_hash": "adjacent-audio",
                "source_id": "audio-source",
                "source_name": "Audio Source",
                "kind": "audio",
                "category": "news",
                "title": "Audio",
                "url": "https://example.org/audio",
                "published_at": day,
                "audio_url": "https://example.org/a.mp3",
                "duration_sec": 200,
                "score": center,
                "level": "B1",
                "origin": "fresh",
            },
            {
                "guid_hash": "adjacent-text",
                "source_id": "text-source",
                "source_name": "Text Source",
                "kind": "text",
                "category": "news",
                "title": "Text",
                "url": "https://example.org/text",
                "published_at": day,
                "body_text": "word " * 200,
                "word_count": 200,
                "score": center,
                "level": "B1",
                "origin": "fresh",
            },
        ]
        trace: list[dict[str, object]] = []
        picks, filled, empty = choose_picks(candidates, day, config, trace=trace)
        self.assertEqual(len(filled), 2)
        stages = {entry["guid_hash"]: entry["stage"] for entry in trace if entry["guid_hash"]}
        self.assertEqual(stages["adjacent-audio"], "adjacent-audio")
        self.assertEqual(stages["adjacent-text"], "adjacent-text")
        self.assertEqual(len(trace), 36)
        selected = {item["guid_hash"] for item in picks.values()}
        self.assertEqual(selected, {"adjacent-audio", "adjacent-text"})

    def test_outside_preferred_window_is_badged(self):
        config = dict(DEFAULTS)
        config["languages"] = ["en"]
        day = "2026-11-21"
        candidates = [{
            "guid_hash": "long-audio",
            "source_id": "long-source",
            "source_name": "Long Source",
            "kind": "audio",
            "category": "culture",
            "title": "Long audio",
            "url": "https://example.org/long",
            "published_at": day,
            "audio_url": "https://example.org/long.mp3",
            "duration_sec": 3000,
            "score": 0.5,
            "level": "B1",
            "origin": "fresh",
        }]
        picks, _, _ = choose_picks(candidates, day, config)
        chosen = next(item for item in picks.values() if item["guid_hash"] == "long-audio")
        self.assertIn("Outside preferred window", chosen["badges"])


class ReconstructTests(unittest.TestCase):
    def test_reconstruct_matches_and_can_write_stored_picks(self):
        with tempfile.TemporaryDirectory() as raw:
            config = dict(DEFAULTS)
            config["languages"] = ["en"]
            config["data_dir"] = raw
            init_db(config)
            day = "2026-11-21"
            conn = connect(config)
            try:
                conn.execute(
                    """INSERT INTO sources
                       (id, name, feed_url, category, kind, level_min, level_max, enabled, lang)
                       VALUES (?,?,?,?,?,?,?,?,?)""",
                    ("source", "Source", "https://example.org/feed", "news", "text", "computed", "computed", 1, "en"),
                )
                cursor = conn.execute(
                    """INSERT INTO items
                       (guid_hash, source_id, kind, category, title, url, summary, published_at,
                        fetched_at, body_text, word_count, score, level, origin, lang)
                       VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                    (
                        "reconstruct-hash", "source", "text", "news", "Sample",
                        "https://example.org/sample", "Summary", day, day,
                        "word " * 200, 200, 0.55, "A1", "fresh", "en",
                    ),
                )
                item_id = int(cursor.lastrowid)
                conn.execute(
                    """INSERT INTO daily_picks
                       (date, level, category, kind, item_id, origin, badges, reconstructed, lang)
                       VALUES (?,?,?,?,?,?,?,0,?)""",
                    (day, "A1", "news", "text", item_id, "fresh", "[]", "en"),
                )
                conn.commit()
            finally:
                conn.close()
            with patch("run.load_entries", return_value=[]):
                summary = run._reconstruct(config, day, "en")
                written = run._reconstruct(config, day, "en", write=True)
            self.assertEqual(summary["matched"], 1)
            self.assertEqual(summary["reconstructed_filled"], 1)
            self.assertEqual(summary["mismatched"], 0)
            self.assertEqual(summary["missing"], 0)
            slot = next(
                item for item in summary["details"]
                if item["level"] == "A1" and item["category"] == "news" and item["kind"] == "text"
            )
            self.assertEqual(slot["status"], "matched")
            self.assertTrue(written["written"])
            conn = connect(config)
            try:
                row = conn.execute(
                    """SELECT reconstructed FROM daily_picks
                       WHERE date=? AND level='A1' AND category='news' AND kind='text' AND lang='en'""",
                    (day,),
                ).fetchone()
                self.assertEqual(int(row["reconstructed"]), 1)
            finally:
                conn.close()


class ReserveBackfillTests(unittest.TestCase):
    def test_picker_uses_language_specific_thresholds(self):
        config = dict(DEFAULTS)
        config["languages"] = ["en", "fr"]
        config["_lang"] = "fr"
        with patch("ingest.picker.level_config", return_value=(dict(DEFAULTS["level_thresholds"]), {})) as mocked:
            choose_picks([], "2026-11-21", config)
        mocked.assert_called_once()
        self.assertEqual(mocked.call_args.args[1], "fr")

    def test_reserve_candidate_uses_language_specific_thresholds(self):
        config = dict(DEFAULTS)
        config["languages"] = ["en", "fr"]
        config["_lang"] = "fr"
        with patch("ingest.reserve.common.level_config", return_value=(dict(DEFAULTS["level_thresholds"]), {})) as mocked:
            candidate = make_candidate(
                title="Sample",
                text="word " * 200,
                source_id="source",
                source_name="Source",
                category="news",
                kind="text",
                license_name="CC BY",
                attribution="Source",
                config=config,
                url="https://example.org/sample",
                published_at="2026-11-21",
            )
        mocked.assert_called_once_with(config, "fr")
        self.assertIsNotNone(candidate)
        self.assertEqual(candidate["lang"], "fr")

    def test_backfill_skips_existing_days_unless_forced(self):
        config = dict(DEFAULTS)
        config["languages"] = ["en"]
        with patch("run.successful_ingest_exists", return_value=True), patch("run.run_ingest") as ingest:
            summary = run._backfill(config, 3, None, None)
            ingest.assert_not_called()
            self.assertEqual(summary["skipped"], 3)
            self.assertEqual(summary["processed"], 0)
        with patch("run.successful_ingest_exists", return_value=True), patch(
            "run.run_ingest", return_value={"filled": 4, "report": "ok"}
        ) as ingest:
            summary = run._backfill(config, 3, None, None, force=True)
            self.assertEqual(ingest.call_count, 3)
            self.assertEqual(summary["filled"], 12)
            self.assertEqual(summary["skipped"], 0)


class LanguagePathTests(unittest.TestCase):
    def test_language_helpers_and_migration(self):
        config = {
            "languages": ["en", "xx"],
            "default_language": "xx",
            "levels": {"en": {}},
        }
        self.assertEqual(available_languages(config), ["en", "xx"])
        self.assertEqual(default_language(config), "xx")
        self.assertEqual(normalize_language(config, "es"), "xx")
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            state_dir = root / "state"
            site_dir = root / "site"
            state_dir.mkdir()
            (site_dir / "data").mkdir(parents=True)
            (state_dir / "used.json").write_text("[]", encoding="utf-8")
            (site_dir / "data" / "index.json").write_text("{}", encoding="utf-8")

            self.assertEqual(migrate_legacy_state(state_dir, "en"), ["used.json"])
            self.assertEqual(migrate_legacy_site(site_dir, "en"), ["index.json"])
            self.assertTrue((state_lang_dir(state_dir, "en") / "used.json").is_file())
            self.assertTrue((site_lang_dir(site_dir, "en") / "index.json").is_file())

            path = write_languages(site_dir, config)
            self.assertEqual(path, languages_path(site_dir))
            payload = json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual(payload["default"], "xx")
            self.assertEqual(payload["languages"], ["en", "xx"])
            self.assertEqual(site_level_path(site_dir, "2026-11-21", "B1", "en").parts[-3:],
                             ("en", "2026-11-21", "B1.json"))
            self.assertEqual(site_phrase_path(site_dir, "2026-11-21", "en").name, "phrases.json")


class MigrationAndExportTests(unittest.TestCase):
    def test_old_database_migrates_twice_with_backup(self):
        with tempfile.TemporaryDirectory() as temp:
            config = dict(DEFAULTS)
            config["languages"] = ["en"]
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
            init_db(config)
            check = connect(config)
            try:
                item_columns = {row["name"] for row in check.execute("PRAGMA table_info(items)")}
                pick_columns = {row["name"] for row in check.execute("PRAGMA table_info(daily_picks)")}
                source_columns = {row["name"] for row in check.execute("PRAGMA table_info(sources)")}
                phrase_columns = {row["name"] for row in check.execute("PRAGMA table_info(phrases)")}
                self.assertIn("lang", item_columns)
                self.assertIn("periods", item_columns)
                self.assertIn("history_terms", item_columns)
                self.assertIn("lang", pick_columns)
                self.assertIn("reconstructed", pick_columns)
                self.assertIn("lang", source_columns)
                self.assertIn("lang", phrase_columns)
                source_sql = check.execute(
                    "SELECT sql FROM sqlite_master WHERE type='table' AND name='sources'"
                ).fetchone()[0]
                self.assertIn("'phrase'", source_sql)
                self.assertEqual(check.execute("SELECT COUNT(*) FROM items").fetchone()[0], 1)
                self.assertEqual(check.execute("SELECT COUNT(*) FROM daily_picks").fetchone()[0], 1)
            finally:
                check.close()
            self.assertTrue(list(root.glob("english.db.bak-*")))

    def test_offline_ingest_writes_picks_phrases_and_static_site(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            config = dict(load_config())
            config["languages"] = ["en"]
            config["default_language"] = "en"
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
                        fetched_at, body_text, word_count, score, level, level_method, origin, lang)
                       VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                    ("test-1", "test_source", "text", "history", "A test article",
                     "https://example.org/article", day, day, "word " * 200, 200, 0.5,
                     "B1", "computed", "fresh", "en"),
                )
                conn.commit()
            finally:
                conn.close()

            summary = run_ingest(day, config, state_dir=str(root / "state"), lang="en")
            self.assertGreaterEqual(summary["filled"], 1)
            self.assertEqual(summary["phrases"], 6)
            conn = connect(config)
            try:
                self.assertEqual(conn.execute("SELECT COUNT(*) FROM phrases WHERE lang='en'").fetchone()[0], 6)
                self.assertGreaterEqual(conn.execute(
                    "SELECT COUNT(*) FROM daily_picks WHERE lang='en'"
                ).fetchone()[0], 1)
            finally:
                conn.close()

            out = root / "site"
            result = export_static(out, config, public_mode=True)
            self.assertIn(day, result["days"])
            level_path = site_level_path(out, day, "B1", "en")
            self.assertTrue(level_path.is_file())
            level_payload = json.loads(level_path.read_text(encoding="utf-8"))
            for category in ("news", "culture", "history"):
                for kind in ("text", "audio"):
                    item = level_payload["slots"][category][kind]
                    if item:
                        self.assertIn("periods", item)
                        self.assertIn("themes", item)
                        self.assertIn("history_terms", item)
                        self.assertIn("alt_text", item)
                        self.assertIn("duration_formatted", item)
                        self.assertIn("source_url", item)
            self.assertEqual(level_payload["meta"]["contract_version"], 2)
            self.assertEqual(
                level_payload["meta"]["search_path"], f"./data/en/search/{day}.json"
            )
            self.assertGreater(level_payload["meta"]["glossary_count"], 0)
            self.assertGreaterEqual(len(level_payload["exercises"]), 3)
            self.assertEqual(len(level_payload["tour"]), 7)
            self.assertEqual(level_payload["tour"][0]["id"], "home")
            self.assertIn("anki", {step["id"] for step in level_payload["tour"]})
            exercise_ids = {exercise["id"] for exercise in level_payload["exercises"]}
            self.assertIn("B1-word", exercise_ids)
            phrase_payload = json.loads(site_phrase_path(out, day, "en").read_text(encoding="utf-8"))
            self.assertIn("history", phrase_payload["B1"])
            self.assertTrue(site_phrase_path(out, day, "en").is_file())
            self.assertTrue((site_lang_dir(out, "en") / "index.json").is_file())
            self.assertTrue(languages_path(out).is_file())
            self.assertTrue(site_search_path(out, day, "en").is_file())
            self.assertTrue((out / "index.html").is_file())
            self.assertTrue((out / "manifest.webmanifest").is_file())
            self.assertTrue((out / "sw.js").is_file())

    def test_second_language_without_sources_is_isolated(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            config = dict(load_config())
            config["languages"] = ["en", "xx"]
            config["default_language"] = "en"
            config["data_dir"] = str(root / "data")
            config["ingest_offline"] = True
            config["reserve_offline"] = True
            config["phrase_offline"] = True
            day = "2026-11-21"
            init_db(config)
            summary = run_ingest(day, config, state_dir=str(root / "state"), lang="xx")
            self.assertEqual(summary["lang"], "xx")
            self.assertEqual(summary["filled"], 0)
            self.assertEqual(summary["phrases"], 0)
            self.assertTrue((state_lang_dir(root / "state", "xx") / "used.json").is_file())
            conn = connect(config)
            try:
                self.assertEqual(conn.execute(
                    "SELECT COUNT(*) FROM daily_picks WHERE lang='xx'"
                ).fetchone()[0], 0)
                self.assertEqual(conn.execute(
                    "SELECT COUNT(*) FROM phrases WHERE lang='xx'"
                ).fetchone()[0], 0)
            finally:
                conn.close()


class DoctorTests(unittest.TestCase):
    def test_check_sources_returns_structured_report(self):
        config = dict(DEFAULTS)
        config["languages"] = ["en"]
        sources = [
            {"id": "good", "name": "Good", "lang": "en", "category": "news",
             "kind": "audio", "enabled": True},
            {"id": "bad", "name": "Bad", "lang": "en", "category": "culture",
             "kind": "text", "enabled": True},
        ]
        entries = [{
            "enclosure_url": "https://example.org/a.mp3",
            "itunes_duration": "03:20",
        }]
        with patch("ingest.doctor.load_sources", return_value=sources), patch(
            "ingest.doctor.fetch_source", side_effect=[entries, RuntimeError("offline")]
        ):
            report = check_sources(config, day="2026-11-21")
        self.assertEqual(report["day"], "2026-11-21")
        self.assertEqual(report["checked"], 2)
        self.assertEqual(report["ok"], 1)
        self.assertEqual(report["failures"], 1)
        good, bad = report["sources"]
        self.assertEqual(good["status"], "ok")
        self.assertEqual(good["entries"], 1)
        self.assertEqual(good["enclosures"], 1)
        self.assertEqual(good["durations_sec"], [200])
        self.assertEqual(bad["status"], "error")
        self.assertIn("offline", bad["error"])

    def test_doctor_json_flag_prints_json(self):
        config = dict(DEFAULTS)
        config["languages"] = ["en"]
        report = {"checked": 0, "failures": 0, "sources": []}
        buffer = StringIO()
        with patch("ingest.doctor.check_sources", return_value=report), redirect_stdout(buffer):
            code = run_doctor(config, json_output=True)
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(buffer.getvalue()), report)


class ContractTests(unittest.TestCase):
    def test_serialize_day_adds_glossary_exercises_tour_and_provenance(self):
        with tempfile.TemporaryDirectory() as raw:
            config = dict(DEFAULTS)
            config["languages"] = ["en"]
            config["data_dir"] = raw
            init_db(config)
            day = "2026-11-21"
            conn = connect(config)
            try:
                conn.execute(
                    """INSERT INTO sources
                       (id, name, feed_url, category, kind, level_min, level_max, enabled, lang)
                       VALUES (?,?,?,?,?,?,?,?,?)""",
                    ("contract-source", "Contract Source", "https://example.org/feed", "history", "text",
                     "computed", "computed", 1, "en"),
                )
                conn.execute(
                    """INSERT INTO items
                       (guid_hash, source_id, kind, category, title, url, summary, published_at,
                        fetched_at, body_text, word_count, score, level, origin, lang,
                        periods, themes, history_terms)
                       VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                    (
                        "contract-hash", "contract-source", "text", "history", "Renaissance art",
                        "https://example.org/article", "A short summary", day, day,
                        "Renaissance " + "word " * 200, 201, 0.5, "B1", "fresh", "en",
                        json.dumps(["Early modern"]), json.dumps(["Culture"]),
                        json.dumps([{"text": "renaissance"}]),
                    ),
                )
                item_id = int(conn.execute("SELECT id FROM items WHERE guid_hash='contract-hash'").fetchone()[0])
                conn.execute(
                    """INSERT INTO daily_picks
                       (date, level, category, kind, item_id, origin, badges, lang)
                       VALUES (?,?,?,?,?,?,?,?)""",
                    (day, "B1", "history", "text", item_id, "fresh", "[]", "en"),
                )
                conn.commit()
                store_phrases(
                    conn,
                    day,
                    generate_phrases(config, day, raw, offline=True, lang="en"),
                    "en",
                )
                payload = serialize_day(conn, day, "B1", config, lang="en")
            finally:
                conn.close()
            self.assertEqual(payload["meta"]["contract_version"], 2)
            self.assertEqual(payload["meta"]["search_path"], f"/api/search?day={day}&lang=en")
            self.assertEqual(payload["meta"]["history_periods"], ["Early modern"])
            self.assertGreater(len(payload["glossary"]), 0)
            self.assertEqual(len(payload["exercises"]), 18)
            word_exercise = next(item for item in payload["exercises"] if item["id"] == "B1-word")
            self.assertIn(word_exercise["answer"], word_exercise["options"])
            self.assertEqual(payload["tour"][0]["id"], "home")
            self.assertEqual(payload["tour"][0]["target"], "[data-eds-hero]")
            item = payload["slots"]["history"]["text"]
            self.assertIn("Renaissance art", item["alt_text"])
            self.assertEqual(item["source_url"], "https://example.org/feed")
            self.assertEqual(item["reading_time_min"], 2)

    def test_day_endpoint_uses_enriched_serializer(self):
        client = TestClient(app)
        config = {"languages": ["en"], "default_language": "en"}
        payload = {"date": "2026-11-21", "level": "B1", "exercises": []}
        with patch("app.main.load_config", return_value=config), patch(
            "app.main.connect"
        ), patch("app.main.serialize_day", return_value=payload) as serialize:
            response = client.get("/api/day/2026-11-21?level=B1&lang=en")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), payload)
        self.assertEqual(serialize.call_args.args[1:3], ("2026-11-21", "B1"))


class SearchTests(unittest.TestCase):
    def test_search_index_and_query(self):
        with tempfile.TemporaryDirectory() as raw:
            config = dict(DEFAULTS)
            config["languages"] = ["en"]
            config["data_dir"] = raw
            init_db(config)
            day = "2026-11-21"
            conn = connect(config)
            try:
                conn.execute(
                    """INSERT INTO sources
                       (id, name, feed_url, category, kind, level_min, level_max, enabled, lang)
                       VALUES (?,?,?,?,?,?,?,?,?)""",
                    ("source", "Source", "https://example.org/feed", "history", "text", "computed", "computed", 1, "en"),
                )
                cursor = conn.execute(
                    """INSERT INTO items
                       (guid_hash, source_id, kind, category, title, url, summary, published_at,
                        fetched_at, body_text, word_count, score, level, origin, lang,
                        periods, themes, history_terms)
                       VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                    (
                        "search-hash", "source", "text", "history", "Renaissance art",
                        "https://example.org/article", "A Renaissance exhibition", day, day,
                        "Renaissance " + "word " * 200, 201, 0.5, "B1", "fresh", "en",
                        json.dumps(["Early modern"]), json.dumps(["Culture"]),
                        json.dumps([{"text": "renaissance", "meaning_fr": "renaissance"}]),
                    ),
                )
                item_id = int(cursor.lastrowid)
                conn.execute(
                    """INSERT INTO daily_picks
                       (date, level, category, kind, item_id, origin, badges, lang)
                       VALUES (?,?,?,?,?,?,?,?)""",
                    (day, "B1", "history", "text", item_id, "fresh", "[]", "en"),
                )
                conn.commit()
                index = build_search_index(conn, config, "en", day=day, public_mode=True)
            finally:
                conn.close()
            results = search_index(index, "renaissance", day=day, level="B1")
            self.assertEqual(len(results), 1)
            self.assertEqual(results[0]["title"], "Renaissance art")
            self.assertIn("renaissance", results[0]["matched_terms"])


class SearchApiTests(unittest.TestCase):
    def test_search_endpoint_filters_and_returns_results(self):
        client = TestClient(app)
        config = {"languages": ["en"], "default_language": "en"}
        results = [{"title": "Renaissance art"}]
        with patch("app.main.load_config", return_value=config), patch(
            "app.main.connect"
        ), patch("app.main.build_search_index", return_value={"items": []}) as build, patch(
            "app.main.search_index", return_value=results
        ) as search:
            response = client.get("/api/search?q=renaissance&day=2026-11-21&level=B1&lang=en")
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["query"], "renaissance")
        self.assertEqual(payload["lang"], "en")
        self.assertEqual(payload["results"], results)
        self.assertEqual(build.call_args.args[2], "en")
        self.assertEqual(search.call_args.kwargs["level"], "B1")


class PhaseOneBrandingAndLayoutTests(unittest.TestCase):
    def test_language_brand_metadata_is_available_from_config(self):
        config = load_config()
        self.assertEqual(available_languages(config), ["en", "es"])
        self.assertEqual(brand_for_language(config, "en"), "English Daily")
        self.assertEqual(brand_for_language(config, "es"), "Spanish Daily")
        metadata = language_metadata_map(config)
        self.assertEqual(metadata["en"]["label"], "English")
        self.assertEqual(metadata["en"]["tagline"], "A little English, every day.")
        self.assertEqual(metadata["es"]["label"], "Spanish")
        self.assertEqual(metadata["es"]["tagline"], "Un poco de español, cada día.")

    def test_languages_endpoint_exposes_brand_metadata(self):
        config = load_config()
        client = TestClient(app)
        with patch("app.main.load_config", return_value=config):
            response = client.get("/api/languages")
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["languages"], ["en", "es"])
        self.assertEqual(payload["brands"]["en"], "English Daily")
        self.assertEqual(payload["brands"]["es"], "Spanish Daily")
        self.assertEqual(payload["metadata"]["en"]["brand"], "English Daily")
        self.assertEqual(payload["metadata"]["es"]["brand"], "Spanish Daily")
        self.assertEqual(payload["metadata"]["es"]["tagline"], "Un poco de español, cada día.")

    def test_user_facing_brand_and_layout_markers_are_updated(self):
        root = Path(__file__).resolve().parents[1]
        index = (root / "static" / "index.html").read_text(encoding="utf-8")
        manifest = json.loads((root / "static" / "manifest.webmanifest").read_text(encoding="utf-8"))
        readme = (root / "README.md").read_text(encoding="utf-8")
        worker = (root / "static" / "sw.js").read_text(encoding="utf-8")
        self.assertEqual(app.title, "English Daily")
        self.assertIn("<title>English Daily</title>", index)
        self.assertNotIn("english·daily", index)
        self.assertNotIn("english·daily", manifest["name"])
        self.assertEqual(manifest["short_name"], "English Daily")
        self.assertTrue(readme.startswith("# English Daily\n"))
        for marker in (
            "data-eds-home", "class=\"main-nav\"", "id=\"today-view\"", "id=\"archive-view\"",
            "id=\"glossary-view\"", "id=\"settings-view\"", "data-eds-settings", "data-eds-search",
            "./lib/branding.js", "x-text=\"brand\"", "longDate(selectedDate)",
        ):
            self.assertIn(marker, index)
        self.assertNotIn("class=\"progress-panel\"", index)
        self.assertIn("./lib/branding.js", worker)


class PhaseFiveSpanishTests(unittest.TestCase):
    def test_language_setting_resolves_language_scoped_values(self):
        config = load_config()
        keywords = language_setting(config, "history_keywords", "es")
        self.assertIn("antiguo", keywords)
        self.assertEqual(language_setting(config, "history_keywords", "en"), config["history_keywords"])
        custom = {
            "languages": {"xx": {"tagline": "Etiqueta xx"}},
            "tagline": "Global tagline",
            "history_periods_by_lang": {"es": {"Antigüedad": []}},
        }
        self.assertEqual(language_setting(custom, "tagline", "xx"), "Etiqueta xx")
        self.assertEqual(language_setting(custom, "tagline", "es"), "Global tagline")
        self.assertEqual(language_setting(custom, "history_periods", "es"), {"Antigüedad": []})
        self.assertEqual(language_setting({}, "tagline", "es", "fallback"), "fallback")

    def test_stats_markdown_uses_language_brand(self):
        summary = {
            "days": 3, "lang": "es", "brand": "Spanish Daily", "by_level": {},
            "phrase_days": 2, "items": 10, "days_published": 3, "weekly_goal": 5,
        }
        markdown = run._stats_markdown(summary)
        self.assertIn("## Spanish Daily stats (3 days, es)", markdown)
        self.assertNotIn("## English Daily stats", markdown)

    def test_spanish_sources_are_registered_and_language_scoped(self):
        config = load_config()
        sources = load_sources(config, "es")
        source_ids = {str(source["id"]) for source in sources}
        self.assertGreaterEqual(len(sources), 17)
        self.assertTrue(all(str(source["lang"]) == "es" for source in sources))
        for expected in (
            "es_bbc_mundo_text", "es_charlas_hispanas", "es_rne_documentos_rne",
            "es_librivox_culture", "es_gutenberg_text", "es_wikinews",
            "es_wikipedia_history", "es_wikipedia_culture", "es_wikipedia_simple",
        ):
            self.assertIn(expected, source_ids)
        for expected in ("wikipedia", "wikipedia_simple", "wikinews", "gutenberg"):
            self.assertIn(expected, RESERVE_TYPES)
        with tempfile.TemporaryDirectory() as temp:
            local = dict(config)
            local["data_dir"] = str(Path(temp) / "data")
            init_db(local)
            registry = source_registry(local, "es")
        self.assertEqual(len(registry), len(sources))
        self.assertTrue(all(item["lang"] == "es" for item in registry))

    def test_spanish_text_metrics_are_unicode_aware(self):
        self.assertEqual(word_count("El niño corrió por el parque y se durmió."), 9)
        self.assertTrue(is_spanish("es-ES"))
        self.assertFalse(is_spanish("en"))
        values = metrics("El niño corrió por el parque. Después leyó un artículo histórico.", "es")
        self.assertGreater(values["fk_grade"], 0)
        self.assertGreater(values["score"], 0)

    def test_spanish_reserve_generators_use_spanish_hosts_and_ids(self):
        source = {
            "id": "es_wikinews",
            "lang": "es",
            "feed_url": "https://es.wikinews.org/w/api.php",
        }
        self.assertEqual(source_host(source, "en.wikinews.org"), "es.wikinews.org")
        self.assertEqual(_month_category("es", 11, 2026), "Categoría:noviembre de 2026")
        self.assertEqual(_month_category("en", 11, 2026), "Category:November 2026")

    def test_wikipedia_simple_requests_short_intro_extracts(self):
        config = dict(DEFAULTS)
        source = {
            "id": "es_wikipedia_simple", "lang": "es", "type": "wikipedia_simple",
        }
        responses = [
            {"query": {"random": [{"id": 7, "title": "Madrid"}]}},
            {"query": {"pages": {"7": {"extract": "Madrid es la capital de España."}}}},
        ]
        with patch("ingest.fetch_feeds._wiki_api", side_effect=responses) as mocked:
            entries = _wikipedia_simple(config, source)
        self.assertEqual(len(entries), 1)
        self.assertEqual(entries[0]["guid"], "es_wikipedia_simple:7")
        self.assertEqual(mocked.call_args_list[0].args[0], "es.wikipedia.org")
        params = mocked.call_args_list[1].args[1]
        self.assertEqual(params["exintro"], 1)
        self.assertEqual(params["exchars"], 4000)

    def test_spanish_serialize_strings_are_localized(self):
        payloads = {
            "A1": {
                "word": {"text": "casa", "meaning_fr": "maison"},
                "expression": {"expression": "buenos días amigo"},
                "history": {"text": "romano", "period": "Antigüedad"},
            }
        }
        exercises = _build_exercises(payloads, "es")
        prompts = [item["prompt"] for item in exercises]
        self.assertIn("¿Qué significa “casa”?", prompts)
        self.assertIn("Completa la expresión:", " ".join(prompts))
        self.assertIn("¿A qué período pertenece", " ".join(prompts))
        self.assertEqual(_TOUR_STEPS_BY_LANG["es"][0]["title"], "Empieza desde casa")
        self.assertEqual(_TOUR_STEPS_BY_LANG["es"][1]["title"], "Elige tu nivel")

    def test_export_static_writes_spanish_language_index(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            config = dict(load_config())
            config["languages"] = ["en", "es"]
            config["default_language"] = "en"
            config["data_dir"] = str(root / "data")
            init_db(config)
            out = root / "site"
            export_static(out, config, public_mode=True)
            payload = json.loads(languages_path(out).read_text(encoding="utf-8"))
            self.assertEqual(payload["languages"], ["en", "es"])
            self.assertEqual(payload["brands"]["es"], "Spanish Daily")
            self.assertTrue((site_lang_dir(out, "es") / "index.json").is_file())


class DocsTests(unittest.TestCase):
    def test_readme_documents_current_commands_and_features(self):
        root = Path(__file__).resolve().parents[1]
        readme = (root / "README.md").read_text(encoding="utf-8")
        for marker in (
            "python run.py reconstruct", "python run.py doctor --json",
            "python desktop/main.py", "python tools/build_desktop.py",
            "/api/search", "site/data/<lang>/search/YYYY-MM-DD.json",
            "Actions → daily → Run workflow", "contract_version: 2",
            "static/lib/", "no LLM", "python run.py clean-existing",
            "python tools/contrast_check.py", "text_cleaning.patterns",
            "python run.py validate-config", "python run.py demo-data",
            "python run.py backup-db", "python run.py restore-db",
            "python run.py calibrate", "Actions → ci → Run workflow",
        ):
            self.assertIn(marker, readme)


class WorkflowTests(unittest.TestCase):
    def test_workflows_are_valid_and_wire_required_commands(self):
        root = Path(__file__).resolve().parents[1]
        workflows = root / ".github" / "workflows"
        daily = (workflows / "daily.yml").read_text(encoding="utf-8")
        health = (workflows / "health.yml").read_text(encoding="utf-8")
        desktop = (workflows / "desktop.yml").read_text(encoding="utf-8")
        ci = (workflows / "ci.yml").read_text(encoding="utf-8")
        for name, text in (("daily", daily), ("health", health), ("desktop", desktop), ("ci", ci)):
            parsed = yaml.safe_load(text)
            self.assertTrue(parsed.get("jobs"), name)
        for marker in ('cron: "0 5 * * *"', "workflow_dispatch", "timeout-minutes: 60", "validate-config --json", "unittest discover", "static/lib/*.js", "reconstruct --json", "reconstruct --lang es --json", "export-static --out site --public", "deploy-pages@v4"):
            self.assertIn(marker, daily)
        for marker in ("cron:", "workflow_dispatch", "timeout-minutes: 20", "doctor --json", "upload-artifact@v4"):
            self.assertIn(marker, health)
        for marker in ("workflow_dispatch", "timeout-minutes: 30", "matrix:", "build_desktop.py", "upload-artifact@v4"):
            self.assertIn(marker, desktop)
        for marker in ("paths-ignore", "timeout-minutes: 25", "requirements-dev.txt", "playwright install", "validate-config --json", "palette_build.py", "contrast_check.py", "demo-data", "tests/e2e", "calibrate --json"):
            self.assertIn(marker, ci)


class DesktopTests(unittest.TestCase):
    def test_resolve_site_dir_requires_exported_index(self):
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            self.assertIsNone(resolve_site_dir(root))
            (root / "site").mkdir()
            self.assertIsNone(resolve_site_dir(root))
            (root / "site" / "index.html").write_text("ok", encoding="utf-8")
            self.assertEqual(resolve_site_dir(root), root / "site")

    def test_zipapp_build_contains_runtime_assets(self):
        with tempfile.TemporaryDirectory() as raw:
            artifact = build_zipapp(Path(raw) / "EnglishDaily.pyz")
            self.assertTrue(artifact.is_file())
            with zipfile.ZipFile(artifact) as archive:
                names = set(archive.namelist())
            for expected in ("__main__.py", "desktop/main.py", "app/main.py", "static/index.html", "config.yaml"):
                self.assertIn(expected, names)


class AnkiTests(unittest.TestCase):
    def test_note_builder_is_deterministic_and_escaped(self):
        entry = {
            "key": "en-bridge",
            "text": "bridge <a>",
            "meaning_fr": "pont",
            "example": "We crossed the bridge.",
            "level": "B1",
            "learned_at": "2026-11-21",
        }
        note = build_note(entry, lang="en", day="2026-11-21")
        self.assertEqual(note, build_note(entry, lang="en", day="2026-11-21"))
        self.assertEqual(len(note["guid"]), 32)
        self.assertEqual(note["fields"]["Front"], "bridge &lt;a&gt;")
        self.assertEqual(note["fields"]["Back"], "pont")
        self.assertIn("lang-en", note["tags"])
        self.assertIn("level-b1", note["tags"])
        self.assertEqual(anki_connect_note(note)["options"]["duplicateScope"], "deck")
        self.assertEqual(build_notes([entry, entry], lang="en"), [note])

    def test_python_and_javascript_note_builders_match(self):
        root = Path(__file__).resolve().parents[1]
        entry = {
            "key": "en-bridge-2",
            "text": "bridge",
            "meaning_fr": "pont",
            "meaning": "a structure over water",
            "example": "We crossed the bridge.",
            "level": "B1",
            "learned_at": "2026-11-21",
        }
        options = {"lang": "en", "day": "2026-11-21"}
        python_note = build_note(entry, lang="en", day="2026-11-21")
        result = subprocess.run(
            ["node", str(root / "tests" / "anki_bridge.js"), json.dumps(entry), json.dumps(options)],
            capture_output=True,
        )
        self.assertEqual(result.returncode, 0, result.stderr.decode("utf-8", errors="replace"))
        javascript_note = json.loads(result.stdout.decode("utf-8"))
        self.assertEqual(javascript_note["guid"], python_note["guid"])
        self.assertEqual(javascript_note["fields"], python_note["fields"])
        self.assertEqual(javascript_note["tags"], python_note["tags"])

    def test_anki_notes_cli_emits_deterministic_json(self):
        root = Path(__file__).resolve().parents[1]
        entries = [{"key": "cli-1", "text": "word", "meaning_fr": "mot"}]
        with tempfile.TemporaryDirectory() as raw:
            source = Path(raw) / "entries.json"
            source.write_text(json.dumps(entries), encoding="utf-8")
            command = [
                sys.executable, str(root / "run.py"), "anki-notes", "--entries", str(source),
                "--lang", "en", "--json",
            ]
            first = subprocess.run(command, capture_output=True, text=True)
            second = subprocess.run(command, capture_output=True, text=True)
        self.assertEqual(first.returncode, 0, first.stderr)
        self.assertEqual(first.stdout, second.stdout)
        payload = json.loads(first.stdout)
        self.assertEqual(payload["lang"], "en")
        self.assertEqual(len(payload["notes"]), 1)
        self.assertEqual(payload["ankiconnect"][0]["fields"]["Front"], "word")

    def test_anki_build_cli_writes_reusable_package(self):
        root = Path(__file__).resolve().parents[1]
        entries = [{"key": "apkg-1", "text": "word", "meaning_fr": "mot"}]
        with tempfile.TemporaryDirectory() as raw:
            source = Path(raw) / "entries.json"
            output = Path(raw) / "deck.apkg"
            source.write_text(json.dumps(entries), encoding="utf-8")
            result = subprocess.run(
                [sys.executable, str(root / "run.py"), "anki-build", "--entries", str(source), "--out", str(output), "--lang", "en"],
                capture_output=True,
                text=True,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertTrue(output.is_file())
            self.assertTrue(zipfile.is_zipfile(output))


class ContrastTests(unittest.TestCase):
    def test_contrast_ratio_math(self):
        self.assertAlmostEqual(contrast_ratio("#000000", "#ffffff"), 21.0, places=3)
        self.assertAlmostEqual(contrast_ratio("#77736a", "#fbfaf7"), 4.53, places=2)

    def test_css_theme_contrast_audit_passes(self):
        css = (Path(__file__).resolve().parents[1] / "static" / "css" / "themes.css").read_text(encoding="utf-8")
        report = audit_css(css)
        self.assertTrue(report["ok"])
        self.assertTrue(report["dark_definitions_match"])
        self.assertEqual(len(report["rows"]), 54)
        self.assertTrue(all(row["pass"] for row in report["rows"]))

    def test_contrast_check_cli_emits_json(self):
        root = Path(__file__).resolve().parents[1]
        result = subprocess.run(
            [sys.executable, str(root / "tools" / "contrast_check.py"), "--css", str(root / "static" / "css" / "themes.css"), "--json"],
            capture_output=True,
            text=True,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        report = json.loads(result.stdout)
        self.assertTrue(report["ok"])


class PaletteBuildTests(unittest.TestCase):
    def test_generated_css_matches_committed_file(self):
        root = Path(__file__).resolve().parents[1]
        css = (root / "static" / "css" / "themes.css").read_text(encoding="utf-8")
        self.assertEqual(css, build_css())
        for preset in ("paper", "sepia", "ink", "contrast", "system"):
            self.assertIn(f':root[data-theme="{preset}"]', css)
        self.assertIn("@media (prefers-color-scheme: dark)", css)

    def test_palette_build_check_command_passes(self):
        root = Path(__file__).resolve().parents[1]
        result = subprocess.run(
            [sys.executable, str(root / "tools" / "palette_build.py"), "--check", "--out", str(root / "static" / "css" / "themes.css")],
            capture_output=True,
            text=True,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("theme palette check: PASS", result.stdout)

    def test_all_palette_tokens_pass_accessibility_audit(self):
        report = audit_palettes()
        self.assertTrue(report["ok"])
        self.assertEqual(len(report["rows"]), 54)


class FrontendAssetTests(unittest.TestCase):
    def test_modular_accessible_frontend_assets_are_present(self):
        root = Path(__file__).resolve().parents[1]
        static = root / "static"
        index = (static / "index.html").read_text(encoding="utf-8")
        script = (static / "app.js").read_text(encoding="utf-8")
        styles = (static / "style.css").read_text(encoding="utf-8")
        worker = (static / "sw.js").read_text(encoding="utf-8")
        for name in ("store.js", "branding.js", "settings.js", "links.js", "progress.js", "exercises.js", "tour.js", "search.js", "archive.js", "pwa.js", "anki.js"):
            self.assertIn(f"./lib/{name}", index)
            self.assertIn(f"./lib/{name}", worker)
            self.assertTrue((static / "lib" / name).is_file())
        self.assertIn("./css/themes.css", index)
        self.assertIn("./css/themes.css", worker)
        self.assertTrue((static / "css" / "themes.css").is_file())
        for marker in ("data-eds-hero", "data-eds-level", "data-eds-tabs", "data-eds-phrase", "data-eds-exercises", "role=\"dialog\"", "tour-spotlight"):
            self.assertIn(marker, index)
        for marker in ("EDExercises", "EDTour", "EDSearch", "cycleTab", "runSearch", "EDProgress", "dailyTotal", "practicedDates", "ankiAvailable", "canExportAnki", "openAnkiHelp", "exportableAnkiItems", "EDSettings", "setPreference", "resetPreferences", "prefersDark", "visibleExerciseAnswer", "EDArchive", "calendar()", "selectArchiveDate", "shiftArchiveMonth", "openSearchResult", "AnkiConnect", "ankiNotes", "sendAnkiConnect", "checkAnkiConnect", "ankiConnectStatus", "maybeStartTour(", "tourSpotlightStyle(", "trapTourTab(", "data-eds-tour-tabindex", "EDTour.seen(", "EDTour.markSeen("):
            self.assertIn(marker, script)
        for marker in (":focus-visible", "prefers-reduced-motion", ".skip-link", ".exercise-options", ".tour-dialog", ".tour-spotlight", ".tour-highlight", ".source-links", ".source-link-label", ".anki-button.anki-ready", ".anki-button.anki-unlearned", ".anki-status", ".settings-grid", "data-text-size", "data-reading-font", "data-motion", ".archive-calendar", ".calendar-grid", ".calendar-day", ".archive-days", ".setting-input", ".anki-actions"):
            self.assertIn(marker, styles)
        for marker in ("data-eds-anki", "ankiStatus(", "ankiLabel(", "Anki help"):
            self.assertIn(marker, index)
        for marker in ("data-eds-settings-controls", "Theme preset", "Text size", "Reading font", "Default audio speed", "Show exercise answers immediately", "Mark texts as read while scrolling", "Reduce motion", "Reset settings"):
            self.assertIn(marker, index)
        for marker in ("data-eds-calendar", "Previous month", "Next month", "Recent editions", "Open edition", 'x-text="calendar().label"'):
            self.assertIn(marker, index)
        for marker in ("AnkiConnect URL", "data-eds-anki-connect", "data-eds-anki-connect-check", "data-eds-anki-connect-status", "Send to AnkiConnect", "Check AnkiConnect"):
            self.assertIn(marker, index)
        links = (static / "lib" / "links.js").read_text(encoding="utf-8")
        for marker in ("Read the full text", "Listen to the original audio"):
            self.assertIn(marker, links)
        for marker in ("sourceLabel(", "hasSourceUrl("):
            self.assertIn(marker, index)
            self.assertIn(marker, script)
        manifest = json.loads((static / "manifest.webmanifest").read_text(encoding="utf-8"))
        self.assertEqual(manifest["display"], "standalone")
        self.assertEqual(manifest["start_url"], "./")
        self.assertEqual(manifest["scope"], "./")
        self.assertTrue(manifest["shortcuts"][0]["url"].startswith("./"))
        self.assertIn("SKIP_WAITING", worker)
        self.assertIn("request.mode === 'navigate'", worker)
        self.assertIn("offline-banner", index)
        self.assertIn("EDPwa", script)

    def test_language_switching_and_spanish_branding_assets_are_present(self):
        root = Path(__file__).resolve().parents[1]
        static = root / "static"
        index = (static / "index.html").read_text(encoding="utf-8")
        script = (static / "app.js").read_text(encoding="utf-8")
        branding = (static / "lib" / "branding.js").read_text(encoding="utf-8")
        exercises = (static / "lib" / "exercises.js").read_text(encoding="utf-8")
        self.assertIn("data-eds-language-select", index)
        self.assertIn("setLanguage(", index)
        self.assertIn("setLanguage(", script)
        self.assertIn("languageOptions()", index)
        for marker in (
            "languageOptions(", "languageUrl(", "indexUrl(", "updateLanguageUrl(",
            "loadLanguagePayload(", "loadDays(",
        ):
            self.assertIn(marker, script)
        for marker in ("Spanish Daily", "Un poco de español, cada día."):
            self.assertIn(marker, index)
            self.assertIn(marker, branding)
        self.assertIn("document.documentElement.lang", script)
        self.assertIn("exercise:${language}:", exercises)

    def test_frontend_helpers_run_without_browser(self):
        root = Path(__file__).resolve().parents[1]
        result = subprocess.run(
            ["node", str(root / "tests" / "frontend_helpers.js")],
            capture_output=True,
            text=True,
        )
        self.assertEqual(result.returncode, 0, result.stderr)


class SourcesApiTests(unittest.TestCase):
    def test_sources_endpoint_filters_language(self):
        registry = [{"id": "en-1", "name": "Source", "lang": "en", "items": 4}]
        client = TestClient(app)
        with patch("app.main.source_registry", return_value=registry) as mocked:
            response = client.get("/api/sources?lang=en")
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["lang"], "en")
        self.assertEqual(payload["sources"], registry)
        mocked.assert_called_once()
        self.assertEqual(mocked.call_args.args[1], "en")


class PhaseSixTourTests(unittest.TestCase):
    def test_tour_steps_include_home_for_both_languages(self):
        expected = ["home", "level", "tabs", "phrase", "exercises", "anki", "glossary"]
        for lang in ("en", "es"):
            steps = list(_TOUR_STEPS_BY_LANG[lang])
            self.assertEqual([step["id"] for step in steps], expected)
            for step in steps:
                self.assertEqual(set(step), {"id", "title", "body", "target"})
                self.assertTrue(step["target"].startswith("[data-eds-"))
        self.assertEqual(_TOUR_STEPS_BY_LANG["en"][0]["title"], "Start at home")
        self.assertEqual(_TOUR_STEPS_BY_LANG["en"][0]["target"], "[data-eds-hero]")
        self.assertEqual(_TOUR_STEPS_BY_LANG["es"][0]["title"], "Empieza desde casa")


class PhaseSevenE2ETests(unittest.TestCase):
    def test_playwright_e2e_tooling_is_present(self):
        root = Path(__file__).resolve().parents[1]
        dev_requirements = (root / "tests" / "requirements-dev.txt").read_text(encoding="utf-8")
        self.assertIn("playwright==", dev_requirements)

        e2e_dir = root / "tests" / "e2e"
        required = (
            "config.py",
            "e2e_harness.py",
            "test_brand_layout.py",
            "test_themes_settings.py",
            "test_archive_search.py",
            "test_anki_connect.py",
            "test_spanish_switch.py",
            "test_tour_home_highlight.py",
        )
        for name in required:
            self.assertTrue((e2e_dir / name).is_file(), name)

        harness = (e2e_dir / "e2e_harness.py").read_text(encoding="utf-8")
        for marker in ("export_static", "http.server", "127.0.0.1:8765", "route.abort"):
            self.assertIn(marker, harness)

        report = (root / "TEST_REPORT.md").read_text(encoding="utf-8")
        self.assertIn("Playwright", report)


class PhaseEightWorkflowsTests(unittest.TestCase):
    def test_config_validation_accepts_repo_defaults_and_reports_issues(self):
        config = dict(load_config())
        report = validate_config(config)
        self.assertTrue(report["ok"], report["issues"])

        languages = {
            code: dict(metadata) for code, metadata in config["languages"].items()
        }
        languages["en"]["brand"] = ""
        broken = dict(config)
        broken["languages"] = languages
        report = validate_config(broken)
        self.assertFalse(report["ok"])
        self.assertTrue(any("en: missing brand metadata" in issue for issue in report["issues"]))

    def test_demo_backup_restore_and_calibrate_are_wired(self):
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            config = dict(load_config())
            config["data_dir"] = str(root / "data")
            summary = build_demo_data(config, root / "site", root / "state", ["2026-11-21"])
            self.assertTrue((root / "site" / "index.html").is_file())
            self.assertEqual(summary["languages"], ["en", "es"])

            backup = backup_database(config, root / "backup.sqlite3")
            self.assertTrue(Path(backup["backup"]).is_file())
            restore_config = dict(config)
            restore_config["data_dir"] = str(root / "restore")
            restored = restore_database(restore_config, backup["backup"])
            self.assertTrue(Path(restored["target"]).is_file())
            with self.assertRaises(FileExistsError):
                restore_database(restore_config, backup["backup"])

            calibration = calibrate_report(config, lang="en")
            english = calibration["reports"]["en"]
            self.assertGreaterEqual(english["bank"]["words"], 120)
            self.assertGreaterEqual(english["sources"], 1)
            self.assertIn("C2", english["thresholds"])

    def test_validate_config_cli_is_wired(self):
        root = Path(__file__).resolve().parents[1]
        result = subprocess.run(
            [sys.executable, str(root / "run.py"), "validate-config", "--json"],
            capture_output=True,
            text=True,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        payload = json.loads(result.stdout)
        self.assertTrue(payload["ok"], payload["issues"])


if __name__ == "__main__":
    unittest.main()
