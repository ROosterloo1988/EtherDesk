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

# --- CONFIGURATIE ---
DB_FILE = "/data/messages.db"
ENV_FILE = "/app/.env"
STATIC_DIR = "/app/static"
DOCKER_COMPOSE_FILE = "/app/docker-compose.yml"

# Zorg dat de static map bestaat voor QR codes
if not os.path.exists(STATIC_DIR):
    os.makedirs(STATIC_DIR)

# --- DATABASE HULPFUNCTIES ---
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

# --- HELPER: TOKEN LEZEN (DE LOOP FIX) ---
def get_token_from_file():
    """
    Leest het token rechtstreeks uit het bestand.
    Dit is nodig omdat os.getenv() pas update na een herstart.
    """
    try:
        if os.path.exists(ENV_FILE):
            with open(ENV_FILE, 'r') as f:
                for line in f:
                    if line.startswith("MATRIX_TOKEN="):
                        # Split op '=' en pak het tweede deel, strip enters/spaties
                        return line.split('=', 1)[1].strip()
    except Exception as e:
        print(f"Fout bij lezen .env: {e}")
    return ""

# --- 1. HOOFDROUTE (ROUTER) ---
@app.route('/')
def index():
    # Stap 1: Check omgevingsvariabele (snelst)
    token = os.getenv("MATRIX_TOKEN", "")
    
    # Stap 2: Check bestand (fallback voor net na installatie)
    if not token or len(token) < 10:
        token = get_token_from_file()

    studio_name = os.getenv("STUDIO_NAME", "EtherDesk Studio")
    
    # Stap 3: Beslis welke pagina we tonen
    # Geen geldig token? -> Setup Wizard
    if not token or len(token) < 10:
        return render_template('setup_wizard.html', studio_name=studio_name)
    
    # Wel token? -> Dashboard
    return render_template('index.html', 
                           studio_name=studio_name, 
                           slogan=os.getenv("SLOGAN", "Broadcast Interface"), 
                           page_title=os.getenv("PAGE_TITLE", "EtherDesk"))

# --- 2. SETUP API (WIZARD LOGICA) ---
@app.route('/api/setup/submit', methods=['POST'])
def setup_submit():
    data = request.json
    s_name = data.get('studio_name', 'Radio Capri')
    s_slogan = data.get('slogan', 'Live!')
    m_user = data.get('username', 'etherdesk')
    m_pass = data.get('password')
    
    # Genereer random wachtwoord indien leeg
    if not m_pass:
        m_pass = ''.join(random.choices(string.ascii_letters + string.digits, k=16))

    try:
        print("--- START AUTO SETUP ---")
        
        # A. .env Bestand Bijwerken (Naam & Slogan)
        env_lines = []
        if os.path.exists(ENV_FILE):
            with open(ENV_FILE, 'r') as f: env_lines = f.readlines()
        
        new_lines = []
        keys_handled = set()
        
        for line in env_lines:
            key = line.split('=')[0]
            if key == "STUDIO_NAME":
                new_lines.append(f'STUDIO_NAME="{s_name}"\n')
                keys_handled.add(key)
            elif key == "SLOGAN":
                new_lines.append(f'SLOGAN="{s_slogan}"\n')
                keys_handled.add(key)
            elif key in ["MATRIX_USER", "MATRIX_TOKEN"]:
                pass # Verwijder oude tokens, we schrijven nieuwe onderaan
            else:
                new_lines.append(line)
        
        if "STUDIO_NAME" not in keys_handled: new_lines.append(f'STUDIO_NAME="{s_name}"\n')
        if "SLOGAN" not in keys_handled: new_lines.append(f'SLOGAN="{s_slogan}"\n')
        
        # B. Matrix User Aanmaken
        print(f" -> Creating user {m_user}...")
        cmd = [
            "docker", "exec", "etherdesk-synapse-1", 
            "register_new_matrix_user", 
            "-u", m_user, 
            "-p", m_pass, 
            "-c", "/data/homeserver.yaml", 
            "--admin"
        ]
        subprocess.run(cmd, capture_output=True)
        
        # C. Token Ophalen
        print(" -> Fetching token...")
        server_name = os.getenv("SERVER_NAME", "my.local.matrix")
        
        login_url = "http://synapse:8008/_matrix/client/r0/login"
        payload = {
            "type": "m.login.password", 
            "user": f"@{m_user}:{server_name}", 
            "password": m_pass
        }
        
        time.sleep(1) # Synapse adempauze
        resp = requests.post(login_url, json=payload)
        resp_data = resp.json()
        
        if 'access_token' not in resp_data:
            return jsonify({"status": "error", "message": f"Login mislukt: {resp_data}"})
            
        token = resp_data['access_token']
        full_user_id = resp_data['user_id']
        
        # D. Token Opslaan in .env
        new_lines.append(f"\nMATRIX_USER={full_user_id}\n")
        new_lines.append(f"MATRIX_TOKEN={token}\n")
        
        with open(ENV_FILE, 'w') as f:
            f.writelines(new_lines)
            
        # E. Herstarten (Non-blocking)
        print(" -> Restarting Dashboard...")
        # We gebruiken Popen zodat de request kan afronden voordat de container sterft
        subprocess.Popen(["docker", "compose", "restart", "dashboard"], cwd="/app")
        
        return jsonify({"status": "success", "message": "Geconfigureerd! Systeem herstart..."})

    except Exception as e:
        print(f"ERROR: {e}")
        return jsonify({"status": "error", "message": str(e)})

