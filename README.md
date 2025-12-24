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
- This is the expected tree layout after syncing from an official tier 1 mirror.

What i did next was change the mirror to read only, this is the best practice. Of course rsync will still work because it uses temp files and atomic renames:
```Bash
sudo chown -R root:root /srv/archmirror
sudo chmod -R a-w /srv/archmirror
```
