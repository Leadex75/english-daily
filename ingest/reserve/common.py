from __future__ import annotations

import datetime as dt
import html
import re
import time
from typing import Any
from urllib.parse import urlencode

from ingest.fetch_feeds import _wiki_headers, http_get, plain_text
from ingest.fetch_text import clean_text, word_count
from ingest.readability import classify, clamp_level, metrics

_TAG_RE = re.compile(r"<[^>]+>")


class Budget:
    def __init__(self, config: dict[str, Any], scale: float = 1.0):
        self.deadline = time.monotonic() + float(config.get("reserve_time_budget_sec", 420)) * scale
        self.max_requests = int(float(config.get("reserve_max_requests", 400)) * scale)
        self.requests = 0

    @property
    def ok(self) -> bool:
        return self.requests < self.max_requests and time.monotonic() < self.deadline

    def tick(self) -> None:
        self.requests += 1


def api_get(host: str, path: str, params: dict[str, Any], config: dict[str, Any], budget: Budget) -> dict[str, Any]:
    if not budget.ok:
        return {}
    url = f"https://{host}{path}?{urlencode(params)}"
    budget.tick()
    try:
        response = http_get(url, config, headers=_wiki_headers(config))
        if response.status_code != 200:
            return {}
        payload = response.json()
        return payload if isinstance(payload, dict) else {}
    except Exception:
        return {}


def get_url(url: str, config: dict[str, Any], budget: Budget) -> str:
    if not budget.ok:
        return ""
    budget.tick()
    try:
        response = http_get(url, config, headers=_wiki_headers(config))
        if response.status_code == 200:
            return response.text
    except Exception:
        pass
    return ""


def is_blocked(text: str, config: dict[str, Any]) -> bool:
    lowered = (text or "").lower()
    return any(str(word).lower() in lowered for word in config.get("content_blocklist") or [])


def paragraph_cut(text: str, max_words: int) -> str:
    """Cut at a paragraph boundary near max_words, never above it."""
    paragraphs = [part.strip() for part in re.split(r"\n\s*\n", text or "") if part.strip()]
    if not paragraphs:
        return ""
    kept: list[str] = []
    total = 0
    for paragraph in paragraphs:
        count = word_count(paragraph)
        if total + count > max_words and kept:
            break
        kept.append(paragraph)
        total += count
        if total >= max_words:
            break
    result = "\n\n".join(kept)
    if word_count(result) <= max_words:
        return result
    words = result.split()
    result = " ".join(words[:max_words])
    sentences = re.split(r"(?<=[.!?])\s+", result)
    if len(sentences) > 1 and word_count(sentences[0]) >= max_words // 2:
        return sentences[0]
    return result


def make_candidate(
    *,
    title: str,
    text: str,
    source_id: str,
    source_name: str,
    category: str,
    kind: str,
    license_name: str,
    attribution: str | None,
    config: dict[str, Any],
    url: str,
    published_at: str | None = None,
    duration_sec: int | None = None,
    audio_url: str | None = None,
    level_min: str = "A1",
    level_max: str = "C2",
    extra: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    body = clean_text(text)
    if not body or is_blocked(body, config):
        return None
    if kind == "text":
        if word_count(body) > int(config["text_hard_max_words"]):
            body = paragraph_cut(body, int(config["text_pref_max_words"]))
        words = word_count(body)
        if not int(config["text_hard_min_words"]) <= words <= int(config["text_hard_max_words"]):
            return None
    else:
        words = word_count(body)
        if duration_sec is None:
            return None
    values = metrics(body[:4000])
    level = clamp_level(classify(values["score"], config["level_thresholds"]), level_min, level_max)
    guid_seed = f"{source_id}:{title}:{url}:{published_at or ''}:{duration_sec or ''}"
    import hashlib
    guid = hashlib.sha1(guid_seed.encode("utf-8", "ignore")).hexdigest()
    candidate: dict[str, Any] = {
        "guid_hash": guid,
        "source_id": source_id,
        "source_name": source_name,
        "kind": kind,
        "category": category,
        "title": clean_text(title),
        "url": url,
        "summary": body[:400],
        "published_at": published_at or dt.datetime.now().isoformat(timespec="seconds"),
        "added_at": dt.datetime.now().isoformat(timespec="seconds"),
        "body_text": body if kind == "text" else None,
        "word_count": words,
        "duration_sec": duration_sec,
        "audio_remote_url": audio_url,
        "score": values["score"],
        "fk_grade": values["fk_grade"],
        "avg_sentence_len": values["avg_sentence_len"],
        "rare_word_ratio": values["rare_word_ratio"],
        "level": level,
        "level_method": "computed",
        "license": license_name,
        "attribution": attribution,
        "origin": "reserve",
        "origin_kind": "reserve",
    }
    if extra:
        candidate.update(extra)
    return candidate


def strip_html(value: str) -> str:
    return plain_text(html.unescape(_TAG_RE.sub(" ", value or "")))
