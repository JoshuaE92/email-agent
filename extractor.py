"""Turns one Email into a validated extraction dict using the LLM.

Flow for each email:
  1. Build the prompt (system rules + this email).
  2. Ask the LLM for JSON.
  3. Validate it against schema.py.
  4. If it's broken, tell the model what was wrong and ask ONCE more.
  5. Still broken -> give up on this email (return None). Never crash.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import date, datetime
from zoneinfo import ZoneInfo

import config
from llm import LLMError, DailyLimitReached
from models import Email
from prompts import PROMPTS, build_user_message
from schema import ValidationError, parse_and_validate

log = logging.getLogger(__name__)


@dataclass
class ExtractionResult:
    data: dict | None                 # validated JSON, or None if we gave up
    valid_first_try: bool = False
    attempts: int = 0
    latency_s: float = 0.0
    tokens: int = 0
    errors: list = field(default_factory=list)


def urgency_for(deadline: str, today: date) -> str:
    """Same rule the prompt describes, done in code (LLMs are shaky at date math)."""
    days = (date.fromisoformat(deadline) - today).days
    return "high" if days <= 2 else "medium" if days <= 7 else "low"


def today_local() -> date:
    return datetime.now(ZoneInfo(config.TIMEZONE)).date()


def extract(email: Email, llm, today: date | None = None,
            prompt_version: str | None = None) -> ExtractionResult:
    today = today or today_local()
    version = prompt_version or config.PROMPT_VERSION
    system = PROMPTS[version]
    user = build_user_message(email, today, version)
    result = ExtractionResult(data=None)

    for attempt in (1, 2):
        result.attempts = attempt
        try:
            resp = llm.complete_json(system, user)
        except DailyLimitReached:
            raise                      # caller stops the whole run politely
        except LLMError as e:
            result.errors.append(f"llm error: {e}")
            log.warning("LLM call failed for %s: %s", email.id, e)
            return result
        result.latency_s += resp.latency_s
        result.tokens += resp.total_tokens
        try:
            data = parse_and_validate(resp.text)
        except ValidationError as e:
            result.errors.append(str(e))
            log.info("Bad JSON for %s (attempt %d): %s", email.id, attempt, e)
            # Second try: same email + a note saying what was wrong.
            user = (build_user_message(email, today, version) +
                    f"\n\nYour previous answer was invalid ({e}). "
                    "Reply again with ONLY the JSON object, exactly the keys requested.")
            continue
        # We know the real link; never trust a model-written URL.
        data["gmail_link"] = email.gmail_link
        if not data["source"]:
            data["source"] = email.sender
        if config.DERIVE_URGENCY_FROM_DEADLINE and data["deadline"]:
            data["urgency"] = urgency_for(data["deadline"], today)
        result.data = data
        result.valid_first_try = attempt == 1
        return result

    log.warning("Skipping %s after 2 invalid answers", email.id)
    return result
