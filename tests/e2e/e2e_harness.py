from __future__ import annotations

import http.server
import json
import tempfile
import time
import threading
import unittest
from pathlib import Path
from typing import Any

from playwright.sync_api import Browser, BrowserContext, Page, sync_playwright

from app.db import connect, init_db, load_config, upsert_sources
from ingest.export_static import export_static
from ingest.pipeline import run_ingest

try:
    from .config import (
        BASE_URL,
        BROWSER,
        BROWSER_ARGS,
        CHANNEL,
        EXECUTABLE_PATH,
        HEADLESS,
        TIMEOUT_MS,
        VIEWPORT,
    )
except ImportError:
    from config import (
        BASE_URL,
        BROWSER,
        BROWSER_ARGS,
        CHANNEL,
        EXECUTABLE_PATH,
        HEADLESS,
        TIMEOUT_MS,
        VIEWPORT,
    )

DAY = "2026-11-21"
DAYS = (DAY, "2026-11-20")
AUDIO_EXTENSIONS = (".mp3", ".m4a", ".ogg", ".wav")


class _QuietHandler(http.server.SimpleHTTPRequestHandler):
    def log_message(self, format: str, *args: Any) -> None:
        return


class E2EHarness(unittest.TestCase):
    DISMISS_TOUR = True

    @classmethod
    def setUpClass(cls) -> None:
        cls._temp: tempfile.TemporaryDirectory[str] | None = None
        cls._server: http.server.ThreadingHTTPServer | None = None
        cls._thread: threading.Thread | None = None
        cls._playwright = None
        cls.browser: Browser | None = None
        if BASE_URL:
            cls.base_url = BASE_URL
        else:
            cls._temp = tempfile.TemporaryDirectory()
            out = Path(cls._temp.name) / "site"
            cls._seed(out)
            handler = lambda *args, **kwargs: _QuietHandler(*args, directory=str(out), **kwargs)
            cls._server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
            cls._thread = threading.Thread(target=cls._server.serve_forever, daemon=True)
            cls._thread.start()
            cls.base_url = f"http://127.0.0.1:{cls._server.server_address[1]}"
        cls._playwright = sync_playwright().start()
        launch: dict[str, Any] = {"headless": HEADLESS, "args": BROWSER_ARGS}
        if EXECUTABLE_PATH:
            launch["executable_path"] = EXECUTABLE_PATH
        elif CHANNEL:
            launch["channel"] = CHANNEL
        cls.browser = getattr(cls._playwright, BROWSER).launch(**launch)

    @classmethod
    def tearDownClass(cls) -> None:
        if cls.browser is not None:
            cls.browser.close()
        if cls._playwright is not None:
            cls._playwright.stop()
        if cls._server is not None:
            cls._server.shutdown()
            cls._server.server_close()
        if cls._thread is not None:
            cls._thread.join(timeout=5)
        if cls._temp is not None:
            cls._temp.cleanup()

    @classmethod
    def _seed(cls, out: Path) -> None:
        root = out.parent
        config = dict(load_config())
        config["default_language"] = "en"
        config["data_dir"] = str(root / "data")
        config["ingest_offline"] = True
        config["reserve_offline"] = True
        config["phrase_offline"] = True
        init_db(config)
        sources = []
        for lang in ("en", "es"):
            for kind in ("text", "audio"):
                sources.append({
                    "id": f"test_{lang}_{kind}",
                    "name": f"Test {lang} {kind}",
                    "feed_url": "generated",
                    "category": "news",
                    "kind": kind,
                    "level_min": "B1",
                    "level_max": "B1",
                    "enabled": True,
                    "lang": lang,
                })
        upsert_sources(sources, config)
        conn = connect(config)
        try:
            for day in DAYS:
                for lang in ("en", "es"):
                    title = "Renaissance art and reform" if lang == "en" else "Renacimiento y reforma"
                    audio_title = "Museum audio guide" if lang == "en" else "Guía audio del museo"
                    body = ("word " if lang == "en" else "palabra ") * 200
                    for kind, item_title, duration in (("text", title, None), ("audio", audio_title, 120)):
                        conn.execute(
                            """INSERT INTO items
                               (guid_hash, source_id, kind, category, title, url, summary,
                                published_at, fetched_at, body_text, word_count, duration_sec,
                                audio_remote_url, score, level, level_method, origin, lang)
                               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                            (
                                f"{lang}-{kind}-{day}",
                                f"test_{lang}_{kind}",
                                kind,
                                "news",
                                item_title,
                                f"https://example.org/{lang}/{kind}/{day}",
                                item_title,
                                day,
                                day,
                                body,
                                200,
                                duration,
                                f"https://example.org/{lang}/{day}.mp3" if kind == "audio" else None,
                                0.5,
                                "B1",
                                "computed",
                                "fresh",
                                lang,
                            ),
                        )
            conn.commit()
        finally:
            conn.close()
        for lang in ("en", "es"):
            for day in DAYS:
                run_ingest(day, config, state_dir=str(root / "state"), lang=lang)
        export_static(out, config, public_mode=True)

    def setUp(self) -> None:
        self.anki_connect_fail = False
        self.anki_mode = "ok"
        self.anki_proxy = False
        self.context: BrowserContext = self.browser.new_context(
            viewport=VIEWPORT,
            locale="en-US",
            timezone_id="UTC",
            color_scheme="light",
            reduced_motion="no-preference",
            service_workers="block",
            accept_downloads=True,
        )
        self.context.route("**/*", self._route_request)
        self.page: Page = self.context.new_page()
        self.page.set_default_timeout(TIMEOUT_MS)
        self.page.goto(self.base_url)
        self.page.wait_for_selector("[data-eds-route]")
        self.clear_local_storage()
        self.page.reload()
        self.page.wait_for_selector("[data-eds-route]")
        if self.DISMISS_TOUR:
            self.dismiss_tour()

    def tearDown(self) -> None:
        self.context.close()

    def clear_local_storage(self) -> None:
        self.page.evaluate(
            """() => Object.keys(localStorage)
                .filter((key) => key.startsWith('english-daily:'))
                .forEach((key) => localStorage.removeItem(key))"""
        )

    def dismiss_tour(self) -> None:
        dialog = self.page.locator(".tour-dialog")
        try:
            dialog.wait_for(state="visible", timeout=3000)
        except Exception:
            return
        dialog.get_by_role("button", name="Skip tour").click()
        dialog.wait_for(state="hidden")

    def select_language(self, code: str) -> None:
        self.page.select_option("[data-eds-language-select]", code)
        self.page.wait_for_function(
            "expected => new URLSearchParams(window.location.search).get('lang') === expected",
            arg=code,
        )

    def route_anki_failure(self, failed: bool) -> None:
        self.anki_connect_fail = failed
        self.anki_mode = "error" if failed else "ok"

    def route_anki_mode(self, mode: str, proxy: bool = False) -> None:
        self.anki_mode = mode
        self.anki_proxy = proxy

    def _route_request(self, route: Any) -> None:
        url = route.request.url
        path = url.split("?", 1)[0].lower()
        if "127.0.0.1:8765" in url:
            self._fulfill_anki(route)
            return
        if self.anki_proxy and path.endswith("/api/ankiconnect"):
            self._fulfill_anki(route)
            return
        if path.endswith(AUDIO_EXTENSIONS):
            route.abort()
            return
        if self.base_url and url.startswith(self.base_url):
            route.continue_()
            return
        route.abort()

    def _fulfill_anki(self, route: Any) -> None:
        try:
            payload = route.request.post_data_json or {}
        except ValueError:
            payload = {}
        action = payload.get("action")
        params = payload.get("params") or {}
        status = 200
        if self.anki_mode == "not-running":
            route.abort("failed")
            return
        if self.anki_mode == "origin-not-allowed":
            status = 403
            body = {"result": None, "error": "origin is not in webCorsOriginList"}
            route.fulfill(status=status, content_type="application/json", body=json.dumps(body))
            return
        if self.anki_mode == "slow":
            time.sleep(6)
        if action == "version":
            body = {"result": 6, "error": None}
        elif action == "requestPermission":
            body = {"result": None, "error": None}
        elif action == "modelFieldNames":
            if params.get("modelName") == "English Daily Cloze":
                fields = ["Text", "Extra", "Source", "Level", "Language", "Date", "Guid"]
            else:
                fields = ["Front", "Back", "Example", "Source", "Level", "Language", "Date", "Guid"]
            body = {"result": fields, "error": None}
        elif action == "createModel":
            body = {"result": {"name": params.get("modelName")}, "error": None}
        elif action == "addNotes":
            notes = params.get("notes") or []
            if self.anki_mode in ("error", "permission-denied"):
                body = {"result": None, "error": "AnkiConnect permission not granted for this origin"}
            elif self.anki_mode == "duplicate notes":
                body = {"result": [None for _ in notes], "error": None}
            else:
                body = {"result": list(range(1, len(notes) + 1)), "error": None}
        else:
            body = {"result": None, "error": None}
        route.fulfill(status=status, content_type="application/json", body=json.dumps(body))
