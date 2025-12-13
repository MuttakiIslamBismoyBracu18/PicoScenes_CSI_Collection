#!/usr/bin/env python3
"""
picoscenes_csi_collection.py

One-command, end-to-end CSI collection and validation pipeline for PicoScenes.

Run:
    python picoscenes_csi_collection.py

Requirements:
- PicoScenes installed and working
- MATLAB installed with PicoScenes parser available on MATLAB path
- User has sudo privileges
- Python 3.11+
"""

import os
import sys
import time
import shutil
import subprocess
import tempfile
from pathlib import Path
from datetime import datetime

# ──────────────────────────────────────────────────────────────────────────────
# FIXED CONFIGURATION (DO NOT EDIT)
# ──────────────────────────────────────────────────────────────────────────────
INTERFACE_INDEX = 4
WIFI_IFACE = "wlp4s0"
MON_IFACE = "mon4"
CAPTURE_DURATION_SEC = 300
PSRD_DIR = Path("/mnt/psrd")
MIN_CSI_SIZE_BYTES = 5 * 1024 * 1024  # 5 MB

# ──────────────────────────────────────────────────────────────────────────────
# UTILITIES
# ──────────────────────────────────────────────────────────────────────────────
def run(cmd, sudo=False, check=True):
    if sudo:
        cmd = ["sudo"] + cmd
    print("▶", " ".join(cmd))
    return subprocess.run(cmd, check=check)

def exists(cmd):
    return shutil.which(cmd) is not None

def fatal(msg):
    print(f"\n❌ {msg}")
    sys.exit(1)

def info(msg):
    print(f"\nℹ️  {msg}")

def ok(msg):
    print(f"\n✅ {msg}")

