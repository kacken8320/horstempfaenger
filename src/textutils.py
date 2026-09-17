from __future__ import annotations

import re

_TAG_RE = re.compile(r"<[^>]+>")
_ANCHOR_RE = re.compile(r"<a\b[^>]*>.*?</a>", re.IGNORECASE | re.DOTALL)


def strip_html(text: str) -> str:
    # <a>...</a> komplett raus (typisch "Read full story here"/"Continue
    # reading"-Boilerplate, die eigentliche URL steht eh separat im Feld).
    text = _ANCHOR_RE.sub(" ", text)
    # Tags durch Leerzeichen statt "" ersetzen, sonst kleben Woerter ueber
    # Tag-Grenzen (z.B. "</p><a>") aneinander.
    return re.sub(r"\s+", " ", _TAG_RE.sub(" ", text)).strip()


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


def parenthesize_first_clause(text: str) -> str:
    """"Wire service, factual/neutral" -> "(Wire service), factual/neutral"."""
    head, sep, rest = text.partition(",")
    if not sep:
        return f"({text})"
    return f"({head}){sep}{rest}"
