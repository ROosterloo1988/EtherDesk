import os
import time
import sys
import requests
import json

# --- CONFIGURATIE ---
# Paden
CMD_FILE_WA = "/data/cmd_whatsapp.txt"
CMD_FILE_SMS = "/data/cmd_gmessages.txt"
STATIC_DIR = "/app/static"
ENV_FILE = "/app/.env"

# Matrix Settings (worden geladen uit .env)
HOMESERVER = "http://synapse:8008"

def get_env_var(var_name):
    """Lees variabele uit .env bestand"""
    if os.path.exists(ENV_FILE):
        with open(ENV_FILE, 'r') as f:
            for line in f:
                if line.startswith(f"{var_name}="):
                    return line.split('=', 1)[1].strip()
    return None

def log(msg):
    print(f"[HARVESTER] {msg}")
    sys.stdout.flush()

def matrix_login():
    """Haal token op via login of .env"""
    token = get_env_var("MATRIX_TOKEN")
    user_id = get_env_var("MATRIX_USER")
    
    if token and user_id:
        return token, user_id
    
    log("ERROR: Nog geen token in .env gevonden. Harvester wacht...")
    return None, None

def send_matrix_message(token, room_id, text):
    """Stuur bericht naar Matrix room"""
    url = f"{HOMESERVER}/_matrix/client/r0/rooms/{room_id}/send/m.room.message"
    headers = {"Authorization": f"Bearer {token}"}
    data = {
        "msgtype": "m.text",
        "body": text
    }
    # Transaction ID mag random zijn of tijd
    requests.put(f"{url}/{int(time.time())}", headers=headers, json=data)

def create_dm(token, user_id):
    """Maak Direct Message aan met de bridge bot"""
    # We proberen een DM te starten met de WhatsApp bot
    # De bot heet meestal @whatsappbot:domeinnaam
    domain = user_id.split(':')[1]
    bot_id = f"@whatsappbot:{domain}"
    
    url = f"{HOMESERVER}/_matrix/client/r0/createRoom"
    headers = {"Authorization": f"Bearer {token}"}
    data = {
        "invite": [bot_id],
        "is_direct": True,
        "preset": "trusted_private_chat"
    }
    resp = requests.post(url, headers=headers, json=data)
    if resp.status_code == 200:
        return resp.json()['room_id']
    else:
        log(f"Kon geen DM maken met {bot_id}: {resp.text}")
        return None

def download_image(url, filename):
    """Download plaatje van Matrix naar static map"""
    try:
        resp = requests.get(url)
        if resp.status_code == 200:
            with open(f"{STATIC_DIR}/{filename}", 'wb') as f:
                f.write(resp.content)
            log(f"QR Code opgeslagen: {filename}")
            return True
    except Exception as e:
        log(f"Fout bij downloaden: {e}")
    return False

# --- MAIN LOOP ---

log("--- HARVESTER STARTED ---")

# Wacht tot .env gevuld is door de installer
matrix_token = None
matrix_user = None

# We houden bij in welke kamer we praten met de bot
wa_room_id = None

while True:
    # 1. Check of we credentials hebben
    if not matrix_token:
        matrix_token, matrix_user = matrix_login()
        if not matrix_token:
            time.sleep(5)
            continue
        log(f"Ingelogd als {matrix_user}")

    # 2. Check WhatsApp Commando
    if os.path.exists(CMD_FILE_WA):
        log("COMMAND: LOGIN WhatsApp aangevraagd")
        try:
            os.remove(CMD_FILE_WA)
            
            # Zorg dat we een kamer hebben
            if not wa_room_id:
                wa_room_id = create_dm(matrix_token, matrix_user)
            
            if wa_room_id:
                # Stuur 'login' commando naar de bot
                log(f"Stuur 'login' naar room {wa_room_id}")
                send_matrix_message(matrix_token, wa_room_id, "login")
                
                # NU MOETEN WE LUISTEREN NAAR HET ANTWOORD
                # Dit is een simpele sync loop voor de komende 30 seconden
                log("Luisteren naar QR code...")
                sync_url = f"{HOMESERVER}/_matrix/client/r0/sync?timeout=30000"
                headers = {"Authorization": f"Bearer {matrix_token}"}
                
                # We doen 1 lange poll of een paar korte
                # Voor nu simpel: we vragen de sync op.
                # In een echte situatie is dit complexer, maar voor nu hopen we
                # dat de bridge snel antwoordt met een plaatje.
                
                # NOTE: Bridges sturen QR codes vaak als HTML img tags of attachments.
                # Omdat dit complex is om te parsen zonder zware library,
                # doen we een 'Blind Assumption':
                # Als we een image message ontvangen in deze kamer, is het de QR.
                
                # (Voor nu is dit script een placeholder die de logica toont.
                # Het parsen van de QR uit de Matrix event stream is lastig in 
                # een klein scriptje zonder de matrix-nio library. 
                # Zorg dat in de Dockerfile 'matrix-nio' is geïnstalleerd!)
                
        except Exception as e:
            log(f"ERROR WA: {e}")

    # 3. Check SMS Commando
    if os.path.exists(CMD_FILE_SMS):
         # Zelfde logica voor GMessages...
         try:
            os.remove(CMD_FILE_SMS)
            log("COMMAND: LOGIN SMS (nog niet geïmplementeerd in demo)")
         except: pass

    time.sleep(1)
