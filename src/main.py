from __future__ import annotations

import logging
import time
from datetime import datetime, timedelta, timezone

from src.config import DATA_DIR, Outlet, load_outlets, load_settings
from src.discord import DiscordPoster
from src.feeds import Article, fetch_articles
from src.jev import JevClient, shortlist_pool
from src.lang import ALLOWED_LANGUAGES, detect_language
from src.sources import CUSTOM_FETCHERS
from src.sources.base import Source
from src.state import PoolEntry, StateStore
from src.textutils import clean_author, strip_html, strip_source_suffix

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger("main")

EPOCH = datetime.min.replace(tzinfo=timezone.utc)

# Nur Artikel posten, deren published-Datum tatsaechlich in diesem Fenster um
# "jetzt" liegt - sonst wuerden ueber die reine "kennen wir noch nicht"-Dedup
# auch mal Artikel mit x-beliebig altem Datum durchrutschen (z.B. wenn ein Feed
# einen alten Artikel neu einsortiert, oder nach einer Downtime).
MAX_ARTICLE_AGE = timedelta(minutes=5)

# Max. Anzahl Artikel, die pro Zyklus (ueber alle Outlets zusammen) gepostet
# werden - Tier 0/1 sind davon ausgenommen und kommen immer durch, zaehlen
# aber trotzdem gegen das Budget, das den niedrigeren Tiers noch bleibt.
MAX_POSTS_PER_CYCLE = 5
TIER_PRIORITY = ["Tier 0", "Tier 1", "Tier 2", "Tier 3", "Tier 4"]
ALWAYS_POST_TIERS = {"Tier 0", "Tier 1"}


def _tier_rank(tier: str) -> int:
    try:
        return TIER_PRIORITY.index(tier)
    except ValueError:
        return len(TIER_PRIORITY)


def _select_candidates(candidates: list[tuple]) -> tuple[list[tuple], list[tuple]]:
    """candidates: Liste von (source, article, language), noch nicht sortiert.
    Tier 0/1 kommen immer komplett durch (auch ueber MAX_POSTS_PER_CYCLE
    hinaus), zaehlen aber gegen das Budget fuer die restlichen Tiers - d.h. bei
    3 Tier-1 + 2 Tier-2 + 5 Tier-3-Kandidaten werden alle 3 Tier-1 und beide
    Tier-2 gepostet (macht schon 5), die 5 Tier-3 fallen komplett raus."""
    exempt = [c for c in candidates if c[0].tier in ALWAYS_POST_TIERS]
    rest = sorted(
        (c for c in candidates if c[0].tier not in ALWAYS_POST_TIERS),
        key=lambda c: (_tier_rank(c[0].tier), c[1].published or EPOCH),
    )
    budget = max(0, MAX_POSTS_PER_CYCLE - len(exempt))
    selected = exempt + rest[:budget]
    dropped = rest[budget:]
    selected.sort(key=lambda c: (_tier_rank(c[0].tier), c[1].published or EPOCH))
    return selected, dropped


# Jev-Filter (siehe readme.txt): Tiers, die den Relevanz-Check umgehen. Leer =
# gilt fuer alle Outlets.
RELEVANCE_EXEMPT_TIERS: set[str] = set()
# Pool "von heute" fuer den Duplikat-Check
POOL_WINDOW = timedelta(hours=24)
POOL_MAX_ENTRIES = 800


def _dedupe_against_pool(
    candidates: list[tuple], state: StateStore, jev: JevClient, source_stats: dict,
) -> tuple[list[tuple], dict]:
    """Verwirft Kandidaten, ueber deren Ereignis schon berichtet wurde (Pool aus
    heute gepostetem + bereits angenommenen Kandidaten dieses Zyklus). Ist die
    neue Tier hoeher als die des Pool-Treffers, kommt sie trotzdem durch und
    ersetzt den alten Eintrag. Rueckgabe: (Ueberlebende, {(outlet, key): pool_id
    des zu ersetzenden Eintrags})."""
    if not jev.enabled or not candidates:
        return candidates, {}

    since = (datetime.now(timezone.utc) - POOL_WINDOW).strftime("%Y-%m-%d %H:%M:%S")
    pool = state.pool_recent(since, POOL_MAX_ENTRIES)
    next_temp_id = -1
    supersede: dict[tuple, int] = {}
    survivors = []

    # beste Tier zuerst: bei zwei Outlets zur selben Story im selben Zyklus
    # gewinnt das hoehere, das niedrigere fliegt als Duplikat raus.
    for candidate in sorted(candidates, key=lambda c: (_tier_rank(c[0].tier), c[1].published or EPOCH)):
        source, article, _ = candidate
        match = jev.find_duplicate(article.title, shortlist_pool(article.title, pool))
        if match is not None and _tier_rank(source.tier) >= _tier_rank(match.tier):
            logger.info("Übersprungen (Duplikat von [%s] '%s'): [%s] %s",
                        match.tier, match.title, source.tier, article.title)
            state.mark_seen(
                source.name, article.key, posted=False,
                title=article.title, link=article.link, tier=source.tier,
            )
            stats = source_stats[source.name]
            stats["dropped_duplicate"] = stats.get("dropped_duplicate", 0) + 1
            continue
        if match is not None and match.id > 0:
            supersede[(source.name, article.key)] = match.id
            pool = [e for e in pool if e.id != match.id]
        survivors.append(candidate)
        pool.insert(0, PoolEntry(id=next_temp_id, title=article.title, tier=source.tier))
        next_temp_id -= 1
    return survivors, supersede


