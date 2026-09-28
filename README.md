# Bulk HR Email Sender

A self-serve web tool: upload a contact list, write one email, personalize it
per recipient, and send in bulk — with live progress, pause/resume/stop, and
a sent/failed report at the end.

## What's in this project
```
app.py           Flask routes (upload, start/pause/resume/stop, live stream, report)
mailer.py        CSV/XLSX parsing, validation, merge-field rendering, the send worker
db.py            SQLite persistence (campaigns + per-recipient status, for resume/report)
templates/       The single-page UI
static/          CSS/JS for that page
dummy_smtp.py    OPTIONAL local fake SMTP server, for testing without a real Gmail account
requirements.txt
Procfile         For gunicorn on Render/Railway/Heroku-style hosts
```

## How it works, in brief
- Nothing is sent from your machine directly to Gmail's servers except via
  Python's `smtplib` — same mechanism as the script you started with.
- The Gmail **App Password** you type in is used once to log in for that
  campaign's send thread, then discarded — it is never written to disk or
  the database.
- Sending happens in a background thread per campaign, so pausing, resuming,
  or closing the browser tab doesn't lose progress (it's tracked in SQLite).
- Progress streams to the browser via Server-Sent Events.

---

## 1. Run it locally and test with a REAL Gmail account (recommended first check)

### 1a. Get a Gmail App Password
Regular Gmail passwords don't work for SMTP anymore. You need an **App
Password**:
1. Turn on 2-Step Verification on the Google account you'll send from:
   https://myaccount.google.com/security
2. Go to https://myaccount.google.com/apppasswords
3. Create one named e.g. "HR Mailer", copy the 16-character password.

### 1b. Install and run
```bash
cd hr-mailer
python3 -m venv venv
source venv/bin/activate          # Windows: venv\Scripts\activate
pip install -r requirements.txt
python3 app.py
```
Open http://127.0.0.1:5000 in your browser.

### 1c. Test checklist — go through these in order
1. **Upload a small test CSV/XLSX** with 2-3 rows, one column named `HR
   EMAIL` (or `Email`) plus optional columns like `first_name`, `company`.
   Include one duplicate email and one broken email address on purpose —
   confirm the UI reports them as removed (e.g. "✓ 3 valid emails / ✓ 1
   duplicate removed / ✓ 1 invalid removed").
2. Fill in **your own Gmail address** as sender, paste the **App Password**.
3. Write a subject/body using `{{first_name}}` if your file has that column.
4. Click **Send Test Email to Myself** — check your inbox arrives correctly,
   with attachment if you added one.
5. Click **START SENDING**. Watch the live log ("1. Sent to ...") and the
   progress bar.
6. Click **PAUSE** mid-send — confirm the counter stops advancing.
7. Click **RESUME** — confirm it continues from where it left off (not
   from zero).
8. Let it finish, then click **STOP** on a *second* test run partway through
   — confirm it actually halts and doesn't send the rest.
9. Download the **CSV report** at the end and check the statuses match what
   you saw sent.
10. Deliberately enter a wrong App Password once, click "Send Test Email",
    and confirm you get a clear error rather than a crash.

If all ten pass, the app is working correctly.

### 1d. (Optional) Test without touching real Gmail at all
`dummy_smtp.py` is a local fake mail server included for exactly this — run
it in one terminal, then run the app pointed at it in another, and nothing
ever leaves your machine:
```bash
# terminal 1
python3 dummy_smtp.py

# terminal 2
MAILER_SMTP_HOST=127.0.0.1 MAILER_SMTP_PORT=1025 MAILER_SKIP_TLS=1 python3 app.py
```
Any email/password will "log in" successfully; sent messages just get
printed to terminal 1's console instead of actually delivered. Useful for
demoing the UI or for any code changes you make later, before spending a
real send quota.

---

## 2. Deploy so other people can use it

Recommended: **Render.com** (simplest, generous free tier, no credit card
for the starter tier as of writing — but double-check current pricing
yourself before relying on it long-term).

### 2a. Push the code to GitHub
```bash
cd hr-mailer
git init
git add .
git commit -m "Initial commit"
# create a new empty repo on github.com, then:
git remote add origin https://github.com/<you>/hr-mailer.git
git push -u origin main
```

### 2b. Create the web service on Render
1. https://render.com → New → Web Service → connect your GitHub repo.
2. Runtime: Python 3. Build command: `pip install -r requirements.txt`.
3. Start command: `gunicorn --workers 2 --threads 4 --timeout 120 app:app`
   (already in the included `Procfile`, Render should detect it automatically).
4. Add an environment variable `FLASK_SECRET` set to any long random string
   (e.g. generate one with `python3 -c "import secrets; print(secrets.token_hex(32))"`).
5. Deploy. Render gives you a URL like `https://hr-mailer.onrender.com`.

### 2c. Important notes for a public deployment
- **SQLite + multiple server instances don't mix.** Render's free tier runs
  a single instance by default, which is fine for this app as-is. If you
  ever scale to multiple instances/workers-across-machines, you'd need to
  move from SQLite to Postgres (Render offers a free Postgres tier) — the
  `db.py` module is the only file you'd need to change.
- **Free-tier instances sleep** after inactivity and take ~30s to wake on
  the next visit — acceptable for a personal tool, worth knowing so it
  doesn't look "broken" on first load.
- **File uploads are ephemeral** on most free hosting — uploaded contact
  files and attachments can disappear on redeploy/restart. Fine for this
  tool's use case (people upload fresh each time they run a campaign), but
  don't rely on it as permanent storage.
- **HTTPS**: Render provides this automatically — never deploy this
  anywhere serving plain HTTP, since it collects Gmail App Passwords in a
  form field.

### 2d. Before telling other people to use it
- Read Gmail's sending limits again (~500/day on a free Gmail account,
  ~2,000/day on Workspace) and keep the app's default `daily_cap` at or
  below that.
- Consider adding your own short "acceptable use" note on the page (e.g.
  "for personal job-search outreach only, keep lists reasonable, don't
  scrape or spam") — you are the one hosting it, so you carry some
  responsibility for how it gets used.
- App Passwords typed into your hosted page travel over HTTPS to your
  server and are used immediately, then discarded — but you're still asking
  strangers to trust your server with a credential. Worth being upfront
  about that in the UI if this becomes multi-user.

---

## 3. Known limitations / good next upgrades
- Auth is currently "type your App Password every time" — swapping to
  Gmail OAuth2 (Google Sign-In) would mean you never touch the credential
  directly, better trust story for a public tool. More setup work (Google
  Cloud OAuth consent screen) so left out of this first version.
- No MX-record/deliverability check on emails yet, just syntax validation —
  add `check_deliverability=True` in `mailer.py`'s `validate_email()` call
  if you want that, at the cost of a slower upload step.
- No per-user accounts — anyone with the link can start a campaign from
  their own Gmail. Fine for personal use; add login if you open it up
  widely.
