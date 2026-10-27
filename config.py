"""All the knobs you might want to change live here.

Secrets never go in this file. They come from environment variables
(a local .env file when testing, GitHub Secrets in Actions).
"""
import os

# ---------------------------------------------------------------------------
# Gmail
# ---------------------------------------------------------------------------
GMAIL_SCOPES = ["https://www.googleapis.com/auth/gmail.readonly"]

# Base search. The "after:<timestamp>" part is added automatically from
# LOOKBACK_HOURS. Same syntax as the Gmail search box.
GMAIL_QUERY = "-category:promotions -category:social -in:spam -in:trash"

# 26 h instead of 24 h so a late or delayed GitHub Actions run never leaves a
# gap. Overlap is harmless: already-processed message IDs are skipped.
LOOKBACK_HOURS = 26

# Safety cap so one busy day can't burn the whole free-tier token budget.
MAX_EMAILS_PER_RUN = 60

# Body text sent to the LLM is cut to this many characters (~750 tokens).
MAX_BODY_CHARS = 3000

# ---------------------------------------------------------------------------
# Cheap noise rules (run BEFORE the LLM, cost nothing)
# ---------------------------------------------------------------------------
# If the subject or the first part of the body contains any of these, the
# email is ALWAYS sent to the LLM, even if another rule says "noise".
# Missing a real deadline is the worst possible error, so we err toward
# letting things through.
RESCUE_KEYWORDS = [
    "interview", "deadline", "due", "action required", "action needed",
    "assessment", "online assessment", "coding challenge", "hackerrank",
    "codesignal", "offer", "background check", "onboarding", "i-9",
    "complete your", "please complete", "please submit", "submit by",
    "reminder", "expires", "expiring", "past due", "overdue", "rsvp",
    "appointment", "schedule", "invitation", "invite", "respond by",
    "waiting on you", "waiting for your", "sign", "signature", "form",
    "verify", "payment due", "amount due", "balance due", "autopay failed",
    "assignment", "exam", "quiz", "meeting", "gbm", "rsvp",
]

# Rule 1: newsletters/mass mail almost always carry a List-Unsubscribe header.
SKIP_IF_LIST_UNSUBSCRIBE = True

# Rule 2: sender address patterns that are usually automated...
NOREPLY_SENDER_PATTERNS = ["noreply", "no-reply", "donotreply", "do-not-reply",
                           "newsletter", "marketing", "news@", "hello@",
                           "promo", "deals@", "offers@"]
# ...and words that make an automated email look like marketing.
MARKETING_WORDS = ["% off", "sale", "deal", "limited time", "shop now",
                   "new arrivals", "discount", "free shipping", "promo code",
                   "weekly digest", "newsletter", "top stories", "recommended for you"]

# Rule 3: receipts / confirmations that need nothing from you.
RECEIPT_SUBJECT_PATTERNS = ["your receipt", "receipt from", "order confirmation",
                            "your order", "order #", "payment received",
                            "thanks for your payment", "thank you for your payment",
                            "thanks for your order", "has shipped", "was delivered",
                            "out for delivery", "transaction alert"]

# Senders that should never be filtered out (substring match on From).
ALWAYS_KEEP_SENDERS = [".edu"]

# ---------------------------------------------------------------------------
# LLM
# ---------------------------------------------------------------------------
LLM_PROVIDER = os.getenv("LLM_PROVIDER", "groq")

# Groq retired the Llama 3.x models on its free/developer tier in Aug 2026
# and points users to gpt-oss as the replacement, so that's the default.
DEFAULT_MODEL = "openai/gpt-oss-120b"   # strong default
FAST_MODEL = "openai/gpt-oss-20b"       # cheaper / faster alternative
LLM_MODEL = os.getenv("LLM_MODEL", DEFAULT_MODEL)

# Which system prompt to use (see prompts.py). Eval decides the winner.
PROMPT_VERSION = os.getenv("PROMPT_VERSION", "v3")

# If the model gives a deadline, recompute urgency from it in code using the
# same rule as the prompt (high <= 2 days/overdue, medium <= 7, else low).
DERIVE_URGENCY_FROM_DEADLINE = True

LLM_TEMPERATURE = 0
LLM_MAX_OUTPUT_TOKENS = 1024

# Extra per-model parameters. gpt-oss models "think" before answering;
# low effort keeps that short so we stay inside the free-tier token budget.
MODEL_OPTIONS = {
    "openai/gpt-oss-120b": {"reasoning_effort": "low", "include_reasoning": False},
    "openai/gpt-oss-20b": {"reasoning_effort": "low", "include_reasoning": False},
    "qwen/qwen3.8-27b": {"reasoning_format": "hidden", "reasoning_effort": "none"},
}

# Free tier (Oct 2026): 30 requests/min and 8,000 tokens/min per model.
# We stay a bit under both so we rarely hit a 429 at all.
REQUESTS_PER_MINUTE = 25
TOKENS_PER_MINUTE = 7000

# Backoff for 429 / temporary errors: 2s, 4s, 8s, 16s, 32s (+ jitter).
MAX_RETRIES = 5
BACKOFF_BASE_SECONDS = 2
# If Groq says "come back in more than this many seconds" (daily limit hit),
# stop for today instead of hanging the job.
MAX_RETRY_AFTER_SECONDS = 120

# ---------------------------------------------------------------------------
# Notifications / items
# ---------------------------------------------------------------------------
TIMEZONE = "America/New_York"
NTFY_SERVER = os.getenv("NTFY_SERVER", "https://ntfy.sh")
URGENT_WINDOW_HOURS = 48          # due within this → high-priority alert
OVERDUE_GRACE_DAYS = 3            # overdue items stay in the summary this long
NO_DEADLINE_KEEP_DAYS = 7         # items without a deadline stay this long
MAX_URGENT_ALERTS = 5             # more than this get bundled into one alert

CATEGORY_ORDER = ["career", "school", "bills", "appointments", "events",
                  "personal", "other"]

# Reminder detection: two tasks from the same sender whose words overlap at
# least this much (Jaccard similarity) are treated as the same task.
REMINDER_SIMILARITY = 0.5

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
STATE_DB_PATH = os.getenv("STATE_DB_PATH", os.path.join(BASE_DIR, "data", "state.sqlite"))
