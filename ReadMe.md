2️⃣ Install PicoScenes Platform & Drivers
 
```bash
sudo PicoScenesMaintainer
```

Select:
1 → Install / Upgrade PicoScenes


Then:
```bash
sudo reboot
```

3️⃣ Disable Secure Boot (MANDATORY)
```bash
sudo mokutil --disable-validation
sudo reboot
```

During the MOK screen:
✔ Disable Secure Boot
✔ Enter BIOS password
✔ Reboot again

Verify:

```bash 
sudo dmesg | grep -i secure
```

4️⃣ Ensure Correct Kernel Installed

Check:
```bash
uname -r
```

If not 6.5.0-15-generic:
```bash
sudo apt install linux-image-6.5.0-15-generic linux-headers-6.5.0-15-generic
sudo reboot
```

Prevent future breaks:
```bash
sudo apt-mark hold linux-image-6.5.0-15-generic linux-headers-6.5.0-15-generic
```

5️⃣ Install Wi-Fi Tools
```bash 
sudo apt install iw wireless-tools default-jre -y
```
6️⃣ Verify Driver + Device

```bash
sudo modprobe -r iwlwifi
sudo modprobe iwlwifi-picoscenes
lspci -nnk | grep -A3 -i network
```

Expected:

Kernel driver in use: iwlwifi-picoscenes


Check PHY mapping:
```bash 
array_status
ANY2PHY 4
iw dev
```
7️⃣ Ensure Kernel Boots by Default
```bash
sudo sed -i 's/^GRUB_DEFAULT=.*/GRUB_DEFAULT="Advanced options for Ubuntu>Ubuntu, with Linux 6.5.0-15-generic"/' /etc/default/grub
sudo update-grub
sudo reboot
```

Confirm:
```bash
uname -r
```

### 🎯 Troubleshooting: Issue	Solution
## “No compatible Wi-Fi COTS NICs found”	Wrong kernel or Secure Boot enabled
```bash
iwlwifi-picoscenes missing	Reinstall picoscenes-driver-modules-$(uname -r)
```
## iw: command not found	sudo apt install iw wireless-tools
Wrong kernel keeps booting	Reset GRUB default (section 7)
MOK screen never appeared	Repeat secure boot disable + reinstall kernel
✔ Successful Installation Checklist
 
Kernel: 6.5.0-15-generic ✔
Driver: iwlwifi-picoscenes ✔
1 compatible Wi-Fi COTS NIC found ✔
ANY2PHY 4 → phy0 ✔
BFI capture ready 🚀


Next step?
➡ Enable Monitor Mode
➡ iperf3 + BFI Logging
➡ Gesture Dataset Pipeline
---

## What’s Included

| Item                                 | Included |
| ------------------------------------ | :------: |
| Clean install steps (correct order)  |     ✔    |
| Driver activation & verification     |     ✔    |
| Kernel setup and secure boot disable |     ✔    |
| GRUB config for auto-boot            |     ✔    |
| Troubleshooting section              |     ✔    |
| Fully compatible with AX200          |     ✔    |

This is now the **gold standard reference** for reliably installing PicoScenes! 💪


### Rough Sequence
```bash
cd ~/Downloads/picoscenes
sudo dpkg -i picoscenes-source-updater.deb [Or Install via GDebi; it works better on that]
sudo apt --fix-broken install -y
MaintainPicoScenes [Run the installer]
1 [1 selects the installer to install PicoScenes and all its dependencies]
sudo reboot
sudo dmesg | grep -i picoscenes
sudo lspci -nnk | grep -A3 -i network
sudo rm /etc/apt/sources.list.d/picoscenes.list
sudo apt update
sudo apt install picoscenes-platform
sudo apt install picoscenes-driver-modules-$(uname -r)
dpkg -l | grep picoscenes
sudo dmesg | grep -i picoscenes
lspci -nnk | grep -A3 -i network
dpkg --list | grep linux-image
sudo dmesg | grep -i picoscenes
lspci -nnk | grep -A3 -i network
PicoScenes
sudo apt-mark hold linux-image-6.5.0-15-generic linux-headers-6.5.0-15-generic
sudo apt update
sudo apt install linux-image-6.5.0-15-generic linux-headers-6.5.0-15-generic
sudo apt install linux-image-lowlatency-hwe-22.04 linux-headers-6.5.0-15-generic
sudo reboot
sudo mokutil --disable-validation
sudo reboot
During reboot → a blue MOK screen will appear:

► Choose: Disable Secure Boot
► Enter your BIOS password
► Reboot again after confirmation
sudo dmesg | grep -i secure
sudo modprobe -r iwlwifi
sudo modprobe iwlwifi-picoscenes
lspci -nnk | grep -A3 -i network
sudo apt install default-jre
array_status
ANY2PHY 4
sudo rm /etc/apt/sources.list.d/picoscenes.list
sudo apt update
grep -r "picoscenes" /etc/apt/sources.list.d
sudo apt search picoscenes-driver
sudo apt install iw wireless-tools
iw dev
array_status
ANY2PHY 4
grep -n "menuentry '" /boot/grub/grub.cfg
sudo nano /etc/default/grub
sudo sed -i 's/^GRUB_DEFAULT=.*/GRUB_DEFAULT="Advanced options for Ubuntu>Ubuntu, with Linux 6.5.0-15-generic"/' /etc/default/grub
sudo update-grub
sudo reboot
```

---
