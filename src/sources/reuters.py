from __future__ import annotations

import logging
from datetime import datetime
from typing import Callable
from urllib.parse import urlparse

from src.feeds import Article, fetch_articles
from src.googlenews import decode_real_url
from src.textutils import strip_source_suffix

logger = logging.getLogger(__name__)

# Reuters selbst blockt jeden automatisierten Zugriff (DataDome-Challenge, 401
# auf jede Seite) und ihre robots.txt untersagt "Collection of content, data
# and/or information from reuters.com through automated means" explizit ohne
# schriftliche Erlaubnis -> kein direkter Abruf/Scraping von reuters.com,
# das waere ein Bot-Detection-Bypass. Workaround bleibt Google News RSS
# (site:reuters.com), aber zusaetzlich decodieren wir Googles eigenen
# Redirect-Mechanismus (src/googlenews.py), um an die ECHTE reuters.com-URL
# zu kommen - daraus ziehen wir die Kategorie aus dem URL-Pfad (z.B. /world/,
# /business/, /technology/) fuers Topic-Filtering. Ein Artikel-Intro/Body-Text
# ist damit NICHT moeglich (der kommt nur von reuters.com selbst) - Summary
# bleibt leer.

# politics/geopolitics/wars -> world, economics/finance -> business/markets,
# tech -> technology. Bewusst kein sports/lifestyle/entertainment/breakingviews.
ALLOWED_CATEGORIES = {"world", "business", "markets", "technology"}


def _category_of(url: str) -> str | None:
    parts = urlparse(url).path.strip("/").split("/")
    return parts[0] if parts and parts[0] else None


def make_fetch(feed_url: str) -> Callable[[datetime], list[Article]]:
    def fetch(since: datetime) -> list[Article]:
        try:
            articles = fetch_articles(feed_url)
        except Exception:
            logger.exception("Fehler beim Abrufen von Reuters (Google News)")
            return []

        result = []
        for article in articles:
            if (article.source_title or "").lower() != "reuters":
                # Google News mischt bei site:-Suchen gelegentlich Treffer
                # anderer Quellen unter.
                continue
            article.title = strip_source_suffix(article.title, article.source_title)
            article.summary = ""

            if article.published and article.published >= since:
                # teurer Decode-Schritt (2 Requests) nur fuer frische
                # Kandidaten - alte Artikel unveraendert durchreichen (siehe
                # sources/tonline.py fuer die identische Begruendung: main.py
                # braucht den kompletten Feed-Inhalt fuer den Erstlauf-Backlog).
                real_url = decode_real_url(article.link)
                if not real_url or _category_of(real_url) not in ALLOWED_CATEGORIES:
                    continue
                article.link = real_url

            result.append(article)
        return result

    return fetch
