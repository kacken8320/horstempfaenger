from __future__ import annotations

import logging
import time
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from src.config import DATA_DIR, load_outlets, load_settings
from src.discord import DiscordPoster
from src.feeds import fetch_articles
from src.lang import ALLOWED_LANGUAGES, detect_language
from src.state import StateStore
from src.textutils import clean_author, strip_html, strip_source_suffix

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger("main")

EPOCH = datetime.min.replace(tzinfo=timezone.utc)


def run_cycle(outlets, state: StateStore, poster: DiscordPoster, settings) -> None:
    active_outlets = [o for o in outlets if o.active]
    if not active_outlets:
        logger.warning("Kein aktives Outlet mit gesetzter feed_url - nichts zu tun.")
        return

    logger.info("Zyklus startet fuer: %s", ", ".join(o.name for o in active_outlets))

    for outlet in active_outlets:
        try:
            articles = fetch_articles(outlet.feed_url)
        except Exception:
            logger.exception("Fehler beim Abrufen von %s", outlet.name)
            continue

        for article in articles:
            article.author = clean_author(article.author)

        if outlet.source_type == "google_news":
            # Google News liefert keinen echten Artikel-Body (nur Titel+Quellen-
            # Badge als "description") und mischt bei Textsuchen auch Treffer
            # anderer Quellen unter (z.B. "AFP" matcht auch "Americans for
            # Prosperity"). Nur Artikel behalten, deren <source> exakt zur
            # erwarteten Quelle passt, dann den " - <Quelle>"-Titelsuffix strippen.
            expected_source = (outlet.google_news_source or outlet.name).lower()
            matched = []
            for article in articles:
                if (article.source_title or "").lower() != expected_source:
                    continue
                article.title = strip_source_suffix(article.title, article.source_title)
                article.summary = ""
                matched.append(article)
            articles = matched

        first_run = not state.has_any(outlet.name)
        sample_keys = set()
        if first_run and not settings.initial_backfill:
            if settings.initial_backfill_sample > 0:
                newest_first = sorted(articles, key=lambda a: a.published or EPOCH, reverse=True)
                sample_keys = {a.key for a in newest_first[: settings.initial_backfill_sample]}
            logger.info(
                "Erster Lauf für %s: markiere %d bestehende Artikel als gesehen (%d als Test gepostet).",
                outlet.name, len(articles), len(sample_keys),
            )

        posted_count = 0
        skipped_language_count = 0
        already_known_count = 0

        for article in sorted(articles, key=lambda a: a.published or EPOCH):
            if state.is_known(outlet.name, article.key):
                already_known_count += 1
                continue

            if first_run and not settings.initial_backfill and article.key not in sample_keys:
                state.mark_seen(outlet.name, article.key, posted=False)
                continue

            if outlet.feed_language:
                # Sprache steht schon durch die Feed-Konfiguration fest (z.B. Google
                # News mit fixem hl/ceid) - Titel-only-Erkennung waere hier nur
                # unzuverlaessiges Raten auf kurzen, eigennamenlastigen Strings.
                language = outlet.feed_language
            else:
                language = detect_language(f"{article.title} {strip_html(article.summary)}")

            if language not in ALLOWED_LANGUAGES:
                logger.info("Übersprungen (Sprache '%s'): %s", language, article.title)
                state.mark_seen(outlet.name, article.key, posted=False)
                skipped_language_count += 1
                continue

            posted = poster.post_article(outlet, article, settings.content_max_chars, language)
            state.mark_seen(outlet.name, article.key, posted=posted)
            if posted:
                posted_count += 1
                logger.info("Gepostet [%s]: [%s] %s - %s", language, outlet.tier, outlet.name, article.title)

        logger.info(
            "%s: %d Artikel im Feed, %d neu gepostet, %d wegen Sprache übersprungen, %d schon bekannt.",
            outlet.name, len(articles), posted_count, skipped_language_count, already_known_count,
        )


def _next_scheduled_run(now_utc: datetime, hours: list[int], tz: ZoneInfo) -> datetime:
    """Naechster Zeitpunkt aus `hours` (lokale Stunden in `tz`), der nach
    `now_utc` liegt. `hours` muss aufsteigend sortiert sein."""
    local_now = now_utc.astimezone(tz)
    for day_offset in (0, 1):
        day = local_now.date() + timedelta(days=day_offset)
        for hour in hours:
            candidate = datetime(day.year, day.month, day.day, hour, tzinfo=tz)
            if candidate > local_now:
                return candidate.astimezone(timezone.utc)
    raise AssertionError("schedule_hours darf nicht leer sein")


def main() -> None:
    settings = load_settings()
    poster = DiscordPoster(settings.discord_webhook_url, settings.discord_min_interval_seconds)
    state = StateStore(DATA_DIR / "state.db")
    tz = ZoneInfo(settings.schedule_timezone)

    startup_outlets = load_outlets()
    active_names = [o.name for o in startup_outlets if o.active]
    logger.info(
        "Starte RSS-Scraper, feste Laufzeiten (%s): %s Uhr",
        settings.schedule_timezone,
        ", ".join(f"{h:02d}:00" for h in settings.schedule_hours),
    )
    logger.info("Aktive Outlets: %s", ", ".join(active_names) if active_names else "(keine)")
    try:
        while True:
            outlets = load_outlets()  # neu laden, damit neue feed_urls ohne Neustart greifen
            run_cycle(outlets, state, poster, settings)

            next_run = _next_scheduled_run(datetime.now(timezone.utc), settings.schedule_hours, tz)
            sleep_seconds = (next_run - datetime.now(timezone.utc)).total_seconds()
            logger.info(
                "Naechster Lauf: %s Uhr (%s)",
                next_run.astimezone(tz).strftime("%d.%m. %H:%M"),
                settings.schedule_timezone,
            )
            time.sleep(max(sleep_seconds, 0))
    except KeyboardInterrupt:
        logger.info("Beendet durch Benutzer.")
    finally:
        state.close()


if __name__ == "__main__":
    main()
