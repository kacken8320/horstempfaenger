from __future__ import annotations

import logging
import re
from dataclasses import dataclass

import requests

from src.feeds import REQUEST_HEADERS
from src.textutils import strip_html

logger = logging.getLogger(__name__)

# Anders als reuters.com hat afp.com keinen Bot-Schutz (kein DataDome, kein
# Hinweis in der robots.txt gegen automatisierte Sammlung) - echtes Scraping
# des Artikel-Bodys ist hier moeglich. Der Fliesstext steckt im
# "afp-story-page__body"-Div, direkt danach kommt (im gleichen HTML) noch ein
# "Latest stories"-Widget - da der Body selbst keine verschachtelten <div>
# enthaelt, reicht ein non-greedy Match bis zum naechsten </div>.
_BODY_RE = re.compile(r'afp-story-page__body">(.*?)</div>', re.DOTALL)

# Jeder Artikel traegt direkt im Header (vor dem <h1>) genau einen Kategorie-
# Tag (z.B. "Sports", "Business and Economy", "Digital World", "Middle East").
# Achtung: derselbe CSS-Klassenname "afp-homepage-tag" taucht weiter unten im
# "Latest stories"-Widget nochmal auf (fuer ANDERE Artikel) - deshalb explizit
# an "afp-story-page__header" verankert, nicht einfach das erste Vorkommen im
# ganzen Dokument nehmen.
_CATEGORY_RE = re.compile(
    r'afp-story-page__header">\s*<span class="afp-homepage-tag[^"]*">([^<]+)</span>'
)


@dataclass
class AfpArticle:
    body: str
    category: str | None


def fetch_article(article_url: str) -> AfpArticle:
    """Liefert Fliesstext + Kategorie eines afp.com-Artikels (leer/None bei Fehler)."""
    try:
        resp = requests.get(article_url, headers=REQUEST_HEADERS, timeout=15)
        resp.raise_for_status()
    except requests.RequestException as exc:
        logger.warning("AFP-Artikelseite nicht abrufbar: %s (%s)", article_url, exc)
        return AfpArticle(body="", category=None)

    body_match = _BODY_RE.search(resp.text)
    if not body_match:
        logger.warning("Kein Artikel-Body auf AFP-Seite gefunden: %s", article_url)

    category_match = _CATEGORY_RE.search(resp.text)

    return AfpArticle(
        body=strip_html(body_match.group(1)) if body_match else "",
        category=category_match.group(1).strip() if category_match else None,
    )
