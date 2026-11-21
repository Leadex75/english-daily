from __future__ import annotations

import datetime as dt
import random
from typing import Any

from ingest.fetch_feeds import plain_text
from ingest.reserve.common import Budget, api_get, make_candidate

MONTHS = ["January", "February", "March", "April", "May", "June", "July", "August",
          "September", "October", "November", "December"]


def sample_wikinews(config: dict[str, Any], budget: Budget, batches: int = 2) -> list[dict[str, Any]]:
    today = dt.date.today()
    titles: list[str] = []
    for year in (today.year, today.year - 1):
        payload = api_get(
            "en.wikinews.org", "/w/api.php",
            {"action": "query", "format": "json", "list": "categorymembers",
             "cmtitle": f"Category:{MONTHS[today.month - 1]} {year}", "cmtype": "page", "cmlimit": 100},
            config, budget,
        )
        titles.extend(str(item.get("title")) for item in (payload.get("query") or {}).get("categorymembers") or [])
        if titles:
            break
    if not titles:
        return []
    candidates: list[dict[str, Any]] = []
    for _ in range(batches):
        if not budget.ok or not titles:
            break
        batch = random.sample(titles, min(20, len(titles)))
        payload = api_get(
            "en.wikinews.org", "/w/api.php",
            {"action": "query", "format": "json", "prop": "extracts", "exintro": 1,
             "explaintext": 1, "redirects": 1, "titles": "|".join(batch)},
            config, budget,
        )
        for page in ((payload.get("query") or {}).get("pages") or {}).values():
            text = plain_text(page.get("extract") or "")
            if len(text.split()) < int(config["text_hard_min_words"]):
                continue
            title = str(page.get("title") or "")
            candidate = make_candidate(
                title=title, text=text, source_id="wikinews", source_name="Wikinews",
                category="news", kind="text", license_name="cc_by",
                attribution="Wikinews, CC BY 2.5", config=config,
                url="https://en.wikinews.org/wiki/" + title.replace(" ", "_"),
                level_min="B1", level_max="C2",
            )
            if candidate:
                candidates.append(candidate)
    return candidates
