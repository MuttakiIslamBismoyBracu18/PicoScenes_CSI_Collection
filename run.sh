# Recreate the two files and display them for download

# Shell script content
sh_content = """#!/bin/bash
set -e

echo "=== PicoScenes Automated Installer for Ubuntu 20.04/22.04 with AX200 ==="

# Step 1: Install source updater from downloaded .deb
cd ~/Downloads/picoscenes || exit
sudo dpkg -i picoscenes-source-updater.deb || true
sudo apt --fix-broken install -y

# Step 2: Run Maintainer and install platform/drivers
MaintainPicoScenes << EOF
1
EOF

echo ">>> PLEASE REBOOT and disable Secure Boot in the MOK screen if prompted!"
"""

# Markdown guide content
md_content = """# PicoScenes Full Installation & Troubleshooting Guide

*(Ubuntu 20.04/22.04 — Intel AX200 — Verified Stable Setup)*

---

## Requirements
- Ubuntu **20.04 / 22.04**
- Kernel **6.5.0-15-generic**
- Intel **AX200 Wi-Fi NIC**
- Secure Boot **disabled**
- PicoScenes `.deb` installer downloaded

---

## 1️⃣ Install PicoScenes Source Updater

```bash
cd ~/Downloads/picoscenes
sudo dpkg -i picoscenes-source-updater.deb
sudo apt --fix-broken install -y
