from __future__ import annotations

from datetime import datetime

from src.feeds import Article, fetch_articles
from src.sources.base import Source
from src.tonline import is_dpa_exclusive

_COUNTRY = {"de": "Deutschland", "en": "Germany"}
_AUSRICHTUNG = {
    "de": "dpa-Meldung, weitergeleitet via t-online, sachlich/neutral",
    "en": "dpa wire content, relayed via t-online, factual/neutral",
}


def _fetch_dpa_only(feed_url: str, since: datetime) -> list[Article]:
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


def _fetch_politik(since: datetime) -> list[Article]:
    # Politik + Ausland/Geopolitik - keine eigene "Geopolitik"-Rubrik bei
    # t-online, internationale Politik (Krieg, Diplomatie etc.) laeuft hier mit.
    return _fetch_dpa_only("https://www.t-online.de/nachrichten/feed.rss", since)


def _fetch_wirtschaft(since: datetime) -> list[Article]:
    return _fetch_dpa_only("https://www.t-online.de/finanzen/feed.rss", since)


def _fetch_technik(since: datetime) -> list[Article]:
    # Bewusst /digital/aktuelles statt /digital/feed.rss - letzteres mischt
    # Gaming-Reviews, Smartphone-/Hardware-Howtos etc. mit rein, hier nicht
    # gewuenscht ("technik, nicht digital").
    return _fetch_dpa_only("https://www.t-online.de/digital/aktuelles/feed.rss", since)


SOURCES = [
    Source(
        name="t-online (Politik/Geopolitik)",
        tier="Tier 0",
        flag="🇩🇪",
        country=_COUNTRY,
        ausrichtung=_AUSRICHTUNG,
        fetch=_fetch_politik,
    ),
    Source(
        name="t-online (Wirtschaft/Finanzen)",
        tier="Tier 0",
        flag="🇩🇪",
        country=_COUNTRY,
        ausrichtung=_AUSRICHTUNG,
        fetch=_fetch_wirtschaft,
    ),
    Source(
        name="t-online (Technik)",
        tier="Tier 0",
        flag="🇩🇪",
        country=_COUNTRY,
        ausrichtung=_AUSRICHTUNG,
        fetch=_fetch_technik,
    ),
]
