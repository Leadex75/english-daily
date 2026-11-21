from __future__ import annotations

import datetime as dt
from typing import Any

from app.db import default_language, level_config
from ingest.readability import CATEGORIES, KINDS, LEVELS, band_center

STAGES: tuple[dict[str, Any], ...] = (
    {"name": "exact-fresh-preferred", "distance": "exact", "origins": ("fresh",), "preferred": True, "kinds": None},
    {"name": "exact-fresh-other", "distance": "exact", "origins": ("fresh",), "preferred": False, "kinds": None},
    {"name": "exact-reserve-archive", "distance": "exact", "origins": ("reserve", "archive"), "preferred": None, "kinds": None},
    {"name": "adjacent-audio", "distance": "adjacent", "origins": ("fresh", "archive", "reserve"), "preferred": None, "kinds": ("audio",)},
    {"name": "adjacent-text", "distance": "adjacent", "origins": ("fresh", "archive", "reserve"), "preferred": None, "kinds": ("text",)},
)


def _date(value: Any) -> dt.date:
    try:
        return dt.date.fromisoformat(str(value)[:10])
    except (TypeError, ValueError):
        return dt.date.min


def _origin_badges(origin: str, published_at: Any, source_name: str) -> list[str]:
    badges: list[str] = []
    if origin == "archive":
        badges.append(f"From the archive · {_date(published_at).isoformat()}")
    elif origin == "reserve":
        badges.append(f"Reserve · {source_name}")
    return badges


def _preferred(candidate: dict[str, Any], config: dict[str, Any]) -> bool:
    if str(candidate.get("kind")) == "audio":
        duration = candidate.get("duration_sec")
        if duration is None:
            return False
        return int(config["audio_pref_min_sec"]) <= int(duration) <= int(config["audio_pref_max_sec"])
    words = candidate.get("word_count")
    if words is None:
        return False
    return int(config["text_pref_min_words"]) <= int(words) <= int(config["text_pref_max_words"])


def _hard_ok(candidate: dict[str, Any], config: dict[str, Any]) -> bool:
    if str(candidate.get("kind")) == "audio":
        if not candidate.get("audio_url") and not candidate.get("audio_remote_url"):
            return False
        duration = candidate.get("duration_sec")
        low = config.get("audio_hard_min_sec")
        high = config.get("audio_hard_max_sec")
        if duration is not None:
            if low is not None and int(duration) < int(low):
                return False
            if high is not None and int(high) > 0 and int(duration) > int(high):
                return False
        return True
    if not candidate.get("body_text"):
        return False
    words = candidate.get("word_count")
    if words is None:
        return False
    low = int(config["text_hard_min_words"])
    high = int(config["text_hard_max_words"])
    return low <= int(words) <= high


def _origin(candidate: dict[str, Any], day: str, config: dict[str, Any]) -> str:
    declared = str(candidate.get("origin_kind") or "fresh")
    if declared in {"archive", "reserve"}:
        return declared
    published = _date(candidate.get("published_at"))
    target = _date(day)
    if published < target - dt.timedelta(days=int(config.get("lookback_days", 7))):
        return "archive"
    return "fresh"


def _sort_key(candidate: dict[str, Any], center: float) -> tuple[Any, ...]:
    score = float(candidate.get("score") or 0)
    return (
        0 if candidate.get("_preferred") else 1,
        -_date(candidate.get("published_at")).toordinal(),
        abs(score - center),
        str(candidate.get("guid_hash")),
    )


