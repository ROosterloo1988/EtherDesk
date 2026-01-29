#!/bin/bash
echo "--- STARTING ETHERDESK ---"

# 1. Start de Harvester in de achtergrond (& is VERPLICHT!)
python harvester.py &

# 2. Start de Webserver (Flask) op de voorgrond
python web.py
