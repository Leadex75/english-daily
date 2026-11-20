# english-daily

A local, account-free English practice app organised by CEFR level (A1–C2). A standalone Python
ingester pulls real free RSS/podcast/Wikipedia content into SQLite plus local MP3 files; a FastAPI
backend serves a small offline frontend. The same frontend can also be exported as a static
GitHub Pages site refreshed daily by GitHub Actions. Level classification is deterministic
(`textstat` + `wordfreq`) — **no LLM, no API keys, no accounts, no telemetry**.

## One-command start

```bash
# first time
python -m venv .venv
# Windows: .\.venv\Scripts\python.exe -m pip install -r requirements.txt
# macOS/Linux: ./.venv/bin/python -m pip install -r requirements.txt

# every day (Windows)
.\.venv\Scripts\python.exe run.py

# every day (macOS/Linux)
./.venv/bin/python run.py
```

Open <http://127.0.0.1:8000/>. On startup the app creates the schema, loads `sources.yaml`, and
(if `auto_ingest_on_start: true`) ingests today's content in a background thread. The server starts
immediately; the first day's content appears within a minute or two.

Other commands:

```bash
python run.py ingest                 # fetch/score/download/pick for today
python run.py ingest --date 2026-11-20
python run.py doctor                 # check every enabled source
python run.py prune                  # delete expired MP3s (text rows stay)
python run.py export-static --out site --public   # GitHub-Pages-ready site
python run.py import-state --site-dir site --state-dir state
python -m ingest.readability         # readability self-test
```

`ffmpeg` is optional: `shutil.which("ffmpeg")` is checked, and re-encoding only happens when
`reencode_audio: true` and ffmpeg is installed. Otherwise MP3s are kept exactly as downloaded.

## Daily scheduling

Cron (every day at 07:05, adjust the paths):

```cron
5 7 * * * cd /path/to/english-daily && ./.venv/bin/python run.py ingest >> ingest.log 2>&1
```

Windows Task Scheduler: create a *Basic Task* → trigger *Daily* → action *Start a program*:

- Program/script: `C:\path\to\english-daily\.venv\Scripts\python.exe`
- Add arguments: `run.py ingest`
- Start in: `C:\path\to\english-daily`

The server itself can stay running; ingestion is idempotent and does not duplicate items or picks.

## Nextcloud tip

Set `data_dir` in `config.yaml` to a folder inside your Nextcloud sync directory, e.g.
`data_dir: /home/me/Nextcloud/english-daily-data` (or `C:\Users\me\Nextcloud\english-daily-data`).
The SQLite database and `audio/YYYY-MM-DD/*.mp3` files then sync too.

Keep SQLite **single-writer**: run only one ingester/backend against the same `data_dir`. Do not
sync the database while two machines write to it; stop the app on the other device, or point each
device at its own `data_dir` and sync only the MP3s. Journal mode is `DELETE` and foreign keys are
enabled.

## LAN / phone access

Set `host: 0.0.0.0` in `config.yaml`, restart the app, allow TCP port 8000 through the firewall,
then browse to `http://<your-computer-IP>:8000/` on your phone. This is a local, unauthenticated app:
only expose it on a network you trust (or tunnel it over SSH/WireGuard).

## Deploy online (GitHub Pages)

The same codebase has two modes selected by `<meta name="eds-mode">` in `static/index.html`:

- **server** (default): the FastAPI app keeps serving `/api/...` and local MP3s exactly as before.
- **static**: a generated site fetches only `./data/index.json` and `./data/<date>/<level>.json`; there are no API calls and no server.

`.github/workflows/daily.yml` runs ingestion every day at **05:00 UTC** (`timezone: Europe/Paris` in
`config.yaml` is used to compute the published date), then exports `site/`, commits the changed
`site/data/` history and `state/used.json`, and deploys with GitHub Actions. Trigger it manually from
the **Actions → daily → Run workflow** tab. The workflow only fails when **zero** items are fetched
from all sources; individual dead feeds, bad audio URLs and timeouts are logged and skipped.

