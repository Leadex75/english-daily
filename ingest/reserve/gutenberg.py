from __future__ import annotations

import random
from typing import Any

from ingest.pool import load_books
from ingest.reserve.common import Budget, make_candidate, paragraph_cut
from ingest.reserve.librivox import gutenberg_text

CURATED_IDS = ["1184", "1342", "11", "2701", "1661", "84", "174", "98", "1400", "2600", "345", "1260"]
CURATED_IDS_ES = ["2000", "1051", "17315", "15115", "14971", "29223", "2002", "2034"]


def sample_gutenberg(
    config: dict[str, Any],
    budget: Budget,
    state_dir: str,
    lang: str | None = None,
    source: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    language = str(lang or config.get("_lang") or "en")
    source_id = str((source or {}).get("id") or "gutenberg_text")
    source_name = str((source or {}).get("name") or "Project Gutenberg")
    ids = list(CURATED_IDS_ES if language == "es" else CURATED_IDS)
    cached = [str(item.get("gutenberg_id") or "") for item in load_books(state_dir, config, lang).values()]
    ids.extend(gid for gid in cached if gid and gid not in ids)
    random.shuffle(ids)
    candidates: list[dict[str, Any]] = []
    for gid in ids[:6]:
        if not budget.ok:
            break
        text = gutenberg_text(gid, config, budget)
        if len(text.split()) < int(config["text_hard_min_words"]):
            continue
        words = text.split()
        start = random.randint(0, max(0, len(words) - 900))
        passage = paragraph_cut(" ".join(words[start:start + 900]), int(config["text_pref_max_words"]))
        if len(passage.split()) < 500:
            passage = " ".join(words[start:start + 700])
        candidate = make_candidate(
            title=f"Project Gutenberg #{gid}", text=passage, source_id=source_id,
            source_name=source_name, category="culture", kind="text",
            license_name="public_domain", attribution="Project Gutenberg", config=config,
            url=f"https://www.gutenberg.org/ebooks/{gid}", level_min="A2", level_max="C2",
            extra={"gutenberg_id": gid},
        )
        if candidate:
            candidates.append(candidate)
    return candidates
