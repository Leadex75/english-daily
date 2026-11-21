from __future__ import annotations

import datetime as dt
import json
from typing import Any

from app.db import available_languages, default_language, load_sources
from ingest.fetch_audio import parse_itunes_duration
from ingest.fetch_feeds import fetch_source, is_reserve_source


def _duration_seconds(entry: dict[str, Any]) -> int | None:
    value = parse_itunes_duration(entry.get("itunes_duration"))
    if value is not None:
        return int(value)
    try:
        raw = entry.get("duration_sec")
        return int(raw) if raw is not None else None
    except (TypeError, ValueError):
        return None


def check_sources(
    config: dict[str, Any], lang: str | None = None, day: str | None = None
) -> dict[str, Any]:
    languages = [str(lang)] if lang else available_languages(config)
    reference_day = str(day or dt.date.today().isoformat())
    results: list[dict[str, Any]] = []
    for language in languages:
        for source in load_sources(config, language):
            if not source.get("enabled", True):
                continue
            result: dict[str, Any] = {
                "id": str(source.get("id") or ""),
                "name": str(source.get("name") or source.get("id") or ""),
                "lang": language,
                "category": str(source.get("category") or ""),
                "kind": str(source.get("kind") or ""),
                "reserve": is_reserve_source(source),
                "status": "ok",
                "entries": 0,
                "enclosures": 0,
                "durations_sec": [],
                "error": None,
            }
            try:
                entries = fetch_source(source, config, reference_day)
                durations: list[int] = []
                for entry in entries:
                    if entry.get("enclosure_url"):
                        value = _duration_seconds(entry)
                        if value is not None:
                            durations.append(value)
                    if len(durations) >= 3:
                        break
                result["entries"] = len(entries)
                result["enclosures"] = sum(1 for entry in entries if entry.get("enclosure_url"))
                result["durations_sec"] = durations[:3]
            except Exception as exc:
                result["status"] = "error"
                result["error"] = f"{type(exc).__name__}: {exc}"
            results.append(result)
    failures = sum(1 for result in results if result["status"] != "ok")
    return {
        "checked_at": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z"),
        "day": reference_day,
        "default": default_language(config),
        "languages": languages,
        "sources": results,
        "checked": len(results),
        "ok": len(results) - failures,
        "failures": failures,
    }


def _format_duration(value: int) -> str:
    return f"{value // 60}:{value % 60:02d}"


def _print_report(report: dict[str, Any]) -> None:
    print(f"{'LANG':6s} {'SOURCE':40s} {'STATUS':7s} {'ENTRIES':>7s} {'ENC':>4s}  SAMPLE DURATIONS")
    for source in report["sources"]:
        name = source["name"][:40]
        status = source["status"].upper()
        durations = ", ".join(_format_duration(value) for value in source["durations_sec"])
        if source["error"]:
            detail = source["error"][:70]
            print(f"{source['lang']:6s} {name:40s} {status:7s} {'-':>7s} {'-':>4s}  {detail}")
        else:
            print(f"{source['lang']:6s} {name:40s} {status:7s} {source['entries']:7d} {source['enclosures']:4d}  {durations or '-'}")
    print(f"\nChecked {report['checked']} source(s). Failures: {report['failures']}")


def run_doctor(
    config: dict[str, Any], json_output: bool = False, lang: str | None = None
) -> int:
    report = check_sources(config, lang=lang)
    if json_output:
        print(json.dumps(report, indent=2, ensure_ascii=False))
    else:
        _print_report(report)
    return 0
