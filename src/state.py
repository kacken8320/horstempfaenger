from __future__ import annotations

import sqlite3
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS seen_articles (
    outlet TEXT NOT NULL,
    article_key TEXT NOT NULL,
    posted INTEGER NOT NULL,
    seen_at TEXT NOT NULL DEFAULT (datetime('now')),
    title TEXT,
    link TEXT,
    tier TEXT,
    PRIMARY KEY (outlet, article_key)
);
"""

# title/link/tier kamen erst spaeter dazu (fuer query.py) - bereits bestehende
# state.db-Dateien (z.B. auf Railway) haben diese Spalten noch nicht, deshalb
# hier per ALTER TABLE nachruesten statt vorauszusetzen, dass CREATE TABLE IF
# NOT EXISTS das fuer eine schon existierende Tabelle miterledigt.
_MIGRATION_COLUMNS = ("title", "link", "tier")


class StateStore:
    def __init__(self, db_path: Path):
        db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(db_path)
        self._conn.execute(SCHEMA)
        existing_columns = {row[1] for row in self._conn.execute("PRAGMA table_info(seen_articles)")}
        for column in _MIGRATION_COLUMNS:
            if column not in existing_columns:
                self._conn.execute(f"ALTER TABLE seen_articles ADD COLUMN {column} TEXT")
        self._conn.commit()

    def is_known(self, outlet: str, article_key: str) -> bool:
        row = self._conn.execute(
            "SELECT 1 FROM seen_articles WHERE outlet = ? AND article_key = ?",
            (outlet, article_key),
        ).fetchone()
        return row is not None

    def has_any(self, outlet: str) -> bool:
        row = self._conn.execute(
            "SELECT 1 FROM seen_articles WHERE outlet = ? LIMIT 1",
            (outlet,),
        ).fetchone()
        return row is not None

    def mark_seen(
        self, outlet: str, article_key: str, posted: bool,
        title: str = "", link: str = "", tier: str = "",
    ) -> None:
        self._conn.execute(
            "INSERT OR IGNORE INTO seen_articles (outlet, article_key, posted, title, link, tier) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (outlet, article_key, int(posted), title, link, tier),
        )
        self._conn.commit()

    def recent_posted(self, tiers: list[str], since_iso_utc: str) -> list[sqlite3.Row]:
        self._conn.row_factory = sqlite3.Row
        placeholders = ",".join("?" for _ in tiers)
        rows = self._conn.execute(
            f"SELECT outlet, title, link, tier, seen_at FROM seen_articles "
            f"WHERE posted = 1 AND tier IN ({placeholders}) AND seen_at >= ? "
            f"ORDER BY seen_at DESC",
            (*tiers, since_iso_utc),
        ).fetchall()
        self._conn.row_factory = None
        return rows

    def close(self) -> None:
        self._conn.close()
