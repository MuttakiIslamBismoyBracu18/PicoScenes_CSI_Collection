# PicoScenes CSI Collection Guide (Ubuntu 22.04 + AX200/AX210)

This README gives you a **complete, step‑by‑step pipeline** to:

1. Install PicoScenes
2. Install the PicoScenes Wi‑Fi driver
3. Troubleshoot installation / crashes
4. Update PicoScenes cleanly
5. Repair a broken PicoScenes pipeline
6. Turn off Wi‑Fi and prepare the NIC in **monitor mode**
7. Collect CSI with PicoScenes
8. Open and parse the `.csi` file in **MATLAB**

All commands and examples are written and tested for **Ubuntu 22.04 (Jammy)** with an **Intel AX200/AX210** NIC.

---

## 0. System Overview & Assumptions

- OS: **Ubuntu 22.04 LTS (Jammy)**
- User example: `obak-b` on host `obak-b-EQ`
- Example Wi‑Fi NIC: **Intel Wi‑Fi 6 AX200**
- Example normal Wi‑Fi interface: `wlp4s0`
- Example monitor interface: `mon4`
- Example PHY/array ID: **4**
- Example working directory (for CSI logs): your **home directory** (e.g., `/home/obak-b`)

Wherever you see:
- `4` → replace with your own **PhyPath / device index** from `array_status`
- `wlp4s0` → replace with your own **managed Wi‑Fi interface name**
- `Sony_Home` and `torbaap@2024` → replace with your own **SSID** and **password**

---

## 1. How to Install PicoScenes

### 1.1 Install prerequisites

```bash
sudo apt update
sudo apt install -y iw wireless-tools default-jre
```

Expected output (abridged):

```text
Reading package lists... Done
Building dependency tree... Done
Reading state information... Done
default-jre is already the newest version (...)
iw is already the newest version (...)
wireless-tools is already the newest version (...)
0 upgraded, 0 newly installed, 0 to remove and X not upgraded.
```

These tools are required for:
- `iw`, `wireless-tools`: inspecting and managing Wi‑Fi NICs
- `default-jre`: Java runtime for parts of PicoScenes tooling

---

### 1.2 Add the official PicoScenes APT repository

Create a sources list entry:

```bash
echo "deb [arch=amd64] https://ps2204.zpj.io/PicoScenes/22.04/x86_64 stable avx2 main"       | sudo tee /etc/apt/sources.list.d/picoscenes.list
```

Update APT cache:

```bash
sudo apt update
```

Expected output (abridged):

```text
Hit:1 http://us.archive.ubuntu.com/ubuntu jammy InRelease
...
Hit:8 https://ps2204.zpj.io/PicoScenes/22.04/x86_64 stable Release
Reading package lists... Done
Building dependency tree... Done
Reading state information... Done
```

> If you see warnings about `legacy trusted.gpg` keyrings, they are harmless for PicoScenes.

---

### 1.3 Install the PicoScenes platform

```bash
sudo apt install -y picoscenes-platform
```

Expected output (abridged):

```text
The following NEW packages will be installed:
  fping libqrencode4 ntpdate picoscenes-driver-modules-6.5.0-15-generic
  picoscenes-platform qrencode
...
Setting up picoscenes-platform (2025.0922.2120) ...

-------------------------------------------------------
PicoScenes Platform has been successfully installed.
View documentation at https://ps.zpj.io
-------------------------------------------------------
```

This installs:
- The **PicoScenes binary** (`PicoScenes`)
- Supporting libraries
- Some helper tools (`fping`, QR code tools, time sync, etc.)

---

### 1.4 Install the kernel‑matched PicoScenes driver

PicoScenes needs a driver package **matching your current kernel**:

```bash
sudo apt install -y picoscenes-driver-modules-$(uname -r)
```

Expected output (first install):

```text
Selecting previously unselected package picoscenes-driver-modules-6.5.0-15-generic ...
Unpacking picoscenes-driver-modules-6.5.0-15-generic (20240210) ...
Setting up picoscenes-driver-modules-6.5.0-15-generic (20240210) ...
```

If it's already installed:

```text
picoscenes-driver-modules-6.5.0-15-generic is already the newest version (20240210).
0 upgraded, 0 newly installed, 0 to remove and X not upgraded.
```

