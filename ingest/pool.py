from __future__ import annotations

import datetime as dt
import hashlib
import json
from pathlib import Path
from typing import Any, Iterable

from ingest.readability import CATEGORIES, KINDS, LEVELS

OPEN_LICENSES = {"cc_by", "cc_by_sa", "public_domain", "public_domain_us_gov"}


def pool_dir(state_dir: str | Path) -> Path:
    return Path(state_dir) / "pool"


def item_id(guid_hash: str) -> int:
    return 1_000_000_000 + (int(hashlib.sha1(guid_hash.encode()).hexdigest()[:12], 16) % 900_000_000)


def bucket(item: dict[str, Any]) -> tuple[str, str, str]:
    level = str(item.get("level") or "B1")
    category = str(item.get("category") or "culture")
    kind = str(item.get("kind") or "text")
    return (level if level in LEVELS else "B1", category if category in CATEGORIES else "culture",
            kind if kind in KINDS else "text")


def read_json(path: Path, fallback: Any) -> Any:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        return payload if isinstance(payload, type(fallback)) else fallback
    except (OSError, ValueError):
        return fallback


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    temporary.replace(path)


def load_pool(state_dir: str | Path, config: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    root = pool_dir(state_dir)
    if not root.is_dir():
        return []
    items: list[dict[str, Any]] = []
    for path in sorted(root.glob("*.json")):
        payload = read_json(path, {})
        if isinstance(payload, dict) and payload.get("guid_hash"):
            items.append(payload)
    return items


def _expired(item: dict[str, Any], config: dict[str, Any], reference: dt.date) -> bool:
    license_name = str(item.get("license") or "")
    if license_name in OPEN_LICENSES:
        return False
    try:
        added = dt.date.fromisoformat(str(item.get("added_at") or "")[:10])
    except ValueError:
        return True
    return (reference - added).days > int(config.get("archive_days", 90))


def save_pool(
    state_dir: str | Path,
    items: Iterable[dict[str, Any]],
    config: dict[str, Any],
    reference: dt.date | None = None,
) -> list[dict[str, Any]]:
    """Keep the best/newest items per bucket, drop picked and expired ones."""
    reference = reference or dt.date.today()
    cap = int(config.get("pool_cap_per_bucket", 12))
    by_bucket: dict[tuple[str, str, str], list[dict[str, Any]]] = {}
    for item in items:
        guid = str(item.get("guid_hash") or "")
        if not guid or _expired(item, config, reference):
            continue
        by_bucket.setdefault(bucket(item), []).append(item)

    kept: dict[str, dict[str, Any]] = {}
    for group in by_bucket.values():
        unique = {str(item["guid_hash"]): item for item in group}
        ranked = sorted(
            unique.values(),
            key=lambda item: (str(item.get("added_at") or ""), float(item.get("score") or 0)),
            reverse=True,
        )[:cap]
        for item in ranked:
            kept[str(item["guid_hash"])] = item

    root = pool_dir(state_dir)
    root.mkdir(parents=True, exist_ok=True)
    for path in root.glob("*.json"):
        if path.stem not in kept:
            path.unlink(missing_ok=True)
    for guid, item in kept.items():
        write_json(root / f"{guid}.json", item)
    return list(kept.values())


def hydrate_db(conn: Any, items: Iterable[dict[str, Any]]) -> int:
    inserted = 0
    for item in items:
        guid = str(item.get("guid_hash") or "")
        if not guid:
            continue
        source_id = str(item.get("source_id") or "reserve")
        conn.execute(
            """INSERT OR IGNORE INTO sources
               (id, name, feed_url, category, kind, level_min, level_max, enabled)
               VALUES (?,?,?,?,?,?,?,1)""",
            (source_id, str(item.get("source_name") or source_id), "generated",
             str(item.get("category") or "culture"), str(item.get("kind") or "text"),
             str(item.get("level") or "B1"), str(item.get("level") or "B1")),
        )
        conn.execute(
            """INSERT OR IGNORE INTO items
               (id, guid_hash, source_id, kind, category, title, url, summary, published_at,
                fetched_at, body_text, word_count, duration_sec, audio_remote_url, score,
                fk_grade, avg_sentence_len, rare_word_ratio, level, level_method, license,
                attribution, origin)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?, 'reserve')""",
            (
                item_id(guid), guid, source_id, str(item.get("kind") or "text"),
                str(item.get("category") or "culture"), str(item.get("title") or "Untitled"),
                item.get("url"), item.get("summary"), item.get("published_at"),
                item.get("added_at") or dt.datetime.now().isoformat(timespec="seconds"),
                item.get("body_text"), item.get("word_count"), item.get("duration_sec"),
                item.get("audio_remote_url"), item.get("score", 0), item.get("fk_grade", 0),
                item.get("avg_sentence_len", 0), item.get("rare_word_ratio", 0),
                str(item.get("level") or "B1"), item.get("level_method") or "computed",
                str(item.get("license") or "public_domain"), item.get("attribution"),
            ),
        )
        inserted += 1
    conn.commit()
    return inserted


def _row_to_item(row: Any) -> dict[str, Any]:
    return {
        "guid_hash": row["guid_hash"],
        "source_id": row["source_id"],
        "kind": row["kind"],
        "category": row["category"],
        "title": row["title"],
        "url": row["url"],
        "summary": row["summary"],
        "published_at": row["published_at"],
        "added_at": row["fetched_at"],
        "body_text": row["body_text"],
        "word_count": row["word_count"],
        "duration_sec": row["duration_sec"],
        "audio_remote_url": row["audio_remote_url"],
        "score": row["score"],
        "fk_grade": row["fk_grade"],
        "avg_sentence_len": row["avg_sentence_len"],
        "rare_word_ratio": row["rare_word_ratio"],
        "level": row["level"],
        "level_method": row["level_method"],
        "license": row["license"],
        "attribution": row["attribution"],
        "origin": "reserve",
    }


def writeback_db(
    conn: Any,
    state_dir: str | Path,
    config: dict[str, Any],
    picked_hashes: set[str],
    used_hashes: set[str],
) -> list[dict[str, Any]]:
    existing = {str(item["guid_hash"]): item for item in load_pool(state_dir, config)}
    for guid in picked_hashes | used_hashes:
        existing.pop(guid, None)
    rows = conn.execute(
        """SELECT * FROM items WHERE origin='reserve' AND guid_hash IS NOT NULL"""
    ).fetchall()
    for row in rows:
        guid = str(row["guid_hash"])
        if guid in picked_hashes or guid in used_hashes:
            continue
        existing[guid] = _row_to_item(row)
    return save_pool(state_dir, existing.values(), config)


def load_books(state_dir: str | Path) -> dict[str, Any]:
    return read_json(Path(state_dir) / "books.json", {})


def save_books(state_dir: str | Path, books: dict[str, Any]) -> None:
    write_json(Path(state_dir) / "books.json", books)


def load_wiki_cache(state_dir: str | Path) -> dict[str, Any]:
    return read_json(Path(state_dir) / "wiki_cache.json", {})


def save_wiki_cache(state_dir: str | Path, cache: dict[str, Any]) -> None:
    write_json(Path(state_dir) / "wiki_cache.json", cache)
