"""The shape every LLM answer must have, and a small validator for it.

We hand-write the validator instead of adding the `jsonschema` package to
keep dependencies small. EXTRACTION_SCHEMA is a normal JSON Schema, so it
also documents the contract (and could be sent to providers that support
schema-constrained output).
"""
import json
import re
from datetime import date

CATEGORIES = ["career", "school", "bills", "appointments", "events", "personal", "other"]
URGENCIES = ["high", "medium", "low"]

EXTRACTION_SCHEMA = {
    "type": "object",
    "required": ["is_actionable", "task", "deadline", "urgency", "category",
                 "source", "gmail_link"],
    "properties": {
        "is_actionable": {"type": "boolean"},
        "task": {"type": ["string", "null"]},
        "deadline": {"type": ["string", "null"], "format": "date"},
        "urgency": {"enum": URGENCIES},
        "category": {"enum": CATEGORIES},
        "source": {"type": "string"},
        "gmail_link": {"type": "string"},
    },
    "additionalProperties": False,
}

_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


class ValidationError(ValueError):
    pass


def parse_and_validate(raw: str) -> dict:
    """Turn the model's raw text into a clean dict, or raise ValidationError.

    Small, safe clean-ups are allowed (trim spaces, lower-case enum values,
    "null" string -> None, drop unknown keys). Anything else is an error.
    """
    if raw is None:
        raise ValidationError("empty response")
    text = raw.strip()
    # Some models wrap JSON in ```json fences even in JSON mode.
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text, flags=re.S).strip()
    try:
        data = json.loads(text)
    except json.JSONDecodeError as e:
        raise ValidationError(f"not valid JSON: {e.msg}") from e
    if not isinstance(data, dict):
        raise ValidationError("top-level JSON must be an object")
    return validate(data)


def validate(data: dict) -> dict:
    errors = []
    out = {}

    for key in EXTRACTION_SCHEMA["required"]:
        if key not in data:
            errors.append(f"missing key '{key}'")
    if errors:
        raise ValidationError("; ".join(errors))

    # is_actionable: must be a real boolean
    if not isinstance(data["is_actionable"], bool):
        errors.append("is_actionable must be true/false")
    out["is_actionable"] = data["is_actionable"]

    # task
    task = data["task"]
    if task is not None and not isinstance(task, str):
        errors.append("task must be a string or null")
    task = (task or "").strip() if isinstance(task, (str, type(None))) else task
    if data["is_actionable"] is True and not task:
        errors.append("task is required when is_actionable is true")
    out["task"] = task or None

    # deadline: YYYY-MM-DD that is a real calendar date, or null
    dl = data["deadline"]
    if isinstance(dl, str) and dl.strip().lower() in ("", "null", "none", "n/a"):
        dl = None
    if dl is not None:
        if not isinstance(dl, str) or not _DATE_RE.match(dl.strip()):
            errors.append(f"deadline must be YYYY-MM-DD or null, got {dl!r}")
        else:
            try:
                date.fromisoformat(dl.strip())
                dl = dl.strip()
            except ValueError:
                errors.append(f"deadline is not a real date: {dl!r}")
    out["deadline"] = dl

    # enums
    for key, allowed in (("urgency", URGENCIES), ("category", CATEGORIES)):
        val = data[key]
        val = val.strip().lower() if isinstance(val, str) else val
        if val not in allowed:
            errors.append(f"{key} must be one of {allowed}, got {data[key]!r}")
        out[key] = val

    for key in ("source", "gmail_link"):
        val = data[key]
        if val is None:
            val = ""
        if not isinstance(val, str):
            errors.append(f"{key} must be a string")
        out[key] = val.strip() if isinstance(val, str) else val

    if errors:
        raise ValidationError("; ".join(errors))
    return out
