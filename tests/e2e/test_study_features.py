from __future__ import annotations

from playwright.sync_api import expect

from e2e_harness import DAY, E2EHarness


class StudyFeaturesSpec(E2EHarness):
    def test_reading_mode_and_annotations_are_local(self) -> None:
        toggle = self.page.locator("[data-eds-reading-toggle]")
        toggle.click()
        expect(self.page.locator("html")).to_have_attribute("data-reading", "focus")
        expect(toggle).to_be_visible()
        toggle.click()
        expect(self.page.locator("html")).to_have_attribute("data-reading", "off")

        self.page.fill("#annotation-input", "Keep this sentence")
        self.page.click("[data-eds-annotation-save]")
        note = self.page.locator("[data-eds-annotations] li").first
        expect(note).to_contain_text("Keep this sentence")
        keys = self.page.evaluate(
            "() => Object.keys(localStorage).filter((key) => key.startsWith('eds.en.annotations.'))"
        )
        self.assertTrue(keys)

        self.page.reload()
        self.page.wait_for_selector("[data-eds-route]")
        expect(self.page.locator("[data-eds-annotations] li").first).to_contain_text("Keep this sentence")

    def test_quiz_check_saves_score(self) -> None:
        self.page.click("#tab-phrase")
        expect(self.page.locator("[data-eds-exercises]")).to_be_visible()
        self.page.locator("[data-eds-exercises] .exercise-options button").first.click()
        self.page.click("[data-eds-quiz-check]")
        expect(self.page.locator(".quiz-message")).to_contain_text("correct")
        keys = self.page.evaluate(
            "() => Object.keys(localStorage).filter((key) => key.startsWith('eds.en.quiz.'))"
        )
        self.assertEqual(len(keys), 1)

    def test_semester_plan_tracks_practice(self) -> None:
        mark_read = self.page.locator("[data-eds-mark-read]")
        if mark_read.is_enabled():
            mark_read.click()
        self.page.click("#tab-semester")
        expect(self.page.locator("[data-eds-semester]")).to_be_visible()
        self.page.fill("[data-eds-semester-start]", DAY)
        self.page.fill("[data-eds-semester-end]", DAY)
        self.page.fill("[data-eds-semester-goal]", "1")
        self.page.click("[data-eds-semester-save]")
        expect(self.page.locator("[data-eds-semester-progress] .byline")).to_contain_text("1 of 1 days")
        keys = self.page.evaluate(
            "() => Object.keys(localStorage).filter((key) => key === 'eds.en.semester')"
        )
        self.assertEqual(keys, ["eds.en.semester"])

    def test_shortcuts_dialog_and_reminder_download(self) -> None:
        self.page.click("[data-eds-shortcuts-open]")
        dialog = self.page.locator("[data-eds-shortcuts]")
        expect(dialog).to_be_visible()
        expect(dialog.locator(".shortcut-list li")).to_have_count(11)
        self.page.click("[data-eds-shortcuts-close]")
        expect(dialog).to_be_hidden()

        self.page.click("[data-eds-settings-open]")
        self.page.fill("[data-eds-reminder-time]", "08:30")
        with self.page.expect_download() as download_info:
            self.page.click("[data-eds-reminders-download]")
        self.assertTrue(download_info.value.suggested_filename.endswith(".ics"))
