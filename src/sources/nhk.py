from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Callable

import requests

from src.feeds import REQUEST_HEADERS, Article
from src.textutils import truncate

logger = logging.getLogger(__name__)

BASE_URL = "https://www3.nhk.or.jp"

# NHK World hat kein RSS mehr, aber eine interne JSON-Liste, die ihre eigene
# (JS-gerenderte) News-Startseite selbst laedt - liefert Titel, echte
# Kurzbeschreibung, Kategorie und Timestamp direkt mit, neueste zuerst
# sortiert. Kein Scraping einzelner Artikelseiten noetig. Beobachtete
# Kategorien: JAPAN/WORLD/ASIA/BIZTCH - Sport/Entertainment/Society tauchten
# in Stichproben nie auf (laufen offenbar in eigenen NHK-World-Bereichen),
# Deny-Liste trotzdem als Absicherung falls sich das aendert.
DENY_CATEGORIES = {"sports", "entertainment", "lifestyle", "culture"}

INTRO_MAX_CHARS = 256


def _parse_timestamp(raw: str) -> datetime | None:
    try:
        return datetime.fromtimestamp(int(raw) / 1000, tz=timezone.utc)
    except (TypeError, ValueError):
        return None


def make_fetch(feed_url: str) -> Callable[[datetime], list[Article]]:
    def fetch(since: datetime) -> list[Article]:
        try:
            resp = requests.get(feed_url, headers=REQUEST_HEADERS, timeout=15)
            resp.raise_for_status()
            items = resp.json().get("data", [])
        except (requests.RequestException, ValueError):
            logger.exception("Fehler beim Abrufen von NHK World")
            return []

        result = []
        for item in items:
            category = (item.get("categories") or {}).get("name", "")
            if category.lower() in DENY_CATEGORIES:
                continue

            page_url = item.get("page_url") or ""
            key = item.get("id") or page_url
            if not key:
                continue

            result.append(
                Article(
                    key=key,
                    title=(item.get("title") or "").strip(),
                    link=f"{BASE_URL}{page_url}" if page_url else "",
                    author="",
                    published=_parse_timestamp(item.get("updated_at", "")),
                    summary=truncate((item.get("description") or "").strip(), INTRO_MAX_CHARS),
                )
            )
        return result

    return fetch
