import json
import sqlite3
import tempfile
import unittest
from collections import Counter
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path
from unittest.mock import patch

from app.db import (
    DEFAULTS,
    available_languages,
    connect,
    data_dir,
    db_path,
    default_language,
    init_db,
    load_config,
    normalize_language,
    upsert_sources,
)
from app.main import app
from fastapi.testclient import TestClient

from ingest.doctor import check_sources, run_doctor
from ingest.export_static import export_static
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
from ingest.phrases import annotate_history, generate_phrases, load_bank, load_history_terms
from ingest.picker import choose_picks
from ingest.pipeline import run_ingest
from ingest.readability import band_center
from ingest.reserve.common import make_candidate
from ingest.search import build_search_index, search_index
import run


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
        self.assertEqual(len(terms), 36)
        self.assertEqual({str(item["level"]) for item in terms}, set(expected_words))
        for item in terms:
            self.assertTrue(str(item.get("meaning_fr") or "").strip())
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


if __name__ == "__main__":
    unittest.main()
