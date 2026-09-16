#!/usr/bin/env python3
"""Incremental log processing for mirror-stats.sh.

Reads only new bytes appended to the live access log since last run
(tracked by byte offset + inode in STATE_FILE). Maintains per-day
request/byte buckets and an all-time unique-IP hash set as persistent
state, so nothing ever needs to re-scan old log data.

On first run (no state file yet), does a one-time full scan of every
existing archmirror.access.log* file to bootstrap totals and day buckets,
matching what the old always-full-rescan script would have shown.
"""
import argparse
import glob
import gzip
import hashlib
import json
import os
import re
import sys
import time

LINE_RE = re.compile(rb'^(\S+) \S+ \S+ \[(\d+/\w+/\d+):[^\]]*\] "[^"]*" \d+ (\S+)')
RETENTION_DAYS = 35


def parse_line(raw):
    m = LINE_RE.match(raw)
    if not m:
        return None
    ip = m.group(1).decode("ascii", "replace")
    date_str = m.group(2).decode("ascii", "replace")
    b = m.group(3)
    nbytes = int(b) if b.isdigit() else 0
    try:
        day_key = time.strftime("%Y-%m-%d", time.strptime(date_str, "%d/%b/%Y"))
    except ValueError:
        return None
    return ip, day_key, nbytes


def load_json(path, default):
    try:
        with open(path) as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return default


def existing_log_files():
    files = set(glob.glob("/var/log/nginx/archmirror.access.log")) | \
        set(glob.glob("/var/log/nginx/archmirror.access.log.*"))
    return sorted(files)


def open_maybe_gz(path):
    return gzip.open(path, "rb") if path.endswith(".gz") else open(path, "rb")


def process_lines(fh, daily, today_key, today_ip_hashes, alltime_hashes):
    requests = 0
    total_bytes = 0
    for raw in fh:
        parsed = parse_line(raw)
        if parsed is None:
            continue
        ip, day_key, nbytes = parsed
        requests += 1
        total_bytes += nbytes
        h = hashlib.sha256(ip.encode()).hexdigest()
        alltime_hashes.add(h)
        bucket = daily.setdefault(day_key, {"requests": 0, "bytes": 0})
        bucket["requests"] += 1
        bucket["bytes"] += nbytes
        if day_key == today_key:
            today_ip_hashes.add(h)
    return requests, total_bytes


def prune_daily(daily, now):
    cutoff = now - RETENTION_DAYS * 86400
    for k in list(daily.keys()):
        try:
            ts = time.mktime(time.strptime(k, "%Y-%m-%d"))
        except ValueError:
            daily.pop(k, None)
            continue
        if ts < cutoff:
            daily.pop(k, None)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--access-log", required=True)
    ap.add_argument("--state-file", required=True)
    ap.add_argument("--persistent-file", required=True)
    ap.add_argument("--baseline-file", required=True)
    ap.add_argument("--cache-file", required=True)
    ap.add_argument("--last-sync-ts", type=int, required=True)
    ap.add_argument("--sync-ok", required=True)
    ap.add_argument("--disk-used-bytes", type=int, required=True)
    ap.add_argument("--disk-free-bytes", type=int, required=True)
    ap.add_argument("--repos-json", required=True)
    ap.add_argument("--now", type=int, required=True)
    args = ap.parse_args()

    now = args.now
    today_key = time.strftime("%Y-%m-%d", time.gmtime(now))

    baseline = load_json(args.baseline_file, {"total_bytes_served_offset": 0})
    persistent = load_json(args.persistent_file, {"total_unique_ip_count": 0, "seen_ip_hashes": []})
    alltime_hashes = set(persistent.get("seen_ip_hashes", []))

    state = load_json(args.state_file, None)
    bootstrapping = state is None
    if bootstrapping:
        state = {
            "offset": 0,
            "inode": 0,
            "today_key": today_key,
            "today_ip_hashes": [],
            "total_bytes_served": int(baseline.get("total_bytes_served_offset", 0)),
            "daily": {},
        }

    daily = state.get("daily", {})

    # Day rollover: flush accumulated today_ip_hashes count isn't stored
    # per se (daily bucket only needs requests/bytes, both already updated
    # incrementally as lines were processed) - just reset the per-day IP set.
    if state["today_key"] != today_key:
        state["today_key"] = today_key
        state["today_ip_hashes"] = []
    today_ip_hashes = set(state.get("today_ip_hashes", []))

    try:
        cur_inode = os.stat(args.access_log).st_ino
        cur_size = os.path.getsize(args.access_log)
    except OSError:
        cur_inode = 0
        cur_size = 0

    if bootstrapping:
        # One-time full scan of every log file that currently exists.
        for path in existing_log_files():
            try:
                with open_maybe_gz(path) as fh:
                    process_lines(fh, daily, today_key, today_ip_hashes, alltime_hashes)
            except OSError:
                continue
        # total_bytes_served = baseline + sum of all bytes just counted
        state["total_bytes_served"] = int(baseline.get("total_bytes_served_offset", 0)) + \
            sum(b["bytes"] for b in daily.values())
        state["offset"] = cur_size
        state["inode"] = cur_inode
    else:
        # Log rotated or truncated since last run -> restart from 0.
        if state.get("inode") != cur_inode or state.get("offset", 0) > cur_size:
            state["offset"] = 0
            state["inode"] = cur_inode

        new_requests = 0
        new_bytes = 0
        try:
            with open(args.access_log, "rb") as f:
                f.seek(state["offset"])
                new_requests, new_bytes = process_lines(
                    f, daily, today_key, today_ip_hashes, alltime_hashes
                )
                state["offset"] = f.tell()
        except OSError:
            pass
        state["total_bytes_served"] = state.get("total_bytes_served", 0) + new_bytes

    prune_daily(daily, now)
    state["daily"] = daily
    state["today_ip_hashes"] = list(today_ip_hashes)

    persistent["seen_ip_hashes"] = sorted(alltime_hashes)
    persistent["total_unique_ip_count"] = len(alltime_hashes)

    with open(args.persistent_file, "w") as f:
        json.dump(persistent, f)
    with open(args.state_file, "w") as f:
        json.dump(state, f)

    today_bucket = daily.get(today_key, {"requests": 0, "bytes": 0})

    uptime_days = []
    for i in range(29, -1, -1):
        day = time.strftime("%Y-%m-%d", time.gmtime(now - i * 86400))
        uptime_days.append(1 if daily.get(day, {}).get("requests", 0) > 0 else 0)
    uptime_30d = round(sum(uptime_days) * 100 / 30, 1)

    traffic_7d = []
    for i in range(6, -1, -1):
        day = time.strftime("%Y-%m-%d", time.gmtime(now - i * 86400))
        traffic_7d.append({"date": day, "bytes": daily.get(day, {}).get("bytes", 0)})

    repos = json.loads(args.repos_json)

    output = {
        "last_sync_ts": args.last_sync_ts,
        "sync_ok": args.sync_ok == "true",
        "disk_used_bytes": args.disk_used_bytes,
        "disk_free_bytes": args.disk_free_bytes,
        "requests_today": today_bucket["requests"],
        "unique_ips_today": len(today_ip_hashes),
        "bytes_served_today": today_bucket["bytes"],
        "total_unique_ip_count": len(alltime_hashes),
        "total_bytes_served": state["total_bytes_served"],
        "uptime_30d": uptime_30d,
        "uptime_days": uptime_days,
        "traffic_7d": traffic_7d,
        "repos": repos,
        "generated_at": now,
    }

    with open(args.cache_file, "w") as f:
        json.dump(output, f)


if __name__ == "__main__":
    sys.exit(main())