---

### 1.5 Verify installation

#### 1.5.1 Check installed packages

```bash
dpkg -l | grep picoscenes
```

Expected output:

```text
ii  picoscenes-driver-modules-6.5.0-15-generic 20240210  amd64  PicoScenes Driver
ii  picoscenes-platform                        2025.0922.2120  amd64  PicoScenes Platform
ii  picoscenes-source-updater                  1.3             amd64  PicoScenes-source-updater
```

#### 1.5.2 Launch PicoScenes

```bash
PicoScenes
```

First launch after installation may produce a **scheduled crash** once (see troubleshooting below). On a normal run, you should eventually see:

```text
=====================================================================================

      PicoScenes Platform - Enabling Modern Wi-Fi ISAC Research! 

=====================================================================================
[Platform] [Info ] Loading PicoScenes Platform...
[License ] [Info ] Loaded license: PicoScenes License Plan -- Free License (PSLP-FL)
[Platform] [Info ] PicoScenes Platform version: 2025.0922.2120
[Frontend] [Info ]     PicoScenes Driver (picoscenes-driver-modules-6.5.0-15-generic) is installed. [OK]
[Frontend] [Info ]     Current Linux kernel version: 6.5.0-15-generic. [OK]
[Frontend] [Info ]     PicoScenes Driver (ver: 20240210) is activated. [OK]
[Frontend] [Info ]     1 compatible Wi-Fi COTS NICs are found.
[Platform] [Info ]  *******  PicoScenes Platform has been launched successfully. You can press <Ctrl+C> to exit at any time.  *******
```

Press `Ctrl + C` to exit.

---

## 2. Installing and Verifying Relevant Drivers

The PicoScenes driver for Intel AX200/AX210 is packaged as:

- `picoscenes-driver-modules-$(uname -r)`

Install / re‑install it explicitly if needed:

```bash
sudo apt install -y picoscenes-driver-modules-$(uname -r)
```

To confirm that the AX200 kernel module is in use:

```bash
lspci -nnk | grep -A3 -i network
```

Expected output (abridged):

```text
04:00.0 Network controller [0280]: Intel Corporation Wi-Fi 6 AX200 [8086:2723] (rev 1a)
    Subsystem: Intel Corporation Wi-Fi 6 AX200 [8086:0084]
    Kernel driver in use: iwlwifi
    Kernel modules: iwlwifi
```

### 2.1 Loading the PicoScenes‑enabled iwlwifi module

For some kernels, you explicitly swap the stock `iwlwifi` with the PicoScenes one:

```bash
sudo modprobe -r iwlwifi
sudo modprobe iwlwifi-picoscenes
```

- If `iwlwifi-picoscenes` **loads successfully**, you are ready for CSI.
- If you see:

  ```text
  modprobe: FATAL: Module iwlwifi-picoscenes not found in directory /lib/modules/...
  ```

  then the driver package is either **not installed for this kernel** or the kernel is not supported. In that case, recheck the installed package and kernel version (see troubleshooting).

---

## 3. Troubleshooting Installation Problems

This section covers **common errors** seen during install / first launch and how to fix them.

---

### 3.1 Scheduled crash on very first launch

Symptom:

```text
[Platform] [Warn ] PicoScenes crashes at the very early stage due to the following error:
------------------------------------
Don't worry! ^_^ This is a scheduled crash if you have just installed PicoScenes.
------------------------------------
You may seek technical support by:
1. viewing the Troubleshooting page ...
3. run PicoScenes repair script "RepairPicoScenes"
```

✅ This is expected the **first time**. Simply:

1. Run the repair script (if available) – in a terminal:
   ```bash
   RepairPicoScenes
   ```
2. Then re‑launch:
   ```bash
   PicoScenes
   ```

After this, you should see a normal startup with NIC detection.

---

### 3.2 PicoScenes build expired

Symptom when launching `PicoScenes`:

```text
[License ] [Info ] Current build will expire in -9 days.
[Platform] [Warn ] Current PicoScenes build (2025.0922.2120) is expired. You should upgrade PicoScenes to the latest version.
```

Solution: **Upgrade PicoScenes** (see Section 4). In practice, it still runs, but upgrading is strongly recommended.

