"""Cheap, rule-based noise filter that runs before the LLM.

Every email we can throw away here is one less LLM call (free-tier budget)
and one less chance of a false alarm. The rules live in config.py.

Order matters:
  1. "Rescue" rules win: anything that smells like a deadline is kept.
  2. Then the skip rules: List-Unsubscribe header, automated marketing
     sender, receipt/confirmation subject.
"""
import re
from email.utils import parseaddr

import config
from models import Email


def _contains_word(text: str, phrases: list[str]) -> str | None:
    """Return the first phrase found in text as a whole word/phrase."""
    for p in phrases:
        if re.search(r"(?<![a-z0-9])" + re.escape(p.lower()) + r"(?![a-z0-9])", text):
            return p
    return None


def is_noise(email: Email, cfg=config) -> tuple[bool, str]:
    """Return (skip?, reason). reason explains the decision either way."""
    subject = (email.subject or "").lower()
    body_head = (email.body or "")[:1500].lower()
    sender_addr = parseaddr(email.sender or "")[1].lower() or (email.sender or "").lower()

    # --- keep rules -------------------------------------------------------
    for s in cfg.ALWAYS_KEEP_SENDERS:
        if s.lower() in sender_addr:
            return False, f"keep: trusted sender ({s})"

    hit = _contains_word(subject + "\n" + body_head, cfg.RESCUE_KEYWORDS)
    if hit:
        return False, f"keep: rescue keyword '{hit}'"

    # --- skip rules -------------------------------------------------------
    if cfg.SKIP_IF_LIST_UNSUBSCRIBE and "list-unsubscribe" in email.headers:
        return True, "skip: List-Unsubscribe header (mass mail)"

    automated = any(p in sender_addr for p in cfg.NOREPLY_SENDER_PATTERNS)
    if automated:
        mk = _contains_word(subject + "\n" + body_head, cfg.MARKETING_WORDS)
        if mk:
            return True, f"skip: automated sender + marketing word '{mk}'"

    rc = _contains_word(subject, cfg.RECEIPT_SUBJECT_PATTERNS)
    if rc:
        return True, f"skip: receipt/confirmation ('{rc}')"

    return False, "keep: no skip rule matched"
