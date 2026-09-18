from __future__ import annotations

import logging
import re

import requests

from src.feeds import REQUEST_HEADERS

logger = logging.getLogger(__name__)

# t-online verrät die tatsaechliche Quelle (dpa vs. eigene Redaktion vs. Mix)
# nicht im RSS-Feed - das dc:creator-Feld dort ist immer der t-online-Redakteur,
# der den Artikel eingestellt hat, nicht die Agentur. Die echte Quellenangabe
# ("agencies": [...]) steckt nur im eingebetteten Next.js-Page-JSON der vollen
# Artikelseite (undokumentiert, kann sich jederzeit aendern). Beispiele:
#   ["dpa"]                 -> reine dpa-Meldung
#   ["dpa-afx"]              -> reine dpa-afx-Meldung (dpas Wirtschafts-Wire)
#   ["dpa-afx", "t-online"]  -> von t-online redaktionell bearbeitete dpa-Meldung
#   []                       -> komplett eigene t-online-Redaktion, keine Agentur
_AGENCIES_RE = re.compile(r'"agencies":\[([^\]]*)\]')


def is_dpa_exclusive(article_url: str) -> bool:
    """True nur, wenn t-online als Quelle AUSSCHLIESSLICH dpa/dpa-afx angibt,
    ohne redaktionelle Mitbearbeitung (kein 't-online' o.ae. mit in der Liste)."""
    try:
        resp = requests.get(article_url, headers=REQUEST_HEADERS, timeout=15)
        resp.raise_for_status()
    except requests.RequestException as exc:
        logger.warning("t-online-Artikelseite nicht abrufbar: %s (%s)", article_url, exc)
        return False

    match = _AGENCIES_RE.search(resp.text)
    if not match:
        logger.warning("Kein agencies-Feld auf t-online-Artikelseite gefunden: %s", article_url)
        return False

    agencies = re.findall(r'"([^"]+)"', match.group(1))
    return bool(agencies) and all(a.lower().startswith("dpa") for a in agencies)
