from __future__ import annotations

import logging
import time

import requests

from src.config import Outlet
from src.feeds import Article
from src.textutils import strip_html, truncate

logger = logging.getLogger(__name__)

TIER_COLORS = {
    "T1": 0xE67E22,  # orange
    "T2": 0x3498DB,  # blue
    "T3": 0x95A5A6,  # grey
    "T4": 0x7F8C8D,  # dark grey
}
DEFAULT_COLOR = 0x2C3E50

LABELS = {
    "de": {
        "tier": "Tier",
        "outlet": "Outlet",
        "country": "Land",
        "ausrichtung": "Grobe Ausrichtung",
        "author": "Autor",
        "date": "Datum",
        "further_reading": "Weiterlesen",
        "no_summary": "(keine Zusammenfassung verfügbar)",
        "unknown_author": "unbekannt",
        "unknown_date": "unbekannt",
        "no_title": "(ohne Titel)",
        "date_format": "%d.%m.%Y %H:%M UTC",
    },
    "en": {
        "tier": "Tier",
        "outlet": "Outlet",
        "country": "Country",
        "ausrichtung": "Rough Orientation",
        "author": "Author",
        "date": "Date",
        "further_reading": "Further reading",
        "no_summary": "(no summary available)",
        "unknown_author": "unknown",
        "unknown_date": "unknown",
        "no_title": "(no title)",
        "date_format": "%Y-%m-%d %H:%M UTC",
    },
}


class DiscordPoster:
    def __init__(self, webhook_url: str, min_interval_seconds: float = 1.0):
        self._webhook_url = webhook_url
        self._min_interval = min_interval_seconds
        self._last_sent = 0.0

    def _throttle(self) -> None:
        elapsed = time.monotonic() - self._last_sent
        wait = self._min_interval - elapsed
        if wait > 0:
            time.sleep(wait)

    def post_article(self, outlet: Outlet, article: Article, content_max_chars: int, language: str) -> bool:
        labels = LABELS.get(language, LABELS["en"])

        date_str = (
            article.published.strftime(labels["date_format"])
            if article.published
            else labels["unknown_date"]
        )
        summary = truncate(strip_html(article.summary), content_max_chars) or labels["no_summary"]

        embed = {
            "title": truncate(article.title, 256) or labels["no_title"],
            "url": article.link or None,
            "description": summary,
            "color": TIER_COLORS.get(outlet.tier, DEFAULT_COLOR),
            "fields": [
                {"name": labels["tier"], "value": outlet.tier, "inline": True},
                {"name": labels["outlet"], "value": outlet.name, "inline": True},
                {"name": labels["country"], "value": outlet.country_for(language), "inline": True},
                {"name": labels["ausrichtung"], "value": outlet.ausrichtung_for(language), "inline": False},
                {"name": labels["author"], "value": article.author or labels["unknown_author"], "inline": True},
                {"name": labels["date"], "value": date_str, "inline": True},
            ],
        }
        if article.link:
            embed["fields"].append(
                {"name": labels["further_reading"], "value": article.link, "inline": False}
            )

        payload = {"embeds": [embed]}
        return self._send(payload)

    def _send(self, payload: dict) -> bool:
        self._throttle()
        try:
            resp = requests.post(self._webhook_url, json=payload, timeout=10)
        except requests.RequestException as exc:
            logger.error("Discord-Post fehlgeschlagen: %s", exc)
            return False
        finally:
            self._last_sent = time.monotonic()

        if resp.status_code == 429:
            retry_after = resp.json().get("retry_after", 1.0)
            logger.warning("Rate-limited von Discord, warte %.2fs", retry_after)
            time.sleep(float(retry_after))
            return self._send(payload)

        if not resp.ok:
            logger.error("Discord-Post fehlgeschlagen: %s %s", resp.status_code, resp.text)
            return False

        return True
