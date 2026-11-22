from __future__ import annotations

from playwright.sync_api import expect

from e2e_harness import E2EHarness


class SpanishSwitchSpec(E2EHarness):
    def test_spanish_brand_content_paths_and_exercise_keys(self) -> None:
        self.select_language("es")
        expect(self.page.locator("[data-eds-home] .brand-mark")).to_have_text("Spanish Daily")
        expect(self.page.locator("[data-eds-home] .tagline")).to_have_text(
            "Un poco de español, cada día."
        )
        expect(self.page.locator("html")).to_have_attribute("lang", "es")
        self.assertIn("lang=es", self.page.url)

        self.page.click("#tab-phrase")
        expect(self.page.locator("[data-eds-exercises]")).to_be_visible()
        self.page.locator("[data-eds-exercises] .exercise-options button").first.click()
        keys = self.page.evaluate(
            "() => Object.keys(localStorage).filter((key) => key.startsWith('english-daily:exercise:'))"
        )
        self.assertTrue(any(key.startswith("english-daily:exercise:es:") for key in keys))
        self.assertFalse(any(key.startswith("english-daily:exercise:en:") for key in keys))

        self.select_language("en")
        expect(self.page.locator("[data-eds-home] .brand-mark")).to_have_text("English Daily")
        self.assertNotIn("lang=es", self.page.url)
        keys = self.page.evaluate(
            "() => Object.keys(localStorage).filter((key) => key.startsWith('english-daily:exercise:'))"
        )
        self.assertTrue(any(key.startswith("english-daily:exercise:es:") for key in keys))
        self.assertFalse(any(key.startswith("english-daily:exercise:en:") for key in keys))
