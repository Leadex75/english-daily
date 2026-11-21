from __future__ import annotations

import datetime as dt
import json
import re
import shutil
from pathlib import Path
from typing import Any

from app.db import PROJECT_ROOT, connect, data_dir, today
from app.serialize import serialize_day
from ingest.phrases import load_phrases
from ingest.readability import CATEGORIES, KINDS, LEVELS

_DAY_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def _prepare_index(out: Path, config: dict[str, Any]) -> None:
    index = out / "index.html"
    text = index.read_text(encoding="utf-8")
    if 'name="eds-mode"' not in text:
        marker = '<meta charset="utf-8">'
        text = text.replace(marker, marker + '\n  <meta name="eds-mode" content="server">', 1)
    text = re.sub(
        r'<meta name="eds-mode" content="[^"]*">',
        '<meta name="eds-mode" content="static">',
        text,
        count=1,
    )
    text = re.sub(
        r'<meta name="eds-goal" content="[^"]*">',
        f'<meta name="eds-goal" content="{int(config.get("weekly_goal_default", 5))}">',
        text,
        count=1,
    )
    if 'name="robots"' not in text and bool(config.get("noindex")):
        marker = '<meta name="eds-mode" content="static">'
        text = text.replace(marker, marker + '\n  <meta name="robots" content="noindex,nofollow">', 1)
    for old, new in (
        ('href="/style.css"', 'href="./style.css"'),
        ('src="/app.js"', 'src="./app.js"'),
        ('src="/vendor/alpine.min.js"', 'src="./vendor/alpine.min.js"'),
        ('src="/lib/anki.js"', 'src="./lib/anki.js"'),
        ('href="/manifest.webmanifest"', 'href="./manifest.webmanifest"'),
        ('src="/sw.js"', 'src="./sw.js"'),
    ):
        text = text.replace(old, new)
    index.write_text(text, encoding="utf-8")


def _prepare_service_worker(out: Path) -> None:
    source = out / "sw.js"
    if not source.is_file():
        return
    stamp = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%d%H%M%S")
    text = source.read_text(encoding="utf-8").replace("__CACHE_VERSION__", f"english-daily-{stamp}")
    source.write_text(text, encoding="utf-8")


def _copy_local_audio(out: Path, config: dict[str, Any], payload: dict[str, Any]) -> None:
    for category in CATEGORIES:
        for kind in KINDS:
            item = payload["slots"][category][kind]
            if not item:
                continue
            audio_url = str(item.get("audio_url") or "")
            if not audio_url.startswith("./audio/"):
                continue
            relative = audio_url[2:]
            source = data_dir(config) / relative
            if source.is_file():
                target = out / relative
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(source, target)


def _prune_old_days(out: Path, config: dict[str, Any]) -> list[str]:
    retention = int(config["static_retention_days"])
    if retention <= 0:
        return []
    cutoff = dt.date.fromisoformat(today(config)) - dt.timedelta(days=retention)
    removed: list[str] = []
    root = out / "data"
    if not root.is_dir():
        return removed
    for child in root.iterdir():
        if not child.is_dir() or not _DAY_RE.fullmatch(child.name):
            continue
        try:
            day = dt.date.fromisoformat(child.name)
        except ValueError:
            continue
        if day < cutoff:
            shutil.rmtree(child, ignore_errors=True)
            removed.append(child.name)
    return removed


def _count_slots(payload: dict[str, Any]) -> int:
    count = 0
    for category in CATEGORIES:
        for kind in KINDS:
            if payload.get("slots", {}).get(category, {}).get(kind):
                count += 1
    return count


def _write_index(out: Path) -> dict[str, Any]:
    root = out / "data"
    days = sorted(
        (child.name for child in root.iterdir() if child.is_dir() and _DAY_RE.fullmatch(child.name)),
        reverse=True,
    )
    counts: dict[str, dict[str, int]] = {}
    for day in days:
        per_level: dict[str, int] = {}
        for level in LEVELS:
            path = root / day / f"{level}.json"
            try:
                payload = json.loads(path.read_text(encoding="utf-8"))
                per_level[level] = _count_slots(payload)
            except (OSError, ValueError):
                per_level[level] = 0
        counts[day] = per_level
    index = {
        "generated_at": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z"),
        "days": days,
        "counts": counts,
        "levels": LEVELS,
        "categories": CATEGORIES,
    }
    (root / "index.json").write_text(
        json.dumps(index, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    return index


def export_static(
    out_dir: str | Path,
    config: dict[str, Any],
    public_mode: bool | None = None,
) -> dict[str, Any]:
    out = Path(out_dir)
    if not out.is_absolute():
        out = PROJECT_ROOT / out
    root = data_dir(config)
    shutil.copytree(PROJECT_ROOT / "static", out, dirs_exist_ok=True)
    _prepare_index(out, config)
    _prepare_service_worker(out)
    (out / "data").mkdir(parents=True, exist_ok=True)

    publish_public = bool(config["public_mode"]) if public_mode is None else bool(public_mode)
    conn = connect(config)
    days: list[str] = []
    written = 0
    audios = 0
    try:
        day_rows = conn.execute("SELECT DISTINCT date FROM daily_picks ORDER BY date DESC").fetchall()
        phrase_days = conn.execute("SELECT DISTINCT date FROM phrases ORDER BY date DESC").fetchall()
        for row in phrase_days:
            if str(row[0]) not in {str(day[0]) for day in day_rows}:
                day_rows.append(row)
        for row in day_rows:
            day = str(row[0])
            days.append(day)
            for level in LEVELS:
                payload = serialize_day(
                    conn,
                    day,
                    level,
                    config,
                    public_mode=publish_public,
                    audio_base="./audio/",
                )
                target = out / "data" / day / f"{level}.json"
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text(
                    json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
                )
                written += 1
                _copy_local_audio(out, config, payload)
                audios += sum(
                    1
                    for category in CATEGORIES
                    for kind in KINDS
                    if payload["slots"][category][kind]
                    and payload["slots"][category][kind].get("audio_url")
                )
            phrases = load_phrases(conn, day)
            if phrases:
                (out / "data" / day / "phrases.json").write_text(
                    json.dumps(phrases, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
                )
    finally:
        conn.close()

    removed = _prune_old_days(out, config)
    index = _write_index(out)
    (out / ".nojekyll").write_text("", encoding="utf-8")
    shutil.copy2(out / "index.html", out / "404.html")
    return {
        "out": str(out),
        "days": index["days"],
        "written": written,
        "audios": audios,
        "pruned": removed,
        "public_mode": publish_public,
        "root": str(root),
    }
