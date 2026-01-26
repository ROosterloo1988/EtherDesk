from flask import Flask, render_template, g, jsonify
import sqlite3
import datetime
import git
import subprocess
import os

app = Flask(__name__)
DB_FILE = "/data/messages.db"

# --- CONFIG LADEN UIT ENVIRONMENT ---
# Hier pakken we de variabelen die je in .env instelt
STUDIO_NAME = os.getenv("STUDIO_NAME", "EtherDesk Studio")
SLOGAN = os.getenv("SLOGAN", "Professional Broadcast Interface")
PAGE_TITLE = os.getenv("PAGE_TITLE", "EtherDesk")
MATRIX_USER = os.getenv("MATRIX_USER", "Niet ingesteld")
MATRIX_URL = os.getenv("MATRIX_URL", "http://synapse:8008")

def get_db():
    db = getattr(g, '_database', None)
    if db is None:
        db = g._database = sqlite3.connect(DB_FILE)
        db.row_factory = sqlite3.Row
    return db

@app.teardown_appcontext
def close_connection(exception):
    db = getattr(g, '_database', None)
    if db is not None:
        db.close()

# --- ROUTES ---
@app.route('/')
def index():
    return render_template('index.html', 
                         studio_name=STUDIO_NAME, 
                         slogan=SLOGAN, 
                         page_title=PAGE_TITLE)

@app.route('/install')
def install():
    return render_template('install.html',
                         studio_name=STUDIO_NAME,
                         matrix_user=MATRIX_USER,
                         matrix_url=MATRIX_URL)

# --- API ---
@app.route('/api/check_update')
def check_update():
    try:
        repo = git.Repo('/app')
        repo.remotes.origin.fetch()
        local = repo.head.commit.hexsha
        remote = repo.remotes.origin.refs.main.commit.hexsha
        if local != remote:
            return jsonify({"available": True, "new": remote[:7]})
        return jsonify({"available": False})
    except:
        return jsonify({"available": False})

@app.route('/api/do_update', methods=['POST'])
def do_update():
    try:
        repo = git.Repo('/app')
        repo.remotes.origin.pull()
        subprocess.Popen(["docker", "compose", "up", "-d", "--build", "dashboard"], cwd="/app")
        return jsonify({"status": "ok"})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route('/api/mark_read/<int:msg_id>', methods=['POST'])
def mark_read(msg_id):
    conn = get_db()
    conn.execute("UPDATE messages SET is_read = 1 WHERE id = ?", (msg_id,))
    conn.commit()
    return jsonify({"success": True})

@app.route('/api/stats')
def api_stats():
    conn = get_db()
    today = datetime.date.today().isoformat()
    try:
        total_today = conn.execute("SELECT COUNT(*) FROM messages WHERE date(timestamp) = ?", (today,)).fetchone()[0]
        unread_total = conn.execute("SELECT COUNT(*) FROM messages WHERE is_read = 0").fetchone()[0]
        history = conn.execute("SELECT date(timestamp) as msg_date, COUNT(*) as count FROM messages GROUP BY date(timestamp) ORDER BY date(timestamp) DESC LIMIT 15").fetchall()
    except:
        return jsonify({"total_today": 0, "unread_total": 0, "chart_labels": [], "chart_values": []})
    
    labels = []
    values = []
    for row in reversed(history):
        d = datetime.datetime.strptime(row['msg_date'], '%Y-%m-%d')
        labels.append(d.strftime('%d-%m'))
        values.append(row['count'])
    return jsonify({"total_today": total_today, "unread_total": unread_total, "chart_labels": labels, "chart_values": values})

@app.route('/api/messages')
def api_messages():
    try:
        cur = get_db().execute("SELECT * FROM messages ORDER BY id DESC LIMIT 150")
        rows = cur.fetchall()
        messages = []
        for row in rows:
            is_read = row["is_read"] if row["is_read"] is not None else 0
            messages.append({
                "id": row["id"], "source": row["source"], 
                "sender_number": row["sender_number"], "sender_name": row["sender_name"], 
                "message": row["message"], "timestamp": row["timestamp"], "is_read": is_read
            })
        return jsonify(messages)
    except:
        return jsonify([])

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=80)
