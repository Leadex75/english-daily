from __future__ import annotations

import datetime as dt
from typing import Any

from app.db import available_languages, load_sources
from ingest.fetch_audio import parse_itunes_duration
from ingest.fetch_feeds import fetch_source


def run_doctor(config: dict[str, Any]) -> int:
    print(f"{'LANG':6s} {'SOURCE':40s} {'STATUS':7s} {'ENTRIES':>7s} {'ENC':>4s}  SAMPLE DURATIONS")
    failures = 0
    today = dt.date.today().isoformat()
    for lang in available_languages(config):
        for source in load_sources(config, lang):
            if not source.get("enabled", True):
                continue
            name = str(source.get("name") or source["id"])[:40]
            try:
                entries = fetch_source(source, config, today)
                durations = []
                for entry in entries:
                    if entry.get("enclosure_url"):
                        value = parse_itunes_duration(entry.get("itunes_duration"))
                        if value is not None:
                            durations.append(f"{value // 60}:{value % 60:02d}")
                    if len(durations) >= 3:
                        break
                enclosures = sum(1 for entry in entries if entry.get("enclosure_url"))
                print(f"{lang:6s} {name:40s} {'OK':7s} {len(entries):7d} {enclosures:4d}  {', '.join(durations) or '-'}")
            except Exception as exc:
                failures += 1
                detail = f"{type(exc).__name__}: {exc}"[:70]
                print(f"{lang:6s} {name:40s} {'FAIL':7s} {'-':>7s} {'-':>4s}  {detail}")
    print(f"\nChecked sources. Failures: {failures}")
    return 0
