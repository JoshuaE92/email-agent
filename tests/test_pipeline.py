"""Extractor retry logic, rate-limit backoff, notifications, and a full dry run."""
from datetime import date

import httpx
import groq
import pytest

import config
from dedup import StateStore
from extractor import extract
from llm import DailyLimitReached, GroqLLM, LLMError, RateLimiter
from main import notify, process_emails
from notifier import Notifier, build_summary, build_urgent_alerts
from tests.helpers import FakeLLM, answer, make_email

TODAY = date(2026, 10, 26)


# ---- extractor: retry once, then skip ---------------------------------------

def test_valid_first_try():
    r = extract(make_email(), FakeLLM([answer()]), today=TODAY)
    assert r.data and r.valid_first_try and r.attempts == 1


def test_gmail_link_is_overwritten_with_real_one():
    e = make_email(id="abc123")
    r = extract(e, FakeLLM([answer(gmail_link="https://evil.example")]), today=TODAY)
    assert r.data["gmail_link"] == e.gmail_link


def test_retries_once_on_bad_json_then_succeeds():
    llm = FakeLLM(["oops not json", answer()])
    r = extract(make_email(), llm, today=TODAY)
    assert r.data and not r.valid_first_try and r.attempts == 2
    assert "previous answer was invalid" in llm.calls[1][1]


def test_gives_up_after_two_bad_answers_without_crashing():
    r = extract(make_email(), FakeLLM(["{bad", answer(category="nope")]), today=TODAY)
    assert r.data is None and r.attempts == 2 and len(r.errors) == 2


def test_llm_error_is_caught():
    r = extract(make_email(), FakeLLM([LLMError("boom")]), today=TODAY)
    assert r.data is None


# ---- Groq client: 429 backoff -----------------------------------------------

def _rate_limit(retry_after="1"):
    req = httpx.Request("POST", "https://api.groq.com/openai/v1/chat/completions")
    headers = {"retry-after": retry_after} if retry_after is not None else {}
    resp = httpx.Response(429, headers=headers, request=req)
    return groq.RateLimitError("rate limited", response=resp, body=None)


class _Msg:
    content = answer()


class _Choice:
    message = _Msg()


class _Resp:
    choices = [_Choice()]
    usage = type("U", (), {"prompt_tokens": 500, "completion_tokens": 50})()


class FakeGroqClient:
    def __init__(self, errors):
        self.errors = list(errors)
        self.chat = self
        self.completions = self
        self.calls = 0

    def create(self, **kw):
        self.calls += 1
        assert kw["response_format"] == {"type": "json_object"}
        if self.errors:
            raise self.errors.pop(0)
        return _Resp()


def test_429_backs_off_then_succeeds():
    sleeps = []
    client = FakeGroqClient([_rate_limit("3"), _rate_limit(None)])
    llm = GroqLLM(model="m", client=client, sleep=sleeps.append,
                  limiter=RateLimiter(1000, 10**9, sleep=lambda s: None))
    r = llm.complete_json("sys", "user")
    assert client.calls == 3 and r.total_tokens == 550
    assert sleeps[0] >= 3            # honours retry-after
    assert 4 <= sleeps[1] <= 5       # exponential: 2 * 2**1 (+ jitter)


def test_429_with_huge_retry_after_stops_for_the_day():
    client = FakeGroqClient([_rate_limit("3600")])
    llm = GroqLLM(model="m", client=client, sleep=lambda s: None,
                  limiter=RateLimiter(1000, 10**9, sleep=lambda s: None))
    with pytest.raises(DailyLimitReached):
        llm.complete_json("sys", "user")


def test_gives_up_after_max_retries():
    client = FakeGroqClient([_rate_limit("1")] * 10)
    llm = GroqLLM(model="m", client=client, sleep=lambda s: None,
                  limiter=RateLimiter(1000, 10**9, sleep=lambda s: None))
    with pytest.raises(LLMError):
        llm.complete_json("sys", "user")
    assert client.calls == config.MAX_RETRIES + 1


