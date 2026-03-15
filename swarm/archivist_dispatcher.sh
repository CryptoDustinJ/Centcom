#!/bin/bash
# Archivist Agent: Long-term Hive-Mind Memory Management
# Model: gemini-1.5-flash-8b (optimized for 1M context retrieval)
#
# Triggers memory paging via the backend API every hour.
# Hive-Mind aware: queries context ledger, logs results back (mandatory protocol).

BACKEND="http://127.0.0.1:19000"
AGENT="archivist"

log_packet() {
  local ptype="$1" pdata="$2"
  curl -s -X POST "$BACKEND/office/log-memory-packet" \
    -H "Content-Type: application/json" \
    -d "{\"type\":\"$ptype\",\"agent\":\"$AGENT\",\"data\":$pdata}" > /dev/null 2>&1
}

while true; do
  # ── Hive-Mind: Query context ledger (mandatory) ──
  HIVEMIND=$(curl -s -X GET "$BACKEND/office/get-hive-mind-context")
  echo "[$(date -Iseconds)] Hive-Mind context loaded" >> /tmp/archivist_hivemind.log

  # Trigger memory paging: archive events older than 24h
  RESULT=$(curl -s -X POST "$BACKEND/office/archive-memory")
  echo "[$(date -Iseconds)] Archive result: $RESULT" >> /tmp/archivist_status.log

  # ── Hive-Mind: Log results back (mandatory) ──
  log_packet "agent_cycle" "\"Archivist dispatch: archived stale memory events\""

  sleep 3600
done
