import os
import io
import csv
import json
import uuid
import time

from flask import (Flask, request, jsonify, render_template, session,
                    Response, send_file, stream_with_context)

import db
import mailer

app = Flask(__name__)
app.secret_key = os.environ.get("FLASK_SECRET", "dev-secret-change-me")

UPLOAD_DIR = os.path.join(os.path.dirname(__file__), "uploads")
os.makedirs(UPLOAD_DIR, exist_ok=True)

db.init_db()

# app passwords are NEVER written to disk/DB — held only in memory for the
# lifetime of the running send thread, keyed by campaign id.
_pending_passwords = {}


def owner():
    if "sid" not in session:
        session["sid"] = str(uuid.uuid4())
    return session["sid"]


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/upload", methods=["POST"])
def upload():
    f = request.files.get("contacts")
    if not f:
        return jsonify({"error": "No file uploaded"}), 400
    try:
        rows, stats = mailer.parse_contact_file(f)
    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    except Exception as e:
        return jsonify({"error": f"Could not read file: {e}"}), 400

    # stash parsed rows on disk for this session, keyed by an upload id
    upload_id = str(uuid.uuid4())
    path = os.path.join(UPLOAD_DIR, f"{upload_id}.json")
    with open(path, "w") as fh:
        json.dump(rows, fh)

    return jsonify({"upload_id": upload_id, "stats": stats})


@app.route("/upload-attachment", methods=["POST"])
def upload_attachment():
    f = request.files.get("file")
    if not f:
        return jsonify({"error": "No file"}), 400
    dest_dir = os.path.join(UPLOAD_DIR, owner())
    os.makedirs(dest_dir, exist_ok=True)
    path = os.path.join(dest_dir, f.filename)
    f.save(path)
    return jsonify({"path": path, "name": f.filename})


@app.route("/test-email", methods=["POST"])
def test_email():
    data = request.json
    try:
        mailer.send_test_email(
            data["sender_email"], data["app_password"],
            data["subject"], data["body"], data.get("attachments", []),
        )
        return jsonify({"ok": True})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 400


@app.route("/start", methods=["POST"])
def start():
    data = request.json
    upload_id = data["upload_id"]
    path = os.path.join(UPLOAD_DIR, f"{upload_id}.json")
    if not os.path.exists(path):
        return jsonify({"error": "Upload expired, please re-upload your contact file"}), 400
    with open(path) as fh:
        rows = json.load(fh)

    cid = str(uuid.uuid4())
    db.create_campaign(
        cid, owner(), data["sender_email"], data["subject"], data["body"],
        data.get("attachments", []),
        int(data.get("delay_min", 8)), int(data.get("delay_max", 15)),
        int(data.get("daily_cap", 450)),
    )
    db.add_recipients(cid, rows)
    mailer.start_campaign_thread(cid, data["app_password"])
    return jsonify({"campaign_id": cid, "total": len(rows)})


@app.route("/pause/<cid>", methods=["POST"])
def pause(cid):
    mailer.pause_campaign(cid)
    return jsonify({"ok": True})


@app.route("/resume/<cid>", methods=["POST"])
def resume(cid):
    mailer.resume_campaign(cid)
    return jsonify({"ok": True})


@app.route("/stop/<cid>", methods=["POST"])
def stop(cid):
    mailer.stop_campaign(cid)
    return jsonify({"ok": True})


@app.route("/status/<cid>")
def status(cid):
    campaign = db.get_campaign(cid)
    if not campaign:
        return jsonify({"error": "not found"}), 404
    counts = db.campaign_counts(cid)
    return jsonify({"status": campaign["status"], "counts": counts})


@app.route("/stream/<cid>")
def stream(cid):
    def gen():
        idx = 0
        while True:
            lines, idx = mailer.get_new_logs(cid, idx)
            for line in lines:
                yield f"data: {line}\n\n"
            campaign = db.get_campaign(cid)
            counts = db.campaign_counts(cid)
            yield f"event: counts\ndata: {json.dumps(counts)}\n\n"
            if campaign and campaign["status"] in ("completed", "stopped"):
                yield "event: done\ndata: done\n\n"
                break
            time.sleep(1)
    return Response(stream_with_context(gen()), mimetype="text/event-stream")


@app.route("/report/<cid>")
def report(cid):
    rows = db.get_all_recipients(cid)
    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=["email", "status", "error", "sent_at"])
    writer.writeheader()
    writer.writerows(rows)
    mem = io.BytesIO(buf.getvalue().encode())
    return send_file(mem, mimetype="text/csv", as_attachment=True,
                      download_name=f"campaign_{cid}_report.csv")


if __name__ == "__main__":
    app.run(debug=False, port=5000, threaded=True)
