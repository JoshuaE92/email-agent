import json

import pytest

from schema import ValidationError, parse_and_validate
from tests.helpers import answer


def test_valid_answer_passes():
    d = parse_and_validate(answer())
    assert d["is_actionable"] is True and d["deadline"] == "2026-10-30"


def test_enum_values_are_normalized():
    d = parse_and_validate(answer(urgency=" HIGH ", category="School"))
    assert d["urgency"] == "high" and d["category"] == "school"


def test_null_deadline_and_string_null():
    assert parse_and_validate(answer(deadline=None))["deadline"] is None
    assert parse_and_validate(answer(deadline="null"))["deadline"] is None


def test_code_fences_are_stripped():
    assert parse_and_validate("```json\n" + answer() + "\n```")["task"] == "Do the thing"


def test_not_actionable_may_have_null_task():
    d = parse_and_validate(answer(is_actionable=False, task=None, deadline=None))
    assert d["task"] is None


def test_unknown_keys_are_dropped():
    raw = json.loads(answer()); raw["confidence"] = 0.9
    assert "confidence" not in parse_and_validate(json.dumps(raw))


@pytest.mark.parametrize("bad, msg", [
    ("not json at all", "not valid JSON"),
    ("[1, 2]", "must be an object"),
    (answer(urgency="critical"), "urgency"),
    (answer(category="work"), "category"),
    (answer(deadline="Friday"), "YYYY-MM-DD"),
    (answer(deadline="2026-02-30"), "not a real date"),
    (answer(deadline="10/30/2026"), "YYYY-MM-DD"),
    (answer(is_actionable="yes"), "true/false"),
    (answer(task=""), "task is required"),
])
def test_invalid_answers_raise(bad, msg):
    with pytest.raises(ValidationError, match=msg):
        parse_and_validate(bad)


def test_missing_key_raises():
    raw = json.loads(answer()); del raw["deadline"]
    with pytest.raises(ValidationError, match="missing key 'deadline'"):
        parse_and_validate(json.dumps(raw))
