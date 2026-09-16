#!/bin/bash
# /usr/local/bin/mirror-stats.sh — generates /srv/archmirror/stats.json
#
# Runs every 60s via mirror-stats.timer. The old version did ~12 full
# rescans of the (unbounded, unrotated) access log per run - it was taking
# 70-90s of wall clock / 1.3 CPU-cores per run, i.e. running almost
# continuously and fighting nginx for disk I/O. This version tracks a byte
# offset into the live log and only reads new lines each run; historical
# per-day totals (needed for uptime_days/traffic_7d) are kept in a small
# state file instead of being recomputed from raw logs every time.
#
# First run after deploying this script has no state file yet, so it does
# one full scan of whatever log files currently exist to bootstrap the
# running totals and day buckets - after that it's incremental forever.

set -uo pipefail

MIRROR_DIR="/srv/archmirror"
ACCESS_LOG="/var/log/nginx/archmirror.access.log"
CACHE_FILE="/srv/archmirror/stats.json"
STATE_DIR="/var/lib/mirror-stats"
STATE_FILE="$STATE_DIR/incremental_state.json"
PERSISTENT_FILE="$STATE_DIR/persistent.json"
BASELINE_FILE="$STATE_DIR/baseline.json"

mkdir -p "$STATE_DIR"
[[ -f "$PERSISTENT_FILE" ]] || echo '{"total_unique_ip_count":0,"seen_ip_hashes":[]}' > "$PERSISTENT_FILE"
[[ -f "$BASELINE_FILE" ]] || echo '{"total_bytes_served_offset":0}' > "$BASELINE_FILE"

LASTSYNC_FILE="$MIRROR_DIR/lastupdate"
if [[ -f "$LASTSYNC_FILE" ]]; then
  last_sync_ts=$(tr -d '[:space:]' < "$LASTSYNC_FILE")
else
  last_sync_ts=$(date +%s)
fi

now=$(date +%s)
sync_ok="true"
(( now - last_sync_ts > 90000 )) && sync_ok="false"

read disk_used_kb disk_free_kb < <(df "$MIRROR_DIR" --output=used,avail | tail -1)
disk_used_bytes=$(( disk_used_kb * 1024 ))
disk_free_bytes=$(( disk_free_kb * 1024 ))

repos=()
for repo in core extra multilib core-testing extra-testing gnome-unstable kde-unstable multilib-testing; do
  repo_path="$MIRROR_DIR/$repo/os/x86_64"
  if [[ -d "$repo_path" ]]; then
    size_bytes=$(find -L "$repo_path" -maxdepth 1 -type f -name "*.pkg.tar.zst" -printf '%s\n' 2>/dev/null | awk '{s+=$1} END {print s+0}')
    repos+=("\"$repo\": $size_bytes")
  fi
done
repos_json="{$(IFS=','; echo "${repos[*]}")}"

python3 "$(dirname "$0")/mirror-stats-incremental.py" \
  --access-log "$ACCESS_LOG" \
  --state-file "$STATE_FILE" \
  --persistent-file "$PERSISTENT_FILE" \
  --baseline-file "$BASELINE_FILE" \
  --cache-file "$CACHE_FILE" \
  --last-sync-ts "$last_sync_ts" \
  --sync-ok "$sync_ok" \
  --disk-used-bytes "$disk_used_bytes" \
  --disk-free-bytes "$disk_free_bytes" \
  --repos-json "$repos_json" \
  --now "$now"

cat "$CACHE_FILE"
