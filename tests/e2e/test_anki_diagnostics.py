from __future__ import annotations

from playwright.sync_api import expect

from e2e_harness import E2EHarness


class AnkiDiagnosticsSpec(E2EHarness):
    def save_one_phrase_and_open_anki(self) -> None:
        self.page.click("#tab-phrase")
        self.page.locator("#phrase-panel .phrase-card button", has_text="Save word").first.click()
        self.page.locator("[data-eds-anki-open]").click()
        expect(self.page.locator("[data-eds-glossary] li").first).to_be_visible()

    def test_origin_diagnostic(self) -> None:
        self.save_one_phrase_and_open_anki()
        self.route_anki_mode("origin-not-allowed")
        self.page.locator("[data-eds-anki-connect-check]").click()
        expect(self.page.locator("[data-eds-anki-connect-status]")).to_contain_text("AnkiConnect unavailable")
        expect(self.page.locator("[data-eds-anki-connect-diagnostic]")).to_contain_text("webCorsOriginList")
        expect(self.page.locator("[data-eds-anki-connect-diagnostic]")).to_contain_text(self.base_url)

    def test_not_running_diagnostic(self) -> None:
        self.save_one_phrase_and_open_anki()
        self.route_anki_mode("not-running")
        self.page.locator("[data-eds-anki-connect-check]").click()
        expect(self.page.locator("[data-eds-anki-connect-status]")).to_contain_text("AnkiConnect unavailable")
        expect(self.page.locator("[data-eds-anki-connect-diagnostic]")).to_contain_text("Start Anki")

    def test_permission_diagnostic(self) -> None:
        self.save_one_phrase_and_open_anki()
        self.route_anki_mode("permission-denied")
        self.page.locator("[data-eds-anki-connect]").click()
        expect(self.page.locator("[data-eds-anki-connect-status]")).to_contain_text("permission not granted")
        expect(self.page.locator("[data-eds-anki-connect-diagnostic]")).to_contain_text("grant access")

    def test_duplicate_counts(self) -> None:
        self.save_one_phrase_and_open_anki()
        self.route_anki_mode("duplicate notes")
        self.page.locator("[data-eds-anki-connect]").click()
        expect(self.page.locator("[data-eds-anki-connect-status]")).to_have_text(
            "AnkiConnect added 0 note(s); 1 already present."
        )
        expect(self.page.locator("[data-eds-anki-connect-counts]")).to_contain_text("duplicates 1")

    def test_proxy_mode(self) -> None:
        self.save_one_phrase_and_open_anki()
        self.route_anki_mode("ok", proxy=True)
        self.page.locator("[data-eds-anki-connect-check]").click()
        expect(self.page.locator("[data-eds-anki-connect-status]")).to_have_text(
            "AnkiConnect 6 is ready via proxy."
        )
