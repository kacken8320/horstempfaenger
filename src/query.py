"""CLI: zeigt, was in den letzten N Stunden in bestimmten Tiers gepostet wurde.

Nur fuer lokale Tests gedacht - liest die lokale data/state.db (Docker-
Compose-Bind-Mount), NICHT die Live-Daten vom tatsaechlichen Railway-Deploy.

Aufruf (im Container, z.B. via docker compose run):
    python -m src.query T0 T2
    python -m src.query T0 T2 --hours 6
"""

from __future__ import annotations

import argparse
import re
import sys
from datetime import datetime, timedelta, timezone

from src.config import DATA_DIR
from src.state import StateStore

_TIER_RE = re.compile(r"^t(?:ier)?\s*(\d+)$", re.IGNORECASE)


def _normalize_tier(raw: str) -> str:
    match = _TIER_RE.match(raw.strip())
    if not match:
        raise ValueError(f"Ungueltiges Tier-Format: {raw!r} (erwartet z.B. 'T0' oder 'Tier 0')")
    return f"Tier {int(match.group(1))}"


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("tiers", nargs="+", help="Tiers, z.B. T0 T2 oder 'Tier 0' 'Tier 2'")
    parser.add_argument("--hours", type=float, default=2.0, help="Zeitfenster in Stunden (default: 2)")
    args = parser.parse_args(argv)

    try:
        tiers = [_normalize_tier(t) for t in args.tiers]
    except ValueError as exc:
        print(f"Fehler: {exc}", file=sys.stderr)
        return 1

    since = datetime.now(timezone.utc) - timedelta(hours=args.hours)
    since_str = since.strftime("%Y-%m-%d %H:%M:%S")

    state = StateStore(DATA_DIR / "state.db")
    try:
        rows = state.recent_posted(tiers, since_str)
    finally:
        state.close()

    if not rows:
        print(f"Nichts gepostet in {', '.join(tiers)} seit {args.hours:g}h.")
        return 0

    print(f"{len(rows)} Artikel in {', '.join(tiers)} seit {args.hours:g}h:\n")
    for row in rows:
        print(f"[{row['tier']}] {row['outlet']} - {row['seen_at']} UTC")
        print(f"  {row['title']}")
        if row["link"]:
            print(f"  {row['link']}")
        print()

    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
