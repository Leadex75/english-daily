from __future__ import annotations

from pathlib import Path

from e2e_harness import E2EHarness


class ScreenshotSpec(E2EHarness):
    def test_capture_responsive_screenshots_in_two_palettes(self) -> None:
        out = Path(__file__).resolve().parents[1] / "screenshots"
        out.mkdir(parents=True, exist_ok=True)
        views = (
            ("main", lambda page: page.goto(f"{self.base_url}#today")),
            ("archive", lambda page: page.goto(f"{self.base_url}#archive")),
            ("anki", lambda page: page.goto(f"{self.base_url}#anki")),
            ("settings", lambda page: page.goto(f"{self.base_url}#settings")),
        )
        for theme in ("paper", "ink"):
            self.page.evaluate(
                """(theme) => {
                    localStorage.setItem('english-daily:settings', JSON.stringify({ theme }));
                    localStorage.setItem('english-daily:tour:seen', JSON.stringify(true));
                }""",
                theme,
            )
            for width in (360, 768, 1280):
                self.page.set_viewport_size({"width": width, "height": 900})
                self.page.reload()
                self.page.wait_for_selector("[data-eds-route]")
                self.dismiss_tour()
                for name, navigate in views:
                    navigate(self.page)
                    self.page.wait_for_timeout(120)
                    self.page.screenshot(
                        path=str(out / f"{name}-{theme}-{width}.png"), full_page=True
                    )
        self.assertTrue((out / "main-paper-360.png").is_file())
        self.assertTrue((out / "settings-ink-1280.png").is_file())
        settings = self.page.evaluate(
            "() => JSON.parse(localStorage.getItem('english-daily:settings') || '{}')"
        )
        self.assertEqual(settings, {"theme": "ink"})
