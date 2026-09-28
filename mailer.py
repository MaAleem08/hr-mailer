"""Email validation, CSV/XLSX parsing, and the background sending worker."""
import re
import io
import json
import time
import random
import smtplib
import threading
import mimetypes
from email.message import EmailMessage
from email_validator import validate_email, EmailNotValidError

import pandas as pd
import os

import db

# Testing hook only: set MAILER_SMTP_HOST/PORT to point at a local dummy SMTP
# server instead of Gmail. Leave unset in production.
SMTP_HOST = os.environ.get("MAILER_SMTP_HOST", "smtp.gmail.com")
SMTP_PORT = int(os.environ.get("MAILER_SMTP_PORT", "587"))
SKIP_TLS = os.environ.get("MAILER_SKIP_TLS") == "1"  # testing only
SKIP_LOGIN = os.environ.get("MAILER_SKIP_LOGIN") == "1"  # testing only

EMAIL_COL_CANDIDATES = ["hr email", "email", "hremail", "contact email", "e-mail", "mail"]

# in-memory control flags + live log lines, per campaign_id
# (kept separate from the DB so pause/stop is instant, no DB round-trip)
_controls = {}   # cid -> {"pause": bool, "stop": bool}
_logs = {}        # cid -> list[str]  (also used by the SSE stream)
_locks = {}


def _get_lock(cid):
    if cid not in _locks:
        _locks[cid] = threading.Lock()
    return _locks[cid]


def log(cid, line):
    with _get_lock(cid):
        _logs.setdefault(cid, []).append(line)


def get_new_logs(cid, since_idx):
    with _get_lock(cid):
        lines = _logs.get(cid, [])
        return lines[since_idx:], len(lines)


def find_email_column(columns):
    lower_map = {c.lower().strip(): c for c in columns}
    for cand in EMAIL_COL_CANDIDATES:
        if cand in lower_map:
            return lower_map[cand]
    # fallback: any column whose name contains "email" or "mail"
    for lower, orig in lower_map.items():
        if "email" in lower or "mail" in lower:
            return orig
    return None


def parse_contact_file(file_storage):
    """Returns (rows, stats) where rows is a list of dicts with a normalized
    'email' key plus all original columns (for merge fields), deduped and
    syntax-validated. stats has counts for the UI."""
    filename = file_storage.filename.lower()
    raw = file_storage.read()
    if filename.endswith(".csv"):
        df = pd.read_csv(io.BytesIO(raw))
    else:
        df = pd.read_excel(io.BytesIO(raw))

    email_col = find_email_column(df.columns)
    if not email_col:
        raise ValueError(
            "Couldn't find an email column. Please name it 'HR EMAIL' or 'Email'."
        )

    seen = set()
    rows = []
    invalid = 0
    duplicates = 0
    for _, row in df.iterrows():
        raw_email = str(row[email_col]).strip()
        if not raw_email or raw_email.lower() == "nan":
            invalid += 1
            continue
        try:
            valid = validate_email(raw_email, check_deliverability=False)
            norm_email = valid.normalized.lower()
        except EmailNotValidError:
            invalid += 1
            continue
        if norm_email in seen:
            duplicates += 1
            continue
        seen.add(norm_email)
        record = {k: ("" if pd.isna(v) else v) for k, v in row.to_dict().items()}
        record["email"] = norm_email
        rows.append(record)

    stats = {
        "total_rows": len(df),
        "valid": len(rows),
        "invalid": invalid,
        "duplicates": duplicates,
        "email_column_used": email_col,
    }
    return rows, stats


def render_template_str(template, row):
    """Replace {{field}} tokens with values from the row dict (case-insensitive
    key match). Unknown tokens are left as a blank rather than crashing."""
    def repl(match):
        key = match.group(1).strip().lower()
        for k, v in row.items():
            if k.lower() == key:
                return str(v)
        return ""
    return re.sub(r"\{\{\s*([\w ]+)\s*\}\}", repl, template)


