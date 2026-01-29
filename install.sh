#!/bin/bash

# Kleuren
GREEN='\033[0;32m'
BLUE='\033[0;34m'
RED='\033[0;31m'
NC='\033[0m'

echo -e "${BLUE}#########################################${NC}"
echo -e "${BLUE}#     ETHERDESK AUTO-INSTALLER V4.0     #${NC}"
echo -e "${BLUE}#     Full-Auto Provisioning Edition    #${NC}"
echo -e "${BLUE}#########################################${NC}"
echo ""

# --- 1. BENODIGDHEDEN ---
echo -e "${BLUE}[1/6] Systeem checks...${NC}"
check_install() {
    if ! [ -x "$(command -v $1)" ]; then
        sudo apt-get update > /dev/null
        sudo apt-get install -y $1 > /dev/null
    fi
}
check_install curl
check_install git
check_install nano
check_install python3 

if ! [ -x "$(command -v docker)" ]; then
    echo -e "${RED} -> Docker installeren...${NC}"
    curl -fsSL https://get.docker.com | sh
    sudo usermod -aG docker $USER
fi

# --- 2. MAPPEN & RECHTEN ---
echo -e "${BLUE}[2/6] Mappenstructuur...${NC}"
mkdir -p data/postgres data/synapse data/dashboard data/whatsapp data/gmessages app/static
# FIX: Startscript in de juiste map uitvoerbaar maken
chmod +x app/start.sh 2>/dev/null
chmod -R 777 data app/static

# --- 3. CONFIGURATIE (.env) ---
echo -e "${BLUE}[3/6] Configuratie (.env)...${NC}"
if [ ! -f .env ]; then cp .env.example .env; fi

get_env() { grep "$1" .env | cut -d '=' -f2 | tr -d '"'; }
SERVER_NAME=$(get_env SERVER_NAME || echo "my.local.matrix")
CURRENT_NAME=$(get_env STUDIO_NAME)

if [ "$CURRENT_NAME" == "EtherDesk Studio" ] || [ -z "$CURRENT_NAME" ]; then
    read -p "Studio Naam [Radio Capri]: " INPUT_NAME
    INPUT_NAME=${INPUT_NAME:-Radio Capri}
    sed -i "s/STUDIO_NAME=.*/STUDIO_NAME=\"$INPUT_NAME\"/" .env
    
    read -p "Slogan [Vanuit Bentelo!]: " INPUT_SLOGAN
    INPUT_SLOGAN=${INPUT_SLOGAN:-Vanuit Bentelo!}
    sed -i "s/SLOGAN=.*/SLOGAN=\"$INPUT_SLOGAN\"/" .env
fi

# --- 4. SYNAPSE & BRIDGES PREP ---
echo -e "${BLUE}[4/6] Matrix & Bridges voorbereiden...${NC}"

if [ ! -f data/synapse/homeserver.yaml ]; then
    echo " -> Genereren Synapse Config..."
    docker run --rm -v $(pwd)/data/synapse:/data -e SYNAPSE_SERVER_NAME=$SERVER_NAME -e SYNAPSE_REPORT_STATS=no matrixdotorg/synapse:latest generate
    sed -i 's/enable_registration: false/enable_registration: true/' data/synapse/homeserver.yaml
fi

configure_bridge() {
    SERVICE=$1
    DIR="data/$1"
    if [ ! -f $DIR/config.yaml ]; then
        docker run --rm -v $(pwd)/$DIR:/data dock.mau.dev/mautrix/$1:latest > /dev/null 2>&1
        sed -i 's|address: http://localhost:8008|address: http://synapse:8008|g' $DIR/config.yaml
        sed -i "s|domain: example.com|domain: $SERVER_NAME|g" $DIR/config.yaml
        sed -i "s|\"example.com\": \"user\"|\"$SERVER_NAME\": \"admin\"\n  \"@etherdesk:$SERVER_NAME\": \"admin\"|g" $DIR/config.yaml
        docker run --rm -v $(pwd)/$DIR:/data dock.mau.dev/mautrix/$1:latest /usr/bin/mautrix-$1 -g -c /data/config.yaml -r /data/registration.yaml
        cp $DIR/registration.yaml data/synapse/$SERVICE-registration.yaml
        
        if ! grep -q "$SERVICE-registration.yaml" data/synapse/homeserver.yaml; then
            if ! grep -q "app_service_config_files" data/synapse/homeserver.yaml; then
                 echo "app_service_config_files:" >> data/synapse/homeserver.yaml
            fi
            echo "  - /data/$SERVICE-registration.yaml" >> data/synapse/homeserver.yaml
        fi
    fi
}
configure_bridge "whatsapp"
configure_bridge "gmessages"

# --- 5. STARTEN ---
echo -e "${BLUE}[5/6] Containers Starten...${NC}"
if groups | grep -q "docker"; then
    docker compose up -d --build
else
    sudo docker compose up -d --build
fi

# --- 6. AUTO-PROVISIONING (TOKEN) ---
echo -e "${BLUE}[6/6] Auto-Provisioning Matrix Token...${NC}"
CURRENT_TOKEN=$(grep "MATRIX_TOKEN=" .env | cut -d '=' -f2)

if [ -z "$CURRENT_TOKEN" ] || [ ${#CURRENT_TOKEN} -lt 10 ]; then
    echo " -> Wachten tot Synapse online komt (kan 30 sec duren)..."
    until curl -s -f -o /dev/null "http://localhost:8008/_matrix/static/"; do
        sleep 5
        echo -n "."
    done
    echo " Online!"

    PW=$(date +%s | sha256sum | base64 | head -c 16)
    echo " -> Gebruiker 'etherdesk' aanmaken..."
    docker exec etherdesk-synapse-1 register_new_matrix_user -u etherdesk -p "$PW" -c /data/homeserver.yaml --admin 2>/dev/null || true
    
    echo " -> Token ophalen..."
    JSON=$(curl -s -XPOST -d "{\"type\":\"m.login.password\", \"user\":\"@etherdesk:$SERVER_NAME\", \"password\":\"$PW\"}" "http://localhost:8008/_matrix/client/r0/login")
    TOKEN=$(echo $JSON | python3 -c "import sys, json; print(json.load(sys.stdin).get('access_token', 'ERROR'))")
    
    if [ "$TOKEN" != "ERROR" ] && [ "$TOKEN" != "None" ]; then
        echo -e "${GREEN} -> Token ontvangen!${NC}"
        if grep -q "MATRIX_TOKEN=" .env; then
            sed -i "s|MATRIX_TOKEN=.*|MATRIX_TOKEN=$TOKEN|" .env
        else
            echo "MATRIX_TOKEN=$TOKEN" >> .env
        fi
        echo " -> Dashboard herstarten..."
        docker compose restart dashboard
    else
        echo -e "${RED} -> FOUT: Kon geen token krijgen.${NC}"
        echo "Antwoord: $JSON"
    fi
else
    echo -e "${GREEN} -> Token al aanwezig.${NC}"
fi

echo ""
echo -e "${GREEN}INSTALLATIE VOLTOOID! 🚀${NC}"
IP=$(hostname -I | awk '{print $1}')
echo "Ga naar: http://$IP"
