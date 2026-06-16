#!/bin/sh
# Wait for the correct time to sync, then loop daily
# SYNC_HOUR and SYNC_MINUTE come from docker-compose environment

SYNC_HOUR=${SYNC_HOUR:-3}
SYNC_MINUTE=${SYNC_MINUTE:-17}

echo "[sync] Starting Arch mirror sync scheduler"
echo "[sync] Will sync daily at ${SYNC_HOUR}:${SYNC_MINUTE}"

while true; do
    echo "[sync] Running scheduled sync..."
    /usr/local/bin/archmirror-sync.sh && echo "[sync] Sync complete" || echo "[sync] Sync failed"
    echo "[sync] Next sync in 21600s"
    sleep 21600
done
