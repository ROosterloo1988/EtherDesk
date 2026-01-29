import os
import time
import sys
import requests
import json

# --- CONFIGURATIE ---
CMD_FILE_WA = "/data/cmd_whatsapp.txt"
CMD_FILE_SMS = "/data/cmd_gmessages.txt"
STATIC_DIR = "/app/static"
ENV_FILE = "/app/.env"
HOMESERVER = "http://synapse:8008"

def log(msg):
    print(f"[HARVESTER] {msg}")
    sys.stdout.flush()

def get_env_var(var_name):
    if os.path.exists(ENV_FILE):
        with open(ENV_FILE, 'r') as f:
            for line in f:
                if line.startswith(f"{var_name}="):
                    return line.split('=', 1)[1].strip()
    return None

def matrix_login():
    token = get_env_var("MATRIX_TOKEN")
    user_id = get_env_var("MATRIX_USER")
    if token and user_id: return token, user_id
    return None, None

def create_dm(token, user_id, bridge_suffix):
    """Maakt een chat aan met de bot (bijv @whatsappbot:domein)"""
    try:
        domain = user_id.split(':')[1]
        bot_id = f"@{bridge_suffix}:{domain}"
        
        # 1. Probeer eerst te kijken of we al een room hebben (via sync)
        # (Voor nu skippen we dit voor eenvoud en maken gewoon een create request, 
        # Matrix geeft bestaande room terug als die er al is)
        
        url = f"{HOMESERVER}/_matrix/client/r0/createRoom"
        headers = {"Authorization": f"Bearer {token}"}
        data = {"invite": [bot_id], "is_direct": True, "preset": "trusted_private_chat"}
        
        resp = requests.post(url, headers=headers, json=data)
        if resp.status_code == 200:
            return resp.json()['room_id']
        else:
            log(f"Kon DM niet starten met {bot_id}: {resp.status_code}")
    except Exception as e:
        log(f"Fout bij create_dm: {e}")
    return None

def send_message(token, room_id, text):
    url = f"{HOMESERVER}/_matrix/client/r0/rooms/{room_id}/send/m.room.message/{int(time.time())}"
    headers = {"Authorization": f"Bearer {token}"}
    requests.put(url, headers=headers, json={"msgtype": "m.text", "body": text})

def download_mxc(token, mxc_url, filename):
    """Vertaalt mxc://server/mediaid naar http url en downloadt het"""
    if not mxc_url.startswith("mxc://"): return False
    
    # mxc://example.com/12345 -> example.com/12345
    clean_url = mxc_url[6:] 
    download_url = f"{HOMESERVER}/_matrix/media/r0/download/{clean_url}"
    
    headers = {"Authorization": f"Bearer {token}"}
    try:
        r = requests.get(download_url, headers=headers)
        if r.status_code == 200:
            with open(f"{STATIC_DIR}/{filename}", 'wb') as f:
                f.write(r.content)
            log(f"SUCCESS: QR code opgeslagen als {filename}")
            return True
        else:
            log(f"Download fout {r.status_code} op {download_url}")
    except Exception as e:
        log(f"Download exceptie: {e}")
    return False

# --- MAIN LOOP ---
log("--- HARVESTER STARTED ---")

# State
token = None
user = None
wa_room = None
next_batch = None # Voor sync positie

while True:
    # 1. Zorg dat we ingelogd zijn
    if not token:
        token, user = matrix_login()
        if token: 
            log(f"Ingelogd als {user}")
            # Haal eerste sync token op om oude berichten te negeren
            try:
                r = requests.get(f"{HOMESERVER}/_matrix/client/r0/sync?timeout=0", headers={"Authorization": f"Bearer {token}"})
                next_batch = r.json().get('next_batch')
            except: pass
        else:
            time.sleep(5)
            continue

    # 2. Check WhatsApp Trigger
    if os.path.exists(CMD_FILE_WA):
        log("COMMAND: LOGIN WhatsApp")
        try:
            os.remove(CMD_FILE_WA)
            if not wa_room: wa_room = create_dm(token, user, "whatsappbot")
            
            if wa_room:
                send_message(token, wa_room, "login")
                
                # --- SYNC LOOP (Luister 20 sec naar antwoord) ---
                log("Wachten op QR (20s)...")
                for _ in range(10): # 10x 2 seconden
                    try:
                        sync_url = f"{HOMESERVER}/_matrix/client/r0/sync?timeout=2000&since={next_batch}"
                        r = requests.get(sync_url, headers={"Authorization": f"Bearer {token}"})
                        data = r.json()
                        next_batch = data.get('next_batch', next_batch)
                        
                        # Loop door rooms
                        rooms = data.get('rooms', {}).get('join', {})
                        if wa_room in rooms:
                            events = rooms[wa_room].get('timeline', {}).get('events', [])
                            for e in events:
                                content = e.get('content', {})
                                # Check op Plaatje (QR)
                                if content.get('msgtype') == 'm.image':
                                    mxc = content.get('url')
                                    log(f"Plaatje ontvangen! URL: {mxc}")
                                    if download_mxc(token, mxc, "qr_whatsapp.png"):
                                        break # Klaar!
                                
                                # Check op Tekst (Foutmeldingen of status)
                                if content.get('msgtype') == 'm.text':
                                    body = content.get('body', '')
                                    log(f"Bot zegt: {body}")
                                    if "Logged in" in body:
                                        log("Al ingelogd!")
                                        break
                    except Exception as e:
                        log(f"Sync fout: {e}")
                    
                    # Als het bestand er is, stop met wachten
                    if os.path.exists(f"{STATIC_DIR}/qr_whatsapp.png"):
                        break
                        
        except Exception as e:
            log(f"Fout in WA flow: {e}")

    # 3. Check SMS Trigger
    if os.path.exists(CMD_FILE_SMS):
        try:
            os.remove(CMD_FILE_SMS)
            log("SMS Login nog niet actief in deze demo.")
        except: pass

    time.sleep(1)
