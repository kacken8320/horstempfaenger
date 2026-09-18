"""CLI: fragt Outlets bestimmter Tiers JETZT live ab und zeigt alles, was in
den letzten N Stunden erschienen ist - mit den gleichen inhaltlichen Filtern
wie im echten Betrieb (Sprache, bei t-online der dpa-Check), aber ohne
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

from src.config import Outlet, load_outlets
from src.discord import DISPLAY_TZ
from src.feeds import Article, fetch_articles
from src.lang import ALLOWED_LANGUAGES, detect_language
from src.textutils import clean_author, strip_html, strip_source_suffix
from src.tonline import is_dpa_exclusive

_TIER_RE = re.compile(r"^t(?:ier)?\s*(\d+)$", re.IGNORECASE)


def _normalize_tier(raw: str) -> str:
    match = _TIER_RE.match(raw.strip())
    if not match:
        raise ValueError(f"Ungueltiges Tier-Format: {raw!r} (erwartet z.B. 'T0' oder 'Tier 0')")
    return f"Tier {int(match.group(1))}"


def _fetch_recent(outlet: Outlet, since: datetime) -> list[Article]:
    try:
        articles = fetch_articles(outlet.feed_url)
    except Exception as exc:
        print(f"  [Fehler beim Abrufen von {outlet.name}: {exc}]")
        return []

    for article in articles:
        article.author = clean_author(article.author)

    if outlet.source_type == "google_news":
        expected_source = (outlet.google_news_source or outlet.name).lower()
        matched = []
        for article in articles:
            if (article.source_title or "").lower() != expected_source:
                continue
            article.title = strip_source_suffix(article.title, article.source_title)
            matched.append(article)
        articles = matched

    results = []
    for article in sorted(articles, key=lambda a: a.published or since, reverse=True):
        if article.published is None or article.published < since:
            continue

        if outlet.feed_language:
            language = outlet.feed_language
        else:
            language = detect_language(f"{article.title} {strip_html(article.summary)}")
        if language not in ALLOWED_LANGUAGES:
            continue

        if outlet.source_type == "t_online_dpa" and not is_dpa_exclusive(article.link):
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
    outlets = [o for o in load_outlets() if o.active and o.tier in tiers]

    if not outlets:
        print(f"Keine aktiven Outlets in {', '.join(tiers)}.")
        return 0

    print(f"Frage {len(outlets)} Outlet(s) live ab ({', '.join(tiers)}, letzte {args.hours:g}h)...\n")

    total = 0
    for outlet in outlets:
        for article in _fetch_recent(outlet, since):
            total += 1
            local_time = article.published.astimezone(DISPLAY_TZ).strftime("%d.%m.%Y %H:%M")
            print(f"[{outlet.tier}] {outlet.name} - {local_time}")
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