- `state/used.json` is the committed dedup ledger. Each entry is `{"guid_hash": ..., "date": ...}`;
  entries older than 30 days are pruned. The SQLite database in CI (`ENGLISH_DAILY_DATA_DIR=./.ci-data`)
  is disposable; `site/data/` is the real history. If history exists but state is missing, run
  `python run.py import-state --site-dir site --state-dir state`.
- `site/data/YYYY-MM-DD/*.json` holds one file per CEFR level, plus `index.json` (days and per-day
  slot counts). `static_retention_days: 365` prunes old date folders. `site/.nojekyll` and
  `site/404.html` are generated. `noindex: true` adds `noindex,nofollow` to the static site.
- Audio is never re-hosted in CI: `ENGLISH_DAILY_AUDIO_MODE=hotlink` verifies the publisher URL with a
  ranged GET, downloads the MP3 only transiently to measure its real duration with `mutagen`, stores
  the original HTTPS enclosure URL, and deletes the temp file. The browser streams from the publisher,
  with `referrerpolicy="no-referrer"` and an "Audio unavailable here / Open original" fallback.
- `public_mode: true` means proprietary text is published only as a sentence-boundary excerpt of
  `excerpt_words` words with a link to the original; open-license items (VOA, Wikipedia) keep their
  full text and attribution. You can override the export for one run with `--public` or `--private`.
  **Do not publish a `--private` export on a public site**: it can contain full proprietary text.
- All generated URLs are relative (`./data/...`, `./style.css`, `./app.js`), so the site works under
  `https://<owner>.github.io/<repo>/` as well as at a domain root.

GitHub disables scheduled workflows after long repository inactivity. The daily commits normally
prevent this; if it happens, re-enable the schedule from the **Actions** tab. Free-tier limits for
GitHub Pages size/bandwidth and Actions minutes apply — check them on GitHub's pricing/pages pages.

Nextcloud can still be used as a **backup of the repository folder** (`site/`, `state/`, sources), but
it cannot serve this app: the static site needs GitHub Pages or another static host.

## Adding a source

Edit `sources.yaml` and restart (or run ingest again):

```yaml
sources:
  - id: my_podcast
    name: My Podcast
    feed_url: https://example.org/feed.xml
    category: news          # news | culture
    kind: audio             # text | audio
    level_min: B1           # A1..C2, or "computed" for pure readability scoring
    level_max: B2
    enabled: true
    #     max_duration_sec: 3300  # optional per-source exception to audio_max_sec
    # type: rss               # rss | wikipedia_featured | wikipedia_simple
    license: proprietary     # proprietary | public_domain_us_gov | cc_by_sa
    # attribution: "Source, CC BY-SA 4.0"  # required for open-license sources
```

`license` and `attribution` travel with each item into the static export. `level_min`/`level_max` are used for deterministic level fusion: a computed level is clamped into

the source's band (`level_method: blend`); `computed` means the raw score decides (`computed`).
Text items must extract to 120–1500 words; audio enclosures are filtered by announced duration,
then measured with `mutagen`. One dead feed or bad MP3 is logged and skipped, never fatal.

## Sources notes

- VOA Learning English RSS URLs were discovered on `learningenglish.voanews.com/rssfeeds` and the
  podcast pages. The site has no feeds literally named Beginning/Intermediate/Advanced, so
  All About America (A1–A2), Health & Lifestyle (B1) and As It Is (B2) are used. VOA's RSS and
  podcast feeds currently stop in March 2025, so their items fall outside `lookback_days: 7` and
  are intentionally not picked. The feeds are kept for when VOA resumes publishing.
- Current BBC Learning Easy English (A2) and Learning English from the News (B1) feeds were added
  to cover levels that the seed sources cannot supply today.
- BBC In Our Time has `max_duration_sec: 3300` (documented exception); many episodes are 55–60 min
  and are skipped by the real-duration check.
- Thresholds, audio window, lookback/retention and request settings are all in `config.yaml`.

## API

- `GET /api/health`
- `GET /api/days`
- `GET /api/day/YYYY-MM-DD?level=B1`
- `GET /audio/YYYY-MM-DD/<sha1>.mp3` (HTTP Range supported for seeking)
- `/` serves `static/` (Alpine.js is vendored; no CDN requests)
