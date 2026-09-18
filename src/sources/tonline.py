from __future__ import annotations

from datetime import datetime
from typing import Callable

from src.feeds import Article, fetch_articles
from src.tonline import is_dpa_exclusive


def make_fetch(feed_url: str) -> Callable[[datetime], list[Article]]:
    """Fetch-Factory fuer source_type: t_online_dpa - feed_url kommt aus der
    YAML (config/outlets.yaml), hier nur die wiederverwendbare Filterlogik."""

    def fetch(since: datetime) -> list[Article]:
        articles = fetch_articles(feed_url)
        result = []
        for article in articles:
            if article.published and article.published >= since:
                # Nur fuer Kandidaten im Freshness-Fenster lohnt sich der teure
                # Seiten-Check pro Artikel - alles ausserhalb wird UNGEFILTERT
                # durchgereicht (nicht verworfen!), weil main.py's Erstlauf-Logik
                # den kompletten Feed-Inhalt braucht, um einen neuen Outlet einmalig
                # komplett als "gesehen" zu markieren. Alte Artikel fallen dort
                # ohnehin ueber den zentralen Freshness-/Dedup-Check raus, nicht
                # weil wir sie hier schon rausgefiltert haetten.
                if is_dpa_exclusive(article.link):
                    result.append(article)
            else:
                result.append(article)
        return result

    return fetch
