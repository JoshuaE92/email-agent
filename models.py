"""Plain data containers shared by every module."""
from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class Email:
    id: str                      # Gmail message ID
    thread_id: str
    subject: str
    sender: str                  # raw "From" header, e.g. 'Acme HR <hr@acme.com>'
    date: datetime               # timezone-aware send time
    body: str                    # trimmed plain text
    headers: dict = field(default_factory=dict)   # lower-cased header names
    labels: list = field(default_factory=list)

    @property
    def gmail_link(self) -> str:
        return f"https://mail.google.com/mail/u/0/#all/{self.id}"


@dataclass
class Item:
    """One actionable thing extracted from one email."""
    message_id: str
    thread_id: str
    task: str
    deadline: str | None         # "YYYY-MM-DD" or None
    urgency: str                 # high / medium / low
    category: str
    source: str
    gmail_link: str
    sender: str = ""
    is_new: bool = True          # first time we've seen it (this run)
