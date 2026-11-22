from __future__ import annotations

from typing import Any, Callable

from app.db import default_language, load_sources
from ingest.phrases import annotate_history
from ingest.pool import save_pool
from ingest.readability import CATEGORIES, KINDS, LEVELS
from ingest.reserve.common import Budget, source_host
from ingest.reserve.gutenberg import sample_gutenberg
from ingest.reserve.history import sample_history
from ingest.reserve.librivox import sample_librivox
from ingest.reserve.wikipedia import sample_wikipedia
from ingest.reserve.wikinews import sample_wikinews


def _deficient(items: list[dict[str, Any]], config: dict[str, Any]) -> int:
    counts: dict[tuple[str, str, str], int] = {}
    for item in items:
        level = str(item.get("level") or "B1")
        category = str(item.get("category") or "culture")
        kind = str(item.get("kind") or "text")
        if level in LEVELS and category in CATEGORIES and kind in KINDS:
            counts[(level, category, kind)] = counts.get((level, category, kind), 0) + 1
    minimum = int(config.get("pool_min_per_bucket", 4))
    return sum(1 for bucket in ((l, c, k) for l in LEVELS for c in CATEGORIES for k in KINDS)
               if counts.get(bucket, 0) < minimum)


def generate_reserves(
    config: dict[str, Any],
    state_dir: str,
    pool: list[dict[str, Any]],
    scale: float = 1.0,
    lang: str | None = None,
) -> list[dict[str, Any]]:
    """One sampling pass per round, shared budget, fills every deficient bucket."""
    all_items = list(pool)
    language = str(lang or default_language(config))
    scoring_config = dict(config)
    scoring_config["_lang"] = language
    budget = Budget(scoring_config, scale=scale)
    sources = load_sources(config, language)
    librivox_sources = [source for source in sources if source.get("type") == "librivox"
                        and source.get("enabled", True)]
    generators: list[tuple[str, Callable[[], list[dict[str, Any]]]]] = []
    if language == "en":
        generators.extend([
            ("wikipedia", lambda: sample_wikipedia(scoring_config, budget)),
            ("simple wikipedia", lambda: sample_wikipedia(scoring_config, budget, host="simple.wikipedia.org")),
            ("wikipedia history", lambda: sample_history(scoring_config, budget, state_dir, lang=language)),
            ("wikinews", lambda: sample_wikinews(scoring_config, budget)),
            ("gutenberg", lambda: sample_gutenberg(scoring_config, budget, state_dir, lang=language)),
        ])
    elif language == "es":
        wiki_types = {"wikipedia", "wikipedia_simple", "wikipedia_history", "wikinews", "gutenberg"}
        for source in sources:
            if not source.get("enabled", True):
                continue
            source_type = str(source.get("type") or "")
            if source_type not in wiki_types:
                continue
            if source_type in {"wikipedia", "wikipedia_simple"}:
                host = source_host(source, "es.wikipedia.org" if language == "es" else "en.wikipedia.org")
                generators.append((
                    f"wikipedia {source['id']}",
                    lambda source=source, host=host: sample_wikipedia(
                        scoring_config, budget, host=host, source=source
                    ),
                ))
            elif source_type == "wikipedia_history":
                generators.append((
                    f"wikipedia history {source['id']}",
                    lambda source=source: sample_history(
                        scoring_config, budget, state_dir, lang=language, source=source
                    ),
                ))
            elif source_type == "wikinews":
                generators.append((
                    f"wikinews {source['id']}",
                    lambda source=source: sample_wikinews(
                        scoring_config, budget, lang=language, source=source
                    ),
                ))
            elif source_type == "gutenberg":
                generators.append((
                    f"gutenberg {source['id']}",
                    lambda source=source: sample_gutenberg(
                        scoring_config, budget, state_dir, lang=language, source=source
                    ),
                ))
    for source in librivox_sources:
        generators.append((f"librivox {source['id']}", lambda source=source: sample_librivox(
            scoring_config, budget, state_dir, source, int(config.get("new_books_per_run", 25)), lang=language
        )))

    for _ in range(3):
        if not budget.ok or _deficient(all_items, config) == 0:
            break
        before = budget.requests
        for name, generator in generators:
            if not budget.ok:
                break
            try:
                produced = generator()
            except Exception as exc:
                print(f"[reserve] {name}: {type(exc).__name__}: {exc}")
                continue
            print(f"[reserve] {name}: {len(produced)} candidate(s)")
            for candidate in produced:
                candidate["lang"] = language
                all_items.append(annotate_history(candidate, scoring_config, language))
            continue
        if budget.requests == before:
            break
    return save_pool(state_dir, all_items, config, lang=language)
