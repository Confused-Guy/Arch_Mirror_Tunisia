# Arch Linux Mirror - Tunisia

Tunisia's first public Arch Linux mirror. Official Tier 2, listed on [archlinux.org](https://archlinux.org/mirrors/mirror.safiabidi.com/).

```
Server = https://mirror.safiabidi.com/$repo/os/$arch
```

**Dashboard:** https://mirror.safiabidi.com/dashboard

---

## Current Infrastructure

| | |
|---|---|
| **Host** | ATI VPS (Tunisia) |
| **OS** | Arch Linux |
| **CPU / RAM** | 4 vCPUs / 8 GB |
| **Disk** | 200 GB |
| **Bandwidth** | ~5 Gbps |
| **Mirror URL** | https://mirror.safiabidi.com |
| **Status** | Live - Official Tier 2 |

---

## Architecture

```
[ Upstream Tier 1 Mirrors (selfnet.de → kernel.org → puzzle.ch fallback) ]
                    ↓ rsync, every 6 hours
        [ /srv/archmirror on ATI VPS ]
                    ↓ nginx (Docker)
        [ https://mirror.safiabidi.com ]
                    ↓
            [ Public Internet ]
```

The entire stack runs on a VPS hosted at ATI (Agence Tunisienne d'Internet), Tunisia's national internet backbone. No residential connection, no CGNAT, no port forwarding required.

---

## Stack

### Docker Compose

Two containers, one shared volume:

- **mirror-nginx** - serves the mirror over HTTPS on ports 80/443. nginx runs inside the container; the host has no system nginx service.
- **mirror-sync** - runs rsync every 6 hours to sync from upstream. Tries selfnet.de first, falls back to kernel.org then puzzle.ch if DNS or connection fails.

Both containers mount `/srv/archmirror` on the host as a shared volume. nginx reads it read-only; the sync container writes to it.

Nginx logs are also volume-mounted to `/var/log/nginx` on the host so the stats script can read them directly without going through Docker.

The full `docker-compose.yml` is in `/arch-mirror-docker/` in this repo.

---

### Sync Script

`/arch-mirror-docker/sync/archmirror-sync.sh`

Uses the exact rsync flags specified in the [Arch mirror documentation](https://wiki.archlinux.org/title/DeveloperWiki:NewMirrors), with multi-source fallback:

```bash
#!/bin/sh
set -euo pipefail

DEST="/srv/archmirror"

SOURCES="
rsync://mirror.selfnet.de/archlinux/
rsync://mirrors.kernel.org/archlinux/
rsync://mirror.puzzle.ch/archlinux/
"

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
```

Flag breakdown:
- `-rlptH` - recursive, preserve symlinks/permissions/timestamps/hardlinks
- `--safe-links` - ignore symlinks pointing outside the tree
- `--delete-delay` / `--delay-updates` - atomic updates, mirror is never in a partial state during sync. Note: these flags cause rsync to stage files in a `.~tmp~` directory before moving them into place, so disk usage will temporarily spike during a sync. Don't panic.
- `--partial` - resume interrupted transfers
- `--timeout=600` - drop stalled connections after 10 minutes
- `--exclude=stats.json` - don't overwrite the locally generated stats file

The fallback list exists because DNS resolution for `mirror.selfnet.de` occasionally fails from inside the Docker container (transient ATI DNS issue). If the first source fails, it tries the next one automatically.

---

### Sync Entrypoint

`/arch-mirror-docker/sync/entrypoint.sh`

Runs inside the sync container and loops every 6 hours:

```sh
#!/bin/sh

while true; do
    echo "[sync] Running scheduled sync..."
    /usr/local/bin/archmirror-sync.sh && echo "[sync] Sync complete" || echo "[sync] Sync failed"
    echo "[sync] Next sync in 21600s"
    sleep 21600
done
```

Originally this used GNU date syntax (`date -d`) to calculate time until a specific hour. That broke silently on Alpine Linux inside the container, which uses BusyBox date. Replaced with a simple 6-hour sleep loop.

---

### nginx Config

Lives inside the nginx container at `/etc/nginx/conf.d/archmirror.conf`. The Dockerfile copies it in at build time.

```nginx
server {
    listen 80;
    listen [::]:80;
    server_name mirror.safiabidi.com;
    return 301 https://$host$request_uri;
}

server {
    listen 443 ssl;
    listen [::]:443 ssl ipv6only=on;
    server_name mirror.safiabidi.com;

    ssl_certificate /etc/letsencrypt/live/mirror.safiabidi.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/mirror.safiabidi.com/privkey.pem;
    include /etc/letsencrypt/options-ssl-nginx.conf;
    ssl_dhparam /etc/letsencrypt/ssl-dhparams.pem;

    root /srv/archmirror;
    autoindex on;
    access_log /var/log/nginx/archmirror.access.log;
    error_log /var/log/nginx/archmirror.error.log;

    location / {
        try_files $uri $uri/ =404;
    }

    location /stats.json {
        add_header Access-Control-Allow-Origin "https://safiabidi.com";
        add_header Cache-Control "no-store";
        try_files $uri =404;
    }

    location /dashboard {
        alias /srv/archmirror-dashboard;
        index index.html;
    }
}
```

HTTP redirects to HTTPS. The dashboard is served from a separate directory so it doesn't interfere with the mirror's directory listing. `stats.json` has its own location block to set CORS and cache headers.

---

### SSL

Let's Encrypt cert issued via `certbot --standalone` (not `--nginx`, since nginx runs inside Docker and certbot can't find the binary on the host):

```bash
sudo certbot certonly --standalone -d mirror.safiabidi.com
```

This generates the cert but not `options-ssl-nginx.conf` or `ssl-dhparams.pem`, which the nginx config references. Those need to be created manually:

```bash
# Download the options file certbot-nginx normally generates
sudo curl -o /etc/letsencrypt/options-ssl-nginx.conf \
  https://raw.githubusercontent.com/certbot/certbot/master/certbot-nginx/certbot_nginx/_internal/tls_configs/options-ssl-nginx.conf

# Generate DH params (takes a minute)
sudo openssl dhparam -out /etc/letsencrypt/ssl-dhparams.pem 2048
```

Auto-renewal is handled by certbot's systemd timer:

```bash
sudo systemctl enable --now certbot-renew.timer
```

The nginx container mounts `/etc/letsencrypt` read-only, so renewed certs are picked up automatically on the next nginx reload.

---

### Stats Script

`/usr/local/bin/mirror-stats.sh` on the host (not inside Docker). Runs every 60 seconds via a systemd timer and generates `/srv/archmirror/stats.json`, which nginx serves as a static file. The dashboard fetches it client-side.

```bash
#!/bin/bash
# /usr/local/bin/mirror-stats.sh - generates /srv/archmirror/stats.json

MIRROR_DIR="/srv/archmirror"
ACCESS_LOG="/var/log/nginx/archmirror.access.log"
CACHE_FILE="/srv/archmirror/stats.json"
CACHE_TTL=60

mirror_log_files() {
  find /var/log/nginx -maxdepth 1 -type f \( -name 'archmirror.access.log' -o -name 'archmirror.access.log.*' \) 2>/dev/null | LC_ALL=C sort -u
}

LASTSYNC_FILE="$MIRROR_DIR/lastupdate"
if [[ -f "$LASTSYNC_FILE" ]]; then
  last_sync_ts=$(cat "$LASTSYNC_FILE" | tr -d '[:space:]')
else
  last_sync_ts=$(date +%s)
fi

now=$(date +%s)
diff=$(( now - last_sync_ts ))
sync_ok="true"
if [[ $diff -gt 90000 ]]; then sync_ok="false"; fi

read disk_used_kb disk_free_kb < <(df "$MIRROR_DIR" --output=used,avail | tail -1)
disk_used_bytes=$(( disk_used_kb * 1024 ))
disk_free_bytes=$(( disk_free_kb * 1024 ))

# Use UTC to match nginx log timestamps (nginx inside Docker logs in UTC regardless of host timezone)
today=$(date -u +%d/%b/%Y)
requests_today=0
unique_ips_today=0
bytes_served_today=0
total_bytes_served=0

mapfile -t _LOGFILES < <(mirror_log_files)

if ((${#_LOGFILES[@]} > 0)); then
  requests_today=$(grep -a -hF "$today" "${_LOGFILES[@]}" 2>/dev/null | wc -l)
  unique_ips_today=$(grep -a -hF "$today" "${_LOGFILES[@]}" 2>/dev/null | awk '{print $1}' | sort -u | wc -l)
  bytes_served_today=$(grep -a -hF "$today" "${_LOGFILES[@]}" 2>/dev/null | \
    awk '{b=$10; if(b=="-") b=0; sum+=b} END{print sum+0}')
  for _lf in "${_LOGFILES[@]}"; do
    [[ -f "$_lf" ]] || continue
    if [[ "$_lf" == *.gz ]]; then
      _part=$(gzip -dc "$_lf" 2>/dev/null | awk '{b=$10; if(b=="-") b=0; sum+=b} END{print sum+0}')
    else
      _part=$(awk '{b=$10; if(b=="-") b=0; sum+=b} END{print sum+0}' "$_lf" 2>/dev/null)
    fi
    total_bytes_served=$(( total_bytes_served + ${_part:-0} ))
  done
fi

# Historical offset from before VPS migration. Set to 0 if starting fresh.
_offset=$(python3 -c "import json; print(json.load(open('/var/lib/mirror-stats/baseline.json')).get('total_bytes_served_offset', 0))")
total_bytes_served=$(( total_bytes_served + _offset ))

repos=()
for repo in core extra multilib core-testing extra-testing gnome-unstable kde-unstable multilib-testing; do
  repo_path="$MIRROR_DIR/$repo/os/x86_64"
  if [[ -d "$repo_path" ]]; then
    size_bytes=$(find "$repo_path" -maxdepth 1 -type l -name "*.pkg.tar.zst" -exec readlink -f {} \; | xargs -r stat -c%s | awk '{s+=$1} END {print s+0}')
    repos+=("\"$repo\": $size_bytes")
  fi
done
repos_json="{$(IFS=','; echo "${repos[*]}")}"

declare -A day_counts
if ((${#_LOGFILES[@]} > 0)); then
  while IFS= read -r logday; do
    day_counts["$logday"]=$(( ${day_counts["$logday"]:-0} + 1 ))
  done < <(grep -a -h "" "${_LOGFILES[@]}" 2>/dev/null | awk '{match($4, /\[([0-9]+\/[A-Za-z]+\/[0-9]+)/, a); if(a[1]!="") print a[1]}')
fi

uptime_days="["
for i in $(seq 29 -1 0); do
  day_fmt=$(date -d "$i days ago" +%d/%b/%Y)
  if [[ ${day_counts["$day_fmt"]:-0} -gt 0 ]]; then
    uptime_days+="1"
  else
    uptime_days+="0"
  fi
  [[ $i -gt 0 ]] && uptime_days+=","
done
uptime_days+="]"

up_count=$(echo "$uptime_days" | grep -o "1" | wc -l)
uptime_30d=$(echo "scale=1; $up_count * 100 / 30" | bc)

traffic_7d="["
for i in $(seq 6 -1 0); do
  day=$(date -d "$i days ago" +%Y-%m-%d)
  day_fmt=$(date -d "$day" +%d/%b/%Y)
  bytes=0
  if ((${#_LOGFILES[@]} > 0)); then
    bytes=$(grep -a -hF "$day_fmt" "${_LOGFILES[@]}" 2>/dev/null | \
      awk '{b=$10; if(b=="-") b=0; sum+=b} END{print sum+0}')
  fi
  traffic_7d+="{\"date\":\"$day\",\"bytes\":$bytes}"
  [[ $i -gt 0 ]] && traffic_7d+=","
done
traffic_7d+="]"

PERSISTENT_FILE="/var/lib/mirror-stats/persistent.json"
if [[ ! -f "$PERSISTENT_FILE" ]]; then
  echo '{"total_unique_ip_count":0,"seen_ip_hashes":[]}' > "$PERSISTENT_FILE"
fi

if ((${#_LOGFILES[@]} > 0)); then
  todays_ips=$(grep -a -hF "$today" "${_LOGFILES[@]}" 2>/dev/null | awk '{print $1}' | sort -u)
else
  todays_ips=""
fi

python3 -c "
import json, hashlib

with open('$PERSISTENT_FILE') as f:
    data = json.load(f)

existing_hashes = set(data.get('seen_ip_hashes', []))
todays_ips = '''$todays_ips'''.split() if '''$todays_ips'''.strip() else []
todays_hashes = {hashlib.sha256(ip.encode()).hexdigest() for ip in todays_ips}

merged = existing_hashes | todays_hashes
data['seen_ip_hashes'] = sorted(merged)
data['total_unique_ip_count'] = len(merged)

for k in ('last_accounted_day', 'total_bytes_served'):
    data.pop(k, None)

with open('$PERSISTENT_FILE', 'w') as f:
    json.dump(data, f)
"

total_unique_ip_count=$(python3 -c "
import json
with open('$PERSISTENT_FILE') as f:
    data = json.load(f)
print(data.get('total_unique_ip_count', 0))
")

json=$(cat <<EOF
{
  "last_sync_ts": $last_sync_ts,
  "sync_ok": $sync_ok,
  "disk_used_bytes": $disk_used_bytes,
  "disk_free_bytes": $disk_free_bytes,
  "requests_today": $requests_today,
  "unique_ips_today": $unique_ips_today,
  "bytes_served_today": $bytes_served_today,
  "total_unique_ip_count": $total_unique_ip_count,
  "total_bytes_served": $total_bytes_served,
  "uptime_30d": $uptime_30d,
  "uptime_days": $uptime_days,
  "traffic_7d": $traffic_7d,
  "repos": $repos_json,
  "generated_at": $now
}
EOF
)

echo "$json" > "$CACHE_FILE"
cat "$CACHE_FILE"
```

Important notes:
- Uses `grep -a` instead of `grep` or `zgrep` because nginx log files with very long lines get misdetected as binary files, causing silent zero counts
- Uses `date -u` for "today" to match the UTC timestamps nginx writes inside Docker
- Reads `bc` for floating point uptime calculation - install it if missing (`sudo pacman -S bc`)
- The persistent file at `/var/lib/mirror-stats/persistent.json` accumulates all-time unique IP hashes across log rotations
- `baseline.json` at `/var/lib/mirror-stats/baseline.json` holds a `total_bytes_served_offset` for migrating historical totals from a previous setup. Set to `{"total_bytes_served_offset": 0}` for a fresh install.

---

### Stats Systemd Units

`/etc/systemd/system/mirror-stats.timer`:

```ini
[Unit]
Description=Refresh mirror stats every minute

[Timer]
OnBootSec=10
OnUnitActiveSec=60

[Install]
WantedBy=timers.target
```

`/etc/systemd/system/mirror-stats.service`:

```ini
[Unit]
Description=Generate mirror stats JSON

[Service]
Type=oneshot
ExecStart=/usr/local/bin/mirror-stats.sh
User=root
```

Enable with:

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now mirror-stats.timer
```

---

### Firewall

UFW, minimal ruleset:

```bash
sudo ufw allow 80
sudo ufw allow 443
sudo ufw enable
```

Port 873 (rsync) does not need to be open inbound - the server initiates all syncs outbound.

---

### Remote Access

Tailscale is installed on the VPS. SSH is only accessible via the Tailscale IP, port 22 is not open on the public firewall. Install:

```bash
curl -fsSL https://tailscale.com/install.sh | sh
sudo tailscale up
```

---

## Required Host Directories

These must exist on the host before running `docker compose up`. Docker bind mounts don't create them automatically:

```bash
sudo mkdir -p /srv/archmirror /srv/archmirror-dashboard /var/log/nginx
sudo mkdir -p /var/lib/mirror-stats
echo '{"total_bytes_served_offset": 0}' | sudo tee /var/lib/mirror-stats/baseline.json
echo '{"total_unique_ip_count":0,"seen_ip_hashes":[]}' | sudo tee /var/lib/mirror-stats/persistent.json
```

---

## Deployment

```bash
# Install Docker
sudo pacman -S docker docker-compose
sudo systemctl enable --now docker
sudo usermod -aG docker $USER
# Log out and back in

# Clone and start
git clone https://github.com/Confused-Guy/Arch_Mirror_Tunisia
cd Arch_Mirror_Tunisia/arch-mirror-docker
docker compose up -d

# Trigger initial sync immediately (won't wait 6 hours)
docker exec -d mirror-sync /usr/local/bin/archmirror-sync.sh
docker logs -f mirror-sync

# Install stats dependencies on host
sudo pacman -S bc python

# Copy stats script and systemd units to host
sudo cp mirror-stats.sh /usr/local/bin/
sudo chmod +x /usr/local/bin/mirror-stats.sh
# (copy mirror-stats.service and mirror-stats.timer to /etc/systemd/system/)
sudo systemctl daemon-reload
sudo systemctl enable --now mirror-stats.timer
```

---

## Useful Commands

```bash
# Container status
docker ps

# Nginx logs
docker logs mirror-nginx
docker logs -f mirror-nginx

# Trigger a manual sync (background)
docker exec -d mirror-sync /usr/local/bin/archmirror-sync.sh

# Watch sync progress
docker logs -f mirror-sync

# Kill a runaway sync
docker exec mirror-sync pkill -f rsync

# Nginx config inside container
docker exec mirror-nginx cat /etc/nginx/conf.d/archmirror.conf

# Test nginx config
docker exec mirror-nginx nginx -t

# Reload nginx config
docker exec mirror-nginx nginx -s reload

# Disk usage
df -h /srv

# Stats
sudo systemctl start mirror-stats.service
sudo systemctl status mirror-stats.timer
curl -s https://mirror.safiabidi.com/stats.json | python3 -m json.tool
```

---

## Tier Status

The mirror is listed as **Tier 2** on the official Arch Linux mirror list. It syncs from a Tier 1 upstream (selfnet.de, Germany) and is publicly accessible over HTTPS.

Tier 1 requires syncing directly from `rsync.archlinux.org`, which requires explicit approval from the Arch Linux team. That's a future goal once a longer uptime history is established.

---

<details>
<summary><strong>History - From Laptop to VPS (click to expand)</strong></summary>

## Origin

This project started in December 2025 as a learning exercise: understand how Arch Linux mirrors work by building one from scratch. The initial goal wasn't to run an official mirror, just to understand the mechanics.

At the time the setup was:
- Host: old personal laptop running Arch Linux
- Storage: ~380 GB free on NVMe
- Network: residential Tunisie Telecom connection

---

## Initial Sync

First attempt at syncing used `rsync://23m.com/archlinux/` (a German Tier 1 mirror) and immediately failed:

```
rsync: [Receiver] failed to connect to 23m.com (212.83.32.5): No route to host (113)
rsync: [Receiver] failed to connect to 23m.com (2a00:f48:1007::3): Network is unreachable (101)
```

`No route to host` means the network stack couldn't find a valid path to the destination - likely an ISP routing issue, regional block, or upstream firewall. The IPv6 failure is a separate issue: the residential connection had no working IPv6. Neither is inherently a problem; Tier 1 mirrors aren't universally reachable:

- Some block certain ASNs
- Some have regional routing quirks
- Some are reachable via HTTP but not rsync
- Being Tier 1 doesn't mean globally accessible

Switched to `rsync://mirror.selfnet.de/archlinux/` with no issues. First sync pulled ~138 GB and completed in just over 11 hours. A `code 24` warning appeared:

```
rsync warning: some files vanished before they could be transferred (code 24)
```

Not a real error. It means the upstream mirror changed files while the sync was in progress, which is normal for a live package repository. A second run fixed it in 19 minutes.

---

## CGNAT Problem

The first major blocker to going public: Tunisie Telecom was assigning a private `10.x.x.x` address at the router level. This is CGNAT - Carrier-Grade NAT - where the ISP shares one public IP across many customers. Port forwarding is useless in this situation because the machine is behind two layers of NAT.

Fix: upgraded the internet plan to include a fixed public IP. TT sent an SMS confirming the static IP assignment, followed by a phone call to configure the router's APN settings. After a router reboot, `curl ifconfig.me` confirmed a real routable address.

---

## Port Forwarding

With a public IP, the router needed to forward inbound traffic to the laptop's local address (reserved via MAC binding so it wouldn't change).

