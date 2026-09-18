from __future__ import annotations

import logging
import time
from zoneinfo import ZoneInfo

import requests

from src.feeds import Article
from src.sources.base import Source
from src.textutils import parenthesize_first_clause, strip_html, truncate

logger = logging.getLogger(__name__)

# Artikel-Zeitstempel kommen als UTC aus dem Feed (siehe feeds.py), fuer die
# Anzeige aber auf Ortszeit umrechnen statt rohes UTC zu zeigen.
DISPLAY_TZ = ZoneInfo("Europe/Berlin")

TIER_COLORS = {
    "Tier 0": 0xF1C40F,  # gold
    "Tier 1": 0xE67E22,  # orange
    "Tier 2": 0x3498DB,  # blue
    "Tier 3": 0x95A5A6,  # grey
    "Tier 4": 0x7F8C8D,  # dark grey
}
DEFAULT_COLOR = 0x2C3E50

TIER_DESCRIPTIONS = {
    "de": {
        "Tier 0": "beste verfügbare Quelle",
        "Tier 1": "sehr verlässliche Quelle",
        "Tier 2": "sehr verlässliche Quelle",
        "Tier 3": "verlässliche Quelle",
        "Tier 4": "my mom told me",
    },
    "en": {
        "Tier 0": "best available source",
        "Tier 1": "very reliable source",
        "Tier 2": "very reliable source",
        "Tier 3": "reliable source",
        "Tier 4": "my mom told me",
    },
}

LABELS = {
    "de": {
        "unknown_date": "unbekannt",
        "no_title": "(ohne Titel)",
        "date_format": "%d.%m.%Y %H:%M",
    },
    "en": {
        "unknown_date": "unknown",
        "no_title": "(no title)",
        "date_format": "%d.%m.%Y %H:%M",
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

    def post_article(self, source: Source, article: Article, content_max_chars: int, language: str) -> bool:
        labels = LABELS.get(language, LABELS["en"])
        tier_description = TIER_DESCRIPTIONS.get(language, TIER_DESCRIPTIONS["en"]).get(source.tier, "")

        date_str = (
            article.published.astimezone(DISPLAY_TZ).strftime(labels["date_format"])
            if article.published
            else labels["unknown_date"]
        )
        date_line = f"{date_str} - {article.author}" if article.author else date_str
        summary = truncate(strip_html(article.summary), content_max_chars)
        if summary.strip().lower() == article.title.strip().lower():
            # Manche Feeds (z.B. Kyodo "BREAKING NEWS:"-Alerts) liefern als
            # "summary" nur den Titel nochmal - keine echte Zusatzinfo.
            summary = ""

        header = "\n".join(
            [
                f"{source.tier} ({tier_description})",
                f"{source.flag} {source.name} {parenthesize_first_clause(source.ausrichtung_for(language))}".strip(),
                date_line,
            ]
        )
        description = f"{header}\n\n{summary}" if summary else header

        embed = {
            "title": truncate(article.title, 256) or labels["no_title"],
            "url": article.link or None,
            "description": description,
            "color": TIER_COLORS.get(source.tier, DEFAULT_COLOR),
        }

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