def test_rate_limiter_waits_when_token_budget_full():
    t = [0.0]
    slept = []

    def sleep(s):
        slept.append(s); t[0] += s

    lim = RateLimiter(rpm=100, tpm=1000, clock=lambda: t[0], sleep=sleep)
    lim.wait_for(600); lim.record(600)
    lim.wait_for(600)                # would exceed 1000 → must wait ~60 s
    assert slept and 59 <= sum(slept) <= 61


# ---- notifications -----------------------------------------------------------

def _row(task, deadline, category="career", h=None, **kw):
    return dict(task=task, deadline=deadline, category=category, source="Src",
                gmail_link="https://mail/x", task_hash=h or task, urgent_sent_at=None, **kw)


def test_empty_summary_says_nothing_urgent():
    msgs = build_summary([], TODAY)
    assert "Nothing urgent today" in msgs[0]["message"]


def test_summary_groups_by_category_and_sorts_by_deadline():
    items = [_row("Pay rent", "2026-11-01", "bills"), _row("Late OA", "2026-10-30"),
             _row("Early OA", "2026-10-27"), _row("No date", None)]
    m = build_summary(items, TODAY, new_hashes={"Late OA"})[0]["message"]
    assert m.index("CAREER") < m.index("BILLS")
    assert m.index("Early OA") < m.index("Late OA") < m.index("No date")
    assert "NEW Late OA" in m and "https://mail/x" in m


def test_long_summary_is_split():
    items = [_row(f"Task number {i} " + "x" * 150, "2026-11-01", c)
             for i, c in enumerate(config.CATEGORY_ORDER * 6)]
    msgs = build_summary(items, TODAY)
    assert len(msgs) > 1 and all(len(m["message"].encode()) <= 4096 for m in msgs)


def test_urgent_alerts_only_for_overdue_or_48h_and_only_once():
    items = [_row("Overdue", "2026-10-25"), _row("Today", "2026-10-26"),
             _row("In 2 days", "2026-10-28"), _row("In 5 days", "2026-10-31"),
             _row("Already alerted", "2026-10-26") | {"urgent_sent_at": "x"},
             _row("No deadline", None)]
    titles = [m["title"] for _, m in build_urgent_alerts(items, TODAY)]
    assert len(titles) == 3
    assert titles[0].startswith("Due OVERDUE")
    assert all("5 days" not in t and "Already" not in t for t in titles)


# ---- end-to-end dry run ------------------------------------------------------

def test_full_run_dedups_reminders_and_never_alerts_twice():
    def fake(system, user):
        if "40% off" in user:
            raise AssertionError("noise should never reach the LLM")
        if "background check" in user.lower():
            return answer(task="Complete Checkr background check", deadline="2026-10-27",
                          urgency="high", source="Checkr")
        return answer(is_actionable=False, task=None, deadline=None, urgency="low",
                      category="other")

    emails = [
        make_email(id="1", subject="Complete your background check",
                   sender="Checkr <noreply@checkr.com>", body="Please complete by Oct 27."),
        make_email(id="2", subject="Reminder: background check still pending",
                   sender="Checkr <noreply@checkr.com>", body="Reminder, complete by Oct 27."),
        make_email(id="3", subject="40% off sale", sender="Shop <noreply@shop.com>",
                   body="Shop now", headers={"List-Unsubscribe": "x"}),
        make_email(id="4", subject="Team update", sender="Club <club@ucf.edu>", body="FYI."),
    ]
    store, sent = StateStore(":memory:"), []
    notifier = Notifier(dry_run=True, printer=sent.append)

    stats = process_emails(emails, FakeLLM([fake]), store, TODAY)
    assert (stats["new_items"], stats["duplicate"], stats["noise"], stats["not_actionable"]) == (1, 1, 1, 1)
    notify(store, notifier, TODAY, stats["new_hashes"])
    assert sum("priority 5" in s or "priority 4" in s for s in sent) == 1   # one urgent alert

    # Second morning, same emails again (26 h overlap) -> nothing new, no repeat alert.
    sent.clear()
    stats2 = process_emails(emails, FakeLLM([fake]), store, TODAY)
    assert stats2["already_seen"] == 4 and stats2["new_items"] == 0
    notify(store, notifier, TODAY, stats2["new_hashes"])
    assert len(sent) == 1 and "priority 3" in sent[0]   # summary only
