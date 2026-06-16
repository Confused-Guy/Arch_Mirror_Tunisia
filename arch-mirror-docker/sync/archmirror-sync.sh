#!/bin/sh
set -euo pipefail
SOURCES="
rsync://mirror.selfnet.de/archlinux/
rsync://mirrors.kernel.org/archlinux/
rsync://mirror.puzzle.ch/archlinux/
"
DEST="/srv/archmirror"

#The for loop is because selfnet.de kept failing many times.

for SOURCE in $SOURCES; do
    echo "[sync] Trying $SOURCE"
    if rsync -rlptH --safe-links --delete-delay --delay-updates \
        --partial \
        --timeout=600 \
        --exclude=stats.json \
        "$SOURCE" "$DEST"; then
        echo "[sync] Success from $SOURCE"
        date +%s > "$DEST/lastupdate"
        exit 0
    fi
    echo "[sync] Failed, trying next..."
done

echo "[sync] All sources failed"
exit 1
