#!/bin/bash

# Kleurtjes voor de UI
GREEN='\033[0;32m'
BLUE='\033[0;34m'
RED='\033[0;31m'
NC='\033[0m' # No Color

echo -e "${BLUE}#########################################${NC}"
echo -e "${BLUE}#     ETHERDESK AUTO-INSTALLER V2.0     #${NC}"
echo -e "${BLUE}#########################################${NC}"
echo ""

# --- STAP 1: SYSTEEM CHECK & INSTALLATIE ---
echo -e "${BLUE}[1/4] Controleren van benodigdheden...${NC}"

# Functie om te checken of een commando bestaat
check_install() {
    if ! [ -x "$(command -v $1)" ]; then
        echo -e "${RED} -> $1 ontbreekt. Wordt nu geinstalleerd...${NC}"
        sudo apt-get update
        sudo apt-get install -y $1
        echo -e "${GREEN} -> $1 geinstalleerd!${NC}"
    else
        echo -e "${GREEN} -> $1 is al aanwezig.${NC}"
    fi
}

# Basis tools checken
check_install curl
check_install git
check_install nano

# Docker is speciaal, die doen we via het officiële script voor de zekerheid
if ! [ -x "$(command -v docker)" ]; then
    echo -e "${RED} -> Docker ontbreekt. Installeren via get.docker.com...${NC}"
    curl -fsSL https://get.docker.com | sh
    
    # Gebruiker toevoegen aan docker groep (zodat je geen sudo nodig hebt)
    echo -e "${BLUE} -> Rechten instellen voor gebruiker $USER...${NC}"
    sudo usermod -aG docker $USER
    
    echo -e "${GREEN} -> Docker geinstalleerd!${NC}"
    
    # We moeten de groep activeren zonder uitloggen
    echo -e "${RED}LET OP: Omdat Docker net is geinstalleerd, is een herstart aanbevolen na installatie.${NC}"
else
    echo -e "${GREEN} -> Docker is al aanwezig.${NC}"
fi

# Docker Compose check
if ! docker compose version > /dev/null 2>&1; then
     echo -e "${RED} -> Docker Compose plugin ontbreekt. Installeren...${NC}"
     sudo apt-get install -y docker-compose-plugin
fi

echo ""

# --- STAP 2: CONFIGURATIE (.env) ---
echo -e "${BLUE}[2/4] Configuratie Setup...${NC}"

if [ ! -f .env ]; then
    echo -e "${GREEN} -> Nieuwe configuratie aanmaken...${NC}"
    cp .env.example .env
else
    echo -e "${GREEN} -> Bestaande configuratie gevonden.${NC}"
fi

# Waardes uitlezen
CURRENT_NAME=$(grep STUDIO_NAME .env | cut -d '=' -f2 | tr -d '"')

echo ""
echo "-------------------------------------------------------"
echo " Druk op ENTER om de standaardwaarde [tussen haken] te houden."
echo "-------------------------------------------------------"

read -p "Wat is de naam van de studio? [$CURRENT_NAME]: " INPUT_NAME
if [ ! -z "$INPUT_NAME" ]; then
    sed -i "s/STUDIO_NAME=.*/STUDIO_NAME=\"$INPUT_NAME\"/" .env
fi

read -p "Wat is de slogan? [Helemaal vanuit Bentelo!]: " INPUT_SLOGAN
if [ ! -z "$INPUT_SLOGAN" ]; then
    sed -i "s/SLOGAN=.*/SLOGAN=\"$INPUT_SLOGAN\"/" .env
fi

read -p "Wat is de browser titel? [Radio Capri | Studio]: " INPUT_TITLE
if [ ! -z "$INPUT_TITLE" ]; then
    sed -i "s/PAGE_TITLE=.*/PAGE_TITLE=\"$INPUT_TITLE\"/" .env
fi

# --- STAP 3: PERMISSIES ---
echo ""
echo -e "${BLUE}[3/4] Permissies herstellen...${NC}"
chmod +x start.sh
# Zorg dat de data mappen bestaan zodat Docker niet zeurt over rechten
mkdir -p data/postgres data/synapse data/dashboard data/whatsapp data/gmessages
echo -e "${GREEN} -> Mappenstructuur gecontroleerd.${NC}"

# --- STAP 4: STARTEN ---
echo ""
echo -e "${BLUE}[4/4] EtherDesk Starten...${NC}"

# We proberen te starten. Als de gebruiker net aan de docker groep is toegevoegd,
# kan het zijn dat 'docker compose' faalt zonder 'sudo'.
if groups | grep -q "docker"; then
    docker compose up -d --build
else
    # Als de groep nog niet actief is in deze sessie, gebruik tijdelijk sudo
    echo -e "${RED} -> Rechten nog niet actief, we gebruiken eenmalig sudo...${NC}"
    sudo docker compose up -d --build
fi

echo ""
echo -e "${BLUE}=========================================${NC}"
echo -e "${GREEN}   INSTALLATIE VOLTOOID! 🚀              ${NC}"
echo -e "${BLUE}=========================================${NC}"
IP=$(hostname -I | awk '{print $1}')
echo "Het systeem draait!"
echo ""
echo " -> Dashboard:      http://$IP"
echo " -> Installer/Help: http://$IP/install"
echo ""
echo "TIP: Als Docker errors geeft, herstart de server eenmalig met: sudo reboot"
echo ""
