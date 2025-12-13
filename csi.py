#!/usr/bin/env python3
"""
csi.py  —  Inspect a PicoScenes .csi file (Python version of mac.m)

Requires:
    pip install numpy matplotlib
    PicoScenes Python toolbox installed (module: picoscenes)

Usage:
    python csi.py                 # opens file dialog
    python csi.py path/to/file.csi
"""

import sys
import os

import numpy as np
import matplotlib.pyplot as plt

import tkinter as tk
from tkinter import filedialog, messagebox

from picoscenes import Picoscenes


# ----------------- helpers ----------------- #

def pick_file():
    root = tk.Tk()
    root.withdraw()
    root.update()
    path = filedialog.askopenfilename(
        title="Select PicoScenes .csi file",
        filetypes=[("PicoScenes CSI", "*.csi"), ("All files", "*.*")]
    )
    root.destroy()
    if not path:
        raise SystemExit("No file selected.")
    return path


def mac_to_str(field):
    """
    Convert a 6-byte address (list/ndarray/etc.) to 'AA:BB:CC:DD:EE:FF'.
    Returns None if it cannot be interpreted as a MAC.
    """
    if field is None:
        return None
    try:
        arr = np.array(field, dtype=np.uint8).flatten()
    except Exception:
        return None

    if arr.size < 6:
        return None

    vals = [int(x) & 0xFF for x in arr[:6]]
    return ":".join(f"{b:02X}" for b in vals)


def get_timestamp(rx_basic):
    """
    Return one timestamp in microseconds from RxSBasic dict.
    Tries several key spellings (Timestamp/SystemTime).
    """
    if not isinstance(rx_basic, dict):
        return None

    for key in ("Timestamp", "timestamp", "SystemTime", "systemTime"):
        if key in rx_basic:
            arr = np.array(rx_basic[key]).flatten()
            if arr.size:
                return int(arr[0])
    return None


# ----------------- main analysis ----------------- #

def analyze_csi(path):
    print(f"\nOpening file: {path}")
    print(f"File size: {os.path.getsize(path) / (1024 * 1024):.2f} MB\n")

    ps = Picoscenes(path)
    frames = ps.raw        # list[dict], ALL frames

    # CSI-bearing frames only (for CSI stats)
    csi_frames = [f for f in frames if "CSI" in f]
    num_csi = len(csi_frames)

    if num_csi == 0:
        print("No frames with 'CSI' field found in this file.")
        return

    # ---------- MAC extraction: StandardHeader.Addr1/2/3 over ALL frames ----------
    all_macs = set()
    tx_primary = None
    rx_primary = None

    for f in frames:
        sh = f.get("StandardHeader") or f.get("standardHeader")
        if not isinstance(sh, dict):
            continue

        # Try both capitalizations for the fields
        A1 = sh.get("Addr1") or sh.get("addr1")   # Receiver
        A2 = sh.get("Addr2") or sh.get("addr2")   # Transmitter
        A3 = sh.get("Addr3") or sh.get("addr3")   # BSSID / routing address

        ADDRS = [A1, A2, A3]

        # Convert and filter zeros/broadcast for unique MACs
        for addr in ADDRS:
            mac = mac_to_str(addr)
            if mac is None:
                continue
            if mac in ("00:00:00:00:00:00", "FF:FF:FF:FF:FF:FF"):
                continue
            all_macs.add(mac)

        # Find FIRST non-zero, non-broadcast TX/RX pair
        if tx_primary is None and A1 is not None and A2 is not None:
            rx_mac = mac_to_str(A1)
            tx_mac = mac_to_str(A2)

            if (
                rx_mac not in (None, "00:00:00:00:00:00", "FF:FF:FF:FF:FF:FF")
                and tx_mac not in (None, "00:00:00:00:00:00", "FF:FF:FF:FF:FF:FF")
            ):
                tx_primary, rx_primary = tx_mac, rx_mac

    # ---------- timestamps & CSI rate (only CSI frames) ----------
    timestamps = []
    for f in csi_frames:
        rx_basic = f.get("RxSBasic") or f.get("rxSBasic")
        ts = get_timestamp(rx_basic)
        if ts is not None:
            timestamps.append(ts)

    time_span_sec = None
    csi_rate = None
    if len(timestamps) >= 2:
        t_min = min(timestamps)
        t_max = max(timestamps)
        time_span_sec = (t_max - t_min) / 1e6   # µs → seconds
        if time_span_sec > 0:
            csi_rate = num_csi / time_span_sec

    # ---------- subcarriers ----------
    csi_block = csi_frames[0]["CSI"]
    num_tones = csi_block.get("NumTones") or csi_block.get("numTones")
    sub_idx = np.array(
        csi_block.get("SubcarrierIndex") or csi_block.get("subcarrierIndex") or []
    ).flatten()
    if sub_idx.size:
        num_sub = sub_idx.size
    else:
        num_sub = num_tones

    # ---------- print summary ----------
    print("====== CSI FILE SUMMARY (Python) ======")
    print(f"Total frames parsed      : {len(frames)}")
    print(f"Frames with CSI          : {num_csi}")
    if time_span_sec is not None:
        print(f"Capture time span        : {time_span_sec:.3f} s")
        if csi_rate is not None:
            print(f"Average CSI rate         : {csi_rate:.2f} packets/s")
    else:
        print("Capture time span        : N/A")
    print(f"Subcarriers per CSI frame: {num_sub}")
    print()

    print("==========================================")
    print("        Unique MAC Addresses Found")
    print("==========================================")
    if all_macs:
        for m in sorted(all_macs):
            print(m)
    else:
        print("<none>")

    print("\n==========================================")
    print("        Primary TX / RX MAC Addresses")
    print("==========================================")
    if tx_primary and rx_primary:
        print(f"Transmitter MAC: {tx_primary}")
        print(f"Receiver MAC:   {rx_primary}")
    else:
        print("Could not determine non-broadcast TX/RX pair.")

    print("\nDone.\n")

    # ---------- optional: CSI timeline plot ----------
    if timestamps:
        ts_sorted = sorted(timestamps)
        t0 = ts_sorted[0]
        t_rel = [(t - t0) / 1e6 for t in ts_sorted]   # seconds
        plt.figure(figsize=(8, 4))
        plt.plot(t_rel, range(1, len(t_rel) + 1))
        plt.xlabel("Time since first CSI frame (s)")
        plt.ylabel("Cumulative CSI packets")
        plt.title("CSI Packet Timeline")
        plt.grid(True)
        plt.tight_layout()
        plt.show()


def main():
    if len(sys.argv) > 1:
        path = sys.argv[1]
    else:
        try:
            path = pick_file()
        except SystemExit as e:
            print(e)
            return

    if not os.path.isfile(path):
        print(f"File not found: {path}")
        return

    try:
        analyze_csi(path)
    except Exception as e:
        try:
            root = tk.Tk()
            root.withdraw()
            messagebox.showerror("Error", f"Failed to parse CSI file:\n{e}")
            root.destroy()
        except Exception:
            pass
        print(f"\nERROR while parsing: {e}")


if __name__ == "__main__":
    main()