# --- 3. BRIDGE & QR ROUTES ---
@app.route('/api/bridge/<bridge>/login', methods=['POST'])
def bridge_login(bridge):
    """Maakt bestand aan dat Harvester oppikt"""
    filename = f"/data/cmd_{bridge}.txt"
    try:
        with open(filename, "w") as f:
            f.write("LOGIN")
        return jsonify({"status": "requested"})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)})

@app.route('/api/bridge/<bridge>/qr')
def get_qr(bridge):
    """Checkt of Harvester plaatje heeft gedownload"""
    img_path = f"{STATIC_DIR}/qr_{bridge}.png"
    if os.path.exists(img_path):
        # Timestamp voor cache busting
        return jsonify({"found": True, "url": f"/static/qr_{bridge}.png?t={time.time()}"})
    return jsonify({"found": False})

# --- 4. DATA ROUTES (DASHBOARD) ---
@app.route('/api/stats')
def api_stats():
    conn = get_db()
    today = datetime.date.today().isoformat()
    try:
        total = conn.execute("SELECT COUNT(*) FROM messages WHERE date(timestamp) = ?", (today,)).fetchone()[0]
        unread = conn.execute("SELECT COUNT(*) FROM messages WHERE is_read = 0").fetchone()[0]
        # Laatste 15 dagen grafiek
        hist = conn.execute("SELECT date(timestamp) as d, COUNT(*) as c FROM messages GROUP BY date(timestamp) ORDER BY date(timestamp) DESC LIMIT 15").fetchall()
        
        return jsonify({
            "total_today": total, 
            "unread_total": unread, 
            "chart_labels": [datetime.datetime.strptime(r['d'], '%Y-%m-%d').strftime('%d-%m') for r in reversed(hist)], 
            "chart_values": [r['c'] for r in reversed(hist)]
        })
    except Exception:
        return jsonify({"total_today": 0, "unread_total": 0, "chart_labels": [], "chart_values": []})

@app.route('/api/messages')
def api_messages():
    try:
        rows = get_db().execute("SELECT * FROM messages ORDER BY id DESC LIMIT 150").fetchall()
        return jsonify([dict(row) for row in rows])
    except Exception:
        return jsonify([])

@app.route('/api/mark_read/<int:msg_id>', methods=['POST'])
def mark_read(msg_id):
    try:
        get_db().execute("UPDATE messages SET is_read = 1 WHERE id = ?", (msg_id,))
        get_db().commit()
        return jsonify({"success": True})
    except Exception:
        return jsonify({"success": False})

# --- 5. SYSTEM ROUTES ---
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
    except Exception:
        return jsonify({"available": False})

@app.route('/api/do_update', methods=['POST'])
def do_update():
    try:
        git.Repo('/app').remotes.origin.pull()
        # Herbouw en herstart
        subprocess.Popen(["docker", "compose", "up", "-d", "--build", "dashboard"], cwd="/app")
        return jsonify({"status": "ok"})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)})

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=80)
