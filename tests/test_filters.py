import pytest

from filters import is_noise
from tests.helpers import make_email

NOISE = [
    make_email(subject="This week in tech: top stories", sender="Digest <news@techweekly.com>",
               headers={"List-Unsubscribe": "<mailto:u@x.com>"}),
    make_email(subject="40% off everything this weekend", sender="Store <noreply@shop.com>",
               body="Shop now, limited time."),
    make_email(subject="Your receipt from Chipotle", sender="Chipotle <receipts@chipotle.com>",
               body="Thanks! Total $12.40"),
    make_email(subject="Your order has shipped", sender="Amazon <ship-confirm@amazon.com>"),
    make_email(subject="Payment received - thank you", sender="Comcast <billing@comcast.net>"),
]

KEEP = [
    # Interview invite from a no-reply ATS with List-Unsubscribe — rescue keyword wins.
    make_email(subject="Interview invitation: Software Engineer Intern",
               sender="Greenhouse <no-reply@greenhouse.io>",
               headers={"List-Unsubscribe": "<mailto:u@x.com>"}),
    make_email(subject="Action required: complete your background check",
               sender="Checkr <noreply@checkr.com>", headers={"List-Unsubscribe": "x"}),
    make_email(subject="Your bill is ready - amount due Nov 3", sender="Duke Energy <noreply@duke.com>",
               headers={"List-Unsubscribe": "x"}),
    make_email(subject="Homework 5 posted", sender="Canvas <notifications@instructure.com>",
               body="Assignment due Friday"),
    make_email(subject="quick question", sender="Sam <sam@gmail.com>",
               body="Can you send me the slides when you get a chance?"),
    make_email(subject="Office hours moved", sender="Prof Lee <lee@ucf.edu>",
               headers={"List-Unsubscribe": "x"}),
]


@pytest.mark.parametrize("email", NOISE, ids=lambda e: e.subject[:30])
def test_noise_is_skipped(email):
    skip, reason = is_noise(email)
    assert skip, reason


@pytest.mark.parametrize("email", KEEP, ids=lambda e: e.subject[:30])
def test_real_stuff_is_kept(email):
    skip, reason = is_noise(email)
    assert not skip, reason


def test_rescue_keyword_needs_whole_word():
    # "form" must not match "information"; "sign" must not match "design".
    e = make_email(subject="More information about our design newsletter",
                   sender="x <news@brand.com>", headers={"List-Unsubscribe": "x"})
    assert is_noise(e)[0]
