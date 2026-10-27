# email-agent

A personal assistant that reads my Gmail every morning, uses an LLM to find
anything coming up or waiting on me, and pushes the results to my phone.
It comes with an evaluation harness that measures how accurate the LLM is.

```
GitHub Actions, 8 AM ET
        │
        ▼
 Gmail (read-only) ──► cheap noise filter ──► LLM (Groq, JSON) ──► schema check
   last 26 hours          skips newsletters,     "is this a to-do?     retry once,
                          receipts, ads          deadline? category?"  then skip
                                                        │
                                                        ▼
                                     dedup (SQLite): same email? same task? a reminder?
                                                        │
                                                        ▼
                                   ntfy.sh ──► phone: morning summary + urgent alerts
```

Setup steps are in **[SETUP.md](SETUP.md)**. Eval results are in
**[eval/RESULTS.md](eval/RESULTS.md)**.

---

## How each file works

| File | What it does, in plain language |
|---|---|
| `config.py` | Every setting in one place: the Gmail search, the noise rules, the model names, rate limits, time zone and alert window. Secrets are **not** here. They come from environment variables. |
| `models.py` | Two small data shapes: an `Email` and an `Item` (one to-do pulled out of an email). |
| `gmail_client.py` | Logs in to Gmail with a refresh token and the **read-only** scope, so it physically can't send or delete. It searches the last 26 hours, pulls the plain text out of each email (converting from HTML if needed), cuts off quoted reply history and trims the text to 3,000 characters to save tokens. |
| `filters.py` | Free rules that run before the LLM. It skips mass mail (`List-Unsubscribe` header), automated marketing, and receipts or shipping notices. **Rescue keywords** like "interview", "due", "assessment" or "meeting" always win, because missing a real deadline is worse than one extra LLM call. |
| `prompts.py` | The instructions sent to the LLM, kept in versions (`v1` short → `v2` date fixes → `v3` event/appointment fixes, the current default) so the eval can compare them. See eval/RESULTS.md for how each version scored. Each email message includes today's date, the sent date and a 14-day calendar, so "by Friday" becomes a lookup instead of date arithmetic. |
| `llm.py` | A small interface: the rest of the code only calls `complete_json(system, user)`. `GroqLLM` handles the details. It uses JSON mode, **paces** requests to fit the free tier (sliding 60-second window over requests and tokens), and retries **429 rate limits** with exponential backoff (2s, 4s, 8s…), respecting Groq's `retry-after` header. If Groq says "come back in an hour" (daily cap), it stops politely. Switching provider means adding one class and one line in `get_llm()`. |
| `schema.py` | The contract for every LLM answer: `is_actionable, task, deadline, urgency, category, source, gmail_link`. It's a hand-written validator, which saved adding another dependency. It checks types, allowed values and that the deadline is a real `YYYY-MM-DD` date, and it allows safe clean-ups like lower-casing "High". |
| `extractor.py` | One email in, one validated answer out. If the answer is broken, it tells the model what was wrong and asks **once** more. If it's still broken, it skips the email and never crashes. It always overwrites `gmail_link` with the real link (never trust a URL the model wrote) and recalculates urgency from the deadline in code. |
| `dedup.py` | Memory in `data/state.sqlite`. Three checks, in order: (1) **same Gmail message ID**: the 26-hour window overlaps the previous day on purpose; (2) **same normalized task hash**: lower-case, no punctuation, filler words removed, words sorted, plus sender domain and deadline; (3) **reminder detection**: same sender (or thread) and ≥ 50% word overlap (Jaccard), with deadlines no more than 14 days apart, so next month's bill still counts as new. It also tracks which items already got an urgent alert. |
| `notifier.py` | Builds and sends the ntfy messages. **Morning summary**: every open item, grouped by category and sorted by deadline, marked "NEW" if it's new; it says "Nothing urgent today" when empty and splits under ntfy's 4 KB limit. **Urgent alert**: priority 4–5, one per item that's overdue or due within 48 hours (today, tomorrow or the day after), sent **once** per item, and tapping it opens Gmail. |
| `main.py` | Connects the pieces: fetch → filter → extract → dedup → notify. `--dry-run` works on a throwaway in-memory copy of the database and prints instead of sending. `--from-file` reads emails from JSON instead of Gmail. `--scheduled` is the daylight-saving guard described below. |
| `scripts/get_refresh_token.py` | Run once on your laptop. It opens Google login and prints the refresh token to paste into GitHub Secrets. |
| `deploy/daily.yml` | The GitHub Actions workflow. Move it to `.github/workflows/` (SETUP step 11). It runs the tests, runs the agent, then commits `data/state.sqlite` back so tomorrow's run remembers today. |
| `tests/` | 63 unit tests using fake emails and a fake LLM: dedup, JSON validation, noise filtering, retry and backoff, notification formatting, Gmail parsing, eval metrics, and a two-day end-to-end run proving that reminders and repeat alerts are suppressed. |
| `eval/` | The evaluation harness. See below. |

