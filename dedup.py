"""Remembers what we've already processed and alerted, in data/state.sqlite.

Three layers of "have I seen this before?":
  1. Gmail message ID      -> the exact same email (the 26 h window overlaps).
  2. Normalized task hash  -> same task text from a different email.
  3. Reminder similarity   -> same sender + mostly the same words
                              ("Reminder: complete your background check").

Tables
  processed(message_id, processed_at, outcome)   every email we looked at
  items(task_hash, message_id, ...)               every actionable item
  runs(run_date)                                  dates the agent ran
"""
from __future__ import annotations

import hashlib
import os
import re
import sqlite3
from datetime import date, datetime, timedelta, timezone
from email.utils import parseaddr

import config
from models import Item

STOPWORDS = {
    "a", "an", "the", "to", "for", "of", "and", "or", "in", "on", "at", "by",
    "your", "my", "you", "please", "reminder", "re", "fwd", "fw", "with",
    "is", "be", "this", "that", "from", "before", "due", "deadline", "complete",
    "finish", "submit", "do", "get", "it", "its", "action", "required", "final",
    "urgent", "asap", "today", "tomorrow", "now", "still", "again", "need",
}

SCHEMA = """
CREATE TABLE IF NOT EXISTS processed (
    message_id   TEXT PRIMARY KEY,
    processed_at TEXT NOT NULL,
    outcome      TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS items (
    task_hash     TEXT PRIMARY KEY,
    message_id    TEXT NOT NULL,
    thread_id     TEXT,
    task          TEXT NOT NULL,
    deadline      TEXT,
    urgency       TEXT,
    category      TEXT,
    source        TEXT,
    sender        TEXT,
    gmail_link    TEXT,
    first_seen    TEXT NOT NULL,
    urgent_sent_at TEXT
);
CREATE TABLE IF NOT EXISTS item_messages (
    message_id TEXT PRIMARY KEY,
    task_hash  TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS runs (
    run_date TEXT PRIMARY KEY,
    ran_at   TEXT NOT NULL
);
"""


def normalize_words(text: str) -> list[str]:
    words = re.findall(r"[a-z0-9]+", (text or "").lower())
    return [w for w in words if w not in STOPWORDS and len(w) > 1]


FREEMAIL = {"gmail.com", "yahoo.com", "outlook.com", "hotmail.com", "icloud.com",
            "aol.com", "proton.me", "protonmail.com", "live.com", "me.com"}


def task_hash(task: str, source: str = "", deadline: str | None = None) -> str:
    """Same words (any order/case/punctuation) + same sender + same deadline -> same hash."""
    key = "|".join([" ".join(sorted(set(normalize_words(task)))),
                    _sender_key(source), deadline or ""])
    return hashlib.sha256(key.encode()).hexdigest()[:16]


def _sender_key(sender_or_source: str) -> str:
    """Company emails: compare by domain (hr@acme.com ~ noreply@acme.com).
    Personal Gmail/Yahoo/etc: compare by full address."""
    addr = parseaddr(sender_or_source or "")[1].lower()
    if "@" in addr:
        domain = addr.split("@", 1)[1]
        return addr if domain in FREEMAIL else domain
    return " ".join(normalize_words(sender_or_source))


def deadlines_compatible(a: str | None, b: str | None, days: int = 14) -> bool:
    """A reminder can move a deadline a bit, but next month's bill is a new task."""
    if not a or not b:
        return True
    return abs((date.fromisoformat(a) - date.fromisoformat(b)).days) <= days


