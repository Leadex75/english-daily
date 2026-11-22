from __future__ import annotations

from playwright.sync_api import expect

from e2e_harness import E2EHarness


class AnkiConnectSpec(E2EHarness):
    def test_glossary_anki_connect_and_tsv_fallback(self) -> None:
        self.page.click("#tab-phrase")
        self.page.locator("#phrase-panel .phrase-card button", has_text="Mark learned").first.click()
        self.page.click('.main-nav a[href="#glossary"]')
        expect(self.page.locator("#glossary-view")).to_be_visible()
        expect(self.page.locator("[data-eds-glossary] li").first).to_be_visible()

        self.page.locator("[data-eds-anki-connect-check]").click()
        expect(self.page.locator("[data-eds-anki-connect-status]")).to_have_text(
            "AnkiConnect 6 is ready."
        )

        self.route_anki_failure(True)
        self.page.locator("[data-eds-anki-connect]").click()
        expect(self.page.locator("[data-eds-anki-connect-status]")).to_contain_text(
            "AnkiConnect export failed: stubbed failure"
        )

        self.route_anki_failure(False)
        self.page.locator("[data-eds-anki-connect]").click()
        expect(self.page.locator("[data-eds-anki-connect-status]")).to_contain_text(
            "AnkiConnect added"
        )

        with self.page.expect_download() as download_info:
            self.page.get_by_role("button", name="Export learned words to Anki").click()
        self.assertTrue(download_info.value.suggested_filename.endswith(".txt"))
