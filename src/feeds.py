from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timezone

import feedparser
import requests

logger = logging.getLogger(__name__)

# feedparser's eigener Fetcher schickt einen sehr bot-typischen Default-
# User-Agent mit - Google News (u.a.) beantwortet das von manchen Hosting-IPs
# aus mit einer HTML-Blockseite statt echtem RSS, was dann als malformed XML
# auffaellt. Deshalb selbst per requests mit Browser-UA abrufen.
_REQUEST_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "application/rss+xml, application/xml;q=0.9, */*;q=0.8",
}


@dataclass
class Article:
    key: str
    title: str
    link: str
    author: str
    published: datetime | None
    summary: str
    source_title: str | None = None


def _entry_key(entry) -> str:
    return entry.get("id") or entry.get("link") or entry.get("title", "")


def _entry_datetime(entry) -> datetime | None:
    for field in ("published_parsed", "updated_parsed"):
        struct = entry.get(field)
        if struct:
            return datetime(*struct[:6], tzinfo=timezone.utc)
    return None


def fetch_articles(feed_url: str) -> list[Article]:
    try:
        resp = requests.get(feed_url, headers=_REQUEST_HEADERS, timeout=15)
        resp.raise_for_status()
    except requests.RequestException as exc:
        logger.warning("Feed konnte nicht abgerufen werden: %s (%s)", feed_url, exc)
        return []

    parsed = feedparser.parse(resp.content)

    if parsed.bozo and not parsed.entries:
        logger.warning("Feed konnte nicht gelesen werden: %s (%s)", feed_url, parsed.bozo_exception)
        return []

    articles = []
    for entry in parsed.entries:
        key = _entry_key(entry)
        if not key:
            continue
        articles.append(
            Article(
                key=key,
                title=entry.get("title", "(ohne Titel)").strip(),
                link=entry.get("link", ""),
                author=entry.get("author", "unbekannt").strip(),
                published=_entry_datetime(entry),
                summary=(entry.get("summary") or "").strip(),
                source_title=entry.get("source", {}).get("title"),
            )
        )
    return articles
