#!/bin/bash

# Kleuren
GREEN='\033[0;32m'
BLUE='\033[0;34m'
RED='\033[0;31m'
NC='\033[0m'

echo -e "${BLUE}#########################################${NC}"
echo -e "${BLUE}#     ETHERDESK AUTO-INSTALLER V5.0     #${NC}"
echo -e "${BLUE}#     Custom Credentials Edition        #${NC}"
echo -e "${BLUE}#########################################${NC}"
echo ""

# --- 1. CHECKS ---
echo -e "${BLUE}[1/7] Systeem checks...${NC}"
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

# --- 2. INPUT GEBRUIKER ---
echo -e "${BLUE}[2/7] Gegevens invoeren...${NC}"

# .env voorbereiden
if [ ! -f .env ]; then cp .env.example .env; fi
get_env() { grep "$1" .env | cut -d '=' -f2 | tr -d '"'; }

# 1. Studio Naam
CURRENT_NAME=$(get_env STUDIO_NAME)
if [ "$CURRENT_NAME" == "EtherDesk Studio" ] || [ -z "$CURRENT_NAME" ]; then
    read -p "Studio Naam [Radio Capri]: " INPUT_NAME
    INPUT_NAME=${INPUT_NAME:-Radio Capri}
    sed -i "s/STUDIO_NAME=.*/STUDIO_NAME=\"$INPUT_NAME\"/" .env
    
    read -p "Slogan [Vanuit Bentelo!]: " INPUT_SLOGAN
    INPUT_SLOGAN=${INPUT_SLOGAN:-Vanuit Bentelo!}
    sed -i "s/SLOGAN=.*/SLOGAN=\"$INPUT_SLOGAN\"/" .env
fi

# 2. Gebruikersnaam & Wachtwoord
echo ""
echo "-------------------------------------------------------"
echo " Kies je inloggegevens voor het Matrix netwerk."
echo "-------------------------------------------------------"
read -p "Gebruikersnaam [etherdesk]: " INPUT_USER
MATRIX_UID=${INPUT_USER:-etherdesk}