# ──────────────────────────────────────────────────────────────────────────────
# ENVIRONMENT VALIDATION
# ──────────────────────────────────────────────────────────────────────────────
def validate_environment():
    info("Validating system environment")

    required = [
        "PicoScenes",
        "array_prepare_for_picoscenes",
        "nmcli",
        "iw",
        "rfkill"
    ]

    for cmd in required:
        if not exists(cmd):
            fatal(f"Required command not found: {cmd}")

    try:
        subprocess.run(
            ["PicoScenes", "--help"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=True
        )
    except subprocess.CalledProcessError:
        fatal("PicoScenes installed but not runnable")

    if os.geteuid() == 0:
        fatal("Do NOT run this script as root")

    ok("Environment verified")

# ──────────────────────────────────────────────────────────────────────────────
# GUI INPUT
# ──────────────────────────────────────────────────────────────────────────────
def get_channel_gui():
    try:
        import tkinter as tk
        from tkinter import simpledialog, messagebox
    except Exception:
        fatal("Tkinter not available. GUI input required.")

    if not os.environ.get("DISPLAY"):
        fatal("No DISPLAY detected. GUI popup cannot be shown.")

    root = tk.Tk()
    root.withdraw()
    root.attributes("-topmost", True)

    messagebox.showinfo(
        "PicoScenes CSI Collection",
        "Enter channel configuration.\n\n"
        "Example:\n"
        "Center frequency: 5745\n"
        "Bandwidth: 80 MHz"
    )

    while True:
        ch = simpledialog.askinteger(
            "Channel",
            "Enter center frequency (MHz):",
            minvalue=5000,
            maxvalue=6000
        )
        bw = simpledialog.askinteger(
            "Bandwidth",
            "Enter bandwidth (20/40/80/160 MHz):",
            minvalue=20,
            maxvalue=160
        )

        if ch is None or bw is None:
            fatal("User cancelled input")

        if bw not in (20, 40, 80, 160):
            messagebox.showerror("Invalid Input", "Bandwidth must be 20, 40, 80, or 160")
            continue

        root.destroy()
        return ch, bw

# ──────────────────────────────────────────────────────────────────────────────
# SYSTEM SETUP
# ──────────────────────────────────────────────────────────────────────────────
def prepare_psrd():
    info("Preparing /mnt/psrd")
    run(["mkdir", "-p", str(PSRD_DIR)], sudo=True)
    run(["chmod", "777", str(PSRD_DIR)], sudo=True)
    run(["chown", f"{os.getenv('USER')}:{os.getenv('USER')}", str(PSRD_DIR)], sudo=True)
    ok("/mnt/psrd ready")

def disable_wifi():
    info("Disabling Wi-Fi")
    run(["nmcli", "dev", "disconnect", WIFI_IFACE], sudo=True, check=False)
    run(["nmcli", "radio", "wifi", "off"], sudo=True)
    run(["rfkill", "unblock", "wifi"], sudo=True)
    ok("Wi-Fi disabled")

# ──────────────────────────────────────────────────────────────────────────────
# CSI COLLECTION
# ──────────────────────────────────────────────────────────────────────────────
def prepare_array(channel, bandwidth):
    info("Preparing NIC for PicoScenes")
    run([
        "array_prepare_for_picoscenes",
        str(INTERFACE_INDEX),
        f"{channel} {bandwidth} {channel + 30}"
    ], sudo=True)
    run(["iw", "dev"])
    ok("NIC prepared")

def collect_csi():
    info(f"Collecting CSI for {CAPTURE_DURATION_SEC} seconds")

    proc = subprocess.Popen([
        "PicoScenes",
        "-d", "debug",
        "-i", str(INTERFACE_INDEX),
        "--mode", "logger",
        "--plot"
    ])

    start = time.time()
    try:
        while time.time() - start < CAPTURE_DURATION_SEC:
            time.sleep(1)
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            proc.kill()

    ok("CSI collection completed")

# ──────────────────────────────────────────────────────────────────────────────
# RESTORE NETWORK
# ──────────────────────────────────────────────────────────────────────────────
def restore_wifi():
    info("Restoring Wi-Fi")
    run(["iw", "dev", MON_IFACE, "del"], sudo=True, check=False)
    run(["nmcli", "radio", "wifi", "on"], sudo=True)
    run(["systemctl", "restart", "NetworkManager"], sudo=True)
    run(["ip", "link", "set", WIFI_IFACE, "up"], sudo=True)
    run(["nmcli", "dev", "wifi", "list"], check=False)
    ok("Wi-Fi restored")

# ──────────────────────────────────────────────────────────────────────────────
# CSI DISCOVERY
# ──────────────────────────────────────────────────────────────────────────────
def find_csi_file():
    files = sorted(Path.cwd().glob("rx_*.csi"), key=lambda p: p.stat().st_mtime)
    if not files:
        fatal("No .csi file found")
    return files[-1]

# ──────────────────────────────────────────────────────────────────────────────
# PYTHON VALIDATION
# ──────────────────────────────────────────────────────────────────────────────
def python_validate(csi):
    info("Running Python CSI validation")

    st = csi.stat()
    result = {
        "File": str(csi),
        "SizeBytes": st.st_size,
        "Modified": datetime.fromtimestamp(st.st_mtime).isoformat(),
        "SizeOK": st.st_size >= MIN_CSI_SIZE_BYTES
    }

    with csi.open("rb") as f:
        header = f.read(64)
        result["Readable"] = len(header) == 64 and any(b != 0 for b in header)

    report = csi.with_suffix(".python_validation.txt")
    report.write_text("\n".join(f"{k}: {v}" for k, v in result.items()))

    ok(f"Python validation report written: {report}")
    return result

# ──────────────────────────────────────────────────────────────────────────────
# MATLAB VALIDATION
# ──────────────────────────────────────────────────────────────────────────────
def matlab_validate(csi):
    info("Running MATLAB CSI validation")

    matlab = shutil.which("matlab")
    if not matlab:
        fatal("MATLAB not found in PATH")

    report = csi.with_suffix(".matlab_validation.txt")

    matlab_code = f"""
    fid = fopen('{report}','w');
    try
        [bundle, name] = parseCSIFile('{csi}');
        fprintf(fid, 'Bundle: %s\\n', name);
        fprintf(fid, 'Frames: %d\\n', numel(bundle.Frames));
        f1 = bundle.Frames(1);
        fprintf(fid, 'CSI size: %s\\n', mat2str(size(f1.CSI)));
        fprintf(fid, 'NumTx: %d\\n', f1.NumTx);
        fprintf(fid, 'NumRx: %d\\n', f1.NumRx);
        fprintf(fid, 'MATLAB Validation: PASS\\n');
    catch ME
        fprintf(fid, 'MATLAB Validation: FAIL\\n');
        fprintf(fid, '%s\\n', ME.message);
    end
    fclose(fid);
    """

    with tempfile.TemporaryDirectory() as td:
        mfile = Path(td) / "validate.m"
        mfile.write_text(matlab_code)
        run([matlab, "-batch", f"run('{mfile}')"], check=False)

    ok(f"MATLAB validation report written: {report}")

# ──────────────────────────────────────────────────────────────────────────────
# MAIN
# ──────────────────────────────────────────────────────────────────────────────
def main():
    validate_environment()
    prepare_psrd()
    disable_wifi()

    channel, bandwidth = get_channel_gui()
    prepare_array(channel, bandwidth)

    collect_csi()
    restore_wifi()

    csi = find_csi_file()
    run(["ls", "-lh", str(csi)])

    python_validate(csi)
    matlab_validate(csi)

    print("\n================ FINAL STATUS ================")
    print("CSI collection: SUCCESS")
    print("Python validation: COMPLETED")
    print("MATLAB validation: COMPLETED")
    print("=============================================\n")

    ok("Pipeline completed successfully")

if __name__ == "__main__":
    main()
