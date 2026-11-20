from __future__ import annotations

import datetime as dt
import email.utils
import html
import re
import time
from contextlib import contextmanager
from typing import Any, Iterator
from urllib.parse import urlparse, urlunparse, urlencode

import feedparser
import httpx

_last_hit: dict[str, float] = {}
_client: httpx.Client | None = None
_TAG_RE = re.compile(r"<[^>]+>")
_SPACE_RE = re.compile(r"\s+")


def plain_text(value: str | None) -> str:
    if not value:
        return ""
    text = html.unescape(_TAG_RE.sub(" ", value))
    return _SPACE_RE.sub(" ", text).strip()


def _client_for(config: dict[str, Any]) -> httpx.Client:
    global _client
    if _client is None:
        _client = httpx.Client(
            headers={"User-Agent": str(config["user_agent"])},
            timeout=float(config["request_timeout_sec"]),
            follow_redirects=True,
        )
    return _client


def _polite(url: str) -> None:
    host = urlparse(url).netloc
    now = time.monotonic()
    wait = 1.0 - (now - _last_hit[host]) if host in _last_hit else 0.0
    if wait > 0:
        time.sleep(wait)
    _last_hit[host] = time.monotonic()


def http_get(url: str, config: dict[str, Any], headers: dict[str, str] | None = None) -> httpx.Response:
    """GET with the configured user agent and a 1s delay per host."""
    _polite(url)
    return _client_for(config).get(url, headers=headers)


def _wiki_headers(config: dict[str, Any]) -> dict[str, str]:
    # Wikimedia blocks generic agents; keep the configured UA but add contact info.
    ua = str(config["user_agent"]).rstrip(")")
    return {"User-Agent": ua + "; contact: english-daily@example.org)", "Accept": "application/json"}


@contextmanager
def http_stream(
    url: str,
    config: dict[str, Any],
    headers: dict[str, str] | None = None,
    raise_for_status: bool = True,
) -> Iterator[httpx.Response]:
    _polite(url)
    with _client_for(config).stream("GET", url, headers=headers) as response:
        if raise_for_status:
            response.raise_for_status()
        yield response


def _published(entry: Any) -> str:
    for key in ("published_parsed", "updated_parsed"):
        parsed = entry.get(key)
        if parsed:
            try:
                return dt.datetime(*parsed[:6]).isoformat(timespec="seconds")
            except (TypeError, ValueError):
                pass
    for key in ("published", "updated"):
        raw = entry.get(key)
        if raw:
            try:
                parsed_date = email.utils.parsedate_to_datetime(str(raw))
                return parsed_date.replace(tzinfo=None).isoformat(timespec="seconds")
            except (TypeError, ValueError):
                pass
    return dt.datetime.now().isoformat(timespec="seconds")


def _entry(source: dict[str, Any], entry: Any) -> dict[str, Any]:
    link = str(entry.get("link") or "")
    enclosure = None
    for item in entry.get("enclosures") or []:
        href = str(item.get("href") or item.get("url") or "")
        mime = str(item.get("type") or "")
        if href and (mime.startswith("audio") or href.lower().split("?")[0].endswith(".mp3")):
            enclosure = href
            break
    return {
        "guid": str(entry.get("guid") or entry.get("id") or link or entry.get("title", "")),
        "title": plain_text(entry.get("title")) or "Untitled",
        "url": link,
        "summary": plain_text(entry.get("summary") or entry.get("description")),
        "published_at": _published(entry),
        "enclosure_url": enclosure,
        "itunes_duration": entry.get("itunes_duration"),
        "body_text": None,
        "source_id": str(source["id"]),
    }


def _wiki_api(host: str, params: dict[str, Any], config: dict[str, Any]) -> dict[str, Any]:
    url = urlunparse(("https", host, "/w/api.php", "", urlencode(params), ""))
    response = http_get(url, config, headers=_wiki_headers(config))
    response.raise_for_status()
    return response.json()


def _wikipedia_simple(config: dict[str, Any]) -> list[dict[str, Any]]:
    # MediaWiki allows only one full-article extract per request, so ask for
    # random titles first and fetch each extract separately.
    titles_data = _wiki_api(
        "simple.wikipedia.org",
        {"action": "query", "format": "json", "list": "random", "rnnamespace": 0, "rnlimit": 8},
        config,
    )
    today = dt.datetime.now().isoformat(timespec="seconds")
    entries: list[dict[str, Any]] = []
    for random_item in titles_data.get("query", {}).get("random", []):
        title = str(random_item.get("title") or "")
        if not title:
            continue
        page_data = _wiki_api(
            "simple.wikipedia.org",
            {
                "action": "query", "format": "json", "prop": "extracts",
                "explaintext": 1, "redirects": 1, "titles": title,
            },
            config,
        )
        pages = list((page_data.get("query", {}).get("pages") or {}).values())
        extract = plain_text(pages[0].get("extract") or "") if pages else ""
        if not extract:
            continue
        entries.append(
            {
                "guid": f"wikipedia_simple:{random_item.get('id', title)}",
                "title": title,
                "url": "https://simple.wikipedia.org/wiki/" + title.replace(" ", "_"),
                "summary": extract[:400],
                "published_at": today,
                "enclosure_url": None,
                "itunes_duration": None,
                "body_text": extract,
                "source_id": "wikipedia_simple",
            }
        )
    return entries


def _wikipedia_featured(config: dict[str, Any], day: str) -> list[dict[str, Any]]:
    try:
        target = dt.date.fromisoformat(day)
    except ValueError:
        target = dt.date.today()
    feed_url = (
        "https://en.wikipedia.org/api/rest_v1/feed/featured/"
        f"{target.year:04d}/{target.month:02d}/{target.day:02d}"
    )
    response = http_get(feed_url, config, headers=_wiki_headers(config))
    response.raise_for_status()
    payload = response.json()
    article = payload.get("tfa") or payload.get("article") or {}
    title = article.get("title")
    if not title:
        return []
    data = _wiki_api(
        "en.wikipedia.org",
        {
            "action": "query",
            "format": "json",
            "prop": "extracts",
            "explaintext": 1,
            "redirects": 1,
            "titles": title,
        },
        config,
    )
    pages = list((data.get("query", {}).get("pages") or {}).values())
    extract = plain_text(pages[0].get("extract") or "") if pages else ""
    if not extract:
        return []
    return [
        {
            "guid": f"wikipedia_featured:{target.isoformat()}:{title}",
            "title": str(title),
            "url": article.get("content_urls", {}).get("desktop", {}).get("page")
            or "https://en.wikipedia.org/wiki/" + str(title).replace(" ", "_"),
            "summary": extract[:400],
            "published_at": target.isoformat() + "T00:00:00",
            "enclosure_url": None,
            "itunes_duration": None,
            "body_text": extract,
            "source_id": "wikipedia_featured",
        }
    ]


def fetch_source(source: dict[str, Any], config: dict[str, Any], day: str) -> list[dict[str, Any]]:
    """Fetch and normalize entries from one source; raises on network/parse failure."""
    kind = source.get("type") or "rss"
    limit = int(config.get("max_entries_per_source", 10))
    if kind == "wikipedia_simple":
        return _wikipedia_simple(config)[:limit]
    if kind == "wikipedia_featured":
        return _wikipedia_featured(config, day)[:limit]
    response = http_get(str(source["feed_url"]), config)
    response.raise_for_status()
    parsed = feedparser.parse(response.content)
    entries = [_entry(source, item) for item in parsed.entries[:limit]]
    return entries
