#!/usr/bin/env python3
"""
picoscenes_csi_collection.py

One-command, end-to-end CSI collection and validation pipeline for PicoScenes.

Run:
    python picoscenes_csi_collection.py
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
PSRD_DIR = Path("/mnt/psrd")
MIN_CSI_SIZE_BYTES = 5 * 1024 * 1024  # 5 MB

# Allowed user selections
CONTROL_CHANNELS = [36, 40, 44, 48, 52, 56, 60, 64, 100, 104, 108, 112, 149, 153, 157, 162]
CHANNEL_BANDWIDTHS = [20, 40, 80]
CAPTURE_DURATION_RANGE = (20, 420)

# ──────────────────────────────────────────────────────────────────────────────
# UTILITIES
# ──────────────────────────────────────────────────────────────────────────────
def run(cmd, sudo=False, check=True):
    if sudo:
        cmd = ["sudo"] + cmd
    print("▶", " ".join(cmd))
    return subprocess.run(cmd, check=check)

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

    required = ["PicoScenes", "iw", "rfkill", "nmcli", "array_prepare_for_picoscenes"]
    for cmd in required:
        if shutil.which(cmd) is None:
            fatal(f"Required command not found: {cmd}")

    if os.geteuid() == 0:
        fatal("Do NOT run this script as root")

    ok("Environment validation complete")

# ──────────────────────────────────────────────────────────────────────────────
# GUI INPUT (SINGLE PAGE)
# ──────────────────────────────────────────────────────────────────────────────
def get_gui_config():
    try:
        import tkinter as tk
        from tkinter import ttk, messagebox
    except Exception:
        fatal("Tkinter not available")

    if not os.environ.get("DISPLAY"):
        fatal("No DISPLAY detected")

    root = tk.Tk()
    root.title("PicoScenes CSI Configuration")
    root.geometry("420x300")
    root.resizable(False, False)

    # Variables
    ch_var = tk.IntVar(value=149)
    bw_var = tk.IntVar(value=80)
    dur_var = tk.IntVar(value=300)

    ttk.Label(root, text="Control Channel").pack(pady=5)
    ttk.Combobox(
        root,
        textvariable=ch_var,
        values=CONTROL_CHANNELS,
        state="readonly"
    ).pack()

    ttk.Label(root, text="Channel Bandwidth (MHz)").pack(pady=5)
    ttk.Combobox(
        root,
        textvariable=bw_var,
        values=CHANNEL_BANDWIDTHS,
        state="readonly"
    ).pack()

    ttk.Label(root, text="Capture Duration (seconds)").pack(pady=5)
    ttk.Scale(
        root,
        from_=CAPTURE_DURATION_RANGE[0],
        to=CAPTURE_DURATION_RANGE[1],
        orient="horizontal",
        variable=dur_var
    ).pack(fill="x", padx=20)

    ttk.Label(root, textvariable=dur_var).pack()

    def submit():
        root.destroy()

    ttk.Button(root, text="Start CSI Collection", command=submit).pack(pady=15)

    root.mainloop()

    control_channel = ch_var.get()
    bandwidth = bw_var.get()
    duration = int(dur_var.get())

    # Convert channel → center frequency (MHz)
    center_freq = 5000 + 5 * control_channel

    return center_freq, bandwidth, duration

# ──────────────────────────────────────────────────────────────────────────────
# SYSTEM SETUP
# ──────────────────────────────────────────────────────────────────────────────
def prepare_psrd():
    run(["mkdir", "-p", str(PSRD_DIR)], sudo=True)
    run(["chmod", "777", str(PSRD_DIR)], sudo=True)
    run(["chown", f"{os.getenv('USER')}:{os.getenv('USER')}", str(PSRD_DIR)], sudo=True)
    ok("/mnt/psrd ready")

def disable_wifi():
    run(["nmcli", "dev", "disconnect", WIFI_IFACE], sudo=True, check=False)
    run(["nmcli", "radio", "wifi", "off"], sudo=True)
    run(["rfkill", "unblock", "wifi"], sudo=True)
    ok("Wi-Fi disabled")

# ──────────────────────────────────────────────────────────────────────────────
# CSI COLLECTION
# ──────────────────────────────────────────────────────────────────────────────
def prepare_array(center_freq, bandwidth):
    run([
        "array_prepare_for_picoscenes",
        str(INTERFACE_INDEX),
        f"{center_freq} {bandwidth} {center_freq + 30}"
    ], sudo=True)
    run(["iw", "dev"])
    ok("NIC prepared")

def collect_csi(duration):
    info(f"Collecting CSI for {duration} seconds")

    proc = subprocess.Popen([
        "PicoScenes",
        "-d", "debug",
        "-i", str(INTERFACE_INDEX),
        "--mode", "logger",
        "--plot"
    ])

    start = time.time()
    try:
        while time.time() - start < duration:
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
    run(["iw", "dev", MON_IFACE, "del"], sudo=True, check=False)
    run(["nmcli", "radio", "wifi", "on"], sudo=True)
    run(["systemctl", "restart", "NetworkManager"], sudo=True)
    run(["ip", "link", "set", WIFI_IFACE, "up"], sudo=True)
    ok("Wi-Fi restored")

# ──────────────────────────────────────────────────────────────────────────────
# CSI DISCOVERY + VALIDATION
# ──────────────────────────────────────────────────────────────────────────────
def find_csi_file():
    files = sorted(Path.cwd().glob("rx_*.csi"), key=lambda p: p.stat().st_mtime)
    if not files:
        fatal("No .csi file found")
    return files[-1]

def python_validate(csi):
    st = csi.stat()
    report = csi.with_suffix(".python_validation.txt")
    report.write_text(
        f"File: {csi}\n"
        f"Size: {st.st_size}\n"
        f"Modified: {datetime.fromtimestamp(st.st_mtime)}\n"
    )
    ok("Python validation complete")

def matlab_validate(csi):
    matlab = shutil.which("matlab")
    if not matlab:
        fatal("MATLAB not found")

    report = csi.with_suffix(".matlab_validation.txt")
    code = f"""
    fid=fopen('{report}','w');
    try
        [b,n]=parseCSIFile('{csi}');
        fprintf(fid,'Frames: %d\\n',numel(b.Frames));
        fprintf(fid,'CSI size: %s\\n',mat2str(size(b.Frames(1).CSI)));
        fprintf(fid,'PASS\\n');
    catch ME
        fprintf(fid,'FAIL\\n%s\\n',ME.message);
    end
    fclose(fid);
    """

    with tempfile.TemporaryDirectory() as td:
        m = Path(td) / "v.m"
        m.write_text(code)
        run([matlab, "-batch", f"run('{m}')"], check=False)

    ok("MATLAB validation complete")

# ──────────────────────────────────────────────────────────────────────────────
# MAIN
# ──────────────────────────────────────────────────────────────────────────────
def main():
    validate_environment()
    prepare_psrd()
    disable_wifi()

    center_freq, bandwidth, duration = get_gui_config()
    prepare_array(center_freq, bandwidth)

    collect_csi(duration)
    restore_wifi()

    csi = find_csi_file()
    run(["ls", "-lh", str(csi)])

    python_validate(csi)
    matlab_validate(csi)

    ok("Pipeline completed successfully")

if __name__ == "__main__":
    main()
