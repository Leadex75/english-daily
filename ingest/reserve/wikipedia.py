from __future__ import annotations

import random
from typing import Any

from ingest.fetch_feeds import plain_text
from ingest.reserve.common import Budget, api_get, get_url, is_blocked, make_candidate

SKIP_WORDS = ("disambiguation", "list of", "index of", "outline of", "category:")


def _extracts(pages: list[dict[str, Any]]) -> list[dict[str, str]]:
    result: list[dict[str, str]] = []
    for page in pages:
        title = str(page.get("title") or "")
        if not title or any(word in title.lower() for word in SKIP_WORDS):
            continue
        extract = plain_text(page.get("extract") or "")
        result.append({"title": title, "extract": extract, "pageid": str(page.get("pageid") or "")})
    return result


def sample_wikipedia(config: dict[str, Any], budget: Budget, host: str = "en.wikipedia.org", batches: int = 2) -> list[dict[str, Any]]:
    candidates: list[dict[str, Any]] = []
    for _ in range(batches):
        if not budget.ok:
            break
        payload = api_get(
            host, "/w/api.php",
            {"action": "query", "format": "json", "generator": "random", "grnnamespace": 0,
             "grnlimit": 20, "prop": "extracts", "exintro": 1, "explaintext": 1, "redirects": 1},
            config, budget,
        )
        pages = list((payload.get("query") or {}).get("pages") or {}).values()
        for page in _extracts(pages):
            if not budget.ok:
                break
            text = page["extract"]
            if len(text.split()) < int(config["text_pref_min_words"]) and page["pageid"]:
                full = api_get(
                    host, "/w/api.php",
                    {"action": "query", "format": "json", "prop": "extracts", "explaintext": 1,
                     "redirects": 1, "pageids": page["pageid"]},
                    config, budget,
                )
                full_pages = list((full.get("query") or {}).get("pages") or {}).values()
                if full_pages:
                    text = plain_text(full_pages[0].get("extract") or text)
            if is_blocked(text, config) or len(text.split()) < int(config["text_hard_min_words"]):
                continue
            if len(text.split()) > 800:
                words = text.split()
                text = " ".join(words[:800])
            level_min, level_max = ("A1", "B1") if "simple." in host else ("A1", "C2")
            candidate = make_candidate(
                title=page["title"], text=text, source_id="wikipedia_simple" if "simple." in host else "wikipedia",
                source_name="Simple English Wikipedia" if "simple." in host else "Wikipedia",
                category="culture", kind="text", license_name="cc_by_sa",
                attribution="Wikipedia, CC BY-SA 4.0", config=config,
                url=f"https://{host}/wiki/" + page["title"].replace(" ", "_"),
                level_min=level_min, level_max=level_max,
            )
            if candidate:
                candidates.append(candidate)
        if random.random() < 0.5:
            host = "simple.wikipedia.org" if host == "en.wikipedia.org" and "simple." not in host else "en.wikipedia.org"
    return candidates
