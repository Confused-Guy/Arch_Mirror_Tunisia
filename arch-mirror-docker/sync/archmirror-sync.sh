#!/bin/sh
set -euo pipefail
SOURCES="
rsync://mirror.selfnet.de/archlinux/
rsync://mirror.puzzle.ch/archlinux/
"
#Removed rsync://mirrors.kernel.org/archlinux/ because it has too many extra testing packages
DEST="/srv/archmirror"

#The for loop is because selfnet.de kept failing many times.

RUN_LOG="/tmp/rsync-last-run.log"

for SOURCE in $SOURCES; do
    echo "[sync] Trying $SOURCE"
    if rsync -rlptH --safe-links --delete-delay --delay-updates \
        --partial \
        --timeout=600 \
        --exclude=stats.json \
        --stats \
        "$SOURCE" "$DEST" >"$RUN_LOG" 2>&1; then
        echo "[sync] Success from $SOURCE"
        grep -E "Number of (regular files transferred|deleted files)|Total transferred file size|^sent " "$RUN_LOG" || true
        date +%s > "$DEST/lastupdate"
        exit 0
    fi
    cat "$RUN_LOG"
    echo "[sync] Failed, trying next..."
done

echo "[sync] All sources failed"
exit 1