---

### 3.3 “No compatible Wi‑Fi COTS NIC is found”

Symptom in PicoScenes log:

```text
[Frontend] [Warn ]     No compatible Wi-Fi COTS NIC is found.
```

Possible causes:
- AX200/AX210 is missing / disabled in BIOS
- Driver not loaded (`iwlwifi` / `iwlwifi-picoscenes`)
- Unsupported kernel or missing PicoScenes driver modules

Steps to fix:

1. Verify the NIC exists:
   ```bash
   lspci -nnk | grep -A3 -i network
   ```

2. Verify Wi‑Fi device state:
   ```bash
   iw dev
   ```

   - If nothing is printed → kernel driver did not create an interface.

3. Reload the driver:
   ```bash
   sudo modprobe -r iwlwifi
   sudo modprobe iwlwifi       # or iwlwifi-picoscenes if supported
   ```

4. Re‑check:
   ```bash
   iw dev
   array_status
   ```

   Expected `array_status` output:

   ```text
   ----------------------
   Device Status of Wi-Fi NIC array "all":
   PhyPath DEV   PHY  [MON] DEV_MacAddr      [MON_MacAddr] [CF_Control] [BW] [CF] ProductName
   4       wlp4s0 phy0       Wi-Fi 6 AX200
   ----------------------
   ```

Once you see your AX200 with a valid `PhyPath` (e.g., `4`), you can proceed.

---

### 3.4 “Module iwlwifi-picoscenes not found”

Symptom:

```bash
sudo modprobe iwlwifi-picoscenes
# -> modprobe: FATAL: Module iwlwifi-picoscenes not found in directory /lib/modules/6.5.0-15-generic
```

This means **no PicoScenes‑patched iwlwifi** exists for this kernel. Fix:

1. Ensure the driver package is installed for your kernel:
   ```bash
   sudo apt install -y picoscenes-driver-modules-$(uname -r)
   ```

2. If that still fails, you may need to move to a **supported kernel** (e.g., 5.15.x) or check PicoScenes documentation for kernel support.

---

### 3.5 Checking PicoScenes messages in dmesg

If PicoScenes behaves strangely (segfaults, crashes), inspect dmesg:

```bash
sudo dmesg | grep -i picoscenes
```

You may see entries such as:

```text
PicoScenes[21977]: segfault at 18 ip ... in libc.so.6
```

or a lot of **AppArmor DENIED** messages for `/usr/local/PicoScenes/pslib/...`. These usually do not prevent basic CSI logging, but if the program keeps crashing, perform a **full repair** as in Section 5.

---

## 4. How to Update PicoScenes

To update PicoScenes to the newest build from the same repository:

```bash
sudo apt update
sudo apt install -y picoscenes-platform picoscenes-driver-modules-$(uname -r)
```

This will:
- Refresh package lists
- Upgrade `picoscenes-platform` to the newest available version
- Ensure the driver modules match your current kernel

After updating, verify again:

```bash
dpkg -l | grep picoscenes
PicoScenes
```

Make sure PicoScenes starts and lists your AX200 as a compatible NIC.

---

## 5. Repairing a Broken PicoScenes Pipeline (Full Clean Reinstall)

If PicoScenes is badly broken (e.g., repeated crashes, corrupted installation, mismatched drivers), use this **clean purge + reinstall** sequence.

### 5.1 Purge PicoScenes packages

```bash
sudo dpkg --purge       picoscenes-platform       picoscenes-all       picoscenes-driver-modules-$(uname -r)       picoscenes-plugins-demo-echoprobe-forwarder
```

Expected output (abridged):

```text
Removing picoscenes-platform (2025.0922.2120) ...
Purging configuration files for picoscenes-platform ...
Removing picoscenes-all (20200715) ...
Removing picoscenes-driver-modules-6.5.0-15-generic (20240210) ...
dpkg: warning: ignoring request to remove picoscenes-plugins-demo-echoprobe-forwarder which isn't installed
```

---

### 5.2 Remove leftover directories

```bash
sudo rm -rf /usr/local/PicoScenes
```

---

### 5.3 Fix broken dependencies and clean APT

