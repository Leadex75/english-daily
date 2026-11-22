# Test report

## Commands

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
.\.venv\Scripts\python.exe -m compileall -q app ingest desktop tools run.py tests
node --check static/app.js
node --check static/sw.js
Get-ChildItem static/lib/*.js | ForEach-Object { node --check $_.FullName }
node tests/frontend_helpers.js
python tools/palette_build.py --check --out static/css/themes.css
python tools/contrast_check.py --css static/css/themes.css --json > $null
.\.venv\Scripts\python.exe run.py validate-config --json
.\.venv\Scripts\python.exe run.py calibrate --json
.\.venv\Scripts\python.exe run.py demo-data --out <temp-dir>/demo-site --data-dir <temp-dir>/demo-data --state-dir <temp-dir>/demo-state --date 2026-11-21 --json
.\.venv\Scripts\python.exe run.py backup-db --out <temp-dir>/backup.sqlite3 --json
.\.venv\Scripts\python.exe run.py restore-db --from <temp-dir>/backup.sqlite3 --data-dir <temp-dir>/restore-data --json
.\.venv\Scripts\python.exe run.py export-static --out <temp-dir>/site --public
$env:E2E_CHROMIUM_PATH = "C:\Program Files\Google\Chrome\Application\chrome.exe"
.\.venv\Scripts\python.exe -m unittest discover -s tests/e2e -v
```

## Results

- Phase 5: 61 unit tests passed.
- Phase 6: 62 unit tests passed.
- Phase 7: 63 unit tests passed.
- Phase 8: 66 unit tests passed.
- Static checks: compileall, JavaScript syntax checks, frontend helpers, palette check and contrast audit passed.
- Phase 7 E2E: 6 Playwright tests passed against a deterministic static export, with external requests blocked and AnkiConnect stubbed.
- E2E coverage: brand/layout, theme/settings persistence, calendar/search, AnkiConnect success/failure plus TSV fallback, Spanish language switch, and first-visit tour/home spotlight.
- Phase 8 CLI smoke: `validate-config --json` returned `ok: true`; `calibrate --json`, `demo-data`, `backup-db`, `restore-db` and a temp public static export all succeeded.
- Final E2E rerun after Phase 8: 6 Playwright tests passed.

## Environment

- Python: project virtual environment at `.\.venv`.
- Browser: Chromium via `E2E_CHROMIUM_PATH` when set; otherwise Playwright's installed Chromium.
- Static E2E server: Python `http.server` on an ephemeral localhost port.
- External network: blocked from browser routes except the stubbed AnkiConnect endpoint at `127.0.0.1:8765`.
