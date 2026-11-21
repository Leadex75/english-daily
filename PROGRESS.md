# Progress

## Baseline (before Phase 1)

- Repo synced with `origin/main` at `8c78180`.
- Existing implementation already covers: 36-slot cascade picker, reserve generators, history category, phrase bank, basic glossary/Anki/progress, PWA, static export, workflow.
- Gaps confirmed against spec: multilingual `lang` dimension and lang-specific paths, reconstruct command, doctor `--json`, search indexes, history terms, enriched frontend modules/exercises/tour, desktop app, health workflow, many contract fields.
- Local SQLite backed up to `data/english.db.bak-20261121` before migrations.
- Decision: keep existing modules and extend them in place; no rewrite. Implement phases in order and commit after each phase.

## Phase 1 — multilingual configuration and data layout (done)

- Added `languages`, `default_language`, `online_site_url`, per-language `levels`, `history_periods` and `history_themes` to config; all 28 sources are tagged `lang: en`.
- Added `ingest/paths.py` and migrated existing state/site trees to `state/en/` and `site/data/en/`; static export now writes `site/data/languages.json`, `site/data/<lang>/index.json`, per-day levels and phrases.
- SQLite schema now carries `lang` on sources, items, daily picks, phrases, books and ingest runs; migration is idempotent and verified twice on a copy plus the live database.
- All ingest/export/API commands accept a language; commands without `--lang` process all configured languages, and unknown languages fall back to the configured default.
- Frontend reads `languages.json`/`/api/languages` and uses language-prefixed data paths while preserving existing localStorage keys.
- Tests: 7 unit tests passed (`python -m unittest discover -s tests -v`), including old-DB migration twice, language paths, legacy file migration, static export under `en/`, and a dummy second language with no sources.
- Verification: Python modules compile; `node --check` passes for `app.js`, `sw.js`, `anki.js`; static export succeeded (2 days, 12 level files); API smoke returned 200 for health, languages, days, day, phrase and stats.
- Phase 1 committed as `6d1fa2d`.

## Phase 2 — source registry and health checks (done)

- `ingest/doctor.py` now exposes `check_sources()` with a structured report: per-source language, category, kind, entry count, enclosure count, sample durations and error detail.
- `run.py doctor --json [--lang CODE]` prints the report as JSON; text output remains the default and the command keeps returning 0.
- Added `/api/sources?lang=...` backed by `source_registry()` in `app/db.py`, including source metadata, license, type and stored item counts; 28 English sources are returned without network calls.
- Tests: 10 unit tests passed, including structured doctor results, JSON flag output and language-filtered sources API.
- Verification: Python modules compile; CLI JSON smoke printed valid JSON; API smoke returned 200 with 28 sources.
- Phase 2 committed as `f3e3f0e`.

## Phase 3 — pure cascade refinements (done)

- Cascade stages are now explicit and deterministic: exact fresh preferred, exact fresh other, exact reserve/archive, adjacent audio, adjacent text.
- Added an optional `trace` to `choose_picks()` and exposed it on `run_ingest()` summaries for later reconstruct reporting.
- Selections prefer soft-window candidates first, keep source/audio caps where possible, and badge outside-preferred picks alongside existing archive/reserve/adjacent badges.
- Tests: 12 unit tests passed, including explicit stage tracing, adjacent audio/text split and outside-preferred badges.
- Verification: Python modules compile; `node --check` passes for frontend scripts.
- Phase 3 committed as `617effb`.

## Phase 4 — reserve and backfill refinements (done)

- Reserve sampling, readability classification and the picker now use per-language `levels.<lang>.thresholds` instead of the global English thresholds.
- Reserve candidates and pool items carry their language explicitly; `generate_reserves()` builds a language-scoped scoring config for all built-in and LibriVox generators.
- `run.py backfill` is now idempotent: days with an existing successful ingest are skipped unless `--force` is passed, with processed/skipped counts in the summary.
- `run_ingest()` summaries expose a 36-slot cascade trace for future reconstruct reporting.
- Tests: 15 unit tests passed, including language-specific threshold use in picker and reserve, and backfill skip/force behavior.
- Verification: Python modules compile; `node --check` passes; CLI backfill smoke succeeded in an isolated temp data directory.
- Phase 4 committed as `1efd1ff`.