Rules added in the router admin panel:
- `443 → local machine:443`
- `80 → local machine:80`

Port 80 turned out to be blocked by Tunisie Telecom at the ISP level on residential lines. Port 443 worked fine. Since Arch's official mirror requirements prefer HTTPS anyway, this wasn't a problem.

---

## DNS

Initially used a free `dedyn.io` hostname via deSEC:

```
mirror.safi-abidi-arch-mirror.dedyn.io
```

Later moved to a proper subdomain managed via Cloudflare DNS. The A record has the Cloudflare proxy (orange cloud) deliberately disabled - mirrors need direct connections. Proxying through Cloudflare's CDN breaks rsync and causes pacman to see Cloudflare IPs instead of the mirror's real address.

---

## nginx (Original Setup)

nginx was installed directly on the host via `pacman -S nginx`. The initial config was minimal:

```nginx
server {
    listen 80;
    server_name _;
    root /srv/archmirror;
    autoindex on;
}
```

Eventually evolved to the full HTTPS config with Let's Encrypt and a separate dashboard location block. Managed via `systemctl` and `journalctl` directly on the host.

---

## Automation (Original)

The original sync ran via a systemd service and timer directly on the host. The service file included CPU and I/O priority settings to prevent the sync from hogging resources on the laptop:

```ini
[Service]
Type=oneshot
ExecStart=/usr/local/bin/archmirror-sync.sh
Nice=10
IOSchedulingClass=idle
```

