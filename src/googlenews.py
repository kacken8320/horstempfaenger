from __future__ import annotations

import json
import logging
import re
from urllib.parse import quote

import requests

from src.feeds import REQUEST_HEADERS

logger = logging.getLogger(__name__)

# Google-News-RSS-<link>-Eintraege sind obfuskierte Redirect-Links, keine
# echten Publisher-URLs. decode_real_url() loest das ueber Googles eigenen
# (undokumentierten, nicht bot-geschuetzten) Redirect-Mechanismus auf - das
# ist kein Zugriff auf die Publisher-Seite selbst, sondern nur ein Aufloesen
# von Googles eigenem Link-Format. Wiederverwendet von mehreren Sources
# (Reuters, AFP), die jeweils via Google News RSS entdeckt werden.
_ARTICLE_ID_RE = re.compile(r"/articles/([^/?]+)")
_SIG_RE = re.compile(r'data-n-a-sg="([^"]*)"')
_TS_RE = re.compile(r'data-n-a-ts="([^"]*)"')


def decode_real_url(google_link: str) -> str | None:
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
    # Ziel-URL zurueck, ohne dass die Publisher-Seite selbst angefragt wird.
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
