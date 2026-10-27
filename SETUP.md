# Setup checklist

Do these in order. Total time is about 45 minutes. Each step says what you're
doing and why.

---

## Part A — Your computer

**1. Install the project.**
In Terminal:
```bash
cd ~/Projects/email-agent
python3 --version            # needs 3.11 or newer
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
pytest -q                    # should say "63 passed"
cp .env.example .env         # you'll fill this in over the next steps
```

---

## Part B — Google (Gmail access)

**2. Create a Google Cloud project and turn on the Gmail API.**
- Go to <https://console.cloud.google.com/>, sign in with the Gmail account you
  want the agent to read, and click the project picker → **New project**. Name
  it `email-agent`.
- With that project selected, open **APIs & Services → Library**, search
  **Gmail API**, and click **Enable**.

**3. Set up the OAuth consent screen.** This is the "app wants to access your
account" page you'll see once.
- Go to **APIs & Services → OAuth consent screen**. Newer consoles call it
  **Google Auth Platform**.
- **Branding:** app name `email-agent`, plus your email as the support and
  developer contact.
- **Audience:** choose **External**.
- **Data access** (or "Scopes"): add `https://www.googleapis.com/auth/gmail.readonly`.
  That's read-only: the agent can't send, delete or change anything.
- **Audience → Test users:** add your own Gmail address.

**4. Create a Desktop OAuth client.**
- Go to **Clients** (or **Credentials → Create credentials → OAuth client ID**).
- Application type: **Desktop app**. Name: `email-agent-desktop`.
- Click **Download JSON**, rename the file to `credentials.json`, and put it in
  the `email-agent` folder. It's gitignored, so it won't be committed.

**5. ⚠️ Switch the app to "In production" before you get a token.**
- While the app is in **Testing**, Google makes refresh tokens **expire after 7
  days**. The agent would stop working every week.
- Google won't let you publish until **Branding** has a homepage link and a privacy
  policy link. For a personal app, you can use your GitHub profile and a short
  privacy note posted as a GitHub Gist:
  1. Go to <https://gist.github.com>, filename `email-agent-privacy.md`, paste the
     text from `PRIVACY.md` in this repo, then click **Create secret gist**. Copy
     the URL.
  2. **Branding → App domain:** homepage `https://github.com/JoshuaE92`, privacy
     policy = the gist URL. Under **Authorized domains**, add `github.com`. Click
     **Save**.
- Go to **Audience → Publishing status → Publish app → Confirm**.
- You do **not** need Google's verification for personal use. When you log in
  during step 8, Google will show **"Google hasn't verified this app."** Click
  **Advanced → Go to email-agent (unsafe)**. It's your own app, so that's fine.
- Do this *before* step 8. A token issued while the app was in Testing still
  expires after 7 days.

---

## Part C — Groq (the LLM)

**6. Get a Groq API key and put it in `.env`.**
- Create a key at <https://console.groq.com/keys>.
- **Delete the key you pasted into the Claude chat and make a new one.** Any key
  that has been pasted into a chat should be treated as exposed.
- In `.env`, set `GROQ_API_KEY=gsk_...`
- **What happens to your email text:** Groq's policy (checked Oct 2026) says it
  doesn't keep API inputs and outputs by default. It may log them for up to 30
  days only to debug outages or investigate abuse, and that data is stored in the
  US. To turn even that off, enable **Zero Data Retention** in the Groq console
  under **Settings → Data Controls**. Read the current policy here:
  <https://console.groq.com/docs/your-data>.

---

## Part D — ntfy (push notifications)

**7. Install ntfy and pick a secret topic.**
- Install **ntfy** from the App Store or Google Play.
- ntfy has no passwords. **Anyone who knows your topic name can read your
  alerts**, so make it long and random:
  ```bash
  python3 -c "import secrets; print('josh-' + secrets.token_urlsafe(18))"
  ```
- In the app, tap **+** and subscribe to that exact topic on the default server
  (`ntfy.sh`).
