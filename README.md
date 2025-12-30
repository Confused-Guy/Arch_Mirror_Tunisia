# Arch Linux Mirror (Self-Hosted)
Hi! This is where i'll be documenting all the steps i took to set up the arch mirror:
## Project Scope and Intent

This project implements a **self-hosted Arch Linux package mirror** for learning and experimentation! Later on i'll expand and automate in hopes of making it to the official arch mirror list.

But the goal at this stage is **not** to operate an official Tier-1 or Tier-2 mirror, but to:
- Understand how Arch Linux mirrors work internally
- Mirror a subset of Arch repositories correctly
- Serve them locally over HTTP
- Ensure compatibility with `pacman`
- Build a setup that can later be automated and documented properly

The mirror is hosted on my old laptop, intended for controlled, low-traffic usage.

---
## System Environment

- Distribution: Arch Linux
- Host: Old personal laptop
- Architecture: `x86_64`
- Available storage: ~380 GB free on root file-system (df -f to show the available storage on the NVMe)
This amount of storage is sufficient for mirroring the entirety of Arch repositories from a tier 1 mirror, with a lot of room for growth.
---
## File-system Preparation

Arch Linux mirrors are served as static file trees.  
According to the File-system Hierarchy Standard (FHS), service data intended to be exported has to be explicitly placed under `/srv`.
So:
Created these directories for the mirror contents:

```bash
sudo mkdir -p /srv/archmirror
sudo chown -R $USER:$USER /srv/archmirror
```
---
## Which mirror to clone?
There's a lot that goes into which mirror you should sync to before you get access to sync directly from the original arch mirror. Since i'm in Tunisia, the closest and most consistent choice at my disposal is Germany's mirror list:

