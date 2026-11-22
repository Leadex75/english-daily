# Test report

## Commands

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
.\.venv\Scripts\python.exe -m compileall -q app ingest desktop tools run.py tests
node --check static/app.js
node --check static/sw.js
Get-ChildItem static/lib/*.js, static/js/*.js | ForEach-Object { node --check $_.FullName }
node tests/frontend_helpers.js
python tools/palette_build.py --check --out static/css/themes.css
python tools/contrast_check.py --css static/css/themes.css --json > $null
.\.venv\Scripts\python.exe run.py validate-config --json
.\.venv\Scripts\python.exe run.py calibrate --json
.\.venv\Scripts\python.exe run.py demo-data --out <temp-dir>/demo-site --data-dir <temp-dir>/demo-data --state-dir <temp-dir>/demo-state --date 2026-11-21 --json
.\.venv\Scripts\python.exe run.py backup-db --out <temp-dir>/backup.sqlite3 --json
.\.venv\Scripts\python.exe run.py restore-db --from <temp-dir>/backup.sqlite3 --data-dir <temp-dir>/restore-data --json
.\.venv\Scripts\python.exe run.py export-static --out <temp-dir>/site --public
.\.venv\Scripts\python.exe tools/fake_ankiconnect.py --mode ok --port 8765
$env:E2E_CHROMIUM_PATH = "C:\Program Files\Google\Chrome\Application\chrome.exe"
.\.venv\Scripts\python.exe -m unittest discover -s tests/e2e -v
```

Screenshot outputs are written to `tests/screenshots/` by the `test_screenshots.py` E2E spec. The
folder is ignored by Git; regenerate it after UI or palette changes.

## Results

- Phase 5: 61 unit tests passed.
- Phase 6: 62 unit tests passed.
- Phase 7: 63 unit tests passed.
- Phase 8: 66 unit tests passed.
- Static checks: compileall, JavaScript syntax checks, frontend helpers, palette check and contrast audit passed.
- Phase 7 E2E: 6 Playwright tests passed against a deterministic static export, with external requests blocked and AnkiConnect stubbed.
- E2E coverage: brand/layout, theme/settings persistence, calendar/search, AnkiConnect success/failure plus TSV fallback, CORS/permission/not-running diagnoses, duplicate counts, proxy detection, Spanish language switch, first-visit tour/Today spotlight, and responsive screenshot capture.
- Phase 8 CLI smoke: `validate-config --json` returned `ok: true`; `calibrate --json`, `demo-data`, `backup-db`, `restore-db` and a temp public static export all succeeded.
- Final E2E rerun after Phase 8: 6 Playwright tests passed.
- Addendum Phase 9: 66 unit tests passed; 7 Playwright tests passed, including responsive screenshots for main, Archive, Anki and Settings at 360/768/1280 in Paper and Ink palettes.
- Addendum Phase 9 static checks: compileall, JavaScript syntax checks, frontend helpers, palette check and contrast audit passed.
- Addendum Phase 10: 75 unit tests passed; 12 Playwright tests passed, including origin/permission/not-running diagnostics, duplicate counts and proxy-mode detection.
- Addendum Phase 10 static checks: compileall, JavaScript syntax checks (including `static/js/`), frontend helpers, palette check and contrast audit passed.
- Addendum Phase 10 proxy checks: allowlist, loopback/Host/Origin/Referer validation, body cap, `text/plain` direct calls, model definitions and fake-server modes all passed in unit tests.
- Addendum Phase 11: 77 unit tests passed; 16 Playwright tests passed, including reading mode, annotation persistence, quiz score, semester progress, shortcuts dialog and ICS reminder download.
- Addendum Phase 11 static checks: compileall, all JavaScript syntax checks (including all `static/lib/` modules), frontend helpers, palette check and contrast audit passed.
- Addendum Phase 11 storage checks: new `eds.<lang>.*` keys are covered by frontend helpers and E2E cleanup; legacy `english-daily:*` keys remain unchanged.
- Addendum Phase 12: 79 unit tests passed; 16 Playwright tests passed, including persisted annotation highlight tones and translated tour copy.
- Addendum Phase 12 static checks: compileall, all JavaScript syntax checks, frontend helpers, palette build and 72-pair contrast audit passed.

## Environment

- Python: project virtual environment at `.\.venv`.
- Browser: Chromium via `E2E_CHROMIUM_PATH` when set; otherwise Playwright's installed Chromium.
- Static E2E server: Python `http.server` on an ephemeral localhost port.
- External network: blocked from browser routes except the stubbed AnkiConnect endpoint at `127.0.0.1:8765`; the same-origin `/api/ankiconnect` proxy is stubbed when proxy mode is enabled.
