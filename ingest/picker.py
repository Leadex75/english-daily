from __future__ import annotations

import datetime as dt
from typing import Any

from app.db import connect
from ingest.readability import CATEGORIES, KINDS, LEVELS, band_center


def fill_picks(
    day: str,
    config: dict[str, Any],
    excluded_hashes: set[str] | None = None,
) -> tuple[list[str], list[str]]:
    """Fill the 24 slots for `day`, never reusing an item already published."""
    excluded = set(excluded_hashes or ())
    conn = connect(config)
    try:
        conn.execute("DELETE FROM daily_picks WHERE date=?", (day,))
        used = {
            int(row[0])
            for row in conn.execute(
                "SELECT item_id FROM daily_picks WHERE date<>? AND item_id IS NOT NULL", (day,)
            )
        }
        target = dt.date.fromisoformat(day)
        cutoff = (target - dt.timedelta(days=int(config["lookback_days"]))).isoformat()
        thresholds = config["level_thresholds"]
        filled: list[str] = []
        empty: list[str] = []

        for level in LEVELS:
            center = band_center(level, thresholds)
            for category in CATEGORIES:
                for kind in KINDS:
                    rows = conn.execute(
                        """SELECT id, guid_hash, score FROM items
                           WHERE level=? AND category=? AND kind=?
                             AND date(published_at) >= date(?)
                             AND (? = 'audio' OR (body_text IS NOT NULL AND body_text <> ''
                                                  AND word_count BETWEEN 120 AND 1500))
                              AND (? = 'text' OR audio_path IS NOT NULL OR audio_remote_url IS NOT NULL)

                           ORDER BY published_at DESC, ABS(COALESCE(score, 0) - ?) ASC, id DESC""",
                        (level, category, kind, cutoff, kind, kind, center),
                    ).fetchall()
                    candidates = [
                        row
                        for row in rows
                        if int(row["id"]) not in used and str(row["guid_hash"]) not in excluded
                    ]
                    if not candidates:
                        empty.append(f"{level}/{category}/{kind}")
                        continue
                    chosen_row = candidates[0]
                    chosen = int(chosen_row["id"])
                    conn.execute(
                        """INSERT OR REPLACE INTO daily_picks (date, level, category, kind, item_id)
                           VALUES (?,?,?,?,?)""",
                        (day, level, category, kind, chosen),
                    )
                    used.add(chosen)
                    excluded.add(str(chosen_row["guid_hash"]))
                    filled.append(f"{level}/{category}/{kind}")
        conn.commit()
        return filled, empty
    finally:
        conn.close()
