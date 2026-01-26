import asyncio
import sqlite3
import re
import os
import aiohttp
from datetime import datetime
from nio import AsyncClient, MatrixRoom, RoomMessageText

# CONFIG
MATRIX_URL = os.getenv("MATRIX_URL", "http://synapse:8008")
MATRIX_USER = os.getenv("MATRIX_USER", "")
ACCESS_TOKEN = os.getenv("MATRIX_TOKEN", "")
DB_FILE = "/data/messages.db"
STATIC_DIR = "/app/static"

if not os.path.exists(STATIC_DIR): os.makedirs(STATIC_DIR)

client = AsyncClient(MATRIX_URL, MATRIX_USER)

def init_db():
    conn = sqlite3.connect(DB_FILE)
    conn.execute('CREATE TABLE IF NOT EXISTS messages (id INTEGER PRIMARY KEY AUTOINCREMENT, event_id TEXT UNIQUE, timestamp DATETIME DEFAULT CURRENT_TIMESTAMP, sender_number TEXT, sender_name TEXT, message TEXT, source TEXT, is_read INTEGER DEFAULT 0)')
    conn.commit()
    conn.close()

async def check_commands():
    bridges = {'whatsapp': '@whatsappbot:my.local.matrix', 'gmessages': '@gmessagesbot:my.local.matrix'}
    for name, user_id in bridges.items():
        cmd_file = f"/data/cmd_{name}.txt"
        if os.path.exists(cmd_file):
            print(f" -> COMMAND: LOGIN {name}")
            os.remove(cmd_file)
            try:
                room = await client.room_create(invite=[user_id])
                await client.room_send(room.room_id, message_type="m.room.message", content={"msgtype": "m.text", "body": "login"})
            except Exception as e: print(f"Err: {e}")

async def main():
    print("--- HARVESTER V2 ---")
    while not ACCESS_TOKEN:
        print("Waiting for Token...")
        await asyncio.sleep(5)
        return

    init_db()
    client.access_token = ACCESS_TOKEN
    await client.whoami()

    async def event_callback(room: MatrixRoom, event: RoomMessageText):
        # QR Code Check
        if event.sender in ['@whatsappbot:my.local.matrix', '@gmessagesbot:my.local.matrix']:
            if 'url' in event.source['content']:
                bridge = "whatsapp" if "whatsapp" in event.sender else "gmessages"
                try:
                    resp = await client.download_media(event.source['content']['url'])
                    with open(f"{STATIC_DIR}/qr_{bridge}.png", "wb") as f: f.write(resp.body)
                    print(f" -> QR SAVED: {bridge}")
                except: pass

        # Message Storage
        if event.sender == MATRIX_USER: return
        source = "Matrix"
        if "whatsapp" in event.sender: source = "WhatsApp"
        elif "gmessages" in event.sender: source = "SMS"
        
        num = re.findall(r'\d{7,}', event.sender)
        number = num[-1] if num else "Onbekend"
        name = ""
        try: name = (await client.get_displayname(event.sender)).displayname
        except: pass
        
        try:
            conn = sqlite3.connect(DB_FILE)
            conn.execute("INSERT OR IGNORE INTO messages (event_id, timestamp, sender_number, sender_name, message, source, is_read) VALUES (?, ?, ?, ?, ?, ?, 0)", 
                (event.event_id, datetime.now().strftime("%Y-%m-%d %H:%M:%S"), number, name, event.body, source))
            conn.commit()
            conn.close()
        except: pass

    client.add_event_callback(event_callback, RoomMessageText)
    
    while True:
        await check_commands()
        try: await client.sync(timeout=3000)
        except: await asyncio.sleep(2)

if __name__ == "__main__":
    asyncio.run(main())
