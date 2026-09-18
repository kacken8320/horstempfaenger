from __future__ import annotations

import json
import logging
import re
from datetime import datetime
from typing import Callable
from urllib.parse import quote, urlparse

import requests

from src.feeds import REQUEST_HEADERS, Article, fetch_articles
from src.textutils import strip_source_suffix

logger = logging.getLogger(__name__)

# Reuters selbst blockt jeden automatisierten Zugriff (DataDome-Challenge, 401
# auf jede Seite) und ihre robots.txt untersagt "Collection of content, data
# and/or information from reuters.com through automated means" explizit ohne
# schriftliche Erlaubnis -> kein direkter Abruf/Scraping von reuters.com,
# das waere ein Bot-Detection-Bypass. Workaround bleibt Google News RSS
# (site:reuters.com), aber zusaetzlich decodieren wir Googles eigenen
# (undokumentierten, nicht bot-geschuetzten) Redirect-Mechanismus, um an die
# ECHTE reuters.com-URL zu kommen - daraus ziehen wir die Kategorie aus dem
# URL-Pfad (z.B. /world/, /business/, /technology/) fuers Topic-Filtering.
# Ein Artikel-Intro/Body-Text ist damit NICHT moeglich (der kommt nur von
# reuters.com selbst) - Summary bleibt leer.
_ARTICLE_ID_RE = re.compile(r"/articles/([^/?]+)")
_SIG_RE = re.compile(r'data-n-a-sg="([^"]*)"')
_TS_RE = re.compile(r'data-n-a-ts="([^"]*)"')

# politics/geopolitics/wars -> world, economics/finance -> business/markets,
# tech -> technology. Bewusst kein sports/lifestyle/entertainment/breakingviews.
ALLOWED_CATEGORIES = {"world", "business", "markets", "technology"}


def _decode_real_url(google_link: str) -> str | None:
    match = _ARTICLE_ID_RE.search(google_link)
    if not match:
        return None
    article_id = match.group(1)

    try:
        resp = requests.get(
            f"https://news.google.com/rss/articles/{article_id}",
            headers=REQUEST_HEADERS,
            # ohne Consent-Cookie liefert Google aus EU-IP-Raeumen (z.B.
            # Railway/Docker-Hosts) eine Consent-Wall statt der Artikelseite -
            # Cookie-Werte sind Googles eigene, seit Jahren stabile Bypass-Werte.
            cookies={"CONSENT": "YES+1", "SOCS": "CAI"},
            timeout=15,
        )
        resp.raise_for_status()
    except requests.RequestException as exc:
        logger.warning("Google-News-Artikelseite nicht abrufbar: %s (%s)", google_link, exc)
        return None

    sig_match = _SIG_RE.search(resp.text)
    ts_match = _TS_RE.search(resp.text)
    if not sig_match or not ts_match:
        logger.warning("Keine Decode-Signatur auf Google-News-Seite gefunden: %s", google_link)
        return None

    # Format eines internen, undokumentierten Google-News-Endpunkts
    # (batchexecute/Fbv4je "garturlreq") - liefert die vom Publisher signierte
    # Ziel-URL zurueck, ohne dass reuters.com selbst angefragt wird.
    inner = json.dumps([
        "garturlreq",
        [["X", "X", ["X", "X"], None, None, 1, 1, "US:en", None, 1,
          None, None, None, None, None, 0, 1],
         "X", "X", 1, [1, 1, 1], 1, 1, None, 0, 0, None, 0],
        article_id, ts_match.group(1), sig_match.group(1),
    ])
    body = "f.req=" + quote(json.dumps([[["Fbv4je", inner, None, "generic"]]], separators=(",", ":")))

    try:
        resp = requests.post(
            "https://news.google.com/_/DotsSplashUi/data/batchexecute",
            headers={**REQUEST_HEADERS, "Content-Type": "application/x-www-form-urlencoded;charset=UTF-8"},
            data=body,
            timeout=15,
        )
        resp.raise_for_status()
    except requests.RequestException as exc:
        logger.warning("Google-News-Decode fehlgeschlagen: %s (%s)", google_link, exc)
        return None

    try:
        line = resp.text.splitlines()[2]
        outer = json.loads(line)
        inner_json = json.loads(outer[0][2])
        return inner_json[1]
    except (IndexError, ValueError, TypeError):
        logger.warning("Google-News-Decode-Antwort nicht lesbar: %s", google_link)
        return None


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
                real_url = _decode_real_url(article.link)
                if not real_url or _category_of(real_url) not in ALLOWED_CATEGORIES:
                    continue
                article.link = real_url

            result.append(article)
        return result

    return fetch
