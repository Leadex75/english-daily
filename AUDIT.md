# Codebase audit

## Scope and method

- Repository: `Leadex75/english-daily`; local branch `main` at `44d6ccb` with a clean tree.
- Audit date: `2026-11-21`.
- Method: static read of backend, ingest pipeline, banks, state, static frontend, service worker, docs, tests, dependencies and all three GitHub Actions workflows; four parallel audit passes were consolidated and verified against the source files.
- Baseline verification:
  - `.\.venv\Scripts\python.exe -m unittest discover -s tests -v` — 41 tests passed.
  - `python -m compileall -q app ingest desktop tools run.py tests` — passed.
  - `node --check` for `static/app.js`, `static/sw.js`, and every `static/lib/*.js`; `node tests/frontend_helpers.js` — passed.
  - `python tools/contrast_check.py --css static/style.css` — passed.
- The system Python lacks PyYAML; use the project virtualenv for Python tests.

## Baseline matrix

| ID | Baseline capability | Status | Evidence / gap |
| --- | --- | --- | --- |
| B1 | Deterministic 36-slot daily pipeline | present | `ingest/picker.py` selects six levels x three categories x two kinds with explicit fresh/reserve/adjacent stages; `ingest/pipeline.py` writes `daily_picks`; no LLM or API keys. |
| B2 | Source registry and health checks | present | `sources.yaml` has 28 English sources; `ingest/doctor.py` and `run.py doctor --json` report per-source counts and errors; `/api/sources` exposes metadata. |
| B3 | Multilingual configuration and data layout | present | `config.yaml` has `languages`, `default_language`, per-language levels/history config; `ingest/paths.py` partitions `state/<lang>/` and `site/data/<lang>/`; SQLite rows carry `lang`. Only English is actually configured. |
| B4 | Reserve generation and idempotent backfill | present | `ingest/reserve/` generators, language-scoped thresholds, pool caps, and `run.py backfill --force` semantics are implemented. |
| B5 | Offline deterministic reconstruction | present | `run.py reconstruct` replays the cascade from SQLite, traces 36 slots, compares stored picks, and can write with `--write`. |
| B6 | History terms and bilingual phrase bank | present | `bank/en/words.yaml`, `expressions.yaml`, `history_terms.yaml`; six phrase payloads per day; history annotations flow through serialize/search. English history bank is only 36 terms, below the expanded 120-term target. |
| B7 | Search indexes and search API | present | `ingest/search.py`, per-day static indexes, `/api/search`; shared public-mode excerpt rules. Search is rebuilt per API request. |
| B8 | Versioned enriched day contract | present | `app/serialize.py` emits contract v2 with slots, phrase, glossary, exercises, tour and provenance metadata. |
| B9 | Enriched frontend, PWA, desktop and workflows | partial | Modular accessible frontend, PWA, desktop launcher/zipapp and daily/health/desktop workflows exist; new brand/layout/themes/archive/Anki Connect/Spanish/tour-home/E2E requirements do not. |

## New-spec gap matrix

| Phase | Area | Status | Main findings |
| --- | --- | --- | --- |
| 1 | Branding and main layout | missing | Product strings are still `english-daily` / `english·daily`; README title and API `name` use the old slug; no language selector; no home/calendar/archive shell; progress bars sit in a separate top panel; search is a top-level panel. |
| 2 | Themes and settings | partial | Light/dark data-theme and localStorage exist, but only two hard-coded themes, no system preset, no settings surface, no theme tokens for multiple palettes, no font/audio/exercise preferences. `tools/contrast_check.py` only audits the current two palettes. |
| 3 | Archive and current-day history | partial | Date select and previous/next buttons use available days; no true calendar, no month grouping, no visible archive navigation, no current-day indicator beyond `days[0]`. |
| 4 | Anki | partial | Browser TSV download, learned-only gating, status labels and Anki tour step exist. Missing persistent note model, deterministic note fields/tags, AnkiConnect client, backend note builder/export path, and dedicated tests. |
| 5 | Spanish | missing | `languages: [en]`, 28 English-only sources, `site/data/languages.json` only `en`; no `bank/es`, `state/es`, or `site/data/es`; no Spanish source registry, brands, history config, or live source verification. |
| 6 | Guided tour / home highlight | done | Seven serialized tour steps begin at the home hero; the tour has a positioned spotlight, highlighted target treatment, hidden-view preparation, focus trapping/restoration, Anki-help reopen and first-visit auto-start. |
| 7 | Tests and E2E | done | 63 Python tests, frontend helper Node checks, contrast audit and static checks exist. Playwright dev requirements, env config, deterministic static-export harness, six E2E specs and `TEST_REPORT.md` are present; E2E blocks external requests and stubs AnkiConnect. |
| 8 | Workflows and docs | done | Daily, health, desktop and `ci.yml` exist; CI has push/PR path filters, all workflows have timeouts, and docs describe the English Daily/Spanish Daily UI and new commands. `validate-config`, `demo-data`, `backup-db`, `restore-db` and `calibrate` are wired into the CLI, tests and workflows. |