```bash
sudo apt --fix-broken install -y
sudo apt autoremove -y
sudo apt clean
```

These ensure no dangling dependencies remain.

---

### 5.4 Remove old PicoScenes repo entries (if needed)

If you were using an old `.list` file name:

```bash
sudo rm -f /etc/apt/sources.list.d/picoscenes.list
sudo apt update
```

Confirm the active PicoScenes entries (for reference only):

```bash
grep -R "PicoScenes" /etc/apt/sources.list.d
```

Example output:

```text
/etc/apt/sources.list.d/archive_uri-https_ps2204_zpj_io_picoscenes_22_04_x86_64-jammy.list:deb [arch=amd64] https://ps2204.zpj.io/PicoScenes/22.04/x86_64 stable avx2 main
```

---

### 5.5 Reinstall PicoScenes cleanly

1. Ensure the repository is present (Section 1.2).
2. Install the platform:

   ```bash
   sudo apt install -y picoscenes-platform
   ```

3. Install the driver for your current kernel:

   ```bash
   sudo apt install -y picoscenes-driver-modules-$(uname -r)
   ```

4. Verify:

   ```bash
   dpkg -l | grep picoscenes
   PicoScenes
   ```

You should once again see PicoScenes start with **1 compatible Wi‑Fi COTS NIC** detected.

---

## 6. Turning Off Wi‑Fi and Preparing Monitor Mode

For **CSI collection in monitor mode**, you must:

1. Disconnect from any Wi‑Fi networks
2. Turn off NetworkManager Wi‑Fi control
3. Ensure RF‑kill is unblocked
4. Prepare the NIC using `array_prepare_for_picoscenes`

---

### 6.1 Install extra utilities (recommended)

These tools are useful for CPU governor, interface management, and older networking commands:

```bash
sudo apt install -y linux-tools-common linux-tools-generic
sudo apt install -y net-tools
sudo apt install -y cpufrequtils
```

---

### 6.2 Create a CSI data directory (optional but recommended)

```bash
sudo mkdir -p /mnt/psrd
sudo chmod 777 /mnt/psrd
sudo chown "$USER:$USER" /mnt/psrd
ls -ld /mnt/psrd
```

Expected output:

```text
drwxrwxrwx 2 obak-b obak-b 100 Dec  3 00:00 /mnt/psrd
```

You can choose to `cd /mnt/psrd` before logging CSI so all `.csi` files are stored there.

---

### 6.3 Disconnect and disable Wi‑Fi

Replace `wlp4s0` with your own Wi‑Fi interface.

```bash
sudo nmcli dev disconnect wlp4s0
sudo nmcli radio wifi off
sudo rfkill unblock wifi
rfkill list
```

Expected `rfkill list` output:

```text
0: hci0: Bluetooth
    Soft blocked: no
    Hard blocked: no
4: phy0: Wireless LAN
    Soft blocked: no
    Hard blocked: no
```

At this point, NetworkManager is no longer managing your Wi‑Fi NIC, and RF‑kill is unblocked.

---

### 6.4 Identify the NIC and its PhyPath ID

```bash
array_status
```

Expected example:

```text
----------------------
Device Status of Wi-Fi NIC array "all":
PhyPath DEV   PHY  [MON] DEV_MacAddr      [MON_MacAddr] [CF_Control] [BW] [CF] ProductName
4       wlp4s0 phy0                                Wi-Fi 6 AX200
----------------------
```

Here, **4** is the PhyPath ID (we will use it in later commands).

You can also map the device to PHY:

```bash
ANY2PHY 4
```

Expected output:

```text
phy0
```

---

### 6.5 Prepare NIC for PicoScenes (monitor mode)

You must tell PicoScenes which channel and bandwidth to use. Example for 5 GHz, channel 149, 80 MHz bandwidth, center frequency 5775 MHz:

```bash
sudo array_prepare_for_picoscenes 4 "5745 80 5775"
```

Expected output (abridged):

