from __future__ import annotations

import sqlite3
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS seen_articles (
    outlet TEXT NOT NULL,
    article_key TEXT NOT NULL,
    posted INTEGER NOT NULL,
    seen_at TEXT NOT NULL DEFAULT (datetime('now')),
    PRIMARY KEY (outlet, article_key)
);
"""


class StateStore:
    def __init__(self, db_path: Path):
        db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(db_path)
        self._conn.execute(SCHEMA)
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

    def mark_seen(self, outlet: str, article_key: str, posted: bool) -> None:
        self._conn.execute(
            "INSERT OR IGNORE INTO seen_articles (outlet, article_key, posted) "
            "VALUES (?, ?, ?)",
            (outlet, article_key, int(posted)),
        )
        self._conn.commit()

    def close(self) -> None:
        self._conn.close()
