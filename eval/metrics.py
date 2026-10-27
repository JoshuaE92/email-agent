"""Pure scoring functions for the eval (no network, easy to unit test)."""
from __future__ import annotations

from datetime import date


def _days_apart(a: str | None, b: str | None) -> int | None:
    if a is None or b is None:
        return None
    return abs((date.fromisoformat(a) - date.fromisoformat(b)).days)


def score(rows: list[dict]) -> dict:
    """rows: [{"id", "expected": {...}, "got": {...} | None, "valid_first_try",
               "latency_s", "tokens"}]

    Conventions
      * Positive class = actionable.
      * If the model's output was unusable (got=None), we count it as
        "not actionable" — in production that email would be skipped, so a
        real deadline would be missed.
      * Deadline / category / urgency are scored only on emails that really
        are actionable (that's where those fields matter).
    """
    tp = fp = fn = tn = 0
    dl_exact = dl_within1 = dl_total = 0
    cat_ok = urg_ok = field_total = 0
    mistakes = []

    for r in rows:
        exp, got = r["expected"], r["got"]
        pred = bool(got and got["is_actionable"])
        if exp["is_actionable"] and pred:
            tp += 1
        elif exp["is_actionable"] and not pred:
            fn += 1
            mistakes.append((r["id"], "is_actionable", True,
                             False if got else "INVALID OUTPUT", "MISSED (worst)"))
        elif pred:
            fp += 1
            mistakes.append((r["id"], "is_actionable", False, True, "false alarm"))
        else:
            tn += 1

        if not exp["is_actionable"]:
            continue
        g = got or {}
        dl_total += 1
        field_total += 1
        gd = g.get("deadline")
        if gd == exp["deadline"]:
            dl_exact += 1
            dl_within1 += 1
        else:
            diff = _days_apart(gd, exp["deadline"])
            if diff is not None and diff <= 1:
                dl_within1 += 1
            mistakes.append((r["id"], "deadline", exp["deadline"], gd,
                             f"off by {diff} day(s)" if diff is not None else "null vs date"))
        if g.get("category") == exp["category"]:
            cat_ok += 1
        else:
            mistakes.append((r["id"], "category", exp["category"], g.get("category"), ""))
        if g.get("urgency") == exp["urgency"]:
            urg_ok += 1
        else:
            mistakes.append((r["id"], "urgency", exp["urgency"], g.get("urgency"), ""))

    n = len(rows)
    precision = tp / (tp + fp) if tp + fp else 0.0
    recall = tp / (tp + fn) if tp + fn else 0.0
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    valid_final = sum(1 for r in rows if r["got"] is not None)
    valid_first = sum(1 for r in rows if r.get("valid_first_try"))
    tokens = sum(r.get("tokens", 0) for r in rows)
    return {
        "n": n, "tp": tp, "fp": fp, "fn": fn, "tn": tn,
        "precision": precision, "recall": recall, "f1": f1,
        "deadline_exact": dl_exact / dl_total if dl_total else 0.0,
        "deadline_within1": dl_within1 / dl_total if dl_total else 0.0,
        "category_acc": cat_ok / field_total if field_total else 0.0,
        "urgency_acc": urg_ok / field_total if field_total else 0.0,
        "json_valid_first_try": valid_first / n if n else 0.0,
        "json_valid_after_retry": valid_final / n if n else 0.0,
        "avg_latency_s": sum(r.get("latency_s", 0) for r in rows) / n if n else 0.0,
        "total_tokens": tokens,
        "avg_tokens": tokens / n if n else 0.0,
        "mistakes": mistakes,
    }


PASS_RECALL = 0.95
PASS_DEADLINE = 0.90


def passes(m: dict) -> bool:
    return m["recall"] >= PASS_RECALL and m["deadline_exact"] >= PASS_DEADLINE
