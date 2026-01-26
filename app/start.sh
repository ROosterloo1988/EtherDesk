#!/bin/bash
echo "--- STARTING ETHERDESK ---"
python harvester.py &
python web.py
