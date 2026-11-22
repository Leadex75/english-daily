# English Daily

A local, account-free English and Spanish practice app organised by CEFR level (A1–C2). A Python
ingester pulls real RSS/podcast/Wikipedia/history content into SQLite, a FastAPI backend serves an
offline-capable frontend, and the same frontend can be exported as a GitHub Pages site. Content
selection is deterministic (`textstat` + `wordfreq` + explicit cascade rules) — **no LLM, no API
keys, no accounts, no telemetry**.

The app also carries bilingual history-term banks, per-day exercises, an offline search index, a
guided tour, language-aware paths, deterministic reconstruction, and a small local desktop launcher.

## Brand and navigation

The app is branded `English Daily` in the interface, manifest, API metadata and CLI output. The repository, URL slug, data paths and local storage keys stay `english-daily` for compatibility. Per-language display names come from `languages.<code>.brand` in `config.yaml`.

The interface has four hash-based views: `#today` for the day's reading, `#archive` for the month calendar, recent editions and archive-wide search, `#glossary` for learned phrases, and `#settings` for preferences. All view links are relative, so the same build works from a domain root or a GitHub Pages subdirectory.

## Quick start

```bash
python -m venv .venv
# Windows
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
# macOS/Linux
./.venv/bin/python -m pip install -r requirements.txt
```

Run the server:

```bash
python run.py
```

Open <http://127.0.0.1:8000/>. On startup the app creates/migrates the schema, loads `sources.yaml`,
and (if `auto_ingest_on_start: true`) ingests today's content in a background thread. The server
starts immediately.

Run the desktop launcher (serves the exported `site/` when it exists, otherwise starts the API):

```bash
python desktop/main.py
python desktop/main.py --no-browser --port 8765
```

Build a distributable desktop artifact:

```bash
python tools/build_desktop.py --out dist/EnglishDaily.pyz
python tools/build_desktop.py --out dist/EnglishDaily.exe --pyinstaller
```

`Pillow` is intentionally absent. Icons already exist under `static/icons/`, and no image dependency
is required.

## Commands

```bash
python run.py ingest                         # fetch/score/pick today + reserves + phrases
python run.py ingest --date 2026-11-20 --lang en
python run.py ingest --lang es               # Spanish content from the es source registry
python run.py backfill --days 90              # idempotent local re-pick
python run.py backfill --days 90 --force      # overwrite already-successful days
python run.py reconstruct --json              # offline rebuild check for today
python run.py reconstruct --lang es --json    # Spanish offline rebuild check
python run.py reconstruct --date 2026-11-21 --write
python run.py stats --days 90 --lang en
python run.py stats --days 90 --lang es
python run.py doctor --json                   # structured source health report
python run.py doctor --json --lang es
python run.py anki-notes --entries state/anki-entries.json --lang en --json
python run.py anki-notes --entries state/es/anki-entries.json --lang es --json
python run.py anki-build --entries state/anki-entries.json --out english-daily.apkg --lang en
python run.py anki-build --entries state/es/anki-entries.json --out spanish-daily.apkg --lang es
python run.py export-static --out site --public
python run.py import-state --site-dir site --state-dir state
python run.py prune
python run.py validate-config --json
python run.py demo-data --out demo-site --data-dir demo-data --state-dir demo-state --json
python run.py backup-db --out english-daily.sqlite3.bak
python run.py restore-db --from english-daily.sqlite3.bak --force
python run.py calibrate --json
python -m unittest discover -s tests -v
python -m compileall -q app ingest desktop tools run.py tests
python tools/contrast_check.py --css static/css/themes.css
python tools/palette_build.py --check --out static/css/themes.css
python -m ingest.readability
```

Install browser-test dependencies separately:

```powershell
python -m pip install -r tests/requirements-dev.txt
$env:E2E_CHROMIUM_PATH = "C:\Program Files\Google\Chrome\Application\chrome.exe"
python -m unittest discover -s tests/e2e -v
```

The E2E suite exports a deterministic static site, serves it on localhost, blocks external requests and
stubs AnkiConnect. Results are recorded in `TEST_REPORT.md`.