def choose_picks(
    candidates: list[dict[str, Any]],
    day: str,
    config: dict[str, Any],
    excluded_hashes: set[str] | None = None,
    trace: list[dict[str, Any]] | None = None,
) -> tuple[dict[tuple[str, str, str], dict[str, Any]], list[str], list[str]]:
    """Pure deterministic cascade over candidates: A -> B -> C -> D -> E."""
    excluded = {str(value) for value in (excluded_hashes or ())}
    day_date = _date(day)
    archive_cutoff = day_date - dt.timedelta(days=int(config.get("archive_days", 90)))
    prepared: list[dict[str, Any]] = []
    for candidate in candidates:
        if not _hard_ok(candidate, config):
            continue
        if _date(candidate.get("published_at")) < archive_cutoff and candidate.get("origin_kind") != "reserve":
            continue
        item = dict(candidate)
        item["_origin"] = _origin(candidate, day, config)
        item["_preferred"] = _preferred(candidate, config)
        prepared.append(item)

    audio_counts: dict[str, int] = {}
    source_counts: dict[str, int] = {}
    picked_hashes: set[str] = set()
    picks: dict[tuple[str, str, str], dict[str, Any]] = {}
    filled: list[str] = []
    empty: list[str] = []

    lang = str(
        config.get("_lang")
        or (candidates[0].get("lang") if candidates else None)
        or default_language(config)
    )
    thresholds, _ = level_config(config, lang)

    def select(pool: list[dict[str, Any]], center: float, level: str, target_level: str) -> dict[str, Any] | None:
        ordered = sorted(pool, key=lambda item: _sort_key(item, center))
        limited = [
            item for item in ordered
            if audio_counts.get(str(item.get("source_id")), 0) < 2
            and source_counts.get(str(item.get("source_id")), 0) < 3
        ]
        for item in limited or ordered:
            if str(item.get("guid_hash")) in picked_hashes:
                continue
            chosen = dict(item)
            chosen["level"] = level
            chosen["slot_level"] = target_level
            origin = "adjacent" if level != target_level else str(item["_origin"])
            badges = _origin_badges(
                str(item["_origin"]), item.get("published_at"),
                str(item.get("source_name") or item.get("source_id")),
            )
            if level != target_level:
                badges.append(f"Closest level: {level}")
            if not item["_preferred"]:
                badges.append("Outside preferred window")
            chosen["origin"] = origin
            chosen["badges"] = badges
            picked_hashes.add(str(item.get("guid_hash")))
            source = str(item.get("source_id") or "unknown")
            source_counts[source] = source_counts.get(source, 0) + 1
            if item.get("kind") == "audio":
                audio_counts[source] = audio_counts.get(source, 0) + 1
            return chosen
        return None

    for target_level in LEVELS:
        center = band_center(target_level, thresholds)
        index = LEVELS.index(target_level)
        neighbors = [target_level]
        if index > 0:
            neighbors.append(LEVELS[index - 1])
        if index < len(LEVELS) - 1:
            neighbors.append(LEVELS[index + 1])

        for category in CATEGORIES:
            for kind in KINDS:
                key = (target_level, category, kind)
                chosen: dict[str, Any] | None = None
                chosen_stage = "empty"
                for stage in STAGES:
                    levels = (target_level,) if stage["distance"] == "exact" else tuple(
                        level for level in neighbors if level != target_level
                    )
                    if not levels:
                        continue
                    if stage["kinds"] and kind not in stage["kinds"]:
                        continue
                    pool = [
                        item for item in prepared
                        if item.get("category") == category and item.get("kind") == kind
                        and item.get("level") in levels and item["_origin"] in stage["origins"]
                        and (stage["preferred"] is None or item["_preferred"] == stage["preferred"])
                        and str(item.get("guid_hash")) not in excluded
                    ]
                    if not pool:
                        continue
                    nearest = sorted(
                        pool,
                        key=lambda item: (
                            abs(float(item.get("score") or 0) - center),
                            LEVELS.index(str(item["level"])),
                        ),
                    )
                    neighbor_level = str(nearest[0]["level"])
                    stage_pool = [item for item in pool if item.get("level") == neighbor_level]
                    candidate = select(stage_pool, center, neighbor_level, target_level)
                    if candidate:
                        chosen = candidate
                        chosen_stage = str(stage["name"])
                        break
                if chosen:
                    picks[key] = chosen
                    filled.append(f"{target_level}/{category}/{kind}")
                else:
                    empty.append(f"{target_level}/{category}/{kind}")
                if trace is not None:
                    trace.append({
                        "level": target_level,
                        "category": category,
                        "kind": kind,
                        "stage": chosen_stage,
                        "status": "filled" if chosen else "empty",
                        "selected_level": chosen.get("level") if chosen else None,
                        "guid_hash": chosen.get("guid_hash") if chosen else None,
                        "origin": chosen.get("origin") if chosen else None,
                    })
    return picks, filled, empty