- In `.env`, set `NTFY_TOPIC=<that topic>`.
- Quick test: `curl -d "hello from email-agent" ntfy.sh/<your-topic>`. Your
  phone should buzz.

---

## Part E — Connect Gmail

**8. Get your refresh token.**
```bash
python scripts/get_refresh_token.py
```
- A browser opens. Log in, click past the unverified-app warning (step 5), and
  allow read-only Gmail access.
- The script prints three lines: `GMAIL_CLIENT_ID`, `GMAIL_CLIENT_SECRET` and
  `GMAIL_REFRESH_TOKEN`. Paste all three into `.env`.
- Keep them private. Together they let anyone read your email.

---

## Part F — Test on your computer first

**9. Run the eval to find out whether Groq is accurate enough.**
```bash
python eval/run_eval.py --models openai/gpt-oss-120b,openai/gpt-oss-20b --prompts v2,v3
```
- This takes about 15 minutes. Read `eval/RESULTS.md` when it finishes.
- Already done once (see RESULTS.md: gpt-oss-120b + prompt v3 scored 100%). If you re-run and a different setup wins, change
  `DEFAULT_MODEL` / `PROMPT_VERSION` in `config.py`.
- Optional but worth it: check it against your own inbox.
  ```bash
  python eval/run_eval.py --real 30
  # open eval/real_samples/real_*.csv in Excel/Numbers and mark each row correct/wrong
  python eval/run_eval.py --score eval/real_samples/real_<timestamp>.csv
  ```

**10. Dry run on your real inbox.** This reads Gmail and calls Groq, but sends
nothing and saves nothing.
```bash
python main.py --dry-run
```

---

## Part G — GitHub (runs every morning)

**11. Create a PRIVATE repository and push.**
- On GitHub, click **New repository**, name it `email-agent`, and choose
  **Private**. ⚠️ It *must* stay private: `data/state.sqlite` gets committed
  every day and contains task text and links from your email.
- Move the workflow file into place, then push:
  ```bash
  mkdir -p .github/workflows && mv deploy/daily.yml .github/workflows/daily.yml
  git init && git add . && git status    # make sure .env and credentials.json are NOT listed
  git commit -m "Email agent"
  git branch -M main
  git remote add origin https://github.com/JoshuaE92/email-agent.git
  git push -u origin main
  ```

**12. Add the five GitHub Secrets.**
In the repo, go to **Settings → Secrets and variables → Actions → New
repository secret** and add each one, copying the values from your `.env`:

| Name | Value |
|---|---|
| `GROQ_API_KEY` | your new Groq key |
| `NTFY_TOPIC` | your secret topic |
| `GMAIL_CLIENT_ID` | from step 8 |
| `GMAIL_CLIENT_SECRET` | from step 8 |
| `GMAIL_REFRESH_TOKEN` | from step 8 |

**13. Let the workflow save its database.**
Go to **Settings → Actions → General → Workflow permissions** and select **Read
and write permissions**. This lets the workflow commit `data/state.sqlite` back
to the repo.

**14. Trigger it by hand and confirm a notification arrives.**
- Go to **Actions → Daily email agent → Run workflow**.
- First, tick **Dry run** and check the log. It prints the notifications it
  would send.
- Then run it again without Dry run. Your phone should get the morning summary.
  If anything is due within 48 hours, you'll also get a separate alert.
- After that it runs on its own every day at 8 AM Eastern.

---

## If something breaks later

| Symptom | Fix |
|---|---|
| Action fails with `invalid_grant` | Your refresh token expired or was revoked. Check that step 5 is done, then repeat step 8 and update the secret. |
| No notification | Check that the ntfy topic in the app matches `NTFY_TOPIC` exactly. |
| "rate limit" or stopped early in the log | The free daily token cap was hit. Remaining emails are retried the next day. |
| Too many or too few alerts | Edit the rules in `config.py`, re-run the eval, and run `python main.py --dry-run`. |