`validate-config` checks required keys, language metadata, CEFR thresholds and polite-network settings.
`demo-data` builds a two-day bilingual offline preview without touching the live database. `backup-db`
and `restore-db` copy the SQLite database safely; restore requires `--force` to replace an existing
database and writes its own safety backup. `calibrate` reports source counts, bank coverage and
readability thresholds per language.

`ffmpeg` is optional: re-encoding only happens when `reencode_audio: true` and `ffmpeg` is installed.
Otherwise MP3s are kept exactly as downloaded. Audio is always hotlinked from the original publisher;
the app never re-hosts MP3s.

## Daily content and cascade

Each language has 36 slots per day: 12 text and 12 audio across **news**, **culture** and **history**.
The picker uses five explicit, deterministic stages:

1. exact-level fresh preferred source
2. exact-level fresh other source
3. exact-level reserve/archive
4. adjacent-level with audio
5. adjacent-level text only

Every pick records its stage, origin and badges. `run.py reconstruct` replays the same cascade from
the local database without network access and compares/replaces stored picks with `--write`.
`run.py backfill` re-picks recent days from the local database, skipping already-successful days
unless `--force` is used.

## Reading and learning experience

- The phrase tab contains one word, one expression and one history term per level, generated from
  `bank/<lang>/words.yaml`, `expressions.yaml` and `history_terms.yaml`.
- Daily exercises cover word meaning, expression cloze and history period, with distractors drawn
  from the same day's phrase bank.
- The masthead keeps one wordmark link to Today, a language picker, Tour, Anki and a Settings gear;
  the old primary nav, headline hero, progress summary, date dropdown, light/dark toggle and Anki
  help button have been removed. Archive is the fifth main tab, and the glossary lives on the Anki
  page.
- A seven-step guided tour starts on the first visit at the Today view, then moves through levels,
  tabs, phrases, exercises, Anki and the glossary; archive search, glossary, Anki export and theme
  switch are driven by the versioned day contract (`meta.contract_version: 2`).
- Text and audio cards each expose one labelled source link and a separate mark-as-read or
  mark-as-listened toggle. Truncated text links read "Read the full article on <source>"; complete
  text keeps a plain Source link.
- Anki buttons show ready, learn-first and unavailable states and export only saved items. The tour
  overlays a keyboard-safe spotlight on the current target, reveals hidden views before highlighting
  them, traps Tab focus inside the dialog and restores focus on exit. Notes use a persistent
  `English Daily Phrase` model, deterministic GUIDs, field escaping and stable tags; Settings stores
  the AnkiConnect URL, and the Anki page can check the connection and send notes without a browser
  download. `anki-notes` and `anki-build` expose the same note model as JSON or a reusable `.apkg`
  (via `genanki`).
- `tools/palette_build.py` generates `static/css/themes.css` from audited palette definitions;
  `tools/contrast_check.py` verifies WCAG AA text contrast and 3:1 borders for Paper, Sepia, Ink,
  High contrast and both System modes.
- The Settings view stores the theme preset, text size, reading font, default audio speed, exercise
  feedback, auto-marking and reduced-motion preference in browser `localStorage`.
- Today's progress counts only available text/audio slots; this week's progress counts unique
  practiced days from read, listened, learned and exercised markers.
- Read/listened markers, learned phrases, exercise answers, settings, language, tour position and
  the first-visit tour flag live only in browser `localStorage`.
- Static mode caches the app shell, modules and viewed day files with a service worker. Audio is
  never cached or re-hosted; a labelled "Audio unavailable here" publisher fallback is always shown.
- The frontend is split into browser-native modules under `static/lib/`: `store`, `branding`,
   `settings`, `links`, `progress`, `exercises`, `tour`, `search`, `archive`, `pwa` and `anki`. Keyboard tab navigation, skip link, focus-visible outlines,
   tour spotlight/highlight, dialog focus trapping and reduced-motion support are included.

## Multilingual layout

`config.yaml` defines `languages`, `default_language`, `online_site_url`, and per-language
`levels`, `history_periods` and `history_themes`. Every source in `sources.yaml` carries `lang`.
All state and site data are partitioned by language:

