#!/bin/bash

# --- ETHERDESK SYSTEM PREP ---
# Dit script bereidt de server voor, maar laat de user-aanmaak over aan de Web Interface.

INSTALL_DIR="/opt/etherdesk"
DATA_DIR="$INSTALL_DIR/data"
WA_DIR="$DATA_DIR/whatsapp"
SYNAPSE_DIR="$DATA_DIR/synapse"
APP_DIR="$INSTALL_DIR/app"
SERVER_NAME="my.local.matrix"

GREEN='\033[0;32m'
BLUE='\033[0;34m'
NC='\033[0m'

echo -e "${BLUE}=== ETHERDESK SYSTEM PREPARATION ===${NC}"

# 1. Schoon Schip (Container stop & verwijder oude data)
# LET OP: We gooien de database weg zodat de klant echt vers begint!
cd $INSTALL_DIR
docker compose down > /dev/null 2>&1
rm -rf $SYNAPSE_DIR/homeserver.db 
rm -rf $SYNAPSE_DIR/homeserver.yaml
# We behouden de whatsapp mappen even niet, vers start is beter voor setup
rm -rf $WA_DIR

echo "Mappen aanmaken..."
mkdir -p $APP_DIR/templates $APP_DIR/static
mkdir -p $WA_DIR $SYNAPSE_DIR

# 2. Configuraties
echo "Configs schrijven..."

# A. WhatsApp Config (Hardcoded Fixes)
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
    "$SERVER_NAME": "admin"
    "@etherdesk:$SERVER_NAME": "admin"
logging:
    min_level: info
    writers:
    - type: stdout
      format: pretty-colored
EOF

# B. Synapse Config Genereren
# We doen dit tijdelijk even met een run command
echo "Synapse config genereren..."
docker run --rm -v "$SYNAPSE_DIR:/data" -e SYNAPSE_SERVER_NAME=$SERVER_NAME -e SYNAPSE_REPORT_STATS=no matrixdotorg/synapse:latest generate

# C. CRUCIAAL VOOR KLANT SETUP: REGISTRATIE AANZETTEN!
# Zonder dit kan de website geen user aanmaken.
sed -i 's/enable_registration: false/enable_registration: true/g' $SYNAPSE_DIR/homeserver.yaml

# 3. Rechten & Files
touch $WA_DIR/whatsapp.db
# Zorg dat de Web App in .env mag schrijven
if [ ! -f $APP_DIR/.env ]; then touch $APP_DIR/.env; fi
chmod 666 $APP_DIR/.env
chmod -R 777 $INSTALL_DIR

# 4. Sleutels Genereren (Koppeling Bridge <-> Synapse)
# We maken een tijdelijke compose file voor de key generation
cat > $INSTALL_DIR/docker-compose.yml <<EOF
services:
  synapse:
    image: matrixdotorg/synapse:latest
    ports: [8008:8008]
    volumes: [./data/synapse:/data]
  mautrix-whatsapp:
    image: dock.mau.dev/mautrix/whatsapp:latest
    volumes: [./data/whatsapp:/data]
  dashboard:
    build: ./app
    ports: [80:80]
    volumes: [./app:/app, ./data:/data]
    environment: [MATRIX_HOMESERVER=http://synapse:8008]
EOF

echo "Sleutels genereren..."
docker compose run --rm mautrix-whatsapp /usr/bin/python3 -m mautrix_whatsapp -g -c /data/config.yaml -r /data/registration.yaml > /dev/null 2>&1

# URL Fixen & Kopiëren
sed -i 's|url: http://localhost:29318|url: http://mautrix-whatsapp:29318|g' $WA_DIR/registration.yaml
cp $WA_DIR/registration.yaml $SYNAPSE_DIR/whatsapp-registration.yaml
chmod 644 $SYNAPSE_DIR/whatsapp-registration.yaml

# 5. Starten
echo -e "${GREEN}Configuratie gereed. Starten...${NC}"
docker compose up -d --build

echo ""
echo -e "${GREEN}KLAAR!${NC}"
echo "De server is schoon en Synapse staat open voor registratie."
echo "Ga naar http://<JOUW-IP> om de Setup te starten."