```text
Attempt changing CPU frequency governor to performance ...
Un-managing NICs from Network-Manager ...
Unlocking RF-Kill...
Disabling power management...
Disconnecting Wi-Fi...
Stopping monitor interfaces...
Changing MAC address...
Adding monitor interfaces...
Adding a monitor interface for phy0 (phy0), named mon4 ...
Changing working frequency to 5745 80 5775 ...
Preparation is done.
----------------------
Device Status of Wi-Fi NIC array "all":
PhyPath DEV   PHY  [MON] DEV_MacAddr      [MON_MacAddr] [CF_Control] [BW] [CF] ProductName
4       wlp4s0 phy0 mon4 00:16:ea:12:34:56 ec:4c:8c:52:1f:7f 5745 80 5775 Wi-Fi 6 AX200 
----------------------
```

Check with `iw dev`:

```bash
iw dev
```

Expected output (abridged):

```text
phy#0
    Interface mon4
        ifindex 9
        wdev 0x2
        addr ec:4c:8c:52:1f:7f
        type monitor
        channel 149 (5745 MHz), width: 80 MHz, center1: 5775 MHz
    Interface wlp4s0
        ifindex 8
        wdev 0x1
        addr 00:16:ea:12:34:56
        type managed
```

Now the NIC is ready to **passively capture CSI** on this channel.

---

## 7. Collecting CSI with PicoScenes

There are two main ways you will typically use AX200/AX210 CSI with PicoScenes:

1. **Associated CSI** from your AP (you are connected to the AP)
2. **Fully passive CSI in monitor mode** (you are not associated, just listening)

The steps below follow the official “CSI Measurement using PicoScenes” flow and your specific command history.

---

### 7.1 CSI from associated Wi‑Fi AP (simple logger)

1. Make sure your AX200 is associated with your AP (normal Wi‑Fi connection).
2. Find the PhyPath ID:
   ```bash
   array_status
   ```
   Assume it is `3` for this example.

3. Start CSI logging (with live plot):

   ```bash
   PicoScenes "-d debug -i 3 --mode logger --plot"
   ```

   Interpretation of options:

   - `-d debug` → verbose debug logging
   - `-i 3` → use device with ID 3
   - `--mode logger` → enable CSI logger mode
   - `--plot` → live CSI plot window

4. Generate traffic (e.g., `ping`, `iperf3`, normal browsing) so that AX200 sees frames.
5. When done, press **Ctrl + C** in the PicoScenes terminal.

A `.csi` file will be created in the current working directory, named like:

```text
rx_<Id>_<Time>.csi
```

Example (from your session):

```bash
ls -lh rx_4_251203_011329.csi
```

Expected output:

```text
-rw-rw-r-- 1 obak-b obak-b 494M Dec  3 01:16 rx_4_251203_011329.csi
```

---

### 7.2 Fully passive CSI in monitor mode (AX200/AX210)

This uses the **monitor mode + logger** setup from Section 6.

1. Ensure monitor mode is prepared (Section 6.3–6.5). You should have `mon4` and `wlp4s0`, with `mon4` in monitor mode on the desired channel.

2. Start PicoScenes CSI logger on the PhyPath (e.g., `4`):

   ```bash
   PicoScenes "-d debug -i 4 --mode logger --plot"
   ```

   Same option meaning as above.

3. While PicoScenes is running, **any Wi‑Fi traffic** on that channel will generate CSI: beacons, data frames, etc.

4. When you have collected enough CSI, press **Ctrl + C** to stop.

5. You should now see a `.csi` file in your working directory, e.g.:

   ```bash
   ls -lh rx_4_*.csi
   ```

---

### 7.3 Extra logger options (optional)

The PicoScenes CLI also supports additional logger options; for example:

- Log CSI to a `.psdb` file:
  ```bash
  sudo PicoScenes "-mode logger -i phy0 --CSI 1 --log csi_log.psdb"
  ```

- Inspect CSI from a log file in **offline** mode:
  ```bash
  PicoScenes "-mode offline -i csi_log.psdb --plot"
  ```

- If CSI does not appear as expected, increase debug level:
  ```bash
  sudo PicoScenes "-mode logger -i phy0 --debug 4"
  ```

For most workflows, the simple `--mode logger --plot` with `.csi` output is enough.

---

### 7.4 Restoring Wi‑Fi after CSI collection

After you are done collecting CSI in monitor mode, you should restore normal Wi‑Fi operation.

Replace interface names with your own (`mon4`, `wlp4s0`, `Sony_Home`, etc.).