---

## The evaluation harness (and what the numbers mean)

**Why it exists:** before trusting an LLM with my deadlines, I want to measure
it, not eyeball it.

**`eval/dataset.json`** has 40 realistic synthetic emails (made-up companies)
with labels I wrote by hand (25 actionable, 15 not). It covers interview
invites, OAs, onboarding, background checks, repeated reminders, rejections,
bills, class assignments, appointments, event invites, newsletters, receipts,
and the tricky cases: "by Friday", deadlines buried in paragraph 3, emails that
mention a past date, two dates in one email, and replies where someone is
waiting on me. The source is `eval/build_dataset.py`, which also documents the
labeling rules. In the eval, "today" is the email's sent date, so every relative
date has exactly one right answer.

**`eval/run_eval.py`** runs the real extractor on every email and compares its
answer with the label.

| Metric | Plain meaning | Why it matters |
|---|---|---|
| **Recall** (actionable) | Of the emails that really needed action, what % did it catch? | **The most important number.** A miss is a deadline I never hear about. Pass bar: ≥ 95%. |
| **Precision** | Of the emails it flagged, what % really needed action? | Low precision means noisy alerts: annoying, but not dangerous. |
| **F1** | One number balancing precision and recall. | Handy for ranking models. |
| **Deadline exact** | On real to-dos, % where the date is exactly right (no deadline counts as right only if there truly is none). | A wrong date is almost as bad as a miss. Pass bar: ≥ 90%. |
| **Deadline ±1 day** | Same, but off-by-one counts as right. | If this is much higher than exact, the model has the right idea but fumbles the date math. |
| **Category / Urgency** | % correct on real to-dos. | Affects grouping and which items get the high-priority alert. |
| **JSON valid (1st / final)** | % of answers that passed the schema on the first try / after the one retry. | Shows whether the retry logic is earning its keep. |
| **Latency, tokens** | Seconds and tokens per email. | Cost and speed, and whether a day's mail fits the free tier (about 200K tokens/day per model). |

An invalid answer counts as "not actionable", because in production that email
would be skipped. The harness also prints **every mistake** (expected vs got)
and checks the pre-LLM filter: how much noise it removed for free, and whether
it wrongly dropped anything real.

```bash
python eval/run_eval.py --models openai/gpt-oss-120b,openai/gpt-oss-20b --prompts v1,v2 --write-results
python eval/run_eval.py --mock          # offline, tests the harness itself
python eval/run_eval.py --real 30       # your last 30 real emails -> CSV in eval/real_samples/ (gitignored)
python eval/run_eval.py --score eval/real_samples/real_<time>.csv   # after you mark rows correct/wrong
```

---

## Choices I made (and why)

- **Models.** I was asked for a large Llama-class default plus a cheaper
  alternative. Groq retired Llama 3.3 70B and Llama 3.1 8B on its free and
  developer tiers on Aug 16, 2026, and recommends `openai/gpt-oss-120b` and
  `openai/gpt-oss-20b` as their replacements. Those are the default and the fast
  option. Change them with `LLM_MODEL` in `.env` or in `config.py`. gpt-oss models
  "think" first, so I set `reasoning_effort: low` to save tokens.
- **JSON mode, not strict schema mode.** Groq's `json_object` mode works on
  every model, so swapping models never breaks anything. My own validator plus
  one retry covers the gaps.
- **Free-tier pacing.** The limits are 30 requests/min and 8K tokens/min per
  model. I pace to 25 requests and 7K tokens so a 429 is rare, not routine. One
  email is roughly 1–1.5K tokens.
- **The 26-hour window.** It overlaps the previous run, so a late GitHub run
  never leaves a gap. Message-ID dedup makes the overlap free.
- **Rescue keywords beat skip rules.** Recall matters more than saving an LLM
  call.
- **Upcoming appointment confirmations are actionable** (I have to show up).
  Order confirmations are not.
- **Urgency is recalculated in code from the deadline** (high: overdue or ≤ 2
  days; medium: ≤ 7 days; low: otherwise). LLMs are unreliable at date math and
  code isn't. Turn this off with `DERIVE_URGENCY_FROM_DEADLINE`.
- **Open items expire.** Overdue items stay in the summary for 3 days. Items with
  no deadline stay for 7 days. There's no "mark done" button, so this keeps the
  summary from growing forever.
- **Daylight saving.** GitHub cron only speaks UTC. The workflow runs at both
  12:00 and 13:00 UTC, and `--scheduled` only does real work on the first run at
  or after 8 AM Eastern each day. The result is 8 AM all year, plus a free retry
  if the first run fails.
- **The database is committed to the repo.** That's the simplest free
  persistence. It's why the repo must be **private**.
- **No extra packages** beyond the five requested. ntfy uses the standard
  library's `urllib`, and the schema check is hand-written.

## Run it

```bash
python main.py --dry-run                                  # real Gmail + Groq, prints only
python main.py                                            # the real thing
pytest -q                                                 # tests
```
