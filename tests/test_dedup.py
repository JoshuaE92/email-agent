from datetime import date

from dedup import StateStore, jaccard, task_hash
from models import Item


def item(msg="m1", task="Complete background check", sender="Checkr <noreply@checkr.com>",
         deadline="2026-10-30", thread="t1", category="career"):
    return Item(message_id=msg, thread_id=thread, task=task, deadline=deadline, urgency="high",
                category=category, source="Checkr", gmail_link=f"https://x/{msg}", sender=sender)


def test_hash_ignores_case_order_punctuation():
    a = task_hash("Submit the I-9 form!", "hr@acme.com", "2026-11-01")
    b = task_hash("i 9 FORM submit", "HR <hr@acme.com>", "2026-11-01")
    assert a == b


def test_hash_differs_by_deadline_and_sender():
    assert task_hash("Pay bill", "a@duke.com", "2026-10-01") != task_hash("Pay bill", "a@duke.com", "2026-11-01")
    assert task_hash("Pay bill", "a@duke.com") != task_hash("Pay bill", "a@fpl.com")


def test_same_message_id_is_duplicate():
    s = StateStore(":memory:")
    s.add_item(item())
    assert s.find_duplicate(item(task="something else entirely")) == "same message id"


def test_same_task_from_new_email_is_duplicate():
    s = StateStore(":memory:")
    s.add_item(item())
    assert s.find_duplicate(item(msg="m2", thread="t2")) == "same task hash"


def test_reminder_email_with_different_wording_is_duplicate():
    s = StateStore(":memory:")
    s.add_item(item(task="Complete your Checkr background check"))
    reminder = item(msg="m2", thread="t9", task="Reminder: finish Checkr background check",
                    deadline=None)
    assert (s.find_duplicate(reminder) or "").startswith("reminder of")


def test_similar_task_from_different_sender_is_new():
    s = StateStore(":memory:")
    s.add_item(item(task="Complete background check"))
    other = item(msg="m2", thread="t2", sender="HireRight <noreply@hireright.com>")
    assert s.find_duplicate(other) is None


def test_next_months_bill_is_not_a_reminder():
    s = StateStore(":memory:")
    s.add_item(item(task="Pay Duke Energy bill", sender="Duke <bill@duke.com>", deadline="2026-10-15"))
    nxt = item(msg="m2", thread="t2", task="Pay Duke Energy bill", sender="Duke <bill@duke.com>",
               deadline="2026-11-15")
    assert s.find_duplicate(nxt) is None


def test_two_friends_on_gmail_are_different_senders():
    s = StateStore(":memory:")
    s.add_item(item(task="Send slides to Sam", sender="Sam <sam@gmail.com>"))
    other = item(msg="m2", thread="t2", task="Send slides to Ana", sender="Ana <ana@gmail.com>")
    assert s.find_duplicate(other) is None


def test_processed_and_runs_persist(tmp_path):
    path = str(tmp_path / "state.sqlite")
    s = StateStore(path)
    s.mark_processed("m1", "noise")
    s.mark_ran(date(2026, 10, 26))
    s.close()
    s2 = StateStore(path)
    assert s2.is_processed("m1") and not s2.is_processed("m2")
    assert s2.ran_on(date(2026, 10, 26))


def test_dry_run_copy_does_not_touch_disk(tmp_path):
    path = str(tmp_path / "state.sqlite")
    StateStore(path).close()
    copy = StateStore.in_memory_copy(path)
    copy.mark_processed("m1", "x")
    assert not StateStore(path).is_processed("m1")


def test_open_items_drops_old_ones():
    s = StateStore(":memory:")
    s.add_item(item(msg="a", task="Old thing", deadline="2026-10-01"))
    s.add_item(item(msg="b", task="Soon thing", deadline="2026-10-27"))
    s.add_item(item(msg="c", task="Just overdue", deadline="2026-10-25"))
    tasks = {r["task"] for r in s.open_items(date(2026, 10, 26))}
    assert tasks == {"Soon thing", "Just overdue"}


def test_jaccard():
    assert jaccard("Complete background check", "background check") == 1.0
    assert jaccard("pay rent", "study for exam") == 0.0
