"""Fake emails and a fake LLM so tests never touch Gmail or Groq."""
import json
from datetime import datetime, timezone

from llm import LLMResponse
from models import Email


def make_email(id="m1", subject="Hello", sender="Person <person@example.com>",
               body="Hi there", headers=None, thread_id=None, date=None):
    return Email(id=id, thread_id=thread_id or f"t-{id}", subject=subject, sender=sender,
                 date=date or datetime(2026, 10, 26, 9, 0, tzinfo=timezone.utc),
                 body=body, headers={k.lower(): v for k, v in (headers or {}).items()})


def answer(**overrides):
    base = {"is_actionable": True, "task": "Do the thing", "deadline": "2026-10-30",
            "urgency": "medium", "category": "career", "source": "Acme",
            "gmail_link": "x"}
    base.update(overrides)
    return json.dumps(base)


class FakeLLM:
    """Returns queued responses in order; a callable gets (system, user)."""

    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    def complete_json(self, system, user):
        self.calls.append((system, user))
        r = self.responses.pop(0) if len(self.responses) > 1 else self.responses[0]
        if isinstance(r, Exception):
            raise r
        text = r(system, user) if callable(r) else r
        return LLMResponse(text=text, prompt_tokens=100, completion_tokens=20,
                           latency_s=0.01, model="fake")
