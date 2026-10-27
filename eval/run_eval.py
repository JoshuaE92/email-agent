"""Evaluation harness: how accurate is the LLM extraction?

Synthetic set (eval/dataset.json, hand-labelled):
  python eval/run_eval.py                                  # default model
  python eval/run_eval.py --models openai/gpt-oss-120b,openai/gpt-oss-20b
  python eval/run_eval.py --prompts v1,v2 --models openai/gpt-oss-120b
  python eval/run_eval.py --mock                           # no API key needed (tests the harness)

Your real email:
  python eval/run_eval.py --real 30            # writes eval/real_samples/real_<time>.csv
  # open the CSV, fill the "verdict" column with correct/wrong
  python eval/run_eval.py --score eval/real_samples/real_<time>.csv
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import sys
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from dotenv import load_dotenv  # noqa: E402

import config  # noqa: E402
from extractor import extract  # noqa: E402
from filters import is_noise  # noqa: E402
from llm import DailyLimitReached, LLMResponse, get_llm  # noqa: E402
from main import load_emails_from_file  # noqa: E402
from eval.metrics import PASS_DEADLINE, PASS_RECALL, passes, score  # noqa: E402

EVAL_DIR = os.path.join(ROOT, "eval")
DATASET = os.path.join(EVAL_DIR, "dataset.json")


# ---------------------------------------------------------------------------
# Synthetic set
# ---------------------------------------------------------------------------

class MockLLM:
    """Offline stand-in: returns the expected label (so the harness can be
    tested without an API key). Every 7th email gets a wrong deadline."""

    def __init__(self, dataset):
        self.by_subject = {d["email"]["subject"]: d for d in dataset}
        self.n = 0
        self.model = "mock"

    def complete_json(self, system, user):
        self.n += 1
        subj = user.split("Subject: ", 1)[1].split("\n", 1)[0]
        exp = dict(self.by_subject[subj]["expected"])
        if self.n % 7 == 0 and exp["deadline"]:
            exp["deadline"] = "2026-12-31"
        exp.update(task="mock task" if exp["is_actionable"] else None, source="x", gmail_link="x")
        return LLMResponse(json.dumps(exp), 400, 60, 0.0, "mock")


def run_synthetic(model: str, prompt: str, dataset: list[dict], mock=False, limit=None,
                  log=print) -> dict:
    emails = load_emails_from_file(DATASET)
    pairs = list(zip(dataset, emails))[:limit] if limit else list(zip(dataset, emails))
    llm = MockLLM(dataset) if mock else get_llm(model=model)
    rows = []
    for i, (d, e) in enumerate(pairs, 1):
        today = e.date.date()           # "today" = the day the email was sent
        try:
            res = extract(e, llm, today=today, prompt_version=prompt)
        except DailyLimitReached as err:
            log(f"[{model}] daily limit reached after {i - 1} emails: {err}")
            break
        fatal = [x for x in res.errors if "llm error" in x and any(
            k in x.lower() for k in ("404", "not found", "decommissioned", "401", "invalid api key"))]
        if fatal and not rows:
            log(f"[{model}] model unavailable, skipping it: {fatal[0]}")
            m = score([])
            m.update(model=model + " (UNAVAILABLE)", prompt=prompt, rows=[])
            return m
        rows.append({"id": d["id"], "expected": d["expected"], "got": res.data,
                     "valid_first_try": res.valid_first_try, "latency_s": res.latency_s,
                     "tokens": res.tokens, "errors": res.errors})
        log(f"[{model} {prompt}] {i}/{len(pairs)} {d['id']}: "
            f"{'OK ' if res.data else 'BAD'} {json.dumps(res.data)[:110] if res.data else res.errors}")
    m = score(rows)
    m.update(model=model, prompt=prompt, rows=rows)
    return m


def filter_report(dataset: list[dict]) -> dict:
    """What would the cheap pre-LLM filter do on this set?"""
    emails = load_emails_from_file(DATASET)
    dropped_real, dropped_noise, kept = [], 0, 0
    for d, e in zip(dataset, emails):
        skip, reason = is_noise(e)
        if skip and d["expected"]["is_actionable"]:
            dropped_real.append((d["id"], reason))
        elif skip:
            dropped_noise += 1
        else:
            kept += 1
    n_noise = sum(1 for d in dataset if not d["expected"]["is_actionable"])
    return {"dropped_real": dropped_real, "dropped_noise": dropped_noise,
            "noise_total": n_noise, "kept": kept}


def pct(x):
    return f"{100 * x:.1f}%"


def format_table(results: list[dict]) -> str:
    cols = [("Model", lambda m: m["model"]), ("Prompt", lambda m: m["prompt"]),
            ("Emails", lambda m: str(m["n"])),
            ("Recall*", lambda m: pct(m["recall"])), ("Precision", lambda m: pct(m["precision"])),
            ("F1", lambda m: pct(m["f1"])),
            ("Deadline exact", lambda m: pct(m["deadline_exact"])),
            ("Deadline ±1d", lambda m: pct(m["deadline_within1"])),
            ("Category", lambda m: pct(m["category_acc"])),
            ("Urgency", lambda m: pct(m["urgency_acc"])),
            ("JSON valid (1st/final)",
             lambda m: f"{pct(m['json_valid_first_try'])} / {pct(m['json_valid_after_retry'])}"),
            ("Avg latency", lambda m: f"{m['avg_latency_s']:.2f}s"),
            ("Tokens (total / per email)", lambda m: f"{m['total_tokens']:,} / {m['avg_tokens']:.0f}"),
            ("PASS?", lambda m: "PASS" if passes(m) else "fail")]
    lines = ["| " + " | ".join(c for c, _ in cols) + " |",
             "|" + "|".join("---" for _ in cols) + "|"]
    for m in results:
        lines.append("| " + " | ".join(f(m) for _, f in cols) + " |")
    return "\n".join(lines)


def format_mistakes(m: dict) -> str:
    out = [f"\n### Mistakes: {m['model']} / prompt {m['prompt']} ({len(m['mistakes'])})\n",
           "| Email | Field | Expected | Got | Note |", "|---|---|---|---|---|"]
    for mid, field, exp, got, note in m["mistakes"]:
        out.append(f"| {mid} | {field} | {exp} | {got} | {note} |")
    return "\n".join(out)


def synthetic_main(args):
    with open(DATASET) as f:
        dataset = json.load(f)
    models = [m.strip() for m in (args.models or config.LLM_MODEL).split(",") if m.strip()]
    prompts = [p.strip() for p in (args.prompts or config.PROMPT_VERSION).split(",")]
    combos = [(m, p) for m in models for p in prompts]

    # Groq rate limits are per model, so different models can run in parallel;
    # prompts for the same model run one after another.
    def run_model(model):
        return [run_synthetic(model, p, dataset, mock=args.mock, limit=args.limit,
                              log=(lambda *a: None) if args.quiet else print)
                for p in prompts]

    with ThreadPoolExecutor(max_workers=len(models)) as pool:
        by_model = list(pool.map(run_model, models))
    results = [r for group in by_model for r in group]
    results.sort(key=lambda m: combos.index((m["model"], m["prompt"])))

    fr = filter_report(dataset)
    report = [f"# Eval run {datetime.now():%Y-%m-%d %H:%M}\n",
              f"Dataset: {len(dataset)} emails "
              f"({sum(d['expected']['is_actionable'] for d in dataset)} actionable). "
              f"Pass bar: recall ≥ {pct(PASS_RECALL)} and deadline exact ≥ {pct(PASS_DEADLINE)}.\n",
              format_table(results),
              "\n*Recall = share of truly actionable emails the model flagged. "
              "A miss means a deadline you never hear about.\n",
              f"**Pre-LLM filter:** dropped {fr['dropped_noise']}/{fr['noise_total']} noise emails "
              f"for free; wrongly dropped {len(fr['dropped_real'])} actionable "
              f"{[x[0] for x in fr['dropped_real']]}.\n"]
    for m in results:
        report.append(format_mistakes(m))
    text = "\n".join(report)
    print("\n" + text)

    os.makedirs(os.path.join(EVAL_DIR, "runs"), exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    with open(os.path.join(EVAL_DIR, "runs", f"report_{stamp}.md"), "w") as f:
        f.write(text)
    with open(os.path.join(EVAL_DIR, "runs", f"raw_{stamp}.json"), "w") as f:
        json.dump([{k: v for k, v in m.items()} for m in results], f, indent=2, default=str)
    print(f"\nSaved eval/runs/report_{stamp}.md and raw_{stamp}.json")
    if args.write_results:
        path = os.path.join(EVAL_DIR, "RESULTS.md")
        with open(path, "w") as f:
            f.write(results_markdown(results, dataset, fr))
        print(f"Wrote {os.path.relpath(path, ROOT)}")
    return results


def results_markdown(results: list[dict], dataset: list[dict], fr: dict) -> str:
    """Auto-written eval/RESULTS.md: table, plain-language verdict, error themes."""
    tags = {d["id"]: d["tags"] for d in dataset}
    passing = [m for m in results if passes(m)]
    rank = lambda m: (m["recall"], m["deadline_exact"], m["category_acc"], -m["avg_tokens"])
    best = max(passing or results, key=rank)

    lines = [f"# Eval results ({datetime.now():%Y-%m-%d})\n",
             f"Synthetic set: {len(dataset)} hand-labelled emails "
             f"({sum(d['expected']['is_actionable'] for d in dataset)} actionable). "
             f"Pass bar: actionable recall ≥ {pct(PASS_RECALL)} and deadline exact-match "
             f"≥ {pct(PASS_DEADLINE)}.\n", format_table(results), "",
             "## Verdict\n"]
    if passing:
        lines.append(f"**Good enough.** {len(passing)} of {len(results)} configurations pass. "
                     f"Use **{best['model']}** with prompt **{best['prompt']}**: it caught "
                     f"{best['tp']} of {best['tp'] + best['fn']} real to-dos (recall "
                     f"{pct(best['recall'])}) and got {pct(best['deadline_exact'])} of deadlines "
                     f"exactly right, at ~{best['avg_tokens']:.0f} tokens per email.")
    else:
        lines.append(f"**Not good enough yet.** No configuration hit both bars. Closest: "
                     f"**{best['model']} / {best['prompt']}** (recall {pct(best['recall'])}, "
                     f"deadline {pct(best['deadline_exact'])}). Suggested prompt fixes: see the "
                     f"error themes below and add a rule plus a worked example for each.")
    lines.append(f"\nPre-LLM filter: removed {fr['dropped_noise']} of {fr['noise_total']} noise "
                 f"emails for free and wrongly removed {len(fr['dropped_real'])} actionable "
                 f"email(s) {[x[0] for x in fr['dropped_real']]}.\n")
    lines.append("## What it gets wrong (by email type)\n")
    for m in results:
        counts = {}
        for mid, field, *_ in m["mistakes"]:
            for t in tags.get(mid, []):
                counts[t] = counts.get(t, 0) + 1
        top = ", ".join(f"{t} ({c})" for t, c in sorted(counts.items(), key=lambda x: -x[1])[:6])
        lines.append(f"- **{m['model']} / {m['prompt']}**: {top or 'no mistakes'}")
    for m in results:
        lines.append(format_mistakes(m))
    return "\n".join(lines) + "\n"


# ---------------------------------------------------------------------------
# Real emails
# ---------------------------------------------------------------------------

CSV_FIELDS = ["verdict", "expected_actionable", "notes", "message_id", "date", "sender",
              "subject", "filter_skipped", "filter_reason", "is_actionable", "task",
              "deadline", "urgency", "category", "gmail_link"]


def real_main(args):
    from gmail_client import fetch_recent
    emails = fetch_recent(query=config.GMAIL_QUERY, max_emails=args.real)
    llm = get_llm(model=args.models.split(",")[0] if args.models else None)
    prompt = (args.prompts or config.PROMPT_VERSION).split(",")[0]
    out_dir = os.path.join(EVAL_DIR, "real_samples")
    os.makedirs(out_dir, exist_ok=True)
    path = os.path.join(out_dir, f"real_{datetime.now():%Y%m%d_%H%M%S}.csv")
    with open(path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=CSV_FIELDS)
        w.writeheader()
        for i, e in enumerate(emails, 1):
            skip, reason = is_noise(e)
            row = {"message_id": e.id, "date": e.date.isoformat(), "sender": e.sender,
                   "subject": e.subject, "filter_skipped": skip, "filter_reason": reason,
                   "gmail_link": e.gmail_link, "verdict": "", "expected_actionable": "",
                   "notes": ""}
            if not skip:
                res = extract(e, llm, today=e.date.date(), prompt_version=prompt)
                d = res.data or {}
                row.update(is_actionable=d.get("is_actionable", "INVALID"),
                           task=d.get("task"), deadline=d.get("deadline"),
                           urgency=d.get("urgency"), category=d.get("category"))
            w.writerow(row)
            print(f"{i}/{len(emails)} {'SKIP' if skip else 'LLM '} {e.subject[:60]}")
    print(f"\nWrote {path}\nOpen it, put 'correct' or 'wrong' in the verdict column for each row.\n"
          "For wrong rows, put y/n in expected_actionable (should it have been flagged?).\n"
          f"Then run: python eval/run_eval.py --score {os.path.relpath(path, ROOT)}")


def score_csv(path: str):
    with open(path, newline="") as f:
        rows = list(csv.DictReader(f))
    marked = [r for r in rows if r["verdict"].strip().lower() in ("correct", "wrong", "c", "w", "y", "n")]
    if not marked:
        sys.exit("No rows marked yet. Fill the 'verdict' column with correct/wrong.")
    ok = lambda r: r["verdict"].strip().lower() in ("correct", "c", "y")
    flagged = lambda r: r["filter_skipped"] != "True" and r["is_actionable"] == "True"

    def truly_actionable(r):
        if ok(r):
            return flagged(r)
        e = r["expected_actionable"].strip().lower()
        return e in ("y", "yes", "true", "1") if e else not flagged(r)

    tp = sum(1 for r in marked if flagged(r) and truly_actionable(r))
    fp = sum(1 for r in marked if flagged(r) and not truly_actionable(r))
    fn = sum(1 for r in marked if not flagged(r) and truly_actionable(r))
    correct = sum(1 for r in marked if ok(r))
    print(f"Marked rows: {len(marked)} / {len(rows)}")
    print(f"Overall correct: {correct}/{len(marked)} = {pct(correct / len(marked))}")
    print(f"Actionable recall:    {pct(tp / (tp + fn)) if tp + fn else 'n/a'}  (missed {fn})")
    print(f"Actionable precision: {pct(tp / (tp + fp)) if tp + fp else 'n/a'}  (false alarms {fp})")
    misses = [r for r in marked if not flagged(r) and truly_actionable(r)]
    if misses:
        print("\nMissed (should have alerted):")
        for r in misses:
            why = "filtered: " + r["filter_reason"] if r["filter_skipped"] == "True" else "LLM said no"
            print(f"  - {r['subject'][:70]}  [{why}]")


def main(argv=None):
    load_dotenv(os.path.join(ROOT, ".env"))
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--models", help="comma-separated Groq model IDs")
    ap.add_argument("--prompts", help="comma-separated prompt versions from prompts.py (e.g. v1,v2)")
    ap.add_argument("--limit", type=int, help="only the first N emails (quick check)")
    ap.add_argument("--mock", action="store_true", help="offline fake model, tests the harness")
    ap.add_argument("--quiet", action="store_true")
    ap.add_argument("--write-results", action="store_true",
                    help="also (over)write eval/RESULTS.md with the table and verdict")
    ap.add_argument("--real", type=int, metavar="N", help="run on your last N real emails")
    ap.add_argument("--score", metavar="CSV", help="score a CSV you marked by hand")
    args = ap.parse_args(argv)
    if args.score:
        return score_csv(args.score)
    if args.real:
        return real_main(args)
    return synthetic_main(args)


if __name__ == "__main__":
    main()
