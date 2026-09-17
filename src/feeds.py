from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timezone

import feedparser

logger = logging.getLogger(__name__)


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
    parsed = feedparser.parse(feed_url)

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
