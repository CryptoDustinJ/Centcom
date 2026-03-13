#!/bin/bash
echo "--- System Health Check ---"
uptime
df -h / | tail -n 1
free -h | grep "Mem:"
echo "OpenClaw Gateway: $(pgrep -f openclaw-gateway > /dev/null && echo "RUNNING" || echo "STOPPED")"