```text
state/<lang>/used.json
state/<lang>/phrase_used.json
state/<lang>/pool/
site/data/languages.json
site/data/<lang>/index.json
site/data/<lang>/YYYY-MM-DD/<LEVEL>.json
site/data/<lang>/YYYY-MM-DD/phrases.json
site/data/<lang>/search/YYYY-MM-DD.json
```

Database files also carry `lang` on sources, items, daily picks, phrases, books and ingest runs.
CLI commands without `--lang` process all configured languages.

### Spanish

`config.yaml` defines Spanish levels, thresholds, brand/tagline, and language-scoped history
keywords, categories, periods and themes through `language_setting()`. `sources.yaml` includes 17
Spanish sources (BBC Mundo, Charlas Hispanas, How to Spanish, Easy Spanish, Español Intermedio,
RTVE/RNE, LibriVox, Project Gutenberg, Wikinews and Wikipedia). All audio stays hotlinked from the
original publisher.

Spanish banks live in `bank/es/` (`words.yaml`, `expressions.yaml`, `history_terms.yaml`) and state
in `state/es/`. Unicode-aware token counting and Spanish readability use the same deterministic
scoring path as English. Generated exercises, tour steps and CLI stats use Spanish text when
`--lang es` is selected. The frontend language selector and `?lang=es` query switch the loaded
language payload, brand and tagline, day paths, search URLs and language-scoped exercise answers;
the document `lang` attribute follows the selection.

## Search and enriched contract

`ingest/search.py` builds a pure local index from stored picks and phrase banks. Static builds write
one search file per language and day; the server exposes the same ranking through `/api/search`.
The archive view merges the static day indexes into one archive-wide search, and the server query
omits day/level filters for the same behavior. Search matches titles, phrases, history terms,
summaries, bodies and sources, and returns snippets plus matched terms.

Day payloads include:

- `slots`: text/audio for news, culture and history
- `phrase`: word, expression and history term for the selected level
- `glossary`: all bank entries for the day
- `exercises`: deterministic CEFR-scoped practice items
- `tour`: seven guided steps targeting frontend landmarks, beginning with the Today view
- `meta`: contract version, filled counts, origins, provenance counts, periods, themes and search path

Serialized items include `periods`, `themes`, `history_terms`, `alt_text`, `duration_formatted`,
`source_url`, `reading_time_min`, attribution, license and badges.

## API

```text
GET /api/health
GET /api/languages
GET /api/days?lang=en
GET /api/day/YYYY-MM-DD?level=B1&lang=en
GET /api/phrase/YYYY-MM-DD?level=B1&lang=en
GET /api/stats?days=30&lang=en
GET /api/sources?lang=en
GET /api/search?q=term&day=YYYY-MM-DD&level=B1&lang=en
GET /audio/YYYY-MM-DD/<sha1>.mp3   (HTTP Range supported)
```

`/` serves `static/`. Alpine.js is vendored; there are no CDN requests.

## GitHub Actions

### ci

`.github/workflows/ci.yml` runs on pushes to `main`, pull requests and manual dispatch via
**Actions → ci → Run workflow**. Generated `site/`, `state/` and `data/` changes and markdown-only
changes are ignored. It validates configuration, runs unit and browser tests, checks Python and
JavaScript syntax, audits palettes, builds demo data and prints a calibration report.

### daily

`.github/workflows/daily.yml` runs at **05:00 UTC** and can be triggered from
**Actions → daily → Run workflow**. It compiles Python, checks every JavaScript module, runs unit
tests, ingests with hotlinked audio, verifies deterministic reconstruction, writes a coverage summary,
exports the public static site, commits `site/` and `state/`, and deploys to GitHub Pages.

### health

`.github/workflows/health.yml` runs at **06:17 UTC** and can be triggered manually. It runs
`python run.py doctor --json`, prints the report and uploads `source-health.json` as an artifact.

### desktop

`.github/workflows/desktop.yml` runs on `v*` tags and can be triggered manually. It builds zipapps on
Linux, Windows and macOS, plus an optional Windows executable via PyInstaller. The build tool falls
back to a stdlib zipapp when PyInstaller is unavailable.

