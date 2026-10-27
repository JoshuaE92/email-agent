import base64

from gmail_client import build_query, clean_body, parse_message


def b64(s):
    return base64.urlsafe_b64encode(s.encode()).decode().rstrip("=")


def test_parse_multipart_prefers_plain_text():
    msg = {"id": "abc", "threadId": "t", "labelIds": ["INBOX"], "payload": {
        "headers": [{"name": "Subject", "value": "Hi"}, {"name": "From", "value": "A <a@b.com>"},
                    {"name": "Date", "value": "Mon, 26 Oct 2026 09:00:00 -0400"},
                    {"name": "List-Unsubscribe", "value": "<x>"}],
        "mimeType": "multipart/alternative",
        "parts": [{"mimeType": "text/plain", "body": {"data": b64("Plain body")}},
                  {"mimeType": "text/html", "body": {"data": b64("<p>HTML body</p>")}}]}}
    e = parse_message(msg)
    assert e.body == "Plain body" and e.subject == "Hi" and "list-unsubscribe" in e.headers
    assert e.date.utcoffset().total_seconds() == -4 * 3600
    assert e.gmail_link.endswith("/abc")


def test_html_only_is_converted_to_text():
    msg = {"id": "x", "payload": {"headers": [], "mimeType": "text/html", "body": {
        "data": b64("<html><style>p{}</style><p>Due&nbsp;Friday</p></html>")}}}
    assert "Due\xa0Friday" in parse_message(msg).body or "Due Friday" in parse_message(msg).body


def test_quoted_reply_history_is_removed_and_body_trimmed():
    text = "Can you confirm by Thursday?\n\nOn Mon, Oct 26, 2026 at 9:00 AM Bob <b@x.com> wrote:\n> old stuff"
    assert clean_body(text) == "Can you confirm by Thursday?"
    assert clean_body("x" * 5000, max_chars=100).endswith("[trimmed]")


def test_query_has_after_timestamp():
    q = build_query(26)
    assert q.startswith("-category:promotions") and " after:" in q
