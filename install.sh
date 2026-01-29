#!/bin/bash

# --- ETHERDESK SYSTEM INSTALLER (COMPLETE) ---
# Bevat: Synapse, WhatsApp Bridge (Fixed), Google Messages Bridge, Dashboard

INSTALL_DIR="/opt/etherdesk"
DATA_DIR="$INSTALL_DIR/data"
WA_DIR="$DATA_DIR/whatsapp"
GM_DIR="$DATA_DIR/gmessages"
SYNAPSE_DIR="$DATA_DIR/synapse"
APP_DIR="$INSTALL_DIR/app"
SERVER_NAME="my.local.matrix"

GREEN='\033[0;32m'
BLUE='\033[0;34m'
NC='\033[0m'

echo -e "${BLUE}=== ETHERDESK COMPLETE INSTALLER ===${NC}"

# 1. Docker Installeren (indien nodig)
if ! command -v docker &> /dev/null; then
    echo "Docker installeren..."
    curl -fsSL https://get.docker.com -o get-docker.sh
    sh get-docker.sh
    rm get-docker.sh
fi

# 2. Omgeving Schoonmaken
echo "Omgeving opschonen..."
cd $INSTALL_DIR
docker compose down > /dev/null 2>&1

# Mappen aanmaken
mkdir -p $APP_DIR/templates $APP_DIR/static
mkdir -p $WA_DIR $GM_DIR $SYNAPSE_DIR

# Database crash fixes
touch $WA_DIR/whatsapp.db
# (Google Messages gebruikt standaard ook een DB, die maken we ook vast aan voor de zekerheid)
touch $GM_DIR/gmessages.db

# .env voorbereiden voor de web-setup
if [ ! -f $APP_DIR/.env ]; then touch $APP_DIR/.env; fi
chmod 666 $APP_DIR/.env

# Rechten openzetten
chmod -R 777 $INSTALL_DIR
chown -R 1000:1000 $DATA_DIR

# 3. WhatsApp Configureren (Hardcoded Fix)
echo "WhatsApp Configureren..."
cat > $WA_DIR/config.yaml <<EOF
homeserver:
    address: http://synapse:8008
    domain: $SERVER_NAME
    verify_ssl: false
appservice:
    address: http://mautrix-whatsapp:29318
    hostname: 0.0.0.0
    port: 29318
    database:
        type: sqlite3-fk-wal
        uri: file:whatsapp.db?_txlock=immediate
    id: whatsapp
    bot:
        username: whatsappbot
        displayname: WhatsApp bridge bot
    ephemeral_events: false
    as_token: "GenereerMij"
    hs_token: "GenereerMij"
bridge:
    username_template: whatsapp_{{.}}
    displayname_template: "{{if .NotifyName}}{{.NotifyName}}{{else}}{{.Jid}}{{end}} (WA)"
    history_sync:
        backfill: true
        request_full_sync: true 
    encryption:
        allow: true
        default: true
        require: true
        appservice: false
        allow_key_sharing: true
permissions:
    "*": "relay"
    "$SERVER_NAME": "admin"
    "@etherdesk:$SERVER_NAME": "admin"
logging:
    min_level: info
    writers:
    - type: stdout
      format: pretty-colored
EOF

# 4. Google Messages Configureren (Auto-Generate + Fix)
echo "Google Messages Configureren..."
if [ ! -f "$GM_DIR/config.yaml" ]; then
    # We laten de container de default config maken
    docker run --rm -v "$GM_DIR:/data" dock.mau.dev/mautrix/gmessages:latest > /dev/null 2>&1
    
    # We passen de belangrijke regels aan met sed
    sed -i "s|address: http://localhost:8008|address: http://synapse:8008|g" $GM_DIR/config.yaml
    sed -i "s|domain: example.com|domain: $SERVER_NAME|g" $GM_DIR/config.yaml
    sed -i "s|hostname: localhost|hostname: 0.0.0.0|g" $GM_DIR/config.yaml
    # Fix Permissions
    sed -i "s|\"example.com\": \"user\"|\"$SERVER_NAME\": \"admin\"\n    \"@etherdesk:$SERVER_NAME\": \"admin\"|g" $GM_DIR/config.yaml
fi

# 5. Synapse Configureren
echo "Synapse Configureren..."
if [ ! -f "$SYNAPSE_DIR/homeserver.yaml" ]; then
    docker run --rm -v "$SYNAPSE_DIR:/data" -e SYNAPSE_SERVER_NAME=$SERVER_NAME -e SYNAPSE_REPORT_STATS=no matrixdotorg/synapse:latest generate
    sed -i 's/enable_registration: false/enable_registration: true/g' $SYNAPSE_DIR/homeserver.yaml
fi

# 6. Docker Compose (De Lijm)
echo "Docker Compose updaten..."
cat > $INSTALL_DIR/docker-compose.yml <<EOF
services:
  synapse:
    image: matrixdotorg/synapse:latest
    container_name: synapse
    restart: unless-stopped
    ports:
      - 8008:8008
    volumes:
      - ./data/synapse:/data

  mautrix-whatsapp:
    image: dock.mau.dev/mautrix/whatsapp:latest
    restart: unless-stopped
    volumes:
      - ./data/whatsapp:/data
    depends_on:
      - synapse

  mautrix-gmessages:
    image: dock.mau.dev/mautrix/gmessages:latest
    restart: unless-stopped
    volumes:
      - ./data/gmessages:/data
    depends_on:
      - synapse

  dashboard:
    build: ./app
    restart: unless-stopped
    ports:
      - 80:80
    volumes:
      - ./app:/app
      - ./data:/data
    environment:
      - MATRIX_HOMESERVER=http://synapse:8008
    depends_on:
      - synapse
      - mautrix-whatsapp
      - mautrix-gmessages
EOF

# 7. Sleutels Genereren (Het moeilijke stuk)
# We gebruiken een tijdelijke 'run' om de sleutels te maken, omdat de containers toegang tot elkaar nodig hebben
echo "Sleutels Genereren..."

# WhatsApp
docker compose run --rm mautrix-whatsapp /usr/bin/python3 -m mautrix_whatsapp -g -c /data/config.yaml -r /data/registration.yaml > /dev/null 2>&1
sed -i 's|url: http://localhost:29318|url: http://mautrix-whatsapp:29318|g' $WA_DIR/registration.yaml
cp $WA_DIR/registration.yaml $SYNAPSE_DIR/whatsapp-registration.yaml

# Google Messages
docker compose run --rm mautrix-gmessages /usr/bin/mautrix-gmessages -g -c /data/config.yaml -r /data/registration.yaml > /dev/null 2>&1
# Let op de poort voor Google Messages (standaard 29335)
sed -i 's|url: http://localhost:29335|url: http://mautrix-gmessages:29335|g' $GM_DIR/registration.yaml
cp $GM_DIR/registration.yaml $SYNAPSE_DIR/gmessages-registration.yaml

# Rechten op registraties
chmod 644 $SYNAPSE_DIR/*-registration.yaml

# 8. Starten
echo -e "${GREEN}Installatie Gereed. Starten...${NC}"
docker compose up -d --build

echo ""
echo -e "${GREEN}KLAAR!${NC}"
echo "WhatsApp én Google Messages zijn geïnstalleerd."
echo "Ga naar http://<JOUW-IP> om de Setup te starten."
