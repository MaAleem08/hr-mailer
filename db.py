"""SQLite persistence layer. Kept separate so app.py stays readable."""
import sqlite3
import json
import time
import os

DB_PATH = os.path.join(os.path.dirname(__file__), "data", "mailer.db")


def get_conn():
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = get_conn()
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS campaigns (
            id TEXT PRIMARY KEY,
            owner_session TEXT,
            sender_email TEXT,
            subject TEXT,
            body TEXT,
            attachments TEXT,      -- json list of file paths
            delay_min INTEGER,
            delay_max INTEGER,
            daily_cap INTEGER,
            status TEXT,           -- pending/running/paused/stopped/completed
            created_at REAL
        );

        CREATE TABLE IF NOT EXISTS recipients (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            campaign_id TEXT,
            email TEXT,
            row_data TEXT,         -- json of the full CSV row, for merge fields
            status TEXT,           -- queued/sent/failed/skipped
            error TEXT,
            sent_at REAL
        );

        CREATE INDEX IF NOT EXISTS idx_recipients_campaign
            ON recipients(campaign_id, status);
        """
    )
    conn.commit()
    conn.close()


def create_campaign(cid, owner_session, sender_email, subject, body,
                     attachments, delay_min, delay_max, daily_cap):
    conn = get_conn()
    conn.execute(
        """INSERT INTO campaigns
           (id, owner_session, sender_email, subject, body, attachments,
            delay_min, delay_max, daily_cap, status, created_at)
           VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
        (cid, owner_session, sender_email, subject, body,
         json.dumps(attachments), delay_min, delay_max, daily_cap,
         "pending", time.time()),
    )
    conn.commit()
    conn.close()


def add_recipients(cid, rows):
    """rows: list of dicts, each must contain 'email'."""
    conn = get_conn()
    conn.executemany(
        "INSERT INTO recipients (campaign_id, email, row_data, status) VALUES (?,?,?,?)",
        [(cid, r["email"], json.dumps(r), "queued") for r in rows],
    )
    conn.commit()
    conn.close()


def get_campaign(cid):
    conn = get_conn()
    row = conn.execute("SELECT * FROM campaigns WHERE id=?", (cid,)).fetchone()
    conn.close()
    return dict(row) if row else None


def set_campaign_status(cid, status):
    conn = get_conn()
    conn.execute("UPDATE campaigns SET status=? WHERE id=?", (status, cid))
    conn.commit()
    conn.close()


def get_pending_recipients(cid):
    conn = get_conn()
    rows = conn.execute(
        "SELECT * FROM recipients WHERE campaign_id=? AND status='queued' ORDER BY id",
        (cid,),
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def mark_recipient(cid, recipient_id, status, error=None):
    conn = get_conn()
    conn.execute(
        "UPDATE recipients SET status=?, error=?, sent_at=? WHERE id=?",
        (status, error, time.time(), recipient_id),
    )
    conn.commit()
    conn.close()


def campaign_counts(cid):
    conn = get_conn()
    rows = conn.execute(
        "SELECT status, COUNT(*) as n FROM recipients WHERE campaign_id=? GROUP BY status",
        (cid,),
    ).fetchall()
    conn.close()
    counts = {"queued": 0, "sent": 0, "failed": 0, "skipped": 0}
    for r in rows:
        counts[r["status"]] = r["n"]
    counts["total"] = sum(counts.values())
    return counts


def get_all_recipients(cid):
    conn = get_conn()
    rows = conn.execute(
        "SELECT email, status, error, sent_at FROM recipients WHERE campaign_id=? ORDER BY id",
        (cid,),
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]
