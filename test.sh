#!/usr/bin/env bash
# Lokaler Live-Check: fragt Outlets bestimmter Tiers JETZT live ab (siehe
# src/query.py). Ohne Argumente: T0, letzte 24h.
#
# Beispiele:
#   ./test.sh                  -> T0, letzte 24h
#   ./test.sh T0 T2            -> T0 + T2, letzte 24h
#   ./test.sh T0 --hours 6     -> T0, letzte 6h

set -euo pipefail
cd "$(dirname "$0")"

if [ ! -f .env ]; then
    echo "(.env fehlt, lege leere Datei an - docker-compose braucht sie, query.py selbst nicht)"
    touch .env
fi

if [ "$#" -eq 0 ]; then
    set -- T0 --hours 24
fi

docker compose run --rm rss-scraper python -m src.query "$@"
