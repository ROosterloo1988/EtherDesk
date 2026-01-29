#!/bin/bash

# Kleurtjes
GREEN='\033[0;32m'
BLUE='\033[0;34m'
RED='\033[0;31m'
NC='\033[0m'

echo -e "${BLUE}#########################################${NC}"
echo -e "${BLUE}#     ETHERDESK AUTO-INSTALLER V3.0     #${NC}"
echo -e "${BLUE}#########################################${NC}"
echo ""

# --- 1. CHECKS & INSTALLATIE ---
echo -e "${BLUE}[1/5] Systeem checks...${NC}"
check_install() {
    if ! [ -x "$(command -v $1)" ]; then
        echo -e "${RED} -> $1 ontbreekt. Installeren...${NC}"
        sudo apt-get update > /dev/null
        sudo apt-get install -y $1 > /dev/null
    fi
}
check_install curl
check_install git
check_install nano

if ! [ -x "$(command -v docker)" ]; then
    echo -e "${RED} -> Docker installeren...${NC}"
    curl -fsSL https://get.docker.com | sh
    sudo usermod -aG docker $USER
fi

# --- 2. MAPSTRUCTUUR ---
echo -e "${BLUE}[2/5] Mappen voorbereiden...${NC}"
# We maken alle mappen alvast aan zodat we erin kunnen schrijven
mkdir -p data/postgres data/synapse data/dashboard data/whatsapp data/gmessages app/static
chmod -R 777 data app/static

# --- 3. ENV CONFIGURATIE ---
echo -e "${BLUE}[3/5] Configuratie (.env)...${NC}"
if [ ! -f .env ]; then
    cp .env.example .env
fi

# Lees servernaam uit .env of gebruik default
SERVER_NAME=$(grep SERVER_NAME .env | cut -d '=' -f2 | xargs || echo "my.local.matrix")

# Vraag gebruiker om input als het nog standaard is
CURRENT_NAME=$(grep STUDIO_NAME .env | cut -d '=' -f2 | tr -d '"')
read -p "Studio Naam [$CURRENT_NAME]: " INPUT_NAME
if [ ! -z "$INPUT_NAME" ]; then sed -i "s/STUDIO_NAME=.*/STUDIO_NAME=\"$INPUT_NAME\"/" .env; fi

# --- 4. SYNAPSE INIT ---
echo -e "${BLUE}[4/5] Matrix Server Genereren...${NC}"
# Als homeserver.yaml nog niet bestaat, genereren we hem
if [ ! -f data/synapse/homeserver.yaml ]; then
    echo " -> Genereren Synapse Config..."
    docker run --rm -v $(pwd)/data/synapse:/data -e SYNAPSE_SERVER_NAME=$SERVER_NAME -e SYNAPSE_REPORT_STATS=no matrixdotorg/synapse:latest generate
    
    # Zet registratie aan (nodig voor onze auto-user aanmaak)
    sed -i 's/enable_registration: false/enable_registration: true/' data/synapse/homeserver.yaml
fi

# --- 5. BRIDGE CONFIGURATIE (DE MAGIE) ---
echo -e "${BLUE}[5/5] Bridges Configureren (WhatsApp & SMS)...${NC}"

configure_bridge() {
    SERVICE=$1
    DIR="data/$1"
    IMAGE="dock.mau.dev/mautrix/$1:latest"
    BIN="/usr/bin/mautrix-$1"

    echo " -> Configureren: $SERVICE..."

    # 1. Config genereren (als die er niet is)
    if [ ! -f $DIR/config.yaml ]; then
        docker run --rm -v $(pwd)/$DIR:/data $IMAGE > /dev/null 2>&1
    fi

    # 2. Config patchen met sed (Adres en Rechten)
    # We vervangen localhost door synapse container
    sed -i 's|address: http://localhost:8008|address: http://synapse:8008|g' $DIR/config.yaml
    sed -i "s|domain: example.com|domain: $SERVER_NAME|g" $DIR/config.yaml
    
    # Rechten fixen (admin toegang geven aan ons domein)
    # We zoeken het blokje permissions en vervangen example.com
    sed -i "s|example.com: user|$SERVER_NAME: admin|g" $DIR/config.yaml
    
    # Specifieke admin user toevoegen (bot user) - brute replace
    # We vervangen het hele permissions blokje door een veilige versie
    # Dit is een beetje hacky, maar werkt voor default configs
    sed -i "s|\"example.com\": \"user\"|\"$SERVER_NAME\": \"admin\"\n  \"@etherdesk:$SERVER_NAME\": \"admin\"|g" $DIR/config.yaml

    # 3. Registratie genereren
    if [ ! -f $DIR/registration.yaml ]; then
        echo " -> Registratie aanmaken..."
        docker run --rm -v $(pwd)/$DIR:/data $IMAGE $BIN -g -c /data/config.yaml -r /data/registration.yaml
    fi

    # 4. Kopiëren naar Synapse
    cp $DIR/registration.yaml data/synapse/$SERVICE-registration.yaml
}

# Voer de functie uit voor beide bridges
configure_bridge "whatsapp"
configure_bridge "gmessages"

# --- 6. SYNAPSE KOPPELEN ---
echo " -> Synapse koppelen aan bridges..."
CONFIG_FILE="data/synapse/homeserver.yaml"

# Check of de regels er al in staan, zo niet, toevoegen
if ! grep -q "whatsapp-registration.yaml" $CONFIG_FILE; then
    echo "" >> $CONFIG_FILE
    echo "app_service_config_files:" >> $CONFIG_FILE
    echo "  - /data/whatsapp-registration.yaml" >> $CONFIG_FILE
    echo "  - /data/gmessages-registration.yaml" >> $CONFIG_FILE
fi

# --- 7. STARTEN ---
echo ""
echo -e "${BLUE}🚀 Alles is geconfigureerd! Starten maar...${NC}"

# Rechten fixen voor docker socket
chmod +x start.sh 2>/dev/null

if groups | grep -q "docker"; then
    docker compose up -d --build
else
    echo -e "${RED}Let op: Eerste keer draaien met sudo...${NC}"
    sudo docker compose up -d --build
fi

echo ""
echo -e "${GREEN}INSTALLATIE VOLTOOID!${NC}"
IP=$(hostname -I | awk '{print $1}')
echo "Ga naar: http://$IP"
