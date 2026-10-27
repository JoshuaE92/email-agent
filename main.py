"""Entry point: fetch -> filter -> extract -> dedup -> notify.

Usage:
  python main.py                 # real run: reads Gmail, sends notifications
  python main.py --dry-run       # prints notifications, saves nothing
  python main.py --dry-run --from-file eval/dataset.json   # no Gmail needed
  python main.py --scheduled     # used by GitHub Actions (see workflow file)
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
from datetime import date, datetime
from zoneinfo import ZoneInfo

from dotenv import load_dotenv

import config
from dedup import StateStore
from extractor import extract, today_local
from filters import is_noise
from llm import DailyLimitReached, get_llm
from models import Email, Item
from notifier import Notifier, build_summary, build_urgent_alerts

log = logging.getLogger("email-agent")


def process_emails(emails: list[Email], llm, store: StateStore, today: date) -> dict:
    """Run every new email through filter -> LLM -> dedup. Returns stats."""
    stats = {"fetched": len(emails), "already_seen": 0, "noise": 0, "not_actionable": 0,
             "duplicate": 0, "new_items": 0, "failed": 0, "new_hashes": set(),
             "stopped_early": False}
    # Oldest first, so the original email "owns" the task and later
    # reminders are recognised as repeats.
    for e in sorted(emails, key=lambda m: m.date):
        if store.is_processed(e.id):
            stats["already_seen"] += 1
            continue
        skip, reason = is_noise(e)
        if skip:
            stats["noise"] += 1
            store.mark_processed(e.id, reason)
            continue
        try:
            res = extract(e, llm, today=today)
        except DailyLimitReached as err:
            log.warning("Stopping early: %s. Remaining emails will be retried next run.", err)
            stats["stopped_early"] = True
            break
        if res.data is None:
            stats["failed"] += 1
            # Broken JSON twice -> don't retry forever. LLM/network error -> retry next run.
            if any("llm error" not in x for x in res.errors):
                store.mark_processed(e.id, "invalid llm output")
            continue
        d = res.data
        if not d["is_actionable"]:
            stats["not_actionable"] += 1
            store.mark_processed(e.id, "not actionable")
            continue
        item = Item(message_id=e.id, thread_id=e.thread_id, task=d["task"],
                    deadline=d["deadline"], urgency=d["urgency"], category=d["category"],
                    source=d["source"], gmail_link=d["gmail_link"], sender=e.sender)
        dup = store.find_duplicate(item)
        if dup:
            stats["duplicate"] += 1
            store.link_message(e.id, item)
            store.mark_processed(e.id, f"duplicate: {dup}"[:200])
            continue
        h = store.add_item(item)
        stats["new_hashes"].add(h)
        stats["new_items"] += 1
        store.mark_processed(e.id, "new item")
    return stats


def notify(store: StateStore, notifier: Notifier, today: date, new_hashes: set[str]):
    items = store.open_items(today)
    for msg in build_summary(items, today, new_hashes):
        notifier.send(msg)
    urgent = build_urgent_alerts(items, today)
    for h, msg in urgent:
        if msg:
            notifier.send(msg)
        store.mark_urgent_sent(h)
    return len(items), len(urgent)


def load_emails_from_file(path: str) -> list[Email]:
    """Load emails from a JSON file (e.g. eval/dataset.json) for offline runs."""
    with open(path) as f:
        rows = json.load(f)
    rows = rows["emails"] if isinstance(rows, dict) else rows
    out = []
    for i, r in enumerate(rows):
        e = r.get("email", r)
        out.append(Email(id=r.get("id", f"file-{i}"), thread_id=e.get("thread_id", f"t-{i}"),
                         subject=e["subject"], sender=e["sender"],
                         date=datetime.fromisoformat(e["date"]), body=e["body"],
                         headers={k.lower(): v for k, v in e.get("headers", {}).items()}))
    return out


def main(argv=None) -> int:
    load_dotenv()
    ap = argparse.ArgumentParser(description="Daily Gmail -> LLM -> ntfy agent")
    ap.add_argument("--dry-run", action="store_true",
                    help="print what would be sent; don't send or save state")
    ap.add_argument("--model", help=f"override LLM model (default {config.LLM_MODEL})")
    ap.add_argument("--hours", type=int, default=config.LOOKBACK_HOURS)
    ap.add_argument("--max-emails", type=int, default=config.MAX_EMAILS_PER_RUN)
    ap.add_argument("--from-file", help="read emails from a JSON file instead of Gmail")
    ap.add_argument("--scheduled", action="store_true",
                    help="cron mode: only run once per day, at/after 8 AM Eastern")
    ap.add_argument("-v", "--verbose", action="store_true")
    args = ap.parse_args(argv)
    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.INFO,
                        format="%(levelname)s %(message)s")

    today = today_local()
    store = (StateStore.in_memory_copy(config.STATE_DB_PATH) if args.dry_run
             else StateStore(config.STATE_DB_PATH))

    if args.scheduled:
        now = datetime.now(ZoneInfo(config.TIMEZONE))
        if now.hour < 8:
            log.info("Scheduled run at %s ET is before 8 AM; skipping (DST guard).",
                     now.strftime("%H:%M"))
            return 0
        if store.ran_on(today):
            log.info("Already ran today (%s); skipping.", today)
            return 0

    if args.from_file:
        emails = load_emails_from_file(args.from_file)
    else:
        from gmail_client import fetch_recent
        emails = fetch_recent(hours=args.hours, max_emails=args.max_emails)
    log.info("Fetched %d email(s)", len(emails))

    llm = get_llm(model=args.model)
    stats = process_emails(emails, llm, store, today)
    notifier = Notifier(dry_run=args.dry_run)
    n_open, n_urgent = notify(store, notifier, today, stats["new_hashes"])

    if args.scheduled and not args.dry_run:
        store.mark_ran(today)
    store.close()

    stats.pop("new_hashes")
    log.info("Done. %s | open items: %d | urgent alerts: %d", stats, n_open, n_urgent)
    return 0


if __name__ == "__main__":
    sys.exit(main())
