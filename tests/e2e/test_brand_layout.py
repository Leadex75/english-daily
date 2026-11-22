from __future__ import annotations

from playwright.sync_api import expect

from e2e_harness import E2EHarness


class BrandLayoutSpec(E2EHarness):
    def test_brand_navigation_and_clean_home_layout(self) -> None:
        expect(self.page).to_have_title("English Daily")
        expect(self.page.locator("[data-eds-home] .brand-mark")).to_have_text("English Daily")
        expect(self.page.locator("[data-eds-home]")).to_have_attribute(
            "aria-label", "English Daily home"
        )
        expect(self.page.locator("[data-eds-today]")).to_be_visible()
        expect(self.page.locator("[data-eds-tab-archive]")).to_be_visible()
        expect(self.page.locator("[data-eds-anki-open]")).to_be_visible()
        expect(self.page.locator("[data-eds-settings-open]")).to_be_visible()
        expect(self.page.locator("#day-select")).to_have_count(0)
        expect(self.page.locator(".progress-panel")).to_have_count(0)
        expect(self.page.locator(".main-nav")).to_have_count(0)
        expect(self.page.locator("[data-eds-hero]")).to_have_count(0)