## Current UI control inventory

### Global chrome

| Control | Location | Current behavior |
| --- | --- | --- |
| `Skip to content` link | `static/index.html:29` | Focusable skip link to `#reading-panel`. |
| `Update` button | header, conditional | Appears in static mode when a service-worker update is available; calls `applyUpdate()`. |
| `Tour` button | header | Starts the guided tour at step 0. |
| `Light` / `Dark` button | header | Toggles hard-coded light/dark theme and persists `english-daily:theme`. |
| `Anki` button | header | Exports all learned glossary items as TSV; disabled when no glossary or export unavailable. |
| `Anki help` button | header, `[data-eds-anki]` | Opens the tour at the `anki` step. |

### Date, level, search and progress

| Control | Location | Current behavior |
| --- | --- | --- |
| Previous day `←` button | controls | Shifts `selectedDate` one entry earlier when possible. |
| `Date` select (`#day-select`) | controls | Lists available day strings and calls `loadDay()` on change. |
| Next day `→` button | controls | Shifts `selectedDate` one entry later when possible. |
| Six level buttons `A1`–`C2` | controls, `[data-eds-level]` | Select the CEFR level; read/listened completion adds `done` styling. |
| Search input (`#search-input`) | search panel | Free-text archive query over current day/level. |
| `Search` submit button | search panel | Runs static index query or `/api/search`. |
| `Clear` button | search panel | Clears query and results. |
| Search result links | search panel, dynamic | Open matching item URLs in a new tab. |
| `Today` progress bar | progress panel | Read-only percentage and `count / total` from local markers. |
| `This week` progress bar | progress panel | Read-only percentage and practiced-day count against weekly goal. |

### Category tabs and reading cards

| Control | Location | Current behavior |
| --- | --- | --- |
| `News` tab | tablist | Selects news slots; shows completion check. |
| `Culture` tab | tablist | Selects culture slots; shows completion check. |
| `History` tab | tablist | Selects history slots; shows completion check. |
| `Phrase` tab | tablist | Selects phrase panel and exercises; shows completion check. |
| Text publisher link | text card | `Read the full text` / source name, opens publisher URL. |
| `Read the full text on <source>` link | text card, conditional | Shown for truncated/public-mode items. |
| `Mark as read` / `Read ✓` button | text card | Marks or displays read state. |
| Audio publisher link | audio card | `Listen to the original audio` / source name, opens publisher URL. |
| Audio fallback link | audio card, conditional | `Listen to the original audio` shown when playback fails. |
| Play/Pause button | audio player | Toggles embedded audio playback. |
| Seek range | audio player | Sets `audio.currentTime`. |
| Speed buttons `0.8x`, `1x`, `1.25x` | audio player | Set playback rate. |
| `Hear it` button (word) | phrase card | Plays dictionary audio URL when present. |
| `Mark learned` / `Learned ✓` button (word) | phrase card | Toggles local learned state. |
| Anki item button (word) | phrase card | Exports learned word; disabled/unavailable states from `anki.js`. |
| Anki status text (word) | phrase card | Live region describing Anki readiness. |
| `Hear it` button (expression) | phrase card | Plays expression audio URL when present. |
| `Mark learned` / `Learned ✓` button (expression) | phrase card | Toggles local learned state. |
| Anki item button (expression) | phrase card | Exports learned expression. |
| Anki status text (expression) | phrase card | Live region describing Anki readiness. |
| `Mark learned` / `Learned ✓` button (history term) | phrase card | Toggles local learned state. |
| Anki item button (history term) | phrase card | Exports learned history term. |
| Anki status text (history term) | phrase card | Live region describing Anki readiness. |
| Exercise option buttons | daily practice, dynamic | Answer multiple-choice/cloze exercises; correct/wrong feedback is shown. |
| `Export all to Anki` / `Anki unavailable` button | glossary | Exports all learned glossary cards. |
| `remove` button | glossary, per entry | Forgets the selected learned phrase. |
| `Skip tour` button | tour dialog | Ends the tour and resets state. |
| `Next` / `Done` button | tour dialog | Advances or closes the tour. |