```bash
# Remove monitor interface
sudo iw dev mon4 del

# Re‑enable Wi‑Fi in NetworkManager
sudo nmcli radio wifi on
sudo systemctl restart NetworkManager

# Bring managed interface up
sudo ip link set wlp4s0 up

# Scan and connect to AP
nmcli dev wifi list
nmcli dev wifi connect "Sony_Home" password "torbaap@2024"
```

Your Wi‑Fi should now be back to normal.

---

## 8. Opening and Parsing `.csi` in MATLAB

To work with PicoScenes `.csi` files, you need the **PicoScenes MATLAB Toolbox**.

### 8.1 Prepare MATLAB toolbox

1. Download / clone the PicoScenes MATLAB toolbox and place it under, e.g.:
   ```text
   /home/obak-b/PicoScenes-MATLAB-Toolbox-Core
   ```

2. In MATLAB:
   - Add this folder to the MATLAB path (`Home → Set Path` or using `addpath`)
   - Or `cd` into that directory:

     ```matlab
     cd('/home/obak-b/PicoScenes-MATLAB-Toolbox-Core')
     ```

3. Compile the `.csi` parser:

   ```matlab
   >> compileRXSParser
   ```

   Expected MATLAB output:

   ```text
   Compiling the MATLAB parser for PicoScenes .csi file ...
   Compilation done!
   ```

---

### 8.2 Parse the `.csi` file

Suppose your CSI file is `/home/obak-b/rx_4_251203_020130.csi`.

From MATLAB **Command Window**:

```matlab
>> open("/home/obak-b/rx_4_251203_020130.csi")
```

or equivalently:

```matlab
>> uiimport("/home/obak-b/rx_4_251203_020130.csi")
```

Expected (abridged) output:

```text
Start parsing PicoScenes CSI file: rx_4_251203_020130.csi
182197 PicoScenes frames are decoded in 23.704 seconds.
rx_4_251203_020130
```

After parsing, a MATLAB variable named like `rx_4_251203_020130` will appear in your workspace. This struct/variable contains decoded CSI frames and associated metadata for further processing, plotting, or export.

> You can also simply **drag and drop** the `.csi` file from your file manager into the MATLAB Command Window; MATLAB will call the toolbox parser automatically (once correctly set up).

---

## 9. Quick End‑to‑End Summary

Below is a condensed “single‑shot” pipeline (you're encouraged to adapt it to your own paths and IDs):

```bash
# 1. Install
sudo apt update
sudo apt install -y iw wireless-tools default-jre
echo "deb [arch=amd64] https://ps2204.zpj.io/PicoScenes/22.04/x86_64 stable avx2 main"       | sudo tee /etc/apt/sources.list.d/picoscenes.list
sudo apt update
sudo apt install -y picoscenes-platform picoscenes-driver-modules-$(uname -r)

# 2. Verify NIC
lspci -nnk | grep -A3 -i network
array_status

# 3. Prepare directory
sudo mkdir -p /mnt/psrd
sudo chmod 777 /mnt/psrd
sudo chown "$USER:$USER" /mnt/psrd
cd /mnt/psrd

# 4. Disable Wi‑Fi & prepare monitor mode (example PhyPath=4)
sudo nmcli dev disconnect wlp4s0
sudo nmcli radio wifi off
sudo rfkill unblock wifi
sudo array_prepare_for_picoscenes 4 "5745 80 5775"
iw dev

# 5. Start CSI logger
PicoScenes "-d debug -i 4 --mode logger --plot"
# (Generate traffic; wait; then Ctrl + C)

# 6. Check CSI file
ls -lh rx_4_*.csi

# 7. Restore Wi‑Fi
sudo iw dev mon4 del
sudo nmcli radio wifi on
sudo systemctl restart NetworkManager
sudo ip link set wlp4s0 up
nmcli dev wifi list
nmcli dev wifi connect "Sony_Home" password "torbaap@2024"
```

Then move to MATLAB and parse the `.csi` file as in Section 8.

---

If you follow this README top‑to‑bottom, you will have a **complete, reproducible pipeline** from a fresh Ubuntu 22.04 install to **working AX200/AX210 CSI collection and MATLAB analysis**.
