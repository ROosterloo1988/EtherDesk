#!/bin/bash
# setup_hotspot.sh - Maakt van de Pi een Access Point

echo "--- EtherDesk Hotspot Setup ---"

# 1. Installeer DNSMasq voor de Captive Portal functionaliteit
sudo apt update
sudo apt install -y dnsmasq

# 2. Maak de Hotspot verbinding aan met NetworkManager
# Naam: EtherDesk-Setup, Wachtwoord: broadcast, IP: 10.42.0.1
sudo nmcli con add type wifi ifname wlan0 con-name EtherDesk-Hotspot autoconnect yes ssid "EtherDesk-Setup"
sudo nmcli con modify EtherDesk-Hotspot 802-11-wireless.mode ap 802-11-wireless.band bg ipv4.method shared
sudo nmcli con modify EtherDesk-Hotspot wifi-sec.key-mgmt wpa-psk
sudo nmcli con modify EtherDesk-Hotspot wifi-sec.psk "broadcast"

# 3. DNSMasq configureren om ALLES naar de Pi te sturen (Captive Portal)
# Dit zorgt dat als iemand 'google.com' typt, hij naar onze installer gaat.
sudo bash -c 'cat > /etc/dnsmasq.conf << EOF
interface=wlan0
dhcp-range=10.42.0.10,10.42.0.100,12h
address=/#/10.42.0.1
EOF'

# 4. Herstart services
sudo systemctl restart NetworkManager
sudo systemctl restart dnsmasq

echo "✅ Hotspot 'EtherDesk-Setup' is actief op 10.42.0.1"
