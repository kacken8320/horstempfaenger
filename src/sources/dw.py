from __future__ import annotations

import logging
from datetime import datetime
from typing import Callable

from src.feeds import Article, fetch_articles

logger = logging.getLogger(__name__)

# DWs englischer RSS-Feed liefert pro Item ein sauberes <category>-Feld
# (News/World/Germany/Business/Sports/Culture/Science/Environment/Climate) -
# kein Scraping noetig, reiner Feed-Filter. "Science" ist die naechstbeste
# Naeherung fuer Tech (DW hat keine eigene Tech-Kategorie, kann also auch
# Nicht-Tech-Wissenschaft enthalten). Sport/Kultur/Umwelt/Klima explizit raus.
ALLOWED_CATEGORIES = {"news", "world", "germany", "business", "science"}


def make_fetch(feed_url: str) -> Callable[[datetime], list[Article]]:
    def fetch(since: datetime) -> list[Article]:
        try:
            articles = fetch_articles(feed_url)
        except Exception:
            logger.exception("Fehler beim Abrufen von DW")
            return []

        return [a for a in articles if (a.category or "").lower() in ALLOWED_CATEGORIES]

    return fetch
