"""A tiny interface in front of the LLM provider.

The rest of the code only ever calls `llm.complete_json(system, user)`.
To swap providers, write another class with the same method and register it
in `get_llm()`. To swap models, change LLM_MODEL in config.py or the
LLM_MODEL environment variable.

This file also handles the two free-tier realities:
  * pacing  – a sliding-window limiter keeps us under requests/min and
              tokens/min, so we rarely get rate-limited at all;
  * 429s    – if we do, wait (Groq's retry-after header, or exponential
              backoff 2s, 4s, 8s...) and try again.
"""
from __future__ import annotations

import os
import random
import time
from collections import deque
from dataclasses import dataclass

import config


@dataclass
class LLMResponse:
    text: str
    prompt_tokens: int
    completion_tokens: int
    latency_s: float
    model: str

    @property
    def total_tokens(self) -> int:
        return self.prompt_tokens + self.completion_tokens


class LLMError(Exception):
    """The call failed for good (after retries)."""


class DailyLimitReached(LLMError):
    """Provider asked us to wait far too long — usually the daily cap."""


def estimate_tokens(text: str) -> int:
    """Rough rule of thumb: ~4 characters per token for English."""
    return max(1, len(text) // 4)


class RateLimiter:
    """Sliding 60-second window over requests and tokens."""

    def __init__(self, rpm: int, tpm: int, clock=time.monotonic, sleep=time.sleep):
        self.rpm, self.tpm = rpm, tpm
        self.clock, self.sleep = clock, sleep
        self.events: deque[tuple[float, int]] = deque()   # (time, tokens)

    def _trim(self, now: float):
        while self.events and now - self.events[0][0] >= 60:
            self.events.popleft()

    def wait_for(self, tokens: int):
        tokens = min(tokens, self.tpm)
        while True:
            now = self.clock()
            self._trim(now)
            used = sum(t for _, t in self.events)
            if len(self.events) < self.rpm and used + tokens <= self.tpm:
                return
            # wait until the oldest event leaves the window
            wait = 60 - (now - self.events[0][0]) + 0.05
            self.sleep(max(wait, 0.05))

    def record(self, tokens: int):
        self.events.append((self.clock(), tokens))


class GroqLLM:
    def __init__(self, model: str | None = None, api_key: str | None = None,
                 client=None, limiter: RateLimiter | None = None, sleep=time.sleep):
        self.model = model or config.LLM_MODEL
        if client is None:
            from groq import Groq
            key = api_key or os.environ.get("GROQ_API_KEY")
            if not key:
                raise LLMError("GROQ_API_KEY is not set")
            # max_retries=0: we do our own, visible retry logic below.
            client = Groq(api_key=key, max_retries=0, timeout=60)
        self.client = client
        self.limiter = limiter or RateLimiter(config.REQUESTS_PER_MINUTE,
                                              config.TOKENS_PER_MINUTE)
        self.sleep = sleep

    def complete_json(self, system: str, user: str) -> LLMResponse:
        import groq  # imported here so tests without the SDK still work

        est = estimate_tokens(system + user) + 300   # + a typical answer
        options = dict(config.MODEL_OPTIONS.get(self.model, {}))
        last_err = None

        for attempt in range(config.MAX_RETRIES + 1):
            self.limiter.wait_for(est)
            start = time.monotonic()
            try:
                resp = self.client.chat.completions.create(
                    model=self.model,
                    messages=[{"role": "system", "content": system},
                              {"role": "user", "content": user}],
                    response_format={"type": "json_object"},
                    temperature=config.LLM_TEMPERATURE,
                    max_completion_tokens=config.LLM_MAX_OUTPUT_TOKENS,
                    **options,
                )
            except groq.RateLimitError as e:
                self.limiter.record(est)
                wait = _retry_after(e)
                if wait is not None and wait > config.MAX_RETRY_AFTER_SECONDS:
                    raise DailyLimitReached(f"rate limit, retry after {wait:.0f}s") from e
                last_err = e
            except (groq.APIConnectionError, groq.InternalServerError) as e:
                last_err, wait = e, None
            except groq.APIStatusError as e:
                # 400 "json_validate_failed" = the model produced broken JSON.
                # Return it as text so the caller's retry-once logic handles it.
                if e.status_code == 400 and "json" in str(e).lower():
                    self.limiter.record(est)
                    return LLMResponse(text="", prompt_tokens=estimate_tokens(system + user),
                                       completion_tokens=0,
                                       latency_s=time.monotonic() - start, model=self.model)
                raise LLMError(f"Groq error {e.status_code}: {e}") from e
            else:
                latency = time.monotonic() - start
                usage = getattr(resp, "usage", None)
                pt = getattr(usage, "prompt_tokens", None) or estimate_tokens(system + user)
                ct = getattr(usage, "completion_tokens", None) or 0
                self.limiter.record(pt + ct)
                text = resp.choices[0].message.content or ""
                return LLMResponse(text, pt, ct, latency, self.model)

            if attempt == config.MAX_RETRIES:
                break
            backoff = config.BACKOFF_BASE_SECONDS * (2 ** attempt) + random.uniform(0, 1)
            self.sleep(max(backoff, wait or 0))

        raise LLMError(f"gave up after {config.MAX_RETRIES + 1} attempts: {last_err}")


def _retry_after(err) -> float | None:
    try:
        val = err.response.headers.get("retry-after")
        return float(val) if val is not None else None
    except Exception:
        return None


def get_llm(provider: str | None = None, model: str | None = None):
    provider = (provider or config.LLM_PROVIDER).lower()
    if provider == "groq":
        return GroqLLM(model=model)
    raise ValueError(f"Unknown LLM provider '{provider}'. Add it in llm.get_llm().")