The timer ran nightly at 03:00.

---

## Migration to VPS (June 2026)

After several months running off the laptop, the mirror was migrated to a dedicated VPS at ATI. Reasons:

- Laptop uptime was dependent on power, WiFi stability, and the desktop environment not crashing
- A 3-hour offline gap caused by a WiFi disconnect dropped uptime from 100% to 96.6%
- VPS provides ~5 Gbps bandwidth vs residential upload speeds
- No CGNAT, no port forwarding, no ISP-level port blocking

Issues encountered during migration:

**VPS booted into Arch ISO instead of installed OS.** ATI provisioned the machine but the VM boot order had the CD/DVD drive before the hard disk. Arch was installed manually via `archinstall` from the live ISO console. After install, the VPS correctly booted from disk.

**nginx logs misdetected as binary.** The access log had accumulated since December and contained very long lines (366 chars). `grep` treats files with long lines as binary and returns 0 matches silently. Fixed by switching all `grep` and `zgrep` calls in the stats script to `grep -a`, which forces text mode.

**UTC timezone mismatch.** nginx inside Docker logs timestamps in UTC. The host is UTC+1. This caused the stats script to show zero requests for the first hour of every day (it was grepping for the local date, which was already tomorrow in UTC terms). Fixed by using `date -u` in the stats script.

**Historical stats migration.** 389 GB of traffic data, 11k unique IPs, and 30-day uptime history all lived on the old machine's logs and persistent files. Migrated by copying the old nginx access log (renamed to `archmirror.access.log.1` so the stats script picks it up), copying `/var/lib/mirror-stats/persistent.json`, and setting `total_bytes_served_offset` in `baseline.json` to carry over the historical total.

**Concurrent rsync spike.** Running a manual sync while the scheduled sync was already running caused both to write temp files simultaneously (via `--delay-updates`), spiking disk from 123 GB to 147 GB. Resolved by killing both with `docker exec mirror-sync pkill -f rsync` and letting the scheduler handle it.

**BusyBox date syntax.** The original entrypoint.sh used GNU date syntax (`date -d "today HH:MM"`) to calculate sleep time until the next scheduled sync. Alpine Linux inside Docker uses BusyBox, which doesn't support that syntax. The script was silently sleeping for a negative number of seconds and running immediately. Replaced with a simple `sleep 21600` loop.

The entire mirror stack was containerized into Docker Compose during this migration, replacing the previous systemd-managed nginx and sync services.

</details>