GitHub disables scheduled workflows after long inactivity. Daily commits normally prevent this; if
it happens, re-enable the schedule from the Actions tab.

## Static export and publishing

- `excerpt_words` and `excerpt_min_sentence_words` control sentence-boundary excerpts shared by day
  payloads, search snippets and the static export.
- `text_cleaning.patterns` in `config.yaml` removes publisher boilerplate, malformed ellipses and
  trailing "Continue reading" text after extraction, before scoring, word counts and excerpts.
- `python run.py clean-existing` applies those rules to stored items, pool JSON and exported site
  JSON, recomputes text word counts, then rebuilds the public static site.
- `public_mode: true` publishes proprietary text only as a sentence-boundary excerpt with a link to
  the original; open-license items keep full text and attribution. Override with `--public` or
  `--private`. **Never publish a `--private` export on a public site.**
- All generated URLs are relative (`./data/...`, `./style.css`, `./lib/...`), so the site works under
  `https://<owner>.github.io/<repo>/` and at a domain root.
- `site/.nojekyll`, `site/404.html`, `manifest.webmanifest`, PWA icons and a versioned `sw.js` are
  generated. `noindex: true` adds `noindex,nofollow` to static pages.
- If exported history exists but state ledgers are missing, run
  `python run.py import-state --site-dir site --state-dir state`.
- CI uses `ENGLISH_DAILY_DATA_DIR=./.ci-data`, so the SQLite database is disposable; committed
  `site/data/` and `state/` are the durable history.

## Sources and resilience

- VOA Learning English RSS feeds currently stop in March 2025, so their items fall outside
  `lookback_days: 7` and are intentionally not picked; the feeds are kept for revival.
- BBC Learning Easy English and Learning English from the News cover A2/B1 gaps.
- BBC In Our Time uses `max_duration_sec: 3300`; 55–60 minute episodes are skipped by real-duration
  checks.
- Reserve content comes from Wikipedia extracts, Wikipedia "on this day", Wikinews current-month
  categories, LibriVox chapters and Gutenberg passages.
- Gutenberg may return `503 Temporarily Down for Maintenance`; the generator falls back to
  source-description level scoring. Wikinews `list=recentchanges` can be empty; the generator falls
  back to current-month category members.
- Offline/deterministic runs: set `ingest_offline`, `reserve_offline` and `phrase_offline` in
  `config.yaml`, or use `ENGLISH_DAILY_RESERVE_OFFLINE=1` / `ENGLISH_DAILY_PHRASE_OFFLINE=1`.

## Adding a source

Edit `sources.yaml` and ingest again:

```yaml
sources:
  - id: my_podcast
    name: My Podcast
    feed_url: https://example.org/feed.xml
    category: history
    kind: audio
    level_min: B1
    level_max: B2
    enabled: true
    lang: en
    license: proprietary
```

`license` and `attribution` travel with each item into the static export. Text items must extract to
120–1500 words; audio enclosures are filtered by announced duration, then measured with `mutagen`.
One dead feed or bad MP3 is logged and skipped, never fatal.

## Scheduling on your own machine

Cron (every day at 07:05, adjust paths):

```cron
5 7 * * * cd /path/to/english-daily && ./.venv/bin/python run.py ingest >> ingest.log 2>&1
```

Windows Task Scheduler: Daily → Start a program:

- Program: `C:\path\to\english-daily\.venv\Scripts\python.exe`
- Arguments: `run.py ingest`
- Start in: `C:\path\to\english-daily`

Ingestion is idempotent and does not duplicate items or picks.

## Nextcloud and LAN

Set `data_dir` in `config.yaml` to a Nextcloud synced folder to sync SQLite and audio. Keep SQLite
single-writer: only one ingester/backend should write to a given `data_dir` at a time.

For LAN/phone access, set `host: 0.0.0.0`, restart, allow TCP port 8000, then browse
`http://<your-computer-IP>:8000/`. This is a local unauthenticated app: only expose it on a trusted
network or through SSH/WireGuard.
