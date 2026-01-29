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

# Zorg dat de static map bestaat voor QR codes
if not os.path.exists(STATIC_DIR):
    os.makedirs(STATIC_DIR)

# Hulpfunctie voor Database verbinding
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

# --- 1. HOOFDROUTES (Logica voor Wizard of Dashboard) ---

@app.route('/')
def index():
    """
    Dit is de slimme toegangspoort.
    - Geen Token in .env? -> Toon Setup Wizard (WiFi scenario).
    - Wel Token? -> Toon Dashboard.
    """
    token = os.getenv("MATRIX_TOKEN", "")
    studio_name = os.getenv("STUDIO_NAME", "EtherDesk Studio")
    
    # Check of installatie compleet is (Token moet langer zijn dan 10 tekens)
    if not token or len(token) < 10:
        return render_template('setup_wizard.html', studio_name=studio_name)
    
    # Installatie is klaar, toon Dashboard
    return render_template('index.html', 
                           studio_name=studio_name, 
                           slogan=os.getenv("SLOGAN", "Broadcast Interface"), 
                           page_title=os.getenv("PAGE_TITLE", "EtherDesk"))

# --- 2. SETUP & PROVISIONING API (De WiFi Portal Logica) ---

@app.route('/api/setup/submit', methods=['POST'])
def setup_submit():
    """
    Verwerkt het formulier van de Setup Wizard.
    Schrijft settings weg, maakt Matrix user aan, haalt token op en herstart.
    """
    data = request.json
    s_name = data.get('studio_name', 'Radio Capri')
    s_slogan = data.get('slogan', 'Live!')
    m_user = data.get('username', 'etherdesk')
    m_pass = data.get('password')
    
    # Als geen wachtwoord is ingevuld, genereer een random string
    if not m_pass:
        m_pass = ''.join(random.choices(string.ascii_letters + string.digits, k=16))

    try:
        print("--- START AUTO SETUP ---")
        
        # STAP A: Settings naar .env schrijven (Naam & Slogan)
        env_lines = []
        if os.path.exists(ENV_FILE):
            with open(ENV_FILE, 'r') as f: env_lines = f.readlines()
        
        new_lines = []
        keys_handled = set()
        
        # Update bestaande regels
        for line in env_lines:
            key = line.split('=')[0]
            if key == "STUDIO_NAME":
                new_lines.append(f'STUDIO_NAME="{s_name}"\n')
                keys_handled.add(key)
            elif key == "SLOGAN":
                new_lines.append(f'SLOGAN="{s_slogan}"\n')
                keys_handled.add(key)
            elif key in ["MATRIX_USER", "MATRIX_TOKEN"]:
                pass # Die schrijven we straks vers onderaan
            else:
                new_lines.append(line)
        
        # Voeg toe als ze niet bestonden
        if "STUDIO_NAME" not in keys_handled: new_lines.append(f'STUDIO_NAME="{s_name}"\n')
        if "SLOGAN" not in keys_handled: new_lines.append(f'SLOGAN="{s_slogan}"\n')
        
        # STAP B: Matrix Gebruiker Aanmaken (via Docker Commando)
        print(f" -> Creating user {m_user}...")
        cmd = [
            "docker", "exec", "etherdesk-synapse-1", 
            "register_new_matrix_user", 
            "-u", m_user, 
            "-p", m_pass, 
            "-c", "/data/homeserver.yaml", 
            "--admin"
        ]
        # We negeren de output/error hier (als user al bestaat is het ook prima)
        subprocess.run(cmd, capture_output=True)
        
        # STAP C: Token Ophalen via API
        print(" -> Fetching token...")
        # Server naam ophalen uit env of default
        server_name = os.getenv("SERVER_NAME", "my.local.matrix")
        
        # Login request naar Synapse
        login_url = "http://synapse:8008/_matrix/client/r0/login"
        payload = {
            "type": "m.login.password", 
            "user": f"@{m_user}:{server_name}", 
            "password": m_pass
        }
        
        # Korte pauze om zeker te zijn dat Synapse klaar is
        time.sleep(1)
        resp = requests.post(login_url, json=payload)
        resp_data = resp.json()
        
        if 'access_token' not in resp_data:
            return jsonify({"status": "error", "message": f"Login mislukt: {resp_data}"})
            
        token = resp_data['access_token']
        full_user_id = resp_data['user_id']
        
        # STAP D: Token Opslaan in .env
        new_lines.append(f"\nMATRIX_USER={full_user_id}\n")
        new_lines.append(f"MATRIX_TOKEN={token}\n")
        
        with open(ENV_FILE, 'w') as f:
            f.writelines(new_lines)
            
        # STAP E: Herstarten
        print(" -> Restarting Dashboard...")
        subprocess.Popen(["docker", "compose", "restart", "dashboard"], cwd="/app")
        
        return jsonify({"status": "success", "message": "Setup voltooid! Systeem herstart..."})

    except Exception as e:
        print(f"ERROR: {e}")
        return jsonify({"status": "error", "message": str(e)})

# --- 3. BRIDGE & QR CODE ROUTES ---

@app.route('/api/bridge/<bridge>/login', methods=['POST'])
def bridge_login(bridge):
    """Signaal naar Harvester sturen om login te starten"""
    # Bestandsnaam bijv: /data/cmd_whatsapp.txt
    filename = f"/data/cmd_{bridge}.txt"
    with open(filename, "w") as f:
        f.write("LOGIN")
    return jsonify({"status": "requested"})

@app.route('/api/bridge/<bridge>/qr')
def get_qr(bridge):
    """Checken of er een QR plaatje is"""
    img_path = f"{STATIC_DIR}/qr_{bridge}.png"
    if os.path.exists(img_path):
        # We voegen een timestamp toe om caching te voorkomen
        return jsonify({"found": True, "url": f"/static/qr_{bridge}.png?t={time.time()}"})
    return jsonify({"found": False})

# --- 4. DASHBOARD DATA ROUTES (Statistieken & Berichten) ---

@app.route('/api/stats')
def api_stats():
    conn = get_db()
    today = datetime.date.today().isoformat()
    try:
        # Totaal vandaag
        total = conn.execute("SELECT COUNT(*) FROM messages WHERE date(timestamp) = ?", (today,)).fetchone()[0]
        # Totaal ongelezen
        unread = conn.execute("SELECT COUNT(*) FROM messages WHERE is_read = 0").fetchone()[0]
        # Grafiek data (laatste 15 dagen)
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
        # Haal laatste 150 berichten
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

# --- 5. SYSTEM ROUTES (Update) ---

@app.route('/api/check_update')
def check_update():
    try:
        repo = git.Repo('/app')
        repo.remotes.origin.fetch()
        local_commit = repo.head.commit.hexsha
        remote_commit = repo.remotes.origin.refs.main.commit.hexsha
        if local_commit != remote_commit:
            return jsonify({"available": True, "new": remote_commit[:7]})
        return jsonify({"available": False})
    except Exception:
        return jsonify({"available": False})

@app.route('/api/do_update', methods=['POST'])
def do_update():
    try:
        git.Repo('/app').remotes.origin.pull()
        # Herbouwen en herstarten
        subprocess.Popen(["docker", "compose", "up", "-d", "--build", "dashboard"], cwd="/app")
        return jsonify({"status": "ok"})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)})

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=80)
