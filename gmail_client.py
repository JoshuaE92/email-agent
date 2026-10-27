"""Reads recent email from Gmail (read-only).

Authentication: we never store a password. A one-time browser login
(scripts/get_refresh_token.py) gives a long-lived *refresh token*. Every run,
the Google library trades that refresh token for a short-lived access token.
The scope is gmail.readonly, so this code physically cannot send, delete or
change anything in the mailbox.
"""
from __future__ import annotations

import base64
import html
import os
import re
import time
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from html.parser import HTMLParser

import config
from models import Email


def get_service():
    from google.oauth2.credentials import Credentials
    from googleapiclient.discovery import build

    missing = [k for k in ("GMAIL_CLIENT_ID", "GMAIL_CLIENT_SECRET", "GMAIL_REFRESH_TOKEN")
               if not os.environ.get(k)]
    if missing:
        raise RuntimeError(f"Missing env vars: {', '.join(missing)}")
    creds = Credentials(
        token=None,
        refresh_token=os.environ["GMAIL_REFRESH_TOKEN"],
        client_id=os.environ["GMAIL_CLIENT_ID"],
        client_secret=os.environ["GMAIL_CLIENT_SECRET"],
        token_uri="https://oauth2.googleapis.com/token",
        scopes=config.GMAIL_SCOPES,
    )
    return build("gmail", "v1", credentials=creds, cache_discovery=False)


def build_query(hours: int = config.LOOKBACK_HOURS, base: str = config.GMAIL_QUERY) -> str:
    after = int(time.time() - hours * 3600)
    return f"{base} after:{after}".strip()


def fetch_recent(service=None, hours: int = config.LOOKBACK_HOURS,
                 max_emails: int = config.MAX_EMAILS_PER_RUN, query: str | None = None) -> list[Email]:
    """Newest first. `query=None` means 'the configured query, last N hours'."""
    service = service or get_service()
    q = build_query(hours) if query is None else query
    ids, page = [], None
    while len(ids) < max_emails:
        resp = service.users().messages().list(
            userId="me", q=q, maxResults=min(100, max_emails - len(ids)), pageToken=page
        ).execute()
        ids += [m["id"] for m in resp.get("messages", [])]
        page = resp.get("nextPageToken")
        if not page:
            break
    emails = []
    for mid in ids[:max_emails]:
        msg = service.users().messages().get(userId="me", id=mid, format="full").execute()
        emails.append(parse_message(msg))
    return emails


def parse_message(msg: dict) -> Email:
    payload = msg.get("payload", {})
    headers = {h["name"].lower(): h["value"] for h in payload.get("headers", [])}
    try:
        sent = parsedate_to_datetime(headers.get("date", ""))
        if sent.tzinfo is None:
            sent = sent.replace(tzinfo=timezone.utc)
    except (TypeError, ValueError):
        sent = datetime.fromtimestamp(int(msg.get("internalDate", "0")) / 1000, tz=timezone.utc)
    return Email(
        id=msg["id"],
        thread_id=msg.get("threadId", ""),
        subject=headers.get("subject", "(no subject)"),
        sender=headers.get("from", ""),
        date=sent,
        body=clean_body(extract_text(payload) or msg.get("snippet", "")),
        headers=headers,
        labels=msg.get("labelIds", []),
    )


# ---- body helpers -----------------------------------------------------------

def _decode(data: str) -> str:
    return base64.urlsafe_b64decode(data + "=" * (-len(data) % 4)).decode("utf-8", "replace")


def extract_text(payload: dict) -> str:
    """Prefer text/plain; fall back to HTML converted to text."""
    plain, htmls = [], []

    def walk(part):
        mime = part.get("mimeType", "")
        data = part.get("body", {}).get("data")
        if data and mime == "text/plain":
            plain.append(_decode(data))
        elif data and mime == "text/html":
            htmls.append(_decode(data))
        for p in part.get("parts", []) or []:
            walk(p)

    walk(payload)
    if plain:
        return "\n".join(plain)
    if htmls:
        return html_to_text("\n".join(htmls))
    return ""


class _TextExtractor(HTMLParser):
    def __init__(self):
        super().__init__()
        self.out, self.skip = [], 0

    def handle_starttag(self, tag, attrs):
        if tag in ("script", "style", "head"):
            self.skip += 1
        if tag in ("br", "p", "div", "tr", "li", "h1", "h2", "h3"):
            self.out.append("\n")

    def handle_endtag(self, tag):
        if tag in ("script", "style", "head") and self.skip:
            self.skip -= 1

    def handle_data(self, data):
        if not self.skip:
            self.out.append(data)


def html_to_text(s: str) -> str:
    p = _TextExtractor()
    p.feed(s)
    return html.unescape("".join(p.out))


_QUOTE_MARKERS = [
    re.compile(r"^On .{5,120} wrote:\s*$", re.M),          # Gmail/Apple reply header
    re.compile(r"^-{2,} ?Original Message ?-{2,}", re.M | re.I),
    re.compile(r"^From: .+\nSent: ", re.M),                 # Outlook
]


def clean_body(text: str, max_chars: int = config.MAX_BODY_CHARS) -> str:
    """Drop quoted reply history, collapse whitespace, cut to max_chars.

    The newest message in a thread is at the top, which is the part that
    matters (e.g. "Can you confirm by Thursday?").
    """
    text = text.replace("\r\n", "\n")
    for pat in _QUOTE_MARKERS:
        m = pat.search(text)
        if m and text[:m.start()].strip():  # keep it if the whole email is a quote
            text = text[:m.start()]
    text = "\n".join(l for l in text.split("\n") if not l.lstrip().startswith(">"))
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n\s*\n+", "\n\n", text).strip()
    if len(text) > max_chars:
        text = text[:max_chars] + " …[trimmed]"
    return text
