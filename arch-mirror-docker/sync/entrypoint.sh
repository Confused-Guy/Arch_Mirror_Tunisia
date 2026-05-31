#!/bin/sh
# Wait for the correct time to sync, then loop daily
# SYNC_HOUR and SYNC_MINUTE come from docker-compose environment

SYNC_HOUR=${SYNC_HOUR:-3}
SYNC_MINUTE=${SYNC_MINUTE:-17}

echo "[sync] Starting Arch mirror sync scheduler"
echo "[sync] Will sync daily at ${SYNC_HOUR}:${SYNC_MINUTE}"

while true; do
    # Calculate seconds until next sync time
    NOW=$(date +%s)
    NEXT=$(date -d "today ${SYNC_HOUR}:${SYNC_MINUTE}" +%s 2>/dev/null || date -v${SYNC_HOUR}H -v${SYNC_MINUTE}M +%s)
    
    # If that time already passed today, schedule for tomorrow
    if [ "$NEXT" -le "$NOW" ]; then
        NEXT=$(( NEXT + 86400 ))
    fi
    
    SLEEP=$(( NEXT - NOW ))
    echo "[sync] Next sync in ${SLEEP}s ($(date -d @${NEXT} 2>/dev/null || date -r ${NEXT}))"
    sleep "$SLEEP"
    
    echo "[sync] Running scheduled sync..."
    /usr/local/bin/archmirror-sync.sh && echo "[sync] Sync complete" || echo "[sync] Sync failed"
done