def _source_from_outlet(outlet: Outlet) -> Source:
    """Baut aus einem YAML-Outlet eine Source. Eigenschaften (Name/Tier/Flag/
    Ausrichtung/feed_url/active) kommen komplett aus der YAML - die zentrale
    Uebersicht fuer Menschen. fetch() kommt entweder generisch (official/
    google_news) oder, bei source_type mit eigener Sonderlogik (z.B.
    t_online_dpa), aus der CUSTOM_FETCHERS-Registry in src/sources/."""
    custom_factory = CUSTOM_FETCHERS.get(outlet.source_type)
    if custom_factory:
        fetch = custom_factory(outlet.feed_url)
    elif outlet.source_type == "google_news":
        def fetch(since: datetime) -> list[Article]:
            try:
                articles = fetch_articles(outlet.feed_url)
            except Exception:
                logger.exception("Fehler beim Abrufen von %s", outlet.name)
                return []

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
            return matched
    else:
        def fetch(since: datetime) -> list[Article]:
            try:
                return fetch_articles(outlet.feed_url)
            except Exception:
                logger.exception("Fehler beim Abrufen von %s", outlet.name)
                return []

    return Source(
        name=outlet.name,
        tier=outlet.tier,
        flag=outlet.flag,
        country=outlet.country,
        ausrichtung=outlet.ausrichtung,
        fetch=fetch,
        feed_language=outlet.feed_language,
    )


def load_all_sources() -> list[Source]:
    return [_source_from_outlet(o) for o in load_outlets() if o.active]