# Wachtwoord vragen (masked input)
while true; do
    read -s -p "Wachtwoord [laat leeg voor random]: " INPUT_PW
    echo ""
    if [ -z "$INPUT_PW" ]; then
        MATRIX_PW=$(date +%s | sha256sum | base64 | head -c 16)
        echo " -> Random wachtwoord gegenereerd."
        break
    else
        if [ ${#INPUT_PW} -ge 8 ]; then
            MATRIX_PW=$INPUT_PW
            break
        else
            echo -e "${RED} -> Wachtwoord te kort! Minimaal 8 tekens.${NC}"
        fi
    fi
done

SERVER_NAME=$(get_env SERVER_NAME || echo "my.local.matrix")

# Update .env met de nieuwe username
sed -i "s/MATRIX_USER=.*/MATRIX_USER=@$MATRIX_UID:$SERVER_NAME/" .env

# --- 3. MAPPEN ---
echo -e "${BLUE}[3/7] Mappenstructuur...${NC}"
mkdir -p data/postgres data/synapse data/dashboard data/whatsapp data/gmessages app/static
chmod +x app/start.sh 2>/dev/null
chmod -R 777 data app/static

# --- 4. PREP CONFIGS ---
echo -e "${BLUE}[4/7] Matrix & Bridges voorbereiden...${NC}"
# Synapse Config
if [ ! -f data/synapse/homeserver.yaml ]; then
    docker run --rm -v $(pwd)/data/synapse:/data -e SYNAPSE_SERVER_NAME=$SERVER_NAME -e SYNAPSE_REPORT_STATS=no matrixdotorg/synapse:latest generate
    sed -i 's/enable_registration: false/enable_registration: true/' data/synapse/homeserver.yaml
fi

# Bridges Config
configure_bridge() {
    SERVICE=$1
    DIR="data/$1"
    if [ ! -f $DIR/config.yaml ]; then
        docker run --rm -v $(pwd)/$DIR:/data dock.mau.dev/mautrix/$1:latest > /dev/null 2>&1
        sed -i 's|address: http://localhost:8008|address: http://synapse:8008|g' $DIR/config.yaml
        sed -i "s|domain: example.com|domain: $SERVER_NAME|g" $DIR/config.yaml
        sed -i "s|\"example.com\": \"user\"|\"$SERVER_NAME\": \"admin\"\n  \"@$MATRIX_UID:$SERVER_NAME\": \"admin\"|g" $DIR/config.yaml
        
        docker run --rm -v $(pwd)/$DIR:/data dock.mau.dev/mautrix/$1:latest /usr/bin/mautrix-$1 -g -c /data/config.yaml -r /data/registration.yaml
        cp $DIR/registration.yaml data/synapse/$SERVICE-registration.yaml
        
        if ! grep -q "app_service_config_files" data/synapse/homeserver.yaml; then echo "app_service_config_files:" >> data/synapse/homeserver.yaml; fi
        if ! grep -q "$SERVICE-registration.yaml" data/synapse/homeserver.yaml; then echo "  - /data/$SERVICE-registration.yaml" >> data/synapse/homeserver.yaml; fi
    fi
}
configure_bridge "whatsapp"
configure_bridge "gmessages"

# --- 5. STARTEN ---
echo -e "${BLUE}[5/7] Containers Starten...${NC}"
if groups | grep -q "docker"; then docker compose up -d --build; else sudo docker compose up -d --build; fi

# --- 6. PROVISIONING ---
echo -e "${BLUE}[6/7] Account aanmaken...${NC}"

# Check of token al bestaat
CURRENT_TOKEN=$(grep "MATRIX_TOKEN=" .env | cut -d '=' -f2)
if [ -z "$CURRENT_TOKEN" ] || [ ${#CURRENT_TOKEN} -lt 10 ]; then
    echo " -> Wachten op Synapse (Max 120s)..."
    
    # Loop met timeout teller
    COUNTER=0
    until curl -s -f -o /dev/null "http://localhost:8008/_matrix/static/"; do
        sleep 5
        echo -n "."
        COUNTER=$((COUNTER+1))
        if [ $COUNTER -gt 24 ]; then
            echo ""
            echo -e "${RED}ERROR: Synapse start niet op tijd op.${NC}"
            echo "Check logs met: docker compose logs synapse"
            exit 1
        fi
    done
    echo " Online!"

    echo " -> Gebruiker '$MATRIX_UID' registreren..."
    docker exec etherdesk-synapse-1 register_new_matrix_user -u "$MATRIX_UID" -p "$MATRIX_PW" -c /data/homeserver.yaml --admin 2>/dev/null || true
    
    echo " -> Token ophalen..."
    JSON=$(curl -s -XPOST -d "{\"type\":\"m.login.password\", \"user\":\"@$MATRIX_UID:$SERVER_NAME\", \"password\":\"$MATRIX_PW\"}" "http://localhost:8008/_matrix/client/r0/login")
    TOKEN=$(echo $JSON | python3 -c "import sys, json; print(json.load(sys.stdin).get('access_token', 'ERROR'))")
    
    if [ "$TOKEN" != "ERROR" ] && [ "$TOKEN" != "None" ]; then
        echo -e "${GREEN} -> Token ontvangen!${NC}"
        if grep -q "MATRIX_TOKEN=" .env; then sed -i "s|MATRIX_TOKEN=.*|MATRIX_TOKEN=$TOKEN|" .env; else echo "MATRIX_TOKEN=$TOKEN" >> .env; fi
        
        # Gegevens opslaan in tekstbestand
        echo "EtherDesk Credentials" > credentials.txt
        echo "=====================" >> credentials.txt
        echo "Gebruiker: @$MATRIX_UID:$SERVER_NAME" >> credentials.txt
        echo "Wachtwoord: $MATRIX_PW" >> credentials.txt
        echo "Token: $TOKEN" >> credentials.txt
        chmod 600 credentials.txt
        
        echo " -> Dashboard herstarten..."
        docker compose restart dashboard
    else
        echo -e "${RED} -> FOUT: Kon geen token krijgen. Check logs.${NC}"
        echo "Antwoord: $JSON"
    fi
else
    echo -e "${GREEN} -> Reeds geconfigureerd.${NC}"
fi

echo ""
echo -e "${GREEN}INSTALLATIE VOLTOOID! 🚀${NC}"
echo "Je inloggegevens zijn opgeslagen in: credentials.txt"
IP=$(hostname -I | awk '{print $1}')
echo "Ga naar: http://$IP"
