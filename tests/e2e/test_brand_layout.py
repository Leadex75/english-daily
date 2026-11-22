from __future__ import annotations

from playwright.sync_api import expect

from e2e_harness import E2EHarness


class BrandLayoutSpec(E2EHarness):
    def test_brand_navigation_and_home_highlight_targets(self) -> None:
        expect(self.page).to_have_title("English Daily")
        expect(self.page.locator("[data-eds-home] .brand-mark")).to_have_text("English Daily")
        expect(self.page.locator("[data-eds-home] .tagline")).to_have_text(
            "A little English, every day."
        )
        expect(self.page.locator("[data-eds-home]")).to_have_attribute(
            "aria-label", "English Daily home"
        )
        expect(self.page.locator("[data-eds-hero]")).to_be_visible()
        for view in ("today", "archive", "glossary", "settings"):
            expect(self.page.locator(f'.main-nav a[href="#{view}"]')).to_have_count(1)
        self.assertEqual(self.page.locator(".progress-panel").count(), 0)
