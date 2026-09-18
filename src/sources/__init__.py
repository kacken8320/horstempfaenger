from __future__ import annotations

from src.sources.base import Source
from src.sources.tonline import SOURCES as _TONLINE_SOURCES

# Explizite Registry statt Auto-Discovery - bei einer Handvoll Outlets simpler
# und expliziter als pkgutil-Scanning. Neues Outlet-Modul -> hier eintragen.
_ALL_SOURCES: list[Source] = [
    *_TONLINE_SOURCES,
]


def load_sources() -> list[Source]:
    return list(_ALL_SOURCES)
