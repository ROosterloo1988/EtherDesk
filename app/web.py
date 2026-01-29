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
        print("--- START