def jaccard(a: str, b: str) -> float:
    sa, sb = set(normalize_words(a)), set(normalize_words(b))
    if not sa or not sb:
        return 0.0
    return len(sa & sb) / len(sa | sb)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class StateStore:
    def __init__(self, path: str = config.STATE_DB_PATH):
        if path != ":memory:":
            os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        self.db = sqlite3.connect(path)
        self.db.row_factory = sqlite3.Row
        self.db.executescript(SCHEMA)

    @classmethod
    def in_memory_copy(cls, path: str) -> "StateStore":
        """For --dry-run: work on a throwaway copy so nothing is saved."""
        store = cls(":memory:")
        if os.path.exists(path):
            src = sqlite3.connect(path)
            src.backup(store.db)
            src.close()
            store.db.executescript(SCHEMA)
        return store

    # ---- processed emails --------------------------------------------------
    def is_processed(self, message_id: str) -> bool:
        return self.db.execute("SELECT 1 FROM processed WHERE message_id=?",
                               (message_id,)).fetchone() is not None

    def mark_processed(self, message_id: str, outcome: str):
        self.db.execute("INSERT OR REPLACE INTO processed VALUES (?,?,?)",
                        (message_id, _now(), outcome))
        self.db.commit()

    # ---- items -------------------------------------------------------------
    def find_duplicate(self, item: Item) -> str | None:
        """Return why `item` is a repeat, or None if it's new."""
        if self.db.execute("SELECT 1 FROM item_messages WHERE message_id=?",
                           (item.message_id,)).fetchone():
            return "same message id"
        h = self._hash_for(item)
        if self.db.execute("SELECT 1 FROM items WHERE task_hash=?", (h,)).fetchone():
            return "same task hash"
        # Reminder check: same sender domain/source, mostly the same words.
        me = _sender_key(item.sender or item.source)
        for row in self.db.execute(
                "SELECT task, sender, source, thread_id, deadline FROM items"):
            same_sender = bool(me) and me == _sender_key(row["sender"] or row["source"])
            same_thread = bool(item.thread_id) and item.thread_id == row["thread_id"]
            if (same_sender or same_thread) \
                    and deadlines_compatible(item.deadline, row["deadline"]) \
                    and jaccard(item.task, row["task"]) >= config.REMINDER_SIMILARITY:
                return f"reminder of: {row['task']}"
        return None

    def _hash_for(self, item: Item) -> str:
        return task_hash(item.task, item.sender or item.source, item.deadline)

    def add_item(self, item: Item) -> str:
        h = self._hash_for(item)
        self.db.execute(
            "INSERT OR IGNORE INTO items (task_hash, message_id, thread_id, task, deadline,"
            " urgency, category, source, sender, gmail_link, first_seen)"
            " VALUES (?,?,?,?,?,?,?,?,?,?,?)",
            (h, item.message_id, item.thread_id, item.task, item.deadline, item.urgency,
             item.category, item.source, item.sender, item.gmail_link, _now()))
        self.db.execute("INSERT OR IGNORE INTO item_messages VALUES (?,?)",
                        (item.message_id, h))
        self.db.commit()
        return h

    def link_message(self, message_id: str, item: Item):
        """Remember a reminder email so it's skipped by message ID next time."""
        self.db.execute("INSERT OR IGNORE INTO item_messages VALUES (?,?)",
                        (message_id, self._hash_for(item)))
        self.db.commit()

    def open_items(self, today: date) -> list[dict]:
        """Items still worth showing in the morning summary."""
        rows = [dict(r) for r in self.db.execute("SELECT * FROM items")]
        keep = []
        for r in rows:
            if r["deadline"]:
                d = date.fromisoformat(r["deadline"])
                if d >= today - timedelta(days=config.OVERDUE_GRACE_DAYS):
                    keep.append(r)
            else:
                first = datetime.fromisoformat(r["first_seen"]).date()
                if first >= today - timedelta(days=config.NO_DEADLINE_KEEP_DAYS):
                    keep.append(r)
        return keep

    def mark_urgent_sent(self, task_hash_: str):
        self.db.execute("UPDATE items SET urgent_sent_at=? WHERE task_hash=?",
                        (_now(), task_hash_))
        self.db.commit()

    # ---- runs ----------------------------------------------------------------
    def ran_on(self, d: date) -> bool:
        return self.db.execute("SELECT 1 FROM runs WHERE run_date=?",
                               (d.isoformat(),)).fetchone() is not None

    def mark_ran(self, d: date):
        self.db.execute("INSERT OR REPLACE INTO runs VALUES (?,?)", (d.isoformat(), _now()))
        self.db.commit()

    def close(self):
        self.db.close()
