#!/bin/sh
set -euo pipefail
SOURCE="rsync://mirror.selfnet.de/archlinux/"
DEST="/srv/archmirror"

rsync -rlptH --safe-links --delete-delay --delay-updates \
  --partial \
  --timeout=600 \
  --exclude=stats.json \
  "$SOURCE" "$DEST"

date +%s > "$DEST/lastupdate"
