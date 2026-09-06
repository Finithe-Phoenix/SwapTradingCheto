"""Atomic snapshots and idempotent events, also used by the Freqtrade adapter."""
import json
from pathlib import Path
import sqlite3


class Journal:
    def __init__(self, path):
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(path, timeout=10)
        self.db.execute("PRAGMA journal_mode=WAL")
        self.db.execute("CREATE TABLE IF NOT EXISTS snapshots (name TEXT PRIMARY KEY, body TEXT NOT NULL)")
        self.db.execute("CREATE TABLE IF NOT EXISTS events (id TEXT PRIMARY KEY, body TEXT NOT NULL)")
        self.db.commit()

    def get(self, name):
        row = self.db.execute("SELECT body FROM snapshots WHERE name=?", (name,)).fetchone()
        return json.loads(row[0]) if row else None

    def save(self, name, snapshot, events=()):
        with self.db:
            self.db.execute("INSERT INTO snapshots VALUES (?,?) ON CONFLICT(name) DO UPDATE SET body=excluded.body",
                            (name, json.dumps(snapshot, allow_nan=False, sort_keys=True)))
            for event_id, event in events:
                self.db.execute("INSERT OR IGNORE INTO events VALUES (?,?)", (event_id, json.dumps(event, allow_nan=False)))

    def close(self):
        self.db.close()
