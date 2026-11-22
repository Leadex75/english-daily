from __future__ import annotations

from playwright.sync_api import expect

from e2e_harness import E2EHarness


class ThemesSettingsSpec(E2EHarness):
    def test_theme_size_font_motion_and_reset_persist(self) -> None:
        self.page.click('.main-nav a[href="#settings"]')
        expect(self.page.locator("#settings-view")).to_be_visible()
        controls = self.page.locator("[data-eds-settings-controls]")

        for label, value in (
            ("Paper", "paper"),
            ("Sepia", "sepia"),
            ("Ink", "ink"),
            ("High contrast", "contrast"),
            ("System", "system"),
        ):
            controls.get_by_role("button", name=label, exact=True).click()
            expect(self.page.locator("html")).to_have_attribute("data-theme", value)

        controls.get_by_role("button", name="Large", exact=True).click()
        expect(self.page.locator("html")).to_have_attribute("data-text-size", "large")
        controls.get_by_role("button", name="Sans", exact=True).click()
        expect(self.page.locator("html")).to_have_attribute("data-reading-font", "sans")
        controls.get_by_role("checkbox", name="Reduce motion").check()
        expect(self.page.locator("html")).to_have_attribute("data-motion", "reduce")

        self.page.reload()
        self.page.wait_for_selector("[data-eds-route]")
        self.page.click('.main-nav a[href="#settings"]')
        expect(self.page.locator("html")).to_have_attribute("data-text-size", "large")
        expect(self.page.locator("html")).to_have_attribute("data-reading-font", "sans")
        expect(self.page.locator("html")).to_have_attribute("data-motion", "reduce")

        self.page.locator("[data-eds-settings-controls]").get_by_role(
            "button", name="Reset settings", exact=True
        ).click()
        expect(self.page.locator("html")).to_have_attribute("data-theme", "system")
        expect(self.page.locator("html")).to_have_attribute("data-text-size", "medium")
        expect(self.page.locator("html")).to_have_attribute("data-motion", "auto")
