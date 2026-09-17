from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

import yaml
from dotenv import load_dotenv

ROOT_DIR = Path(__file__).resolve().parent.parent
CONFIG_DIR = ROOT_DIR / "config"
DATA_DIR = ROOT_DIR / "data"


@dataclass
class Outlet:
    name: str
    tier: str
    country: dict[str, str]
    ausrichtung: dict[str, str]
    feed_url: str | None
    active: bool
    source_type: str = "official"
    feed_language: str | None = None
    google_news_source: str | None = None

    def country_for(self, language: str) -> str:
        return self.country.get(language, self.country["en"])

    def ausrichtung_for(self, language: str) -> str:
        return self.ausrichtung.get(language, self.ausrichtung["en"])


@dataclass
class Settings:
    poll_interval_seconds: int
    initial_backfill: bool
    initial_backfill_sample: int
    content_max_chars: int
    discord_min_interval_seconds: float
    discord_webhook_url: str


def load_outlets(path: Path = CONFIG_DIR / "outlets.yaml") -> list[Outlet]:
    with open(path, encoding="utf-8") as f:
        raw = yaml.safe_load(f) or {}

    outlets = []
    for entry in raw.get("outlets", []):
        outlets.append(
            Outlet(
                name=entry["name"],
                tier=entry["tier"],
                country=entry["country"],
                ausrichtung=entry["ausrichtung"],
                feed_url=entry.get("feed_url"),
                active=bool(entry.get("active", False)) and bool(entry.get("feed_url")),
                source_type=entry.get("source_type", "official"),
                feed_language=entry.get("feed_language"),
                google_news_source=entry.get("google_news_source"),
            )
        )

    return outlets


def load_settings(path: Path = CONFIG_DIR / "settings.yaml") -> Settings:
    load_dotenv(ROOT_DIR / ".env")

    with open(path, encoding="utf-8") as f:
        raw = yaml.safe_load(f) or {}

    webhook_url = os.environ.get("DISCORD_WEBHOOK_URL", "").strip()
    if not webhook_url:
        raise RuntimeError(
            "DISCORD_WEBHOOK_URL ist nicht gesetzt. Trag sie in .env ein "
            "(siehe .env.example)."
        )

    return Settings(
        poll_interval_seconds=int(raw.get("poll_interval_seconds", 300)),
        initial_backfill=bool(raw.get("initial_backfill", False)),
        initial_backfill_sample=int(raw.get("initial_backfill_sample", 0)),
        content_max_chars=int(raw.get("content_max_chars", 500)),
        discord_min_interval_seconds=float(raw.get("discord_min_interval_seconds", 1.0)),
        discord_webhook_url=webhook_url,
    )
