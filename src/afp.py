from __future__ import annotations

import logging
import re

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


def fetch_body(article_url: str) -> str:
    """Liefert den reinen Fliesstext eines afp.com-Artikels, oder "" bei Fehler."""
    try:
        resp = requests.get(article_url, headers=REQUEST_HEADERS, timeout=15)
        resp.raise_for_status()
    except requests.RequestException as exc:
        logger.warning("AFP-Artikelseite nicht abrufbar: %s (%s)", article_url, exc)
        return ""

    match = _BODY_RE.search(resp.text)
    if not match:
        logger.warning("Kein Artikel-Body auf AFP-Seite gefunden: %s", article_url)
        return ""

    return strip_html(match.group(1))
