#!/usr/bin/env python3
"""
csi_metadata.py — Robust CSI Inspector for PicoScenes .csi files
"""

import sys
import os
import numpy as np
import matplotlib.pyplot as plt
from collections import Counter

import tkinter as tk
from tkinter import filedialog

from picoscenes import Picoscenes


TARGET_TX_MAC = "24:4B:FE:BE:FF:DC"


# -------------------------------------------------------------
#                   FILE PICKER
# -------------------------------------------------------------
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


# -------------------------------------------------------------
#                   MAC UTILITIES
# -------------------------------------------------------------
def mac_to_str(field):
    if field is None:
        return None
    try:
        arr = np.array(field, dtype=np.uint8).flatten()
    except Exception:
        return None
    if arr.size < 6:
        return None
    return ":".join(f"{int(x) & 0xFF:02X}" for x in arr[:6])


def norm_mac(mac):
    if mac is None:
        return None
    return mac.strip().upper()


def is_valid_unicast(mac):
    if mac in (None, "00:00:00:00:00:00", "FF:FF:FF:FF:FF:FF"):
        return False
    first_octet = int(mac.split(":")[0], 16)
    return (first_octet & 1) == 0   # multicast bit must be 0


# -------------------------------------------------------------
#                   TIMESTAMP EXTRACTOR
# -------------------------------------------------------------
def get_timestamp(rx_basic):
    if not isinstance(rx_basic, dict):
        return None
    for key in ("Timestamp", "timestamp", "SystemTime", "systemTime"):
        if key in rx_basic:
            arr = np.array(rx_basic[key]).flatten()
            if arr.size:
                return int(arr[0])
    return None


# -------------------------------------------------------------
#                   SAVE PLOTS
# -------------------------------------------------------------
def save_plot(fig, folder, name):
    os.makedirs(folder, exist_ok=True)
    path = os.path.join(folder, name)
    fig.savefig(path, dpi=200, bbox_inches="tight")
    plt.close(fig)
    print(f"[+] Saved plot: {path}")


