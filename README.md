# Arch Linux Mirror (Self-Hosted)
Hi! This is where i'll be documenting all the steps i took to set up the arch mirror:
## Project Scope and Intent

This project implements a **self-hosted Arch Linux package mirror** for learning and experimentation!

The goal at this stage is **not** to operate an official Tier-1 or Tier-2 mirror, but to:

- Understand how Arch Linux mirrors work internally
- Mirror a subset of Arch repositories correctly
- Serve them locally over HTTP
- Ensure compatibility with `pacman`
- Build a setup that can later be automated and documented properly

The mirror is hosted on my old laptop and is intended for controlled, low-traffic usage.

---
## System Environment

- Distribution: Arch Linux
- Host: Personal laptop
- Architecture: `x86_64`
- Available storage: ~380 GB free on root filesystem (df -f to show the available storage on the NVMe)

This amount of storage is sufficient for mirroring the primary Arch repositories (`core`, `extra`) with alot of room for growth.
---
## Filesystem Preparation

Arch Linux mirrors are served as static file trees.  
According to the Filesystem Hierarchy Standard (FHS), service data intended to be exported has to be explicitly placed under `/srv`.
So:
Created these directories for the mirror contents:

```bash
sudo mkdir -p /srv/archmirror
sudo chown -R $USER:$USER /srv/archmirror
```
---
## rsync set-up

To actually be able to retrieve from the mirrors we need rsync, which is arch infrastructure so we use pacman:
```bash
sudo pacman -S rsync
```
