#!/bin/bash
echo "Good morning, Dustin. Here is your briefing for $(date "+%A, %B %d")."
echo "---"
/home/dustin/openclaw-office/backend/scripts/get_weather.sh
echo "---"
himalaya envelope list -s 3 || echo "No emails found."
