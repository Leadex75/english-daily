from __future__ import annotations

from playwright.sync_api import expect

from e2e_harness import E2EHarness


class TourHomeHighlightSpec(E2EHarness):
    DISMISS_TOUR = False

    def test_first_visit_home_step_focus_trap_and_seen_state(self) -> None:
        dialog = self.page.locator(".tour-dialog")
        expect(dialog).to_be_visible()
        expect(dialog.locator(".eyebrow")).to_have_text("Tour 1 / 7")
        expect(dialog.locator("#tour-title")).to_have_text("Start at home")
        expect(self.page.locator("[data-eds-hero].tour-highlight")).to_be_visible()
        self.assertIn("left:", self.page.locator(".tour-spotlight").get_attribute("style") or "")

        focused_target = self.page.evaluate(
            "() => Boolean(document.activeElement && document.activeElement.hasAttribute('data-eds-hero'))"
        )
        self.assertTrue(focused_target)
        self.page.keyboard.press("Tab")
        trapped = self.page.evaluate(
            "() => Boolean(document.querySelector('.tour-dialog')?.contains(document.activeElement))"
        )
        self.assertTrue(trapped)

        dialog.get_by_role("button", name="Next").click()
        expect(dialog.locator("#tour-title")).to_have_text("Choose your level")
        expect(self.page.locator("[data-eds-level].tour-highlight")).to_be_visible()
        dialog.get_by_role("button", name="Skip tour").click()
        expect(dialog).to_be_hidden()

        self.page.reload()
        self.page.wait_for_selector("[data-eds-route]")
        expect(dialog).to_be_hidden()

        self.page.get_by_role("button", name="Start the guided tour").click()
        expect(dialog).to_be_visible()
        self.page.locator("[data-eds-anki]").click()
        expect(dialog.locator("#tour-title")).to_have_text("Export learned items")
