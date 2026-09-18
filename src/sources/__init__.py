from __future__ import annotations

from datetime import datetime
from typing import Callable

from src.feeds import Article
from src.sources import tonline

# Registry fuer source_type-Werte, die eigene (nicht-generische) Fetch-Logik
# brauchen - Wert ist eine Factory, die die feed_url aus der YAML entgegennimmt
# und eine fetch(since)-Funktion zurueckgibt. Neues Outlet mit Sonderlogik
# (z.B. spaeter Scraping) -> eigenes Modul hier + Eintrag in dieser Registry,
# Eigenschaften (Name/Tier/Flag/Ausrichtung/feed_url/active) bleiben in der
# YAML - siehe main.py:_source_from_outlet.
CUSTOM_FETCHERS: dict[str, Callable[[str], Callable[[datetime], list[Article]]]] = {
    "t_online_dpa": tonline.make_fetch,
}
