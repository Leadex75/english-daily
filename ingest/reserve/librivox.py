from __future__ import annotations

import datetime as dt
import random
import re
from typing import Any

from ingest.fetch_audio import _https_candidate
from ingest.pool import load_books, save_books
from ingest.readability import classify, clamp_level, metrics
from ingest.reserve.common import Budget, api_get, get_url, make_candidate

GUTENBERG_URLS = [
    "https://www.gutenberg.org/cache/epub/{gid}/pg{gid}.txt",
    "https://www.gutenberg.org/files/{gid}/{gid}-0.txt",
    "https://www.gutenberg.org/ebooks/{gid}.txt.utf-8",
]


def gutenberg_id(value: Any) -> str:
    text = str(value or "")
    match = re.search(r"(?:etext/|ebooks?/|pg)(\d+)", text)
    return match.group(1) if match else ""


def strip_gutenberg(text: str) -> str:
    start = re.search(r"\*\*\*\s*START OF (?:THE|THIS) PROJECT GUTENBERG EBOOK.*?\*\*\*", text, re.I | re.S)
    end = re.search(r"\*\*\*\s*END OF (?:THE|THIS) PROJECT GUTENBERG EBOOK.*?\*\*\*", text, re.I | re.S)
    if start:
        text = text[start.end():]
    if end:
        text = text[:end.start()]
    return text.strip()


def gutenberg_text(gid: str, config: dict[str, Any], budget: Budget) -> str:
    for template in GUTENBERG_URLS:
        body = get_url(template.format(gid=gid), config, budget)
        if body and "DOCTYPE html" not in body[:500] and len(body) > 2000:
            return strip_gutenberg(body)
    return ""


def _book_level(text: str, fallback: str, config: dict[str, Any]) -> tuple[str, float, str]:
    words = text.split()
    if len(words) >= 400:
        scores = []
        for fraction in (0.2, 0.5, 0.8):
            start = int(len(words) * fraction)
            chunk = " ".join(words[start:start + 700])
            if chunk:
                scores.append(metrics(chunk)["score"])
        if scores:
            score = round(sum(scores) / len(scores), 4)
            return clamp_level(classify(score, config["level_thresholds"]), "A1", "C2"), score, "computed"
    values = metrics(fallback[:3000])
    return clamp_level(classify(values["score"], config["level_thresholds"]), "A1", "C2"), values["score"], "source"


def sample_librivox(
    config: dict[str, Any], budget: Budget, state_dir: str, source: dict[str, Any], max_books: int
) -> list[dict[str, Any]]:
    books = load_books(state_dir)
    wanted = [str(name).lower() for name in source.get("genres") or []]
    params = {"format": "json", "extended": 1, "limit": 20, "offset": random.randint(0, 400)}
    payload = api_get("librivox.org", "/api/feed/audiobooks/", params, config, budget)
    raw_books = payload.get("books") or []
    if isinstance(raw_books, dict):
        raw_books = list(raw_books.values())
    candidates: list[dict[str, Any]] = []
    processed = 0
    for book in raw_books:
        if processed >= max_books or not budget.ok:
            break
        book_id = str(book.get("id") or "")
        if not book_id or book_id in books:
            continue
        if "english" not in str(book.get("language") or "").lower():
            continue
        genres = [str(item.get("name") or "") for item in book.get("genres") or []]
        if wanted and not any(any(word in genre.lower() for word in wanted) for genre in genres):
            continue
        gid = gutenberg_id(book.get("url_text_source"))
        text = gutenberg_text(gid, config, budget) if gid else ""
        description = re.sub(r"<[^>]+>", " ", str(book.get("description") or ""))
        title = str(book.get("title") or "Untitled")
        level, score, method = _book_level(text, f"{title}. {description}", config)
        author = ", ".join(str(item.get("name") or "") for item in book.get("authors") or [])
        books[book_id] = {
            "title": title, "author": author, "gutenberg_id": gid,
            "genre": ", ".join(genres), "level": level, "score": score,
            "url_rss": book.get("url_rss"), "fetched_at": dt.datetime.now().isoformat(timespec="seconds"),
            "level_method": method,
        }
        processed += 1
        for section in (book.get("sections") or [])[:3]:
            listen_url = str(section.get("listen_url") or "")
            if not listen_url:
                continue
            try:
                duration = int(section.get("playtime") or 0)
            except (TypeError, ValueError):
                duration = 0
            low = config.get("audio_hard_min_sec")
            high = config.get("audio_hard_max_sec")
            if duration < int(low or 0) or (high is not None and duration > int(high)):
                continue
            section_title = str(section.get("title") or "Chapter")
            candidate = make_candidate(
                title=f"{title} - {section_title}",
                text=f"{title} by {author}. {description}",
                source_id=str(source["id"]), source_name=str(source.get("name") or "LibriVox"),
                category=str(source["category"]), kind="audio", license_name="public_domain",
                attribution="LibriVox (public domain recording)", config=config,
                url=str(book.get("url_librivox") or book.get("url_rss") or listen_url),
                published_at=books[book_id]["fetched_at"], duration_sec=duration,
                audio_url=_https_candidate(listen_url),
                extra={"librivox_id": book_id, "gutenberg_id": gid},
            )
            if candidate:
                candidate["level"] = level
                candidate["level_method"] = method
                candidate["score"] = score
                candidates.append(candidate)
    save_books(state_dir, books)
    return candidates
