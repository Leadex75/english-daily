from __future__ import annotations

import os

BROWSER = os.environ.get("E2E_BROWSER", "chromium")
HEADLESS = os.environ.get("E2E_HEADLESS", "1") not in {"0", "false", "False"}
BASE_URL = os.environ.get("E2E_BASE_URL", "").rstrip("/")
EXECUTABLE_PATH = os.environ.get("E2E_CHROMIUM_PATH") or None
CHANNEL = os.environ.get("E2E_CHANNEL") or None
TIMEOUT_MS = int(os.environ.get("E2E_TIMEOUT_MS", "10000"))
VIEWPORT = {"width": 1280, "height": 900}
BROWSER_ARGS = ["--no-sandbox", "--disable-dev-shm-usage"]
