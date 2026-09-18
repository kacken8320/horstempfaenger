"""CLI: fragt Sources bestimmter Tiers JETZT live ab und zeigt alles, was in
den letzten N Stunden erschienen ist - mit den gleichen inhaltlichen Filtern
wie im echten Betrieb (Sprache zentral hier, alles Quellenspezifische wie
z.B. t-onlines dpa-Check in der jeweiligen Source selbst), aber ohne
Dedup/State - reines Live-Vorschau-Lesen, unabhaengig von data/state.db (die
lokal sowieso leer ist, solange der Bot nicht dauerhaft lokal laeuft).

Aufruf (im Container, z.B. via docker compose run):
    python -m src.query T0 T2
    python -m src.query T0 T2 --hours 6
"""

from __future__ import annotations

import argparse
import re
import sys
from datetime import datetime, timedelta, timezone

from src.discord import DISPLAY_TZ
from src.feeds import Article
from src.lang import ALLOWED_LANGUAGES, detect_language
from src.main import load_all_sources
from src.sources.base import Source
from src.textutils import clean_author, strip_html

_TIER_RE = re.compile(r"^t(?:ier)?\s*(\d+)$", re.IGNORECASE)


def _normalize_tier(raw: str) -> str:
    match = _TIER_RE.match(raw.strip())
    if not match:
        raise ValueError(f"Ungueltiges Tier-Format: {raw!r} (erwartet z.B. 'T0' oder 'Tier 0')")
    return f"Tier {int(match.group(1))}"


def _fetch_recent(source: Source, since: datetime) -> list[Article]:
    try:
        articles = source.fetch(since)
    except Exception as exc:
        print(f"  [Fehler beim Abrufen von {source.name}: {exc}]")
        return []

    for article in articles:
        article.author = clean_author(article.author)

    results = []
    for article in sorted(articles, key=lambda a: a.published or since, reverse=True):
        if article.published is None or article.published < since:
            continue

        if source.feed_language:
            language = source.feed_language
        else:
            language = detect_language(f"{article.title} {strip_html(article.summary)}")
        if language not in ALLOWED_LANGUAGES:
            continue

        results.append(article)
    return results


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("tiers", nargs="+", help="Tiers, z.B. T0 T2 oder 'Tier 0' 'Tier 2'")
    parser.add_argument("--hours", type=float, default=24.0, help="Zeitfenster in Stunden (default: 24)")
    args = parser.parse_args(argv)

    try:
        tiers = [_normalize_tier(t) for t in args.tiers]
    except ValueError as exc:
        print(f"Fehler: {exc}", file=sys.stderr)
        return 1

    since = datetime.now(timezone.utc) - timedelta(hours=args.hours)
    sources = [s for s in load_all_sources() if s.tier in tiers]

    if not sources:
        print(f"Keine aktiven Sources in {', '.join(tiers)}.")
        return 0

    print(f"Frage {len(sources)} Source(n) live ab ({', '.join(tiers)}, letzte {args.hours:g}h)...\n")

    total = 0
    for source in sources:
        for article in _fetch_recent(source, since):
            total += 1
            local_time = article.published.astimezone(DISPLAY_TZ).strftime("%d.%m.%Y %H:%M")
            print(f"[{source.tier}] {source.name} - {local_time}")
            print(f"  {article.title}")
            if article.link:
                print(f"  {article.link}")
            print()

    if total == 0:
        print(f"Nichts gefunden in {', '.join(tiers)} in den letzten {args.hours:g}h.")
    else:
        print(f"{total} Artikel gesamt.")

    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
