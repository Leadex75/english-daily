from __future__ import annotations

import re

from playwright.sync_api import expect

from e2e_harness import E2EHarness


class ArchiveSearchSpec(E2EHarness):
    def test_calendar_search_and_open_edition(self) -> None:
        self.page.click("[data-eds-tab-archive]")
        expect(self.page.locator("#archive-view")).to_be_visible()
        expect(self.page.locator("[data-eds-calendar] .calendar-weekdays span")).to_have_count(7)
        available = self.page.locator("[data-eds-calendar] .calendar-day:not([disabled])")
        self.assertGreaterEqual(available.count(), 2)

        self.page.fill("#search-input", "Renaissance")
        self.page.click('[data-eds-search] button[type="submit"]')
        results = self.page.locator(".search-results li")
        expect(results.first).to_be_visible()
        self.assertIn("Renaissance", results.first.inner_text())
        results.first.get_by_role("button", name="Open edition").click()
        expect(self.page).to_have_url(re.compile(r"#today$"))

        self.page.click("[data-eds-tab-archive]")
        expect(self.page.locator(".search-results li").first).to_be_visible()
        self.page.get_by_role("button", name="Clear", exact=True).click()
        expect(self.page.locator(".search-results")).to_be_hidden()