### Status and non-interactive controls

- Offline banner, loading notice, error notice, audio-error notice, search status, exercise feedback, Anki status and tour counter are live regions only.
- The language selector, home link, calendar grid, month selector, settings controls, theme preset buttons and AnkiConnect status button are live controls; the tour spotlight is a visual-only `aria-hidden` layer.

## Architecture and data findings

- Backend: FastAPI in `app/main.py`; SQLite helpers in `app/db.py`; contract serialization in `app/serialize.py`; static files mounted at `/`.
- Ingest: `ingest/fetch_feeds.py`, `fetch_text.py`, `fetch_audio.py`, `readability.py`, `picker.py`, `pipeline.py`, `pool.py`, `state.py`, `phrases.py`, `search.py`, `doctor.py`, `export_static.py`, plus reserve generators under `ingest/reserve/`.
- CLI: `run.py` supports `serve`, `ingest`, `backfill`, `reconstruct`, `export-static`, `import-state`, `stats`, `doctor`, `clean-existing` and `prune`.
- Content: English-only banks with 180 expressions, 124 words and 36 history terms; one language in `config.yaml`, `sources.yaml` and static language index.
- State/site layout: `state/en/` and `site/data/en/` are present; per-day level JSON, phrases JSON and search JSON are exported with relative URLs.
- Frontend modules: `store.js`, `links.js`, `progress.js`, `anki.js`, `exercises.js`, `tour.js`, `search.js`, `pwa.js`; all are in the service-worker app shell.
- Tests/docs: 41 unit tests in `tests/test_app.py`, helper checks in `tests/frontend_helpers.js`, contrast checker in `tools/contrast_check.py`; README still uses old product casing/wordmark.

## Risks and decisions

- Preserve existing modules and extend in place; do not rewrite the working deterministic pipeline.
- Keep repo slug and generated paths as `english-daily`; change only user-visible brand strings to `English Daily` / `Spanish Daily`.
- Keep all generated site URLs relative and audio hotlinked.
- Back up `data/english-daily.sqlite3` before any schema or data migration.
- Add runtime dependencies only where required by the brief (`genanki`); keep Playwright in dev requirements.
- Do not add Pillow or any LLM/API-key service.

## Addendum Phase 10 resolution

- Root cause: the previous AnkiConnect client posted `application/json`, which triggers a browser CORS preflight; AnkiConnect's default `webCorsOriginList` only allows `http://localhost`, so the GitHub Pages origin is rejected and the old UI gave no diagnosis.
- Resolution: direct requests now use `text/plain` without a preflight, provide explicit origin/permission/connection guidance, and fall back to a loopback-only same-origin proxy in the desktop launcher. The FastAPI server also exposes the same allowlisted proxy.
- The proxy permits only `version`, `requestPermission`, `modelFieldNames`, `createModel` and `addNotes`; it caps request size and timeout, validates local Host/Origin/Referer, and never logs bodies or keys.
- Notes are verified against `bank/anki_models.json` before sending; model fields can be created when absent, and added/duplicate/failed counts are surfaced in the Anki view.
- Manual diagnosis uses `tools/fake_ankiconnect.py` with `ok`, `origin-not-allowed`, `not-running`, `slow`, `permission-denied` and `duplicate notes` modes.
