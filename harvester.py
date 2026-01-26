import asyncio
import sqlite3
import re
import os
from datetime import datetime
from nio import AsyncClient, MatrixRoom, RoomMessageText

# --- CONFIG UIT ENVIRONMENT ---
MATRIX_URL = os.getenv("MATRIX_URL", "http://synapse:8008")
MATRIX_USER = os.getenv("MATRIX_USER", "")
ACCESS_TOKEN = os.getenv("MATRIX_TOKEN", "")
DB_FILE = "/data/messages.db"
BATCH_FILE = "/data/next_batch.txt"

client = AsyncClient(MATRIX_URL, MATRIX_USER)

def init_db():
    try:
        conn = sqlite3.connect(DB_FILE)
        c = conn.cursor()
        c.execute('''CREATE TABLE IF NOT EXISTS messages
                     (id INTEGER PRIMARY KEY AUTOINCREMENT, 
                      event_id TEXT UNIQUE,
                      timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                      sender_number TEXT, 
                      sender_name TEXT,
                      message TEXT, 
                      source TEXT,
                      is_read INTEGER DEFAULT 0)''')
        conn.commit()
        conn.close()
    except Exception as e:
        print(f"!!! DB FOUT: {e}")

def save_batch_token(token):
    with open(BATCH_FILE, "w") as f:
        f.write(token)

def load_batch_token():
    if os.path.exists(BATCH_FILE):
        with open(BATCH_FILE, "r") as f:
            return f.read().strip()
    return None

def extract_number(sender_id):
    matches = re.findall(r'\d{7,}', sender_id)
    if matches: return matches[-1]
    return "Nummer onbekend"

def get_local_time():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")

async def main():
    print(f"--- ETHERDESK OOGSTER START VOOR {MATRIX_USER} ---")
    if not MATRIX_USER or not ACCESS_TOKEN:
        print("!!! CRITISCHE FOUT: Geen MATRIX_USER of MATRIX_TOKEN in .env gevonden !!!")
        return

    init_db()
    client.access_token = ACCESS_TOKEN
    
    try:
        await client.whoami()
        print(" -> Verbonden met Matrix!")
    except Exception as e:
        print(f" -> Connectie fout: {e}")
        return

    next_batch = load_batch_token()
    if not next_batch:
        print(" -> Eerste start: Historie overslaan.")
        try:
            sync_resp = await client.sync(timeout=5000)
            next_batch = sync_resp.next_batch
            save_batch_token(next_batch)
        except Exception as e: pass

    async def event_callback(room: MatrixRoom, event: RoomMessageText):
        sender_id = event.sender
        if sender_id == MATRIX_USER: return
        source = "Matrix"
        if "whatsapp" in sender_id: source = "WhatsApp"
        elif "gmessages" in sender_id or "sms" in sender_id: source = "SMS"
        number = extract_number(sender_id)
        display_name = ""
        try:
            response = await client.get_displayname(sender_id)
            if response.displayname: display_name = response.displayname
        except: pass
        current_time = get_local_time()
        try:
            conn = sqlite3.connect(DB_FILE)
            c = conn.cursor()
            c.execute("""INSERT OR IGNORE INTO messages (event_id, timestamp, sender_number, sender_name, message, source, is_read) VALUES (?, ?, ?, ?, ?, ?, 0)""", (event.event_id, current_time, number, display_name, event.body, source))
            conn.commit()
            conn.close()
        except Exception as e: print(f"DB Fout: {e}")

    client.add_event_callback(event_callback, RoomMessageText)
    while True:
        try:
            sync_response = await client.sync(timeout=30000, since=next_batch)
            next_batch = sync_response.next_batch
            save_batch_token(next_batch)
        except Exception as e: await asyncio.sleep(5)

if __name__ == "__main__":
    asyncio.run(main())
