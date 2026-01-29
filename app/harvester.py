import os
import time
import sys
import requests
import json

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
    try:
        domain = user_id.split(':')[1]
        bot_id = f"@{bridge_suffix}:{domain}"
        url = f"{HOMESERVER}/_matrix/client/r0/createRoom"
        headers = {"Authorization": f"Bearer {token}"}
        data = {"invite": [bot_id], "is_direct": True, "preset": "trusted_private_chat"}
        resp = requests.post(url, headers=headers, json=data)
        if resp.status_code == 200: return resp.json()['room_id']
    except Exception: return None # Fail silently/retry

def send_message(token, room_id, text):
    url = f"{HOMESERVER}/_matrix/client/r0/rooms/{room_id}/send/m.room.message/{int(time.time())}"
    headers = {"Authorization": f"Bearer {token}"}
    requests.put(url, headers=headers, json={"msgtype": "m.text", "body": text})

def download_mxc(token, mxc_url, filename):
    if not mxc_url.startswith("mxc://"): return False
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
    except Exception: pass
    return False

# --- MAIN LOOP ---
log("--- HARVESTER STARTED ---")

token = None
user = None
wa_room = None
next_batch = None 

while True:
    if not token:
        token, user = matrix_login()
        if token: 
            log(f"Ingelogd als {user}")
            try:
                r = requests.get(f"{HOMESERVER}/_matrix/client/r0/sync?timeout=0", headers={"Authorization": f"Bearer {token}"})
                next_batch = r.json().get('next_batch')
            except: pass
        else:
            time.sleep(2)
            continue

    if os.path.exists(CMD_FILE_WA):
        log("COMMAND: LOGIN QR WhatsApp")
        try:
            os.remove(CMD_FILE_WA)
            if not wa_room: wa_room = create_dm(token, user, "whatsappbot")
            
            if wa_room:
                log(f"Stuur 'logout' naar {wa_room}")
                send_message(token, wa_room, "logout")
                time.sleep(1)
                log(f"Stuur 'login qr' naar {wa_room}")
                send_message(token, wa_room, "login qr")
                
                found_qr = False
                for _ in range(25): 
                    try:
                        sync_url = f"{HOMESERVER}/_matrix/client/r0/sync?timeout=2000&since={next_batch}"
                        r = requests.get(sync_url, headers={"Authorization": f"Bearer {token}"})
                        data = r.json()
                        next_batch = data.get('next_batch', next_batch)
                        
                        rooms = data.get('rooms', {}).get('join', {})
                        if wa_room in rooms:
                            events = rooms[wa_room].get('timeline', {}).get('events', [])
                            for e in events:
                                content = e.get('content', {})
                                if e.get('sender') == user: continue 

                                if content.get('msgtype') == 'm.image':
                                    if download_mxc(token, content.get('url'), "qr_whatsapp.png"):
                                        found_qr = True
                                        break 
                                
                                if "Already logged in" in content.get('body', ''):
                                    found_qr = True; break
                    except Exception: pass
                    
                    if found_qr or os.path.exists(f"{STATIC_DIR}/qr_whatsapp.png"): break
                    time.sleep(1)
        except Exception as e: log(f"Fout: {e}")

    if os.path.exists(CMD_FILE_SMS):
        try: os.remove(CMD_FILE_SMS)
        except: pass
    time.sleep(1)
