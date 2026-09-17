from __future__ import annotations

import re

_TAG_RE = re.compile(r"<[^>]+>")


def strip_html(text: str) -> str:
    return re.sub(r"\s+", " ", _TAG_RE.sub("", text)).strip()


def truncate(text: str, max_chars: int) -> str:
    if len(text) <= max_chars:
        return text
    return text[: max_chars - 1].rstrip() + "…"


def strip_source_suffix(title: str, outlet_name: str) -> str:
    """Google News haengt an Titel ' - <Outlet>' an - das entfernen wir wieder."""
    suffix = f" - {outlet_name}"
    if title.endswith(suffix):
        return title[: -len(suffix)].rstrip()
    return title
