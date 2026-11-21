# english-daily

A local, account-free English practice app organised by CEFR level (A1–C2). A Python ingester pulls
real RSS/podcast/Wikipedia/history content into SQLite, a FastAPI backend serves an offline-capable
frontend, and the same frontend can be exported as a GitHub Pages site. Content selection is
deterministic (`textstat` + `wordfreq` + explicit cascade rules) — **no LLM, no API keys, no
accounts, no telemetry**.

From Phase 6 onward the app also carries a bilingual history-term bank, per-day exercises, an
offline search index, a guided tour, language-aware paths, deterministic reconstruction, and a
small local desktop launcher.

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
python run.py backfill --days 90              # idempotent local re-pick
python run.py backfill --days 90 --force      # overwrite already-successful days
python run.py reconstruct --json              # offline rebuild check for today
python run.py reconstruct --date 2026-11-21 --write
python run.py stats --days 90 --lang en
python run.py doctor --json                   # structured source health report
python run.py export-static --out site --public
python run.py import-state --site-dir site --state-dir state
python run.py prune
python -m unittest discover -s tests -v
python -m compileall -q app ingest desktop tools run.py tests
python -m ingest.readability
```

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
- A guided tour, archive search, glossary, Anki export, theme switch and progress bars are all
  driven by the versioned day contract (`meta.contract_version: 2`).
- Read/listened markers, learned phrases, exercise answers, theme, language and tour position live
  only in browser `localStorage`.
- Static mode caches the app shell, modules and viewed day files with a service worker. Audio is
  never cached or re-hosted; an "Audio unavailable here / Open original" fallback is always shown.
- The frontend is split into browser-native modules under `static/lib/`: `store`, `exercises`,
  `tour`, `search`, `pwa` and `anki`. Keyboard tab navigation, skip link, focus-visible outlines,
  dialog focus handling and reduced-motion support are included.

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

## Search and enriched contract

`ingest/search.py` builds a pure local index from stored picks and phrase banks. Static builds write
one search file per language and day; the server exposes the same ranking through `/api/search`.
Search matches titles, phrases, history terms, summaries, bodies and sources, and returns snippets
plus matched terms.

Day payloads include:

- `slots`: text/audio for news, culture and history
- `phrase`: word, expression and history term for the selected level
- `glossary`: all bank entries for the day
- `exercises`: deterministic CEFR-scoped practice items
- `tour`: guided tour steps targeting frontend landmarks
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