## Phase 5 — deterministic reconstruction (done)

- Added `run.py reconstruct [--date] [--lang] [--state-dir] [--write] [--json]` to rebuild a day offline from stored DB candidates using the same pure cascade.
- Reconstruction excludes prior state hashes dated before the target day, compares rebuilt picks against stored picks, and reports matched/mismatched/missing/extra/empty slots.
- Dry-run mode is the default; `--write` replaces stored picks and marks them `reconstructed=1` without touching state ledgers, phrases or network sources.
- Tests: 16 unit tests passed, including reconstruct match detection and write-back flag behavior.
- Verification: Python modules compile; CLI JSON smoke succeeded in an isolated temp data directory.
- Phase 5 committed as `7edde9e`.

## Phase 6 — history terms and bilingual phrase bank (done)

- Added `bank/en/history_terms.yaml` with 36 CEFR-leveled, bilingual (EN/FR) history terms tagged by period, theme and aliases.
- Phrase generation now selects one level-matched history term per level per day, along with the existing word and expression.
- History items are annotated in fresh ingest and reserve generation with matched periods, themes and term details.
- Added `items.history_terms` to the SQLite schema with an idempotent migration; serialized day items now expose `periods`, `themes` and `history_terms`.
- Tests: 17 unit tests passed, including history bank shape, annotation, phrase history payload, migration and static export contract.
- Verification: Python modules compile; `node --check` passes; live stats command migrated the database and returned 200-equivalent CLI output with a fresh backup.
- Phase 6 committed as `5d0ab25`.

## Phase 7 — search indexes and search API (done)

- Added `ingest/search.py` with deterministic, dependency-free index building and weighted term matching over titles, phrases, history terms, summaries, bodies and sources.
- Static export now writes one search index per language and day to `site/data/<lang>/search/<day>.json`, respecting public-mode excerpt rules.
- Added server endpoint `GET /api/search?q=...&day=...&level=...&limit=...&lang=...` with validation and the same ranking logic.
- Tests: 19 unit tests passed, including index building/query ranking, search API filtering and static search file export.
- Verification: Python modules compile; `node --check` passes; API smoke returned HTTP 200 with an empty result set in an isolated temp data directory.
- Phase 7 committed as `980ff23`.

## Phase 8 — enriched day contract (done)

- Day payloads now expose a versioned contract with `glossary`, `exercises`, `tour` and richer per-item provenance: alt text, source URL, formatted duration and reading time.
- Exercise generation is deterministic, CEFR-scoped, and covers word meaning, expression cloze and history period questions with distractors drawn from the same day's phrase bank.
- Static exports point to per-day relative search indexes; the server payload points to `/api/search`.
- Tests: 21 unit tests passed, including serialization, API reuse of the enriched contract, static export fields and provenance metadata.
- Verification: `compileall` passes; `node --check` passes; API smoke returned HTTP 200 with the enriched contract; static export smoke produced 12 exercises, 12 glossary entries, 5 tour steps and the relative search path.
- Phase 8 committed as `acce3cf`.

## Phase 9 — modular accessible frontend (done)

- Split the frontend into browser-native modules for storage, exercises, guided tour and search; all modules are cached by the service worker.
- The day UI now renders history terms, daily exercises, archive search and a guided tour from the enriched contract.
- Added keyboard tab navigation, skip link, focus-visible outlines, dialog focus handling and reduced-motion support.
- Tests: 22 unit tests passed, including asset/module presence and service-worker cache coverage.
- Verification: `node --check` passes for all JavaScript assets; static export smoke copied all new modules into the generated site.
- Phase 9 committed as `2affa27`.

## Phase 10 — PWA and offline polish (done)

- Manifest now provides standalone display, shortcuts, categories, relative scope/start URLs and install metadata.
- Service worker adds navigation fallback, message-based `SKIP_WAITING`, and caches the new PWA module; exported builds still receive a generated cache version.
- Added offline status UI and an update flow backed by `lib/pwa.js`.
- Tests: 22 unit tests passed, including manifest relative paths, service-worker fallback/update markers and offline UI presence.
- Verification: `node --check` passes; static export smoke confirmed versioned cache, PWA module, navigation fallback and manifest in the generated site.
- Phase 10 committed as `5d64463`.

