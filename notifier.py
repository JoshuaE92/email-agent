"""Builds the push notifications and sends them through ntfy.sh.

ntfy is a free pub/sub push service: anyone who POSTs to
https://ntfy.sh/<topic> notifies every phone subscribed to <topic>.
No account needed, so the topic name is effectively the password.

Two kinds of notifications:
  * Morning summary  – all open items, grouped by category, sorted by deadline.
  * Urgent alert     – high priority, one per item that is overdue or due
                       within 48 h. Each item is only alerted once.
"""
from __future__ import annotations

import json
import os
import urllib.request
from datetime import date, timedelta

import config

NTFY_MAX_BYTES = 4000   # ntfy's message limit is 4096 bytes


def _deadline_label(deadline: str | None, today: date) -> str:
    if not deadline:
        return "no deadline"
    d = date.fromisoformat(deadline)
    delta = (d - today).days
    if delta < 0:
        return f"OVERDUE ({d:%a %b %d})"
    if delta == 0:
        return "TODAY"
    if delta == 1:
        return "tomorrow"
    return f"{d:%a %b %d}"


def _sort_key(item: dict):
    return (item["deadline"] is None, item["deadline"] or "")


def is_urgent(item: dict, today: date) -> bool:
    """Overdue, or deadline within URGENT_WINDOW_HOURS. Deadlines are dates
    (no time), so 48 h = due today, tomorrow or the day after."""
    if not item.get("deadline"):
        return False
    days = config.URGENT_WINDOW_HOURS // 24
    return date.fromisoformat(item["deadline"]) <= today + timedelta(days=days)


def build_summary(items: list[dict], today: date, new_hashes: set[str] = frozenset()) -> list[dict]:
    """Return a list of ntfy messages (usually one; split if too long)."""
    title = f"Morning brief – {today:%a %b %d}"
    if not items:
        return [{"title": title, "message": "Nothing urgent today. Inbox is clear.",
                 "priority": 2, "tags": ["sunny"]}]

    groups: dict[str, list[dict]] = {}
    for it in items:
        groups.setdefault(it["category"] or "other", []).append(it)

    blocks = []
    for cat in config.CATEGORY_ORDER + sorted(set(groups) - set(config.CATEGORY_ORDER)):
        if cat not in groups:
            continue
        lines = [f"== {cat.upper()} =="]
        for it in sorted(groups[cat], key=_sort_key):
            new = "NEW " if it.get("task_hash") in new_hashes else ""
            lines.append(f"• {new}{it['task']} — {_deadline_label(it['deadline'], today)}"
                         f" ({it['source']})\n  {it['gmail_link']}")
        blocks.append("\n".join(lines))

    header = f"{len(items)} open item(s)\n\n"
    messages, current = [], header
    for b in blocks:
        if len((current + b).encode()) > NTFY_MAX_BYTES and current != header:
            messages.append(current.rstrip())
            current = ""
        current += b + "\n\n"
    messages.append(current.rstrip())

    n = len(messages)
    return [{"title": title + (f" ({i}/{n})" if n > 1 else ""), "message": m,
             "priority": 3, "tags": ["inbox_tray"]}
            for i, m in enumerate(messages, 1)]


def build_urgent_alerts(items: list[dict], today: date) -> list[tuple[str, dict]]:
    """Return [(task_hash, ntfy message)] for urgent items not alerted before."""
    urgent = [it for it in items if is_urgent(it, today) and not it.get("urgent_sent_at")]
    urgent.sort(key=_sort_key)
    out = []
    for it in urgent[:config.MAX_URGENT_ALERTS]:
        when = _deadline_label(it["deadline"], today)
        out.append((it["task_hash"], {
            "title": f"Due {when}: {it['task']}"[:120],
            "message": f"{it['task']}\nFrom: {it['source']}\nDeadline: {it['deadline']}\n"
                       f"{it['gmail_link']}",
            "priority": 5 if when.startswith("OVERDUE") or when == "TODAY" else 4,
            "tags": ["rotating_light"],
            "click": it["gmail_link"],
        }))
    rest = urgent[config.MAX_URGENT_ALERTS:]
    if rest:
        lines = [f"• {it['task']} — {_deadline_label(it['deadline'], today)}\n  {it['gmail_link']}"
                 for it in rest]
        msg = {"title": f"{len(rest)} more urgent item(s)", "message": "\n".join(lines),
               "priority": 4, "tags": ["rotating_light"]}
        for i, it in enumerate(rest):
            out.append((it["task_hash"], msg if i == 0 else None))
    return out


class Notifier:
    def __init__(self, topic: str | None = None, server: str = config.NTFY_SERVER,
                 dry_run: bool = False, printer=print):
        self.topic = topic or os.environ.get("NTFY_TOPIC", "")
        self.server = server.rstrip("/")
        self.dry_run = dry_run
        self.printer = printer
        if not dry_run and not self.topic:
            raise RuntimeError("NTFY_TOPIC is not set")

    def send(self, msg: dict):
        if self.dry_run:
            self.printer(f"\n[DRY RUN] would send (priority {msg.get('priority', 3)}): "
                         f"{msg['title']}\n{msg['message']}\n" + "-" * 60)
            return
        # JSON publishing handles emoji/unicode safely (headers can't).
        payload = dict(msg, topic=self.topic)
        req = urllib.request.Request(self.server, data=json.dumps(payload).encode(),
                                     headers={"Content-Type": "application/json"},
                                     method="POST")
        with urllib.request.urlopen(req, timeout=20) as r:
            if r.status >= 300:
                raise RuntimeError(f"ntfy returned {r.status}")
