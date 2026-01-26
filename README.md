# 📻 EtherDesk
**Professional Broadcast Interface | Powered by Broadcast Innovations**

![EtherDesk Status](https://img.shields.io/badge/Status-Stable-green?style=flat-square)
![Docker](https://img.shields.io/badge/Docker-Containerized-blue?style=flat-square)
![Python](https://img.shields.io/badge/Backend-Flask-yellow?style=flat-square)
![License](https://img.shields.io/badge/License-Proprietary-red?style=flat-square)

EtherDesk is een geavanceerd softwarepakket speciaal ontwikkeld voor radiostudio's en (geheime) zenders. Het centraliseert alle inkomende luisteraars-interactie (WhatsApp, SMS en Matrix) in één strak, donker dashboard dat geoptimaliseerd is voor gebruik in schemerige studio-omgevingen.

---

## 🚀 Features

* **Unified Inbox:** Combineert WhatsApp, SMS (via Android) en Matrix berichten in één live-stream.
* **Studio Dark Mode:** Een contrastrijk 'Deep Blue' thema, rustig voor de ogen tijdens nachtelijke uitzendingen.
* **Real-time Statistieken:** Direct inzicht in aantal verzoekjes en activiteit van de laatste 15 uitzenddagen.
* **Archief Functie:** Eén klik om een verzoekje af te handelen en te archiveren.
* **Auto-Update System:** Ingebouwd update-mechanisme. Eén druk op de knop in het dashboard en de software update zichzelf direct vanaf GitHub.
* **Smart Provisioning:** Installeer en configureer een nieuwe server in minder dan 5 minuten via het automatische installatiescript.

---

## 🛠️ Installatie (Greenfield)

EtherDesk is ontworpen om te draaien op een kale Ubuntu Server (20.04+) of Raspberry Pi OS (64-bit).

### 1. Download & Installatie
Log in op je server en voer de volgende commando's uit:

```bash
# 1. Update pakketten en installeer Git
sudo apt update && sudo apt install -y git

# 2. Clone de repository
# Vervang <JOUW_REPO_URL> met de url van je Github repo
sudo git clone [https://github.com/ROosterloo1988/EtherDesk.git](https://github.com/ROosterloo1988/EtherDesk.git) /opt/etherdesk

# 3. Start de Automatische Installer
cd /opt/etherdesk
sudo bash install.sh
```
De installer controleert of Docker aanwezig is (en installeert dit zo nodig), vraagt om de naam van je studio en start de omgeving op.

2. Matrix Token Genereren (Eenmalig)
Na de eerste start moet er een veilige koppeling gemaakt worden met de interne message-server.

1. Maak een systeem-gebruiker aan:

```bash
docker compose exec synapse register_new_matrix_user -u etherdesk -p broadcast123 -c /data/homeserver
```
2. Vraag het beveiligingstoken op:
```bash
curl -XPOST -d '{"type":"m.login.password", "user":"@etherdesk:my.local.matrix", "password":"broadcast123"}' "http://localhost:8008/_matrix/client/r0/login"
```
3. Kopieer de access_token (de lange reeks tekens) uit het resultaat.
4. Voeg toe aan configuratie: Open het bestand .env en plak het token achter MATRIX_TOKEN=.
```bash
nano .env
```
5. Herstarten:
```bash
docker compose up -d --force-recreate dashboard
```

📱 Connectiviteit Koppelen
EtherDesk gebruikt interne bridges om te verbinden met WhatsApp en SMS.

WhatsApp Koppelen
1. Open Element (of een andere Matrix client) op je PC.
2. Verbind met je eigen server: http://IP-VAN-JE-SERVER:8008.
3. Start een chat met: @whatsappbot:my.local.matrix.
4. Stuur het bericht: login.
5. Scan de QR-code die verschijnt met de WhatsApp App op je studio-telefoon (Menu > Gekoppelde apparaten).

SMS Koppelen (Via Android)
1. Zorg dat de Google Messages app op de studio-telefoon staat ingesteld als standaard SMS app.
2. Start in Element een chat met: @gmessagesbot:my.local.matrix.
3. Stuur het bericht: login.
4. Open Google Messages op de telefoon > Menu > Apparaat koppelen.
5. Scan de QR-code.

⚙️ Configuratie
De basisinstellingen vind je in het bestand .env in de hoofdmap (/opt/etherdesk/.env).
Variabele Omschrijving Voorbeeld
STUDIO_NAME De naam bovenaan het dashboard "Radio Capri"
SLOGAN De subtitel onder de naam "Helemaal vanuit Bentelo!"
PAGE_TITLE Titel in browser tabblad "Radio Capri"
MATRIX_TOKEN Het geheime token voor de bot (Automatisch gegenereerd)
POSTGRES_PASSWORD Database wachtwoord (Kies een sterk wachtwoord)

Na wijzigingen in dit bestand altijd even herstarten met: docker compose up -d.

🔄 Updates Draaien
1. Wanneer er een nieuwe versie op GitHub staat, verschijnt er automatisch een Paarse Melding bovenin het dashboard.
2. Klik op de knop [ NU INSTALLEREN ].
3. De software downloadt de laatste code en herbouwt de container.
4. Het systeem herstart automatisch (duurt ca. 30 seconden).
5. De pagina ververst zichzelf en de nieuwe versie is actief.

📂 Mappenstructuur
/app: De broncode van de applicatie (Python/HTML).
/data: Permanente opslag (Database, WhatsApp sessies). Wordt nooit overschreven.
.env: Je lokale configuratie en wachtwoorden.

© 2026 Broadcast Innovations. Alle rechten voorbehouden.
