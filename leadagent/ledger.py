"""
Dedupe ledger.

Stores ONLY the place id + when it was first seen + what happened to it.
That keeps the permanent store inside Google's licence (place_id is the
one field explicitly exempt from its caching restrictions) and means each
morning's report contains businesses you have never been shown before.
"""

from __future__ import annotations

import sqlite3
from datetime import datetime
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS seen (
    source_id   TEXT PRIMARY KEY,
    source      TEXT,
    first_seen  TEXT,
    last_seen   TEXT,
    times_seen  INTEGER DEFAULT 1,
    lead_type   TEXT,
    score       INTEGER,
    status      TEXT DEFAULT 'new'   -- new | contacted | replied | won | dead
);
CREATE TABLE IF NOT EXISTS runs (
    run_at TEXT, queries INTEGER, found INTEGER, fresh INTEGER, reported INTEGER
);
"""


class Ledger:
    def __init__(self, path: str = "data/leads.db"):
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        self.con = sqlite3.connect(path)
        self.con.executescript(SCHEMA)
        self.con.commit()

    def is_new(self, source_id: str) -> bool:
        cur = self.con.execute(
            "SELECT 1 FROM seen WHERE source_id = ?", (source_id,))
        return cur.fetchone() is None

    def remember(self, biz) -> None:
        now = datetime.now().isoformat(timespec="seconds")
        self.con.execute(
            """INSERT INTO seen (source_id, source, first_seen, last_seen,
                                 lead_type, score)
               VALUES (?,?,?,?,?,?)
               ON CONFLICT(source_id) DO UPDATE SET
                   last_seen = excluded.last_seen,
                   times_seen = times_seen + 1,
                   lead_type = excluded.lead_type,
                   score = excluded.score""",
            (biz.source_id, biz.source, now, now,
             biz.lead_type, biz.opportunity_score),
        )
        self.con.commit()

    def log_run(self, queries: int, found: int, fresh: int, reported: int) -> None:
        self.con.execute(
            "INSERT INTO runs VALUES (?,?,?,?,?)",
            (datetime.now().isoformat(timespec="seconds"),
             queries, found, fresh, reported),
        )
        self.con.commit()

    def stats(self) -> dict:
        c = self.con.execute(
            "SELECT count(*), coalesce(sum(status='contacted'),0) FROM seen"
        ).fetchone()
        return {"total_known": c[0], "contacted": c[1]}

    def mark(self, source_id: str, status: str) -> None:
        self.con.execute(
            "UPDATE seen SET status=? WHERE source_id=?", (status, source_id))
        self.con.commit()