## Phase 11 — desktop launcher and packaging (done)

- Added a local desktop launcher that serves the exported static site when available and otherwise starts the FastAPI app on localhost.
- Added a stdlib zipapp builder plus an optional PyInstaller path with `desktop/EnglishDaily.spec`; no new runtime dependencies were introduced.
- Tests: 24 unit tests passed, including site resolution and zipapp contents.
- Verification: desktop CLI help works; zipapp build smoke produced a runnable artifact containing runtime source and static assets.
- Phase 11 committed as `dce5bac`.

## Phase 12 — GitHub Actions workflows (done)

- Daily workflow now compiles Python, checks every JavaScript module, verifies deterministic reconstruction and retains Pages deployment.
- Added a scheduled/manual health workflow that runs `doctor --json` and uploads the source report.
- Added a manual/tag desktop workflow that builds zipapps on Linux, Windows and macOS plus an optional Windows executable artifact.
- Tests: 25 unit tests passed, including YAML validity and required workflow commands.
- Verification: `compileall` and all JavaScript syntax checks pass.
- Phase 12 committed as `40ad251`.

## Phase 13 — documentation refresh (done)

- README now documents multilingual layout, reconstruction/backfill, enriched contract, search, exercises/tour, PWA, desktop launcher/build, all three workflows, source resilience and publishing rules.
- Tests: 26 unit tests passed, including documentation coverage of current commands, paths and APIs.
- Verification: `compileall` and all JavaScript syntax checks pass.
- Phase 13 committed as `c06fa7f`.

## Phase 14 — final verification and release (done)

- Final test suite: 26 unit tests passed; `compileall` and all JavaScript syntax checks passed.
- Source health: `python run.py doctor --json` checked 28 sources with 28 OK and 0 failures.
- API smoke: all eight public endpoints returned HTTP 200 against the live database.
- Reconstruction: `run.py reconstruct --write` aligned today's stored picks with the deterministic cascade; the regenerated static site exposes contract v2, 12 exercises, 12 glossary entries, 5 tour steps, per-day search indexes and six versioned JS modules.
- Static site regenerated in public mode with a fresh versioned service worker cache.

## New brief — Phase 0 — audit (done)

- Audited the whole codebase with four parallel passes (pipeline/backend, frontend/UI, content/state, workflows/docs) and verified the findings against source files.
- Added `AUDIT.md` with present/partial/missing status for B1–B9, new-spec gaps by phase, a complete current UI control inventory, architecture/data findings, and decisions.
- Verified baseline: 41 unit tests passed in `.venv`; Python compile check passed; all JavaScript syntax checks and `tests/frontend_helpers.js` passed; contrast audit passed with light/dark definitions matching.
- Decision: use the project `.venv` for Python tests because the system Python has no PyYAML.
- Remaining: Phases 1–8; no implementation or migration was performed in this audit phase.

## New brief — Phase 1 — branding and main layout (done)

- Changed all user-facing brand strings to `English Daily`: document title, manifest, API metadata, CLI output, stats heading, desktop banner and README title; repository slug, URLs, DB filename, storage keys and cache seeds remain `english-daily`.
- Added `languages.<code>.brand`, `label` and `tagline` metadata to `config.yaml`; `available_languages()` now accepts either mapping or list config, and `/api/languages` plus `site/data/languages.json` expose brand metadata.
- Added `static/lib/branding.js` for deterministic route/brand/date helpers and cached it in the service worker.
- Reworked `static/index.html` into hash-based Today, Archive, Glossary and Settings views with a primary nav, home brand link, editorial hero, compact practice summary, and no progress bars in the main reading view; existing reading, phrase, exercise, glossary, Anki and tour controls were preserved.
- Updated CSS for the new masthead navigation, hero, view headings and responsive layout; contrast audit still passes.
- Tests: 44 unit tests passed in `.venv`; frontend helper checks, all JavaScript syntax checks, Python compile check and contrast audit passed.
- Verification: public static export to a temp directory succeeded with 2 days, 12 level files, 5 audio slots, `English Daily` title, branding module and brand metadata in `languages.json`.
- Decision: prepare Archive/Settings view shells now so later phases can fill them without another structural rewrite.
- Remaining: Phases 2–8.
