from flask import Flask, render_template, g, jsonify, request
import sqlite3
import datetime
import git
import subprocess
import os
import requests
import time
import random
import string

app = Flask(__name__)
DB_FILE = "/data/messages.db"
ENV_FILE = "/app/.env"

# --- CONFIG ---
STUDIO_NAME = os.getenv("STUDIO_NAME", "EtherDesk")
SLOGAN = os.getenv("SLOGAN", "Broadcast Interface")
PAGE_TITLE = os.getenv("PAGE_TITLE", "EtherDesk")
MATRIX_TOKEN = os.getenv("MATRIX_TOKEN", "")

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
    # Als token ontbreekt of te kort is -> Naar installatie
    if not MATRIX_TOKEN or len(MATRIX_TOKEN) < 10:
        return render_template('install.html', studio_name=STUDIO_NAME)
    return render_template('index.html', studio_name=STUDIO_NAME, slogan=SLOGAN, page_title=PAGE_TITLE)

@app.route('/install')
def install():
    return render_template('install.html', studio_name=STUDIO_NAME)

# --- PROVISIONING & QR API ---
@app.route('/api/provision/auto_setup', methods=['POST'])
def auto_setup():
    try:
        password = ''.join(random.choices(string.ascii_letters + string.digits, k=16))
        # Docker commando om user te maken in Synapse container
        cmd = ["docker", "exec", "etherdesk-synapse-1", "register_new_matrix_user", "-u", "etherdesk", "-p", password, "-c", "/data/homeserver.yaml", "--admin"]
        subprocess.run(cmd, capture_output=True)
        
        # Token ophalen
        time.sleep(2)
        resp = requests.post("http://synapse:8008/_matrix/client/r0/login", json={"type": "m.login.password", "user": "@etherdesk:my.local.matrix", "password": password})
        data = resp.json()
        
        if 'access_token' not in data: return jsonify({"status": "error", "message": f"Login mislukt: {data}"})
        
        # Schrijf naar .env
        with open(ENV_FILE, 'r') as f: lines = f.readlines()
        with open(ENV_FILE, 'w') as f:
            found = False
            for line in lines:
                if line.startswith("MATRIX_TOKEN="):
                    f.write(f"MATRIX_TOKEN={data['access_token']}\n")
                    found = True
                else: f.write(line)
            if not found: f.write(f"\nMATRIX_TOKEN={data['access_token']}\n")
            
        return jsonify({"status": "success"})
    except Exception as e: return jsonify({"status": "error", "message": str(e)})

@app.route('/api/provision/restart', methods=['POST'])
def trigger_restart():
    subprocess.Popen(["docker", "compose", "restart", "dashboard"], cwd="/app")
    return jsonify({"status": "ok"})

@app.route('/api/bridge/<bridge>/login', methods=['POST'])
def bridge_login(bridge):
    with open(f"/data/cmd_{bridge}.txt", "w") as f: f.write("LOGIN")
    return jsonify({"status": "requested"})

@app.route('/api/bridge/<bridge>/qr')
def get_qr(bridge):
    path = f"/app/static/qr_{bridge}.png"
    if os.path.exists(path): return jsonify({"found": True, "url": f"/static/qr_{bridge}.png?t={time.time()}"})
    return jsonify({"found": False})

# --- DATA API'S ---
@app.route('/api/check_update')
def check_update():
    try:
        repo = git.Repo('/app')
        repo.remotes.origin.fetch()
        if repo.head.commit.hexsha != repo.remotes.origin.refs.main.commit.hexsha:
            return jsonify({"available": True, "new": repo.remotes.origin.refs.main.commit.hexsha[:7]})
        return jsonify({"available": False})
    except: return jsonify({"available": False})

@app.route('/api/do_update', methods=['POST'])
def do_update():
    git.Repo('/app').remotes.origin.pull()
    subprocess.Popen(["docker", "compose", "up", "-d", "--build", "dashboard"], cwd="/app")
    return jsonify({"status": "ok"})

@app.route('/api/mark_read/<int:msg_id>', methods=['POST'])
def mark_read(msg_id):
    get_db().execute("UPDATE messages SET is_read = 1 WHERE id = ?", (msg_id,))
    get_db().commit()
    return jsonify({"success": True})

@app.route('/api/stats')
def api_stats():
    conn = get_db()
    today = datetime.date.today().isoformat()
    try:
        total = conn.execute("SELECT COUNT(*) FROM messages WHERE date(timestamp) = ?", (today,)).fetchone()[0]
        unread = conn.execute("SELECT COUNT(*) FROM messages WHERE is_read = 0").fetchone()[0]
        hist = conn.execute("SELECT date(timestamp) as d, COUNT(*) as c FROM messages GROUP BY date(timestamp) ORDER BY date(timestamp) DESC LIMIT 15").fetchall()
        return jsonify({"total_today": total, "unread_total": unread, "chart_labels": [datetime.datetime.strptime(r['d'], '%Y-%m-%d').strftime('%d-%m') for r in reversed(hist)], "chart_values": [r['c'] for r in reversed(hist)]})
    except: return jsonify({"total_today": 0, "unread_total": 0, "chart_labels": [], "chart_values": []})

@app.route('/api/messages')
def api_messages():
    try:
        rows = get_db().execute("SELECT * FROM messages ORDER BY id DESC LIMIT 150").fetchall()
        return jsonify([dict(row) for row in rows])
    except: return jsonify([])

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=80)
