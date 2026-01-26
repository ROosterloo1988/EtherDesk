#!/bin/bash

# Kleurtjes voor de mooi
GREEN='\033[0;32m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

echo -e "${BLUE}=========================================${NC}"
echo -e "${BLUE}   ETHERDESK AUTO-INSTALLER V1.0         ${NC}"
echo -e "${BLUE}=========================================${NC}"

# 1. Checken of .env bestaat
if [ ! -f .env ]; then
    echo -e "${GREEN} -> Geen configuratie gevonden. We maken een nieuwe aan...${NC}"
    cp .env.example .env
else
    echo -e "${GREEN} -> Bestaande configuratie gevonden. We gebruiken die.${NC}"
fi

# 2. Vragen stellen (Alleen als ze nog standaard zijn)
# We lezen de huidige waardes
CURRENT_NAME=$(grep STUDIO_NAME .env | cut -d '=' -f2 | tr -d '"')

echo ""
echo "We gaan nu de studio configureren. Druk op Enter om de standaardwaarde [tussen haken] te houden."
echo ""

# Vraag: Studio Naam
read -p "Wat is de naam van de studio? [$CURRENT_NAME]: " INPUT_NAME
if [ ! -z "$INPUT_NAME" ]; then
    # Vervang de regel in .env (sed command)
    sed -i "s/STUDIO_NAME=.*/STUDIO_NAME=\"$INPUT_NAME\"/" .env
fi

# Vraag: Slogan
read -p "Wat is de slogan? [Helemaal vanuit Bentelo!]: " INPUT_SLOGAN
if [ ! -z "$INPUT_SLOGAN" ]; then
    sed -i "s/SLOGAN=.*/SLOGAN=\"$INPUT_SLOGAN\"/" .env
fi

# Vraag: Pagina Titel
read -p "Wat is de browser titel? [Radio Capri | Studio]: " INPUT_TITLE
if [ ! -z "$INPUT_TITLE" ]; then
    sed -i "s/PAGE_TITLE=.*/PAGE_TITLE=\"$INPUT_TITLE\"/" .env
fi

# Vraag: Database Wachtwoord
read -p "Kies een database wachtwoord [random]: " INPUT_PW
if [ ! -z "$INPUT_PW" ]; then
    sed -i "s/POSTGRES_PASSWORD=.*/POSTGRES_PASSWORD=$INPUT_PW/" .env
fi

echo ""
echo -e "${GREEN} -> Configuratie opgeslagen in .env!${NC}"
echo -e "${BLUE} -> Starten van containers...${NC}"

# 3. Docker Starten
# We zorgen dat het script uitvoerbaar is
chmod +x start.sh
# Starten
docker compose up -d

echo ""
echo -e "${BLUE}=========================================${NC}"
echo -e "${GREEN}   INSTALLATIE VOLTOOID!                 ${NC}"
echo -e "${BLUE}=========================================${NC}"
echo "1. Ga naar http://$(hostname -I | awk '{print $1}')/install"
echo "2. Volg de stappen daar om Matrix te koppelen."
echo ""
