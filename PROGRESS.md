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
