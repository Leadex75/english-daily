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
