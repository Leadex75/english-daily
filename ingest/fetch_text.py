from __future__ import annotations

import re
from typing import Any

import trafilatura

from ingest.fetch_feeds import http_get, plain_text

_SPACE_RE = re.compile(r"[ \t]+")
_NEWLINES_RE = re.compile(r"\n{3,}")


def clean_text(value: str | None) -> str:
    text = plain_text(value) if "<" in (value or "") else (value or "").strip()
    text = _SPACE_RE.sub(" ", text)
    return _NEWLINES_RE.sub("\n\n", text).strip()


def word_count(text: str) -> int:
    return len(re.findall(r"[A-Za-z]+(?:['\u2019-][A-Za-z]+)*", text or ""))


def extract_article(url: str, config: dict[str, Any]) -> str:
    """Fetch an article and extract its main text with trafilatura."""
    if not url:
        return ""
    response = http_get(url, config)
    response.raise_for_status()
    extracted = trafilatura.extract(
        response.text,
        include_comments=False,
        include_tables=False,
        favor_precision=True,
    )
    return clean_text(extracted)


def body_for_entry(entry: dict[str, Any], config: dict[str, Any]) -> str:
    """Audio items are never scraped: their text must come from the feed summary."""
    if entry.get("body_text"):
        return clean_text(entry["body_text"])
    if entry.get("source_kind") == "audio":
        return ""
    extracted = extract_article(str(entry.get("url") or ""), config)
    return extracted or clean_text(entry.get("summary"))
