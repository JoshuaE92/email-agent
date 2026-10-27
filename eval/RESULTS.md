# Eval results (Oct 26, 2026)

Synthetic set: 40 hand-labelled emails (25 actionable, 15 not), sent to the real
Groq API from my laptop. Pass bar: **actionable recall ≥ 95%** and **deadline
exact-match ≥ 90%**.

| Model | Prompt | Recall* | Precision | F1 | Deadline exact | Deadline ±1d | Category | Urgency | JSON valid (1st/final) | Avg latency | Tokens / email | Result |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| gpt-oss-120b | v1 | 100% | 100% | 100% | 80% | 84% | 96% | 80% | 100% / 100% | 0.78s | 636 | fail |
| gpt-oss-20b | v1 | 100% | 100% | 100% | 76% | 88% | 92% | 80% | 100% / 100% | 0.54s | 630 | fail |
| gpt-oss-120b | v2 | 96% | 100% | 98% | 92% | 92% | 96% | 92% | 100% / 100% | 0.70s | 1,216 | pass |
| gpt-oss-20b | v2 | 96% | 100% | 98% | 92% | 92% | 100% | 96% | 100% / 100% | 0.55s | 1,219 | pass |
| **gpt-oss-120b** | **v3** | **100%** | **100%** | **100%** | **100%** | **100%** | **100%** | **100%** | 100% / 100% | 0.87s | 1,495 | **pass** |
| gpt-oss-20b | v3 | 100% | 100% | 100% | 96% | 96% | 100% | 100% | 100% / 100% | 0.66s | 1,505 | pass |

\*Recall is the share of truly actionable emails the model flagged. A miss means
a deadline I never hear about, so it's the number that matters most.

Pre-LLM filter: removed 5 of the 15 noise emails for free and wrongly removed 0
actionable ones.

## Verdict

**Good enough. Use `openai/gpt-oss-120b` with prompt `v3`** (now the defaults in
`config.py`).

- It caught every real to-do (25/25), raised no false alarms, and got every
  deadline exactly right.
- 20b is nearly as good: it got one date wrong out of 25 and is about 25% faster.
  On the free tier both models have the same limits, so the faster speed buys
  nothing here, and I'd rather have the extra accuracy.
- Cost: about 1,500 tokens per email. The free tier allows 200K per day per
  model, so roughly 130 emails a day before hitting the cap. A normal day after
  filtering is far less.

## How the prompt improved

1. **v1 → v2: date mistakes.** v1 got only 76–80% of deadlines exactly right.
   Most misses were relative dates: "by Friday" came out a few days off, "this
   Saturday" a day early, and "Tuesday" landed on the wrong week. v2 added a
   14-day calendar to each email and explicit rules for resolving relative dates
   from the *sent* date. Deadline accuracy rose to 92%.
2. **v2 → v3: the new rules over-corrected.** v2 said "announcements aren't
   actionable", and each model then dropped one event invite (the club meeting
   for 120b, the Friendsgiving invite for 20b). Both also left the deadline empty
   on a dentist appointment that said "Reply C to confirm" with no reply date. v3
   says any invitation to a future event counts, narrows the announcement rule,
   and falls back to the appointment date when the action itself has no date.
   That brought recall back to 100% and deadline accuracy to 96–100%.

The v3 worked examples were written to be **different** from the test emails
(haircut, board game night, hackathon, library closure). Copying test emails into
the prompt would inflate the score.

## What it still gets wrong / caveats

- **gpt-oss-20b, v3:** for "call grandma this Saturday" (sent on a Wednesday) it
  answered the following Wednesday instead of that Saturday. Weekday names are
  still the weakest spot for the smaller model.
- **This is an optimistic score.** v3 was written *after* seeing v2's mistakes on
  this same set, so it's partly tuned to these 40 emails. The honest next test is
  my real inbox:
  `python eval/run_eval.py --real 30`, mark the CSV, then
  `python eval/run_eval.py --score <csv>`.
- **The set is small.** With 25 actionable emails, one miss moves recall by 4
  points. "100% vs 96%" really means "missed 0 vs missed 1."
- **Urgency is recalculated in code from the deadline**, so urgency accuracy
  mostly mirrors deadline accuracy.

## Re-running

```bash
python eval/run_eval.py --models openai/gpt-oss-120b,openai/gpt-oss-20b --prompts v2,v3
```

Raw outputs go to `eval/runs/` (gitignored). Each model has a 200K-token daily
cap on the free tier, and one prompt version over 40 emails costs about 60K, so
plan runs accordingly.