# -------------------------------------------------------------
#                   MAIN ANALYSIS
# -------------------------------------------------------------
def analyze_csi(path):
    print(f"\nOpening file: {path}")
    print(f"File size: {os.path.getsize(path) / (1024 * 1024):.2f} MB\n")

    out_dir = os.path.splitext(os.path.basename(path))[0]
    os.makedirs(out_dir, exist_ok=True)

    ps = Picoscenes(path)
    frames = ps.raw

    # ---------------------------------------------------------
    #   COLLECT CSI FRAMES
    # ---------------------------------------------------------
    csi_frames_all = [f for f in frames if isinstance(f.get("CSI"), dict)]
    if not csi_frames_all:
        print("No CSI frames found.")
        return

    # ---------------------------------------------------------
    #   EXTRACT ALL MAC ADDRESSES
    # ---------------------------------------------------------
    all_macs = set()
    for f in frames:
        sh = f.get("StandardHeader") or f.get("standardHeader")
        if not isinstance(sh, dict):
            continue
        for k in ("Addr1", "Addr2", "Addr3", "addr1", "addr2", "addr3"):
            mac = norm_mac(mac_to_str(sh.get(k)))
            if mac:
                all_macs.add(mac)

    # ---------------------------------------------------------
    #   FILTER CSI BY TARGET TX
    # ---------------------------------------------------------
    TARGET = norm_mac(TARGET_TX_MAC)
    csi_frames = []
    rx_list = []

    if TARGET in all_macs:
        for f in csi_frames_all:
            sh = f.get("StandardHeader") or f.get("standardHeader")
            if not isinstance(sh, dict):
                continue

            tx = norm_mac(mac_to_str(sh.get("Addr2") or sh.get("addr2")))
            rx = norm_mac(mac_to_str(sh.get("Addr1") or sh.get("addr1")))

            if tx == TARGET:
                csi_frames.append(f)
                if is_valid_unicast(rx):
                    rx_list.append(rx)

        print("==========================================")
        print(" Target TX filtering ENABLED")
        print("==========================================")
        print(f"Forced TX MAC : {TARGET}")
    else:
        csi_frames = csi_frames_all
        print("Target TX not found; using all CSI frames.")

    if not csi_frames:
        print("No CSI frames after TX filtering.")
        return

    # ---------------------------------------------------------
    #   RX SELECTION (MOST CSI, UNICAST ONLY)
    # ---------------------------------------------------------
    rx_counter = Counter(rx_list)
    rx_primary = rx_counter.most_common(1)[0][0] if rx_counter else None

    print(f"Total CSI frames used : {len(csi_frames)}")
    print("RX CSI counts (unicast only):")
    for mac, cnt in rx_counter.most_common():
        print(f"  {mac} : {cnt}")
    print(f"Primary RX : {rx_primary}\n")

    # ---------------------------------------------------------
    #   TIMESTAMPS
    # ---------------------------------------------------------
    timestamps = []
    for f in csi_frames:
        ts = get_timestamp(f.get("RxSBasic") or f.get("rxSBasic"))
        if ts is not None:
            timestamps.append(ts)

    with open(os.path.join(out_dir, "timestamps.txt"), "w") as f:
        for t in timestamps:
            f.write(f"{t}\n")

    # ---------------------------------------------------------
    #   BUILD CSI MATRICES
    # ---------------------------------------------------------
    Amp_list, Phase_list = [], []
    csi_meta = None

    for f in csi_frames:
        c = f.get("CSI")
        if not isinstance(c, dict):
            continue

        if csi_meta is None:
            csi_meta = c

        mag = np.array(c.get("Mag"))
        ph = np.array(c.get("Phase"))

        if mag.size == 0 or ph.size == 0:
            continue

        mag = mag.flatten()
        ph = ph.flatten()

        if Amp_list and mag.size != Amp_list[0].size:
            continue

        Amp_list.append(mag)
        Phase_list.append(ph)

    if not Amp_list:
        raise RuntimeError("No valid CSI matrices.")

    Amp = np.vstack(Amp_list)
    Phase = np.vstack(Phase_list)

    sub_idx = np.array(csi_meta.get("SubcarrierIndex") or []).flatten()
    num_sub = sub_idx.size if sub_idx.size else Amp.shape[1]

    # ---------------------------------------------------------
    #   PLOTS
    # ---------------------------------------------------------
    fig = plt.figure(figsize=(8, 4))
    plt.plot(Amp[0]); plt.grid()
    save_plot(fig, out_dir, "amp_frame1.png")

    fig = plt.figure(figsize=(8, 4))
    plt.plot(Phase[0]); plt.grid()
    save_plot(fig, out_dir, "phase_frame1.png")

    fig = plt.figure(figsize=(8, 4))
    plt.plot(Amp.mean(axis=1)); plt.grid()
    save_plot(fig, out_dir, "amplitude_over_time.png")

    fig = plt.figure(figsize=(8, 4))
    plt.plot(Phase.mean(axis=1)); plt.grid()
    save_plot(fig, out_dir, "phase_over_time.png")

    fig = plt.figure(figsize=(8, 5))
    plt.imshow(Amp, aspect="auto")
    plt.colorbar(label="Amplitude")
    save_plot(fig, out_dir, "amplitude_heatmap.png")

    # ---------------------------------------------------------
    #   SUMMARY FILE
    # ---------------------------------------------------------
    with open(os.path.join(out_dir, "csi_summary.txt"), "w") as f:
        f.write("========== CSI SUMMARY REPORT ==========\n")
        f.write(f"File            : {path}\n")
        f.write(f"TX MAC          : {TARGET}\n")
        f.write(f"Primary RX MAC  : {rx_primary}\n")
        f.write(f"CSI Frames Used : {len(csi_frames)}\n")
        f.write(f"Subcarriers     : {num_sub}\n\n")

        f.write("RX CSI Counts (Unicast Only):\n")
        for mac, cnt in rx_counter.most_common():
            f.write(f"{mac} : {cnt}\n")

    print(f"[+] Saved CSI summary → {out_dir}/csi_summary.txt")
    print("\nDone.\n")


# -------------------------------------------------------------
#                   ENTRY POINT
# -------------------------------------------------------------
def main():
    path = sys.argv[1] if len(sys.argv) > 1 else pick_file()
    if not os.path.isfile(path):
        print("File not found.")
        return
    analyze_csi(path)


if __name__ == "__main__":
    main()