def run_cycle(sources: list[Source], state: StateStore, poster: DiscordPoster, settings, jev: JevClient) -> None:
    if not sources:
        logger.warning("Keine aktive Source - nichts zu tun.")
        return

    logger.info("Zyklus startet fuer: %s", ", ".join(s.name for s in sources))

    now = datetime.now(timezone.utc)
    since = now - MAX_ARTICLE_AGE
    candidates: list[tuple] = []  # (source, article, language), Kandidaten fuers Posten
    source_stats: dict[str, dict[str, int]] = {}

    for source in sources:
        articles = source.fetch(since)

        for article in articles:
            article.author = clean_author(article.author)

        first_run = not state.has_any(source.name)
        sample_keys = set()
        if first_run and not settings.initial_backfill:
            if settings.initial_backfill_sample > 0:
                newest_first = sorted(articles, key=lambda a: a.published or EPOCH, reverse=True)
                sample_keys = {a.key for a in newest_first[: settings.initial_backfill_sample]}
            logger.info(
                "Erster Lauf für %s: markiere %d bestehende Artikel als gesehen (%d als Test gepostet).",
                source.name, len(articles), len(sample_keys),
            )

        stats = {"total": len(articles), "already_known": 0, "skipped_language": 0, "skipped_stale": 0, "skipped_irrelevant": 0}
        source_stats[source.name] = stats

        for article in sorted(articles, key=lambda a: a.published or EPOCH):
            if state.is_known(source.name, article.key):
                stats["already_known"] += 1
                continue

            if first_run and not settings.initial_backfill and article.key not in sample_keys:
                state.mark_seen(
                    source.name, article.key, posted=False,
                    title=article.title, link=article.link, tier=source.tier,
                )
                continue

            if article.published is None or abs(now - article.published) > MAX_ARTICLE_AGE:
                logger.info(
                    "Übersprungen (nicht innerhalb der letzten %d Min., Datum: %s): %s",
                    MAX_ARTICLE_AGE.seconds // 60, article.published, article.title,
                )
                state.mark_seen(
                    source.name, article.key, posted=False,
                    title=article.title, link=article.link, tier=source.tier,
                )
                stats["skipped_stale"] += 1
                continue

            if source.feed_language:
                # Sprache steht schon durch die Feed-Konfiguration fest (z.B. Google
                # News mit fixem hl/ceid) - Titel-only-Erkennung waere hier nur
                # unzuverlaessiges Raten auf kurzen, eigennamenlastigen Strings.
                language = source.feed_language
            else:
                language = detect_language(f"{article.title} {strip_html(article.summary)}")

            if language not in ALLOWED_LANGUAGES:
                logger.info("Übersprungen (Sprache '%s'): %s", language, article.title)
                state.mark_seen(
                    source.name, article.key, posted=False,
                    title=article.title, link=article.link, tier=source.tier,
                )
                stats["skipped_language"] += 1
                continue

            if jev.enabled and source.tier not in RELEVANCE_EXEMPT_TIERS:
                if not jev.is_relevant(article.title, strip_html(article.summary)):
                    logger.info("Übersprungen (Jev: nicht relevant): %s", article.title)
                    state.mark_seen(
                        source.name, article.key, posted=False,
                        title=article.title, link=article.link, tier=source.tier,
                    )
                    stats["skipped_irrelevant"] += 1
                    continue

            candidates.append((source, article, language))

    # Duplikat-Check gegen den Pool von heute (vor dem Cycle-Limit, damit
    # Duplikate kein Budget verbrauchen).
    candidates, supersede = _dedupe_against_pool(candidates, state, jev, source_stats)

    # Cross-Source-Auswahl: erst jetzt, nachdem alle Feeds durch sind, wird
    # ueber alle Sources hinweg nach Tier priorisiert und das Cycle-Limit
    # angewendet (siehe _select_candidates).
    selected, dropped = _select_candidates(candidates)

    if dropped:
        logger.info(
            "%d Artikel wegen Cycle-Limit (max. %d, Tier 0/1 ausgenommen) übersprungen: %s",
            len(dropped), MAX_POSTS_PER_CYCLE,
            ", ".join(f"[{s.tier}] {s.name}: {a.title}" for s, a, _ in dropped),
        )
    for source, article, _ in dropped:
        state.mark_seen(
            source.name, article.key, posted=False,
            title=article.title, link=article.link, tier=source.tier,
        )
        source_stats[source.name]["dropped_cap"] = source_stats[source.name].get("dropped_cap", 0) + 1

    for source, article, language in selected:
        posted = poster.post_article(source, article, settings.content_max_chars, language)
        state.mark_seen(
            source.name, article.key, posted=posted,
            title=article.title, link=article.link, tier=source.tier,
        )
        if posted:
            if jev.enabled:
                state.add_to_pool(article.title, source.tier, article.link, source.name)
                replaced_id = supersede.get((source.name, article.key))
                if replaced_id is not None:
                    state.supersede_pool_entry(replaced_id)
            stats = source_stats[source.name]
            stats["posted"] = stats.get("posted", 0) + 1
            logger.info("Gepostet [%s]: [%s] %s - %s", language, source.tier, source.name, article.title)

    for source in sources:
        stats = source_stats.get(source.name)
        if stats is None:
            continue
        logger.info(
            "%s: %d Artikel im Feed, %d neu gepostet, %d wegen Cycle-Limit übersprungen, "
            "%d wegen Sprache übersprungen, %d zu alt/ohne Datum übersprungen, %d schon bekannt, "
            "%d von Jev als irrelevant, %d als Duplikat verworfen.",
            source.name, stats["total"], stats.get("posted", 0), stats.get("dropped_cap", 0),
            stats["skipped_language"], stats["skipped_stale"], stats["already_known"],
            stats["skipped_irrelevant"], stats.get("dropped_duplicate", 0),
        )


def main() -> None:
    settings = load_settings()
    poster = DiscordPoster(settings.discord_webhook_url, settings.discord_min_interval_seconds)
    state = StateStore(DATA_DIR / "state.db")
    jev = JevClient(settings.openrouter_api_key)
    if not jev.enabled:
        logger.warning("OPENROUTER_API_KEY nicht gesetzt - Jev-Filter (Relevanz/Duplikate) ist AUS.")

    startup_sources = load_all_sources()
    logger.info("Starte RSS-Scraper, Poll-Intervall=%ss", settings.poll_interval_seconds)
    logger.info(
        "Aktive Sources: %s",
        ", ".join(s.name for s in startup_sources) if startup_sources else "(keine)",
    )
    try:
        while True:
            sources = load_all_sources()  # neu laden, damit Config-Aenderungen ohne Neustart greifen
            run_cycle(sources, state, poster, settings, jev)
            time.sleep(settings.poll_interval_seconds)
    except KeyboardInterrupt:
        logger.info("Beendet durch Benutzer.")
    finally:
        state.close()


if __name__ == "__main__":
    main()