I had a couple of choices for this:
These mirrors are listed on the official Arch Linux mirror list as Tier-1 with rsync support:
- `rsync://23m.com/archlinux/`
- `rsync://gwdg.de/archlinux/`
- `rsync://selfnet.de/archlinux/`
- `rsync://xtom.de/archlinux/`
- `rsync://rwth-aachen.de/archlinux/` [Arch Linux](https://archlinux.org/mirrors/tier/1)

![Pasted image 20251224205713](Pasted%20image%2020251224205713.png)

Initially i tried to connect to the first one (being 23m.com) however i got this error in the terminal:
```bash
◄ 0s ○ rsync -avz --delete --delay-updates \ 
rsync://23m.com/archlinux/ \ /srv/archmirror/ 
rsync: [Receiver] failed to connect to 23m.com (212.83.32.5): No route to host (113) 
rsync: [Receiver] failed to connect to 23m.com (2a00:f48:1007::3): Network is unreachable (101) 
rsync error: error in socket IO (code 10) at clientserver.c(139) [Receiver=3.4.1] 
◄ 0s ○
```

What this error basically told me is that my machine knows the ip, but the network stack couldn't find a valid route to it; this could indicate an ISP routing issue, that the mirror was blocking my networl/region, an upstream firewall, or a temporary outage. 
Also:
```Bash
failed to connect to 23m.com (2a00:f48:1007::3): Network is unreachable (101)
```
Just means that my system doesn't have working IPv6 connectivity, when rsync tries it, it fails instantly. Which is fine and not a problem by itself.

TLDR; rsync never got past the TCP connection phase>no data got transferred>failure.

All this means is that 23m.com wasn't reachable from my network.
Even Tier-1 mirrors:
- May block certain ASNs
- May have regional routing quirks
- May be reachable via HTTP but not rsync
- May temporarily drop rsync access
Being Tier-1 =/= universally reachable.

With all that considered, i instead used `rsync://mirror.selfnet.de/archlinux` and ran into none of those issues, so we'll proceed with it instead.

---

## rsync set-up and result:

To actually be able to retrieve from the mirrors we need rsync, which is arch infrastructure so we have to use pacman, not yay or peru:
```bash
sudo pacman -S rsync
```

### Important rsync flags

- `-a` archive  
    Preserves permissions, symlinks, timestamps
- `-v` verbose  
    To see what’s happening
- `-z` compression  
    For saving bandwidth
- `--delete`  
    Removes files deleted upstream  
    (dangerous without understanding, but needed nonetheless)
- `--delay-updates`  
    Prevents partial states during sync
This is what keeps the mirror entirely consistent.

So we end up with:
```bash
rsync -avz --delete --delay-updates \
  rsync://mirror.selfnet.de/archlinux/ \
  /srv/archmirror/
```

This is what i got after the rsync: 
```
sent 795,932 bytes received 137,902,317,850 bytes 3,342,417.05 bytes/sec 
total size is 138,253,860,081 speedup is 1.00 
rsync warning: some files vanished before they could be transferred (code 24) at main.c(1852) [generator=3.4.1] 
◄ 11h27m37s ○
```

This basically means:
-received 137,902,317,850 bytes
-total size is 138,253,860,081
-speedup is 1.00
>>I pulled about 138~ GBs, which matches a partial Arch mirror.
>no corruption implied
>the mirror is usable
>and the transfer completed normally

So, all in all, the sync succeeded!

To address the rsync warning:
```bash
rsync warning: some files vanished before they could be transferred (code 24)
```
- This isn't a problem at all, all it means that the upstream mirror changed WHILE i was syncing since the package indexes are constantly updated, or a file coulda been renamed or removed mid transfer, which is very normal for live package repositories.

Running rsync again gets rid of that altogether, and the second run was CONSIDERABLY faster(Took only 19 minutes to fix said files) and it gave 0 warnings.

By the end, all went as planned, and the /srv/archmirror contained the following directories:

![Pasted image 20251224181402](Pasted%20image%2020251224181402.png)

- This is the expected tree layout after syncing from an official tier 1 mirror.

What i did next was change the mirror to read only, this is the best practice. Of course rsync will still work because it uses temp files and atomic renames:
```Bash
sudo chown -R root:root /srv/archmirror
sudo chmod -R a-w /srv/archmirror
```
---
## Next step, Hosting:
Firstly, `sudo pacman -S nginx` to install nginx for hosting.
`sudo systemctl enable --now nginx` to enable it.
The immediate next thing to do is to serve the mirror's directory with nginx, to do that we gotta change the nginx configs:
```bash
sudo nano /etc/nginx/nginx.conf
```
i changed it into this for the server block:
```bash
//ILL OPEN AND SHOW THIS LATER DONT FORGET :sob:
```
then just run this to see what's happening and reload it:
```bash
sudo nginx -t
sudo systemctl reload nginx
```
I tested if it worked or not via `curl http://localhost/core/` and that was that, it worked.

This was very surprising because things usually don't just work out of the box, and it didn't. 
>Initially i started with just this in the server block:
```nginx
server {
    listen 80;
    server_name _;
    root /srv/archmirror;

    autoindex on;
}
```
Very simplistic just to be able to test.

Yes, nginx was running, but again, it only worked on localhost, so nobody's got access to anything unless they're on the same wifi. We'll get back to this soon.

To ever check the status of nginx, i just run `systemctl status nginx`, for the logs `journalctl -u nginx`, and for access logs 
```bash
cat /var/log/nginx/access.log
```
for example:
```
◄ 12s ◎ cat /var/log/nginx/access.log                                                   ⌂ 05:02

127.0.0.1 - - [25/Dec/2025:04:22:21 +0100] "HEAD / HTTP/1.1" 200 0 "-" "curl/8.17.0"
127.0.0.1 - - [25/Dec/2025:04:22:41 +0100] "GET /core/os/x86_64/ HTTP/1.1" 404 153 "-" "curl/8.17.0"
127.0.0.1 - - [25/Dec/2025:04:30:48 +0100] "GET /core/os/x86_64/ HTTP/1.1" 404 153 "-" "curl/8.17.0"
127.0.0.1 - - [25/Dec/2025:04:34:20 +0100] "GET /core/os/x86_64/ HTTP/1.1" 404 153 "-" "curl/8.17.0"
```
## DNS:
Now realistically speaking, even if we ignore how dangerous having your IP just exposed to the public to use, it's also incredibly inconsistent to just give people my IP for them to be able to connect to the mirror, because it's dynamic.
To mitigate all of that, we use a DNS, or a domain name system. 
For this i went with `deSEC` because it was free and didn't require much hassle. I don't really care what the address ends with as long as it's a working address i can utilize, so there's no need to pay for a cloudflare DNS when there's free alternatives.

I ended up creating this DNS:
```DNS
mirror.safi-abidi-arch-mirror.dedyn.io
```
it's not flashy but it'll do its job.

## Automation:
Now here's the thing. It's cool to know what to copy paste to sync the mirror every time, but that's neither sustainable nor efficient nor will it teach me anything about maintaining such a huge project. So it's important to automate the things we have already established and know work, and make sure to add more important things to make life easier.
So, the goal of automation is:
- Run the sync **reliably**
- Run it **without manual intervention**
- Make failures **visible**
- Avoid unnecessary load (both on my system and upstream mirrors)

As it stands, here's the best way to show the structure of the project so far:
```scss
[ Upstream Arch Mirror ]
           ↓ (rsync)
[ My Local Mirror Storage ]
           ↓ (nginx)
[ HTTP Mirror Endpoint ]
           ↓
[ Internet (blocked by CGNAT,ISPs fault) ]
```
Only the **last arrow** is currently broken. Everything above it works.
I have this shell script:
```bash
nano /usr/local/bin/archmirror-sync.sh
```
inside is this(i'll add comments here to explain):
```bash
#!/bin/bash
#this line's for safety:
set -euo pipefail
#-e to exit immediately on error
#-u to error when we have undefined variables
#-o pipefail to catch any errors within the pipelines

#the where from: 
SOURCE="rsync://mirror.selfnet.de/archlinux/"
#and the where to:
DEST="/srv/archmirror"
#then just the command i always use to sync:
rsync -avz --delete --delay-updates \
  --partial \
  --timeout=600 \
  "$SOURCE" "$DEST"
#this writes what's called an "ISO-8601 timestamp" of the last successful sync, it's cleared me from having to deal with logs:
date -Is > /srv/archmirror/lastsync
```

```bash
nano /etc/systemd/system/archmirror-sync.service
```
Inside:
```bash
#this is to ensure the network is actually up, to prevent failed syncs during early boot, and using "wants" instead of requires avoids hard failures if the networking gets flaky:
[Unit]
Description=Arch Linux Mirror Sync
Wants=network-online.target
After=network-online.target


[Service]
Type=oneshot
#Type=oneshot just means the service runs, does its job, and exits
ExecStart=/usr/local/bin/archmirror-sync.sh
#ExecStart points directly to the script
Nice=10
#Nice=10 lowers the CPU priority and prevents the mirror sync from impacting interactive usage
IOSchedulingClass=idle 
#this last part stops the disk I/O from happening unless the system is idle
#all in all most of this is to make sure the mirror never hogs resources on the pc
```
During execution systemd will show: `Active: activating (start)`
Now for the timer:
```bash
nano /etc/systemd/system/archmirror-sync.timer
```
Which has:
```bash
#timer definition:
[Unit]
Description=Daily Arch Mirror Sync
#Runs exactly at 03:00, off-peak hours for both bandwidth and upstream mirrors:
[Timer]
OnCalendar=*-*-* 03:00:00
#if the system was off at 3, the it does it immediately after boot to prevent missing any syncs:
Persistent=true
#this is what allows enabling the timer via systemctl enable:
[Install]
WantedBy=timers.target
```

An example of how i could tell if the automation was actually working properly:
```bash
systemctl list-timers | grep archmirror
```
Which showed for example:
```bash
Wed 2025-12-31 03:00:00 CET    22h Tue 2025-12-30 03:00:03 CET 1h 53min ago archmirror-sync.timer            archmirror-sync.service
```
To check service history:
```bash
journalctl -u archmirror-sync.service
```
And for a live view:
```bash
journalctl -fu archmirror-sync.service
```
Which prints:
```
Dec 30 02:52:18 ArchV systemd[1]: archmirror-sync.service: Deactivated successfully.
Dec 30 02:52:18 ArchV systemd[1]: Finished Arch Linux Mirror Sync.
Dec 30 02:52:18 ArchV systemd[1]: archmirror-sync.service: Consumed 7.823s CPU time over 17min 23.439s wall clock time, 3.9G memory peak.
Dec 30 03:00:03 ArchV systemd[1]: Starting Arch Linux Mirror Sync...
Dec 30 03:00:08 ArchV archmirror-sync.sh[8534]: receiving file list ... done
Dec 30 03:00:09 ArchV archmirror-sync.sh[8547]: lastsync
Dec 30 03:00:09 ArchV archmirror-sync.sh[8547]: sent 63 bytes  received 6,597,720 bytes  1,015,043.54 bytes/sec
Dec 30 03:00:09 ArchV archmirror-sync.sh[8547]: total size is 140,220,413,320  speedup is 21,252.66
Dec 30 03:00:09 ArchV systemd[1]: archmirror-sync.service: Deactivated successfully.
Dec 30 03:00:09 ArchV systemd[1]: Finished Arch Linux Mirror Sync.
```
>What's printed is live, and does change in real time if it's doing a sync.

If i ever want to (or need to, but i doubt i will) check the space occupied/free space for the mirror i just run `df -h /srv`:

![](Pasted%20image%2020251230050112.png)

```C
//Next section will probably be either setting up a dashboard, or keeping it simple and instead setting up alerts. If i set up alerts, ssh-ing into this pc can allow me to check logs and errors asap, might be the next step
```
