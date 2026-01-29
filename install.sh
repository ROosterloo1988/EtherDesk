#!/bin/bash

# --- CONFIGURATIE ---
INSTALL_DIR="/opt/etherdesk"
DATA_DIR="$INSTALL_DIR/data"
WA_DIR="$DATA_DIR/whatsapp"
SYNAPSE_DIR="$DATA_DIR/synapse"
APP_DIR="$INSTALL_DIR/app"

# Kleurtjes
GREEN='\033[0;32m'
BLUE='\033[0;34m'
NC='\033[0m'

echo -e "${BLUE}=== ETHERDESK DEFINITIVE INSTALLER ===${NC}"

# 1. Docker Check
if ! command -v docker &> /dev/null; then
    echo "Docker installeren..."
    curl -fsSL https://get.docker.com -o get-docker.sh
    sh get-docker.sh
    rm get-docker.sh
fi

# 2. Alles stoppen en opschonen (zodat we vers beginnen)
echo "Oude containers stoppen..."
cd $INSTALL_DIR
docker compose down > /dev/null 2>&1

# 3. Mappen & Rechten (De botte bijl methode: alles mag alles)
echo "Mappen en rechten herstellen..."
mkdir -p $APP_DIR/templates $APP_DIR/static
mkdir -p $WA_DIR $SYNAPSE_DIR

# Database file alvast aanmaken om crashes te voorkomen
touch $WA_DIR/whatsapp.db

# Rechten openzetten
chmod -R 777 $INSTALL_DIR
chown -R 1000:1000 $DATA_DIR

# 4. WhatsApp Configureren (De werkende config forceren)
echo "WhatsApp Config schrijven..."
cat > $WA_DIR/config.yaml <<EOF
homeserver:
    address: http://synapse:8008
    domain: my.local.matrix
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
    as_token: "DitWordtOverschreven"
    hs_token: "DitWordtOverschreven"
bridge:
    username_template: whatsapp_{{.}}
    displayname_template: "{{if .NotifyName}}{{.NotifyName}}{{else}}{{.Jid}}{{end}} (WA)"
    history_sync:
        backfill: true
        request_full_sync: true 
    private_chat_portal_meta: true
    encryption:
        allow: true
        default: true
        require: true
        appservice: false
        allow_key_sharing: true
permissions:
    "*": "relay"
    "my.local.matrix": "admin"
    "@etherdesk:my.local.matrix": "admin"
logging:
    min_level: info
    writers:
    - type: stdout
      format: pretty-colored
EOF

# 5. Synapse Configureren
if [ ! -f "$SYNAPSE_DIR/homeserver.yaml" ]; then
    echo "Synapse config genereren..."
    docker run --rm -v "$SYNAPSE_DIR:/data" -e SYNAPSE_SERVER_NAME=my.local.matrix -e SYNAPSE_REPORT_STATS=no matrixdotorg/synapse:latest generate
    # Registratie aanzetten
    sed -i 's/enable_registration: false/enable_registration: true/g' $SYNAPSE_DIR/homeserver.yaml
fi

# 6. Docker Compose updaten
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
EOF

# 7. Sleutels Genereren (De cruciale stap)
echo "Sleutels genereren..."
# We gebruiken de docker-compose file om de tool te draaien, zodat de volumes kloppen
docker compose run --rm mautrix-whatsapp /usr/bin/python3 -m mautrix_whatsapp -g -c /data/config.yaml -r /data/registration.yaml > /dev/null 2>&1

# URL Fixen (dit ging steeds mis, nu doen we het hardcoded)
sed -i 's|url: http://localhost:29318|url: http://mautrix-whatsapp:29318|g' $WA_DIR/registration.yaml

# Kopiëren naar Synapse
cp $WA_DIR/registration.yaml $SYNAPSE_DIR/whatsapp-registration.yaml
chmod 644 $SYNAPSE_DIR/whatsapp-registration.yaml

# 8. Starten
echo -e "${GREEN}Configuratie gereed. Starten...${NC}"
docker compose up -d --build

echo ""
echo -e "${GREEN}KLAAR! Wacht 30 seconden en ga naar het dashboard.${NC}"