def send_campaign(cid, app_password):
    """Runs in a background thread. app_password is passed in directly (never
    written to the DB) and only lives in this thread's memory for the run."""
    campaign = db.get_campaign(cid)
    if not campaign:
        return
    _controls[cid] = {"pause": False, "stop": False}
    db.set_campaign_status(cid, "running")
    log(cid, f"Starting campaign — sending as {campaign['sender_email']}")

    attachments = json.loads(campaign["attachments"] or "[]")

    try:
        smtp = smtplib.SMTP(SMTP_HOST, SMTP_PORT)
        if not SKIP_TLS:
            smtp.starttls()
        if not SKIP_LOGIN:
            smtp.login(campaign["sender_email"], app_password)
    except Exception as e:
        log(cid, f"FATAL: could not log in to SMTP server ({e}). Stopping.")
        db.set_campaign_status(cid, "stopped")
        return

    sent_today = 0
    pending = db.get_pending_recipients(cid)
    total = db.campaign_counts(cid)["total"]

    for i, recipient in enumerate(pending, start=1):
        # STOP check
        if _controls[cid]["stop"]:
            log(cid, "Stopped by user.")
            db.set_campaign_status(cid, "stopped")
            smtp.quit()
            return

        # PAUSE check (poll until resumed or stopped)
        while _controls[cid]["pause"] and not _controls[cid]["stop"]:
            time.sleep(1)
        if _controls[cid]["stop"]:
            log(cid, "Stopped by user.")
            db.set_campaign_status(cid, "stopped")
            smtp.quit()
            return

        if sent_today >= campaign["daily_cap"]:
            log(cid, f"Daily cap of {campaign['daily_cap']} reached. Stopping "
                      f"here — resume tomorrow to continue the rest.")
            db.set_campaign_status(cid, "paused")
            smtp.quit()
            return

        row = json.loads(recipient["row_data"])
        to_addr = recipient["email"]

        try:
            msg = EmailMessage()
            msg["From"] = campaign["sender_email"]
            msg["To"] = to_addr
            msg["Subject"] = render_template_str(campaign["subject"], row)
            msg.set_content(render_template_str(campaign["body"], row))

            for path in attachments:
                ctype, _ = mimetypes.guess_type(path)
                maintype, subtype = (ctype or "application/octet-stream").split("/", 1)
                with open(path, "rb") as f:
                    msg.add_attachment(
                        f.read(), maintype=maintype, subtype=subtype,
                        filename=path.split("/")[-1],
                    )

            smtp.send_message(msg)
            db.mark_recipient(cid, recipient["id"], "sent")
            sent_today += 1
            log(cid, f"{i}. Sent to {to_addr}")
        except Exception as e:
            db.mark_recipient(cid, recipient["id"], "failed", str(e))
            log(cid, f"{i}. FAILED {to_addr} — {e}")

        delay = random.uniform(campaign["delay_min"], campaign["delay_max"])
        time.sleep(delay)

    smtp.quit()
    db.set_campaign_status(cid, "completed")
    log(cid, "Campaign complete.")


def start_campaign_thread(cid, app_password):
    t = threading.Thread(target=send_campaign, args=(cid, app_password), daemon=True)
    t.start()


def pause_campaign(cid):
    if cid in _controls:
        _controls[cid]["pause"] = True
        db.set_campaign_status(cid, "paused")


def resume_campaign(cid):
    if cid in _controls:
        _controls[cid]["pause"] = False
        db.set_campaign_status(cid, "running")


def stop_campaign(cid):
    if cid in _controls:
        _controls[cid]["stop"] = True
    else:
        db.set_campaign_status(cid, "stopped")


def send_test_email(sender_email, app_password, subject, body, attachments=None):
    smtp = smtplib.SMTP(SMTP_HOST, SMTP_PORT)
    if not SKIP_TLS:
        smtp.starttls()
    smtp.login(sender_email, app_password)
    msg = EmailMessage()
    msg["From"] = sender_email
    msg["To"] = sender_email
    msg["Subject"] = f"[TEST] {subject}"
    msg.set_content(body)
    for path in (attachments or []):
        ctype, _ = mimetypes.guess_type(path)
        maintype, subtype = (ctype or "application/octet-stream").split("/", 1)
        with open(path, "rb") as f:
            msg.add_attachment(f.read(), maintype=maintype, subtype=subtype,
                                filename=path.split("/")[-1])
    smtp.send_message(msg)
    smtp.quit()
