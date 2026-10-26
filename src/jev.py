from __future__ import annotations

import logging
import re
import time
from typing import Protocol

import requests

logger = logging.getLogger(__name__)

# Jev (TypeSafe) ist kein LLM, sondern eine "decision engine": state + typisierte
# Fragen rein, Antworten mit Wahrscheinlichkeiten raus (kein Text, Output ist
# kostenlos). Zugriff ueber OpenRouter, siehe readme.txt ("jev als
# entscheidungs-filter"). Alpha-API -> Modell fest pinnen, nicht den
# ~typesafe/jev-latest Alias nehmen.
JEV_URL = "https://openrouter.ai/api/alpha/decisions"
JEV_MODEL = "typesafe/jev-1.14"

# Beschreibung dessen, was ich sehen will - hier einfach aendern. Darf ein
# Satz oder eine Liste von Kategorien sein, Jev bekommt den Text als
# Frage-Instruktion.
RELEVANCE_PROFILE = (
    "Is this news article about politics, geopolitics, war and military conflicts, "
    "the economy, finance and markets, or technology (including AI), or about "
    "regional news from Germany that has nothing to do with celebrities, "
    "entertainment, sports, lifestyle or beauty?"
)
RELEVANCE_TRUE = (
    "Politics, geopolitics, war, economy, finance, technology, or serious regional "
    "news from Germany."
)
RELEVANCE_FALSE = (
    "Sports, celebrities, entertainment, lifestyle, beauty, human-interest "
    "or other irrelevant content."
)

# Nur verwerfen, wenn Jev sich ziemlich sicher ist, dass der Artikel NICHT
# passt (P(relevant) < Schwelle). Unsicher -> durchlassen.
RELEVANCE_DROP_BELOW = 0.3
# Duplikat nur annehmen, wenn Jev fuer den Pool-Treffer mindestens so sicher ist.
DUPLICATE_MIN_PROB = 0.6

# Pool-Vorfilter (lokal, ohne KI): nur die aehnlichsten Titel + die neuesten
# gehen an Jev, nicht der ganze Pool - haelt Calls klein/guenstig (32k-Limit).
POOL_TOP_SIMILAR = 25
POOL_NEWEST = 10

_WORD_RE = re.compile(r"[a-z0-9äöüß]{3,}")


class PoolLike(Protocol):
    id: int
    title: str
    tier: str


def _words(text: str) -> set[str]:
    return set(_WORD_RE.findall(text.lower()))


def shortlist_pool(title: str, pool: list) -> list:
    """pool: neueste zuerst. Liefert die aehnlichsten + neuesten Eintraege."""
    new_words = _words(title)
    scored = []
    for entry in pool:
        entry_words = _words(entry.title)
        union = new_words | entry_words
        overlap = len(new_words & entry_words) / len(union) if union else 0.0
        if overlap > 0:
            scored.append((overlap, entry))
    scored.sort(key=lambda x: x[0], reverse=True)
    chosen = {e.id: e for _, e in scored[:POOL_TOP_SIMILAR]}
    for entry in pool[:POOL_NEWEST]:
        chosen.setdefault(entry.id, entry)
    return list(chosen.values())


class JevClient:
    def __init__(self, api_key: str):
        self._api_key = api_key

    @property
    def enabled(self) -> bool:
        return bool(self._api_key)

    def _decide(self, state: dict, questions: dict) -> dict | None:
        """Gibt die answers zurueck oder None bei jedem Fehler (fail-open)."""
        payload = {"model": JEV_MODEL, "state": state, "questions": questions}
        headers = {"Authorization": f"Bearer {self._api_key}", "Content-Type": "application/json"}
        for attempt in range(2):
            try:
                resp = requests.post(JEV_URL, json=payload, headers=headers, timeout=15)
            except requests.RequestException as exc:
                logger.warning("Jev-Request fehlgeschlagen: %s", exc)
                return None
            if resp.status_code == 429 and attempt == 0:
                logger.warning("Jev rate-limited, warte kurz und versuche es nochmal.")
                time.sleep(2)
                continue
            if not resp.ok:
                logger.warning("Jev-Fehler %s: %s", resp.status_code, resp.text[:300])
                return None
            try:
                return resp.json()["answers"]
            except (ValueError, KeyError):
                logger.warning("Jev-Antwort nicht lesbar: %s", resp.text[:300])
                return None
        return None

    def is_relevant(self, title: str, summary: str) -> bool:
        answers = self._decide(
            {"title": title, "summary": summary[:256]},
            {
                "relevant": {
                    "type": "noul",
                    "instructions": RELEVANCE_PROFILE,
                    "criteria": {"true": RELEVANCE_TRUE, "false": RELEVANCE_FALSE},
                }
            },
        )
        if answers is None:
            return True
        try:
            probability = float(answers["relevant"]["noul"])
        except (KeyError, TypeError, ValueError):
            logger.warning("Jev-Relevanz-Antwort unerwartet: %s", answers)
            return True
        return probability >= RELEVANCE_DROP_BELOW

    def find_duplicate(self, title: str, candidates: list):
        """Liefert den Pool-Eintrag, ueber dessen Ereignis `title` schon berichtet
        wurde, sonst None. Nur Titel gehen an Jev; URL/Tier bleiben lokal."""
        if not candidates:
            return None
        by_key = {f"p{entry.id}": entry for entry in candidates}
        criteria = {"none": "None of the listed articles reports this same news event."}
        criteria.update({key: entry.title for key, entry in by_key.items()})
        answers = self._decide(
            {"new_article": title},
            {
                "duplicate_of": {
                    "type": "choice",
                    "instructions": (
                        "Which of these already published articles reports the same "
                        "specific news event as the new article? Choose 'none' if the "
                        "new article covers a different event."
                    ),
                    "criteria": criteria,
                }
            },
        )
        if answers is None:
            return None
        try:
            answer = answers["duplicate_of"]
            choice = answer["choice"]
            probability = float(answer["probabilities"][choice])
        except (KeyError, TypeError, ValueError):
            logger.warning("Jev-Duplikat-Antwort unerwartet: %s", answers)
            return None
        if choice == "none" or probability < DUPLICATE_MIN_PROB:
            return None
        return by_key.get(choice)
