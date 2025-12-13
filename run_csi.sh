#!/bin/bash
# ================================================================
#  Full Automated CSI Collection Script for PicoScenes
#  Works on Ubuntu (AX200/AX210) with PicoScenes installed
# ================================================================

### --- USER CONFIGURATIONS --- ###
PHY_ID=4                    # Your PhyPath (from array_status)
WIFI_IFACE="wlp4s0"         # Your Wi-Fi interface name
MON_IFACE="mon${PHY_ID}"    # Monitor interface name auto-created by PicoScenes
CHANNEL_CFG="5745 80 5775"  # Example: CH149, 80MHz, center Freq 5775
OUTPUT_DIR="/mnt/psrd"      # Directory to store CSI files
AP_SSID="Sony_Home"         # Wi-Fi SSID (used during restore)
AP_PASSWORD="torbaap@2024"  # Wi-Fi password (used during restore)
### ----------------------------- ###


echo "==============================================================="
echo "        PicoScenes CSI Collection Script Starting"
echo "==============================================================="

### STEP 1 — Verify root privileges
if [[ $EUID -ne 0 ]]; then
   echo "❌ This script must be run with sudo:"
   echo "   sudo bash collect_csi.sh"
   exit 1
fi


### STEP 2 — Create CSI directory if missing
echo "[+] Creating/checking output directory: $OUTPUT_DIR"
mkdir -p "$OUTPUT_DIR"
chmod 777 "$OUTPUT_DIR"
cd "$OUTPUT_DIR"


### STEP 3 — Disconnect Wi-Fi and disable NetworkManager control
echo "[+] Disconnecting Wi-Fi…"
nmcli dev disconnect "$WIFI_IFACE"
nmcli radio wifi off


### STEP 4 — Unblock RF Kill
echo "[+] Unblocking RF-Kill…"
rfkill unblock wifi
rfkill list


### STEP 5 — Show available devices (for debugging)
echo "[+] Checking PicoScenes Wi-Fi Array Status:"
array_status


### STEP 6 — Prepare NIC for monitor mode
echo "[+] Preparing NIC for monitor mode…"
array_prepare_for_picoscenes "$PHY_ID" "$CHANNEL_CFG"


### STEP 7 — Confirm monitor interface creation
echo "[+] Checking iw dev output:"
iw dev


### STEP 8 — Start CSI Logging
echo "==============================================================="
echo " Starting CSI logging using PicoScenes"
echo " Press CTRL + C after you're done collecting CSI"
echo "==============================================================="

PicoScenes "-d debug -i ${PHY_ID} --mode logger --plot"

echo "[+] PicoScenes CSI collection finished."


### STEP 9 — List saved CSI files
echo "[+] The following CSI files were created:"
ls -lh *.csi


### STEP 10 — Restore Wi-Fi to normal mode
echo "[+] Restoring Wi-Fi…"

# Remove monitor interface if exists
iw dev "$MON_IFACE" del 2>/dev/null

# Re-enable Wi-Fi
nmcli radio wifi on
systemctl restart NetworkManager
ip link set "$WIFI_IFACE" up

# Connect back to AP
nmcli dev wifi connect "$AP_SSID" password "$AP_PASSWORD"

echo "==============================================================="
echo "               CSI Collection Completed Successfully"
echo "    Files saved inside:  $OUTPUT_DIR"
echo "==============================================================="

chmod +x collect_csi.sh
sudo ./collect_csi.sh