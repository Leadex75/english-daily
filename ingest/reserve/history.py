from __future__ import annotations

import datetime as dt
import random
from typing import Any

from ingest.fetch_feeds import plain_text
from ingest.pool import load_wiki_cache, save_wiki_cache
from ingest.reserve.common import Budget, api_get, make_candidate
from ingest.reserve.wikipedia import _extracts

MAX_TITLES = 800


def _refresh_title_cache(
    config: dict[str, Any], state_dir: str, budget: Budget, lang: str | None = None
) -> list[str]:
    cache = load_wiki_cache(state_dir, config, lang)
    month = dt.date.today().strftime("%Y-%m")
    history_cache = cache.get("history") or {}
    if history_cache.get("month") == month and history_cache.get("titles"):
        return list(history_cache["titles"])[:MAX_TITLES]
    titles: list[str] = []
    for category in config.get("history_categories") or []:
        if not budget.ok or len(titles) >= MAX_TITLES:
            break
        payload = api_get(
            "en.wikipedia.org", "/w/api.php",
            {"action": "query", "format": "json", "list": "categorymembers",
             "cmtitle": f"Category:{category}", "cmtype": "page", "cmlimit": 100},
            config, budget,
        )
        for member in (payload.get("query") or {}).get("categorymembers") or []:
            title = str(member.get("title") or "")
            if title and title not in titles:
                titles.append(title)
    random.shuffle(titles)
    titles = titles[:MAX_TITLES]
    cache["history"] = {"month": month, "titles": titles, "refreshed_at": dt.datetime.now().isoformat(timespec="seconds")}
    save_wiki_cache(state_dir, cache, config, lang)
    return titles


def sample_history(
    config: dict[str, Any],
    budget: Budget,
    state_dir: str,
    batches: int = 2,
    lang: str | None = None,
) -> list[dict[str, Any]]:
    titles = _refresh_title_cache(config, state_dir, budget, lang)
    if not titles:
        return []
    candidates: list[dict[str, Any]] = []
    for _ in range(batches):
        if not budget.ok:
            break
        batch = [titles[i:i + 20] for i in range(0, min(len(titles), 300), 20)]
        chosen = random.choice(batch) if batch else []
        payload = api_get(
            "en.wikipedia.org", "/w/api.php",
            {"action": "query", "format": "json", "prop": "extracts", "exintro": 1,
             "explaintext": 1, "redirects": 1, "titles": "|".join(chosen)},
            config, budget,
        )
        for page in _extracts(list((payload.get("query") or {}).get("pages") or {}).values()):
            text = page["extract"]
            if len(text.split()) < int(config["text_hard_min_words"]):
                continue
            candidate = make_candidate(
                title=page["title"], text=text, source_id="wikipedia_history",
                source_name="Wikipedia (history)", category="history", kind="text",
                license_name="cc_by_sa", attribution="Wikipedia, CC BY-SA 4.0", config=config,
                url="https://en.wikipedia.org/wiki/" + page["title"].replace(" ", "_"),
                level_min="A2", level_max="C2",
            )
            if candidate:
                candidates.append(candidate)
    return candidates


def onthisday_linked(config: dict[str, Any], budget: Budget, titles: list[str], day: str) -> list[dict[str, Any]]:
    candidates: list[dict[str, Any]] = []
    chosen = [title for title in titles[:10] if title]
    if not chosen or not budget.ok:
        return candidates
    payload = api_get(
        "en.wikipedia.org", "/w/api.php",
        {"action": "query", "format": "json", "prop": "extracts", "exintro": 1,
         "explaintext": 1, "redirects": 1, "titles": "|".join(chosen)},
        config, budget,
    )
    for page in _extracts(list((payload.get("query") or {}).get("pages") or {}).values()):
        text = page["extract"]
        if len(text.split()) < int(config["text_hard_min_words"]):
            continue
        candidate = make_candidate(
            title=page["title"], text=text, source_id="wikipedia_history",
            source_name="Wikipedia (history)", category="history", kind="text",
            license_name="cc_by_sa", attribution="Wikipedia, CC BY-SA 4.0", config=config,
            url="https://en.wikipedia.org/wiki/" + page["title"].replace(" ", "_"),
            published_at=f"{day}T00:00:00", level_min="A2", level_max="C2",
        )
        if candidate:
            candidates.append(candidate)
    return candidates
