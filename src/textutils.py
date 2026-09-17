from __future__ import annotations

import html
import re

_TAG_RE = re.compile(r"<[^>]+>")
_ANCHOR_RE = re.compile(r"<a\b[^>]*>.*?</a>", re.IGNORECASE | re.DOTALL)
# WordPress haengt an RSS-Excerpts standardmaessig "The post <a>Titel</a>
# appeared first on <a>Site</a>." an (z.B. bei PA Media) - reine Feed-
# Boilerplate, kein Artikelinhalt.
_WP_APPEARED_FIRST_RE = re.compile(
    r"<p>\s*The post .*?appeared first on .*?</p>\s*$", re.IGNORECASE | re.DOTALL
)


def strip_html(text: str) -> str:
    text = _WP_APPEARED_FIRST_RE.sub("", text)
    # <a>...</a> komplett raus (typisch "Read full story here"/"Continue
    # reading"-Boilerplate, die eigentliche URL steht eh separat im Feld).
    text = _ANCHOR_RE.sub(" ", text)
    # Tags durch Leerzeichen statt "" ersetzen, sonst kleben Woerter ueber
    # Tag-Grenzen (z.B. "</p><a>") aneinander.
    text = re.sub(r"\s+", " ", _TAG_RE.sub(" ", text)).strip()
    # Manche Feeds (z.B. PA Media) liefern in CDATA-Blocks numerische
    # HTML-Entities, die feedparser nicht selbst dekodiert (CDATA ist fuer den
    # XML-Parser literaler Text) - daher hier explizit nachholen.
    return html.unescape(text)


def truncate(text: str, max_chars: int) -> str:
    if len(text) <= max_chars:
        return text
    return text[: max_chars - 1].rstrip() + "…"


def strip_source_suffix(title: str, source_name: str) -> str:
    """Google News haengt an Titel ' - <Quelle>' an - das entfernen wir wieder."""
    suffix = f" - {source_name}"
    if title.endswith(suffix):
        return title[: -len(suffix)].rstrip()
    return title


_ZEIT_CREATOR_PREFIX_RE = re.compile(r"^DIE ZEIT: [^-]*-\s*")


def clean_author(author: str) -> str:
    """Zeit haengt an dc:creator ein Ressort-Praefix an, z.B. "DIE ZEIT:
    Ausland - Ulrich Ladurner" oder "DIE ZEIT: News - " ohne Autor."""
    return _ZEIT_CREATOR_PREFIX_RE.sub("", author).strip()


def parenthesize_first_clause(text: str) -> str:
    """"Wire service, factual/neutral" -> "(Wire service), factual/neutral"."""
    head, sep, rest = text.partition(",")
    if not sep:
        return f"({text})"
    return f"({head}){sep}{rest}"
