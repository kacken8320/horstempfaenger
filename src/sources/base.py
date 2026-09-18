from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Callable

from src.feeds import Article


@dataclass
class Source:
    """Eine Nachrichtenquelle, komplett eigenverantwortlich fuer das Holen
    ihrer Artikel (heute per RSS, spaeter ggf. per Scraping) inkl. aller
    quellenspezifischen Filter (Themen-Scoping, Quellen-Checks etc.). Der Rest
    der Pipeline (Dedup, Freshness, Sprache, Tier-Cap, Posten) bleibt zentral
    in main.py und behandelt jede Source gleich.

    fetch(since) bekommt den Freshness-Cutoff mit, damit teure Checks (z.B.
    ein extra Seitenaufruf pro Artikel) nur fuer Artikel laufen, die dieses
    Fenster ueberhaupt treffen - nicht fuer den kompletten Feed-Inhalt.
    """

    name: str
    tier: str
    flag: str
    country: dict[str, str]
    ausrichtung: dict[str, str]
    fetch: Callable[[datetime], list[Article]]
    feed_language: str | None = None

    def country_for(self, language: str) -> str:
        return self.country.get(language, self.country["en"])

    def ausrichtung_for(self, language: str) -> str:
        return self.ausrichtung.get(language, self.ausrichtung["en"])
