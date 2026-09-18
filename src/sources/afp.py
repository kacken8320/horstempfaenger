from __future__ import annotations

import logging
from datetime import datetime
from typing import Callable

from src.afp import fetch_body
from src.feeds import Article, fetch_articles
from src.googlenews import decode_real_url
from src.textutils import strip_source_suffix, truncate

# Intro-Laenge fuer echt gescrapten Artikel-Body (nicht ueber das globale
# content_max_chars aus settings.yaml, das gilt nur fuer normale RSS-
# Summaries und soll durch diese Source nicht mitveraendert werden).
INTRO_MAX_CHARS = 256

logger = logging.getLogger(__name__)

# AFP hat kein offizielles RSS mehr - Discovery weiterhin ueber Google News
# (Suche nach "AFP", gefiltert auf Quelle "afp.com"). Anders als bei Reuters
# ist afp.com selbst aber NICHT bot-geschuetzt, deshalb holen wir hier
# zusaetzlich den echten Artikel-Body (siehe src/afp.py) - volle "scraping"-
# Behandlung statt nur Titel wie bei Reuters. Kein Kategorie-Filter (noch
# keine verlaessliche Kategorie-Struktur auf afp.com gefunden) - wie bei
# t-online/dpa wird der Quelle vertraut, dass sie i.d.R. on-topic ist.


def make_fetch(feed_url: str) -> Callable[[datetime], list[Article]]:
    def fetch(since: datetime) -> list[Article]:
        try:
            articles = fetch_articles(feed_url)
        except Exception:
            logger.exception("Fehler beim Abrufen von AFP (Google News)")
            return []

        result = []
        for article in articles:
            if (article.source_title or "").lower() != "afp.com":
                continue
            article.title = strip_source_suffix(article.title, article.source_title)

            if article.published and article.published >= since:
                # teurer Decode+Scrape-Schritt (3 Requests) nur fuer frische
                # Kandidaten - alte Artikel unveraendert durchreichen (siehe
                # sources/tonline.py fuer die identische Begruendung).
                real_url = decode_real_url(article.link)
                if not real_url:
                    continue
                article.link = real_url
                article.summary = truncate(fetch_body(real_url), INTRO_MAX_CHARS)
            else:
                article.summary = ""

            result.append(article)
        return result

    return fetch
