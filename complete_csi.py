#!/usr/bin/env python3
"""
complete_csi.py — Enhanced CSI Inspector for PicoScenes .csi files

Existing features (unchanged):
    - File dialog to pick .csi
    - MAC extraction (unique + primary TX/RX)
    - Timestamp extraction
    - CSI packet count
    - Subcarrier count
    - CSI rate estimation
    - Timeline plot (now also saved to PNG)

NEW features:
    1. Amplitude data over time (mean amplitude vs frame index)
    2. Phase data over time (mean phase vs frame index)
    3. Amplitude heatmap (frames × subcarriers)
    4. Timestamps saved to timestamps.txt
    5. FPS (sampling rate) derived from timestamps
    6. Frequency mapping for tones (CSV + amplitude-vs-frequency plot)
    7. CSI summary report saved to csi_summary.txt

All outputs are saved into a folder named after the .csi file
(without the .csi extension) in the current working directory.
"""

import sys
import os
import numpy as np
import matplotlib.pyplot as plt

import tkinter as tk
from tkinter import filedialog, messagebox

from picoscenes import Picoscenes


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
#                   MAC PARSER
# -------------------------------------------------------------
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


# -------------------------------------------------------------
#                   TIMESTAMP EXTRACTOR
# -------------------------------------------------------------
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


# -------------------------------------------------------------
#                   SAVE PLOTS UTILITY
# -------------------------------------------------------------
def save_plot(fig, folder, name):
    os.makedirs(folder, exist_ok=True)
    path = os.path.join(folder, name)
    fig.savefig(path, dpi=200, bbox_inches="tight")
    print(f"[+] Saved plot: {path}")
    plt.close(fig)


# -------------------------------------------------------------
#                   MAIN CSI ANALYZER
# -------------------------------------------------------------
def analyze_csi(path):
    print(f"\nOpening file: {path}")
    print(f"File size: {os.path.getsize(path) / (1024 * 1024):.2f} MB\n")

    # Output directory
    out_dir = os.path.splitext(os.path.basename(path))[0]
    os.makedirs(out_dir, exist_ok=True)

    # Load PicoScenes file
    ps = Picoscenes(path)
    frames = ps.raw

    # CSI-bearing frames only
    csi_frames = [f for f in frames if isinstance(f.get("CSI"), dict)]
    num_csi = len(csi_frames)

    if num_csi == 0:
        print("No frames with 'CSI' field found in this file.")
        return

    # ---------------------------------------------------------
    #   MAC EXTRACTION OVER ALL FRAMES
    # ---------------------------------------------------------
    all_macs = set()
    tx_primary = None
    rx_primary = None

    for f in frames:
        sh = f.get("StandardHeader") or f.get("standardHeader")
        if not isinstance(sh, dict):
            continue

        # Try both capitalizations
        A1 = sh.get("Addr1") or sh.get("addr1")   # receiver
        A2 = sh.get("Addr2") or sh.get("addr2")   # transmitter
        A3 = sh.get("Addr3") or sh.get("addr3")   # BSSID / routing

        for addr in (A1, A2, A3):
            mac = mac_to_str(addr)
            if mac is None:
                continue
            if mac in ("00:00:00:00:00:00", "FF:FF:FF:FF:FF:FF"):
                continue
            all_macs.add(mac)

        # first non-broadcast TX/RX pair as "primary"
        if tx_primary is None and A1 is not None and A2 is not None:
            rx_mac = mac_to_str(A1)
            tx_mac = mac_to_str(A2)
            if (
                rx_mac not in (None, "00:00:00:00:00:00", "FF:FF:FF:FF:FF:FF")
                and tx_mac not in (None, "00:00:00:00:00:00", "FF:FF:FF:FF:FF:FF")
            ):
                tx_primary, rx_primary = tx_mac, rx_mac

    # ---------------------------------------------------------
    #   TIMESTAMPS & RATES (CSI FRAMES ONLY)
    # ---------------------------------------------------------
    timestamps = []
    for f in csi_frames:
        rx_basic = f.get("RxSBasic") or f.get("rxSBasic")
        ts = get_timestamp(rx_basic)
        if ts is not None:
            timestamps.append(ts)

    time_span_sec = None
    csi_rate = None
    fps = None

    if len(timestamps) >= 2:
        t_min = min(timestamps)
        t_max = max(timestamps)
        time_span_sec = (t_max - t_min) / 1e6  # microseconds → seconds
        if time_span_sec > 0:
            csi_rate = num_csi / time_span_sec

        ts_sec = np.array(timestamps) / 1e6
        dt = np.diff(ts_sec)
        fps = 1.0 / np.mean(dt)

    # Save timestamps to file (NEW #4)
    ts_path = os.path.join(out_dir, "timestamps.txt")
    with open(ts_path, "w") as f:
        for t in timestamps:
            f.write(str(t) + "\n")
    print(f"[+] Saved timestamp list → {ts_path}")

    # ---------------------------------------------------------
    #   BUILD AMPLITUDE / PHASE MATRICES ACROSS ALL CSI FRAMES
    # ---------------------------------------------------------
    Amp_list = []
    Phase_list = []
    csi_meta = None

    for f in csi_frames:
        c = f.get("CSI")
        if not isinstance(c, dict):
            continue

        if csi_meta is None:
            csi_meta = c  # first CSI block used for metadata (tones, BW, etc.)

        mag = np.array(c.get("Mag"))
        ph = np.array(c.get("Phase"))

        if mag.size == 0 or ph.size == 0:
            continue

        mag = mag.flatten()
        ph = ph.flatten()

        # Ensure all frames have same #tones
        if Amp_list and mag.size != Amp_list[0].size:
            # Skip weird frames with mismatched size
            continue

        Amp_list.append(mag)
        Phase_list.append(ph)

    if not Amp_list:
        raise RuntimeError("No valid CSI Mag/Phase arrays found in frames.")

    Amp = np.vstack(Amp_list)      # shape: (N, K)
    Phase = np.vstack(Phase_list)  # shape: (N, K)
    N, K = Amp.shape

    # ---------------------------------------------------------
    #   SUBCARRIER INFO
    # ---------------------------------------------------------
    sub_idx = np.array(
        csi_meta.get("SubcarrierIndex") or []
    ).flatten()
    if sub_idx.size == 0:
        num_sub = K
    else:
        num_sub = sub_idx.size

    # ---------------------------------------------------------
    #   PRINT CONSOLE SUMMARY (original behavior)
    # ---------------------------------------------------------
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

    print("\n(Plots and summary files are being generated...)\n")

    # ---------------------------------------------------------
    #   PLOT: AMPLITUDE OF FIRST FRAME (Frame 1)
    # ---------------------------------------------------------
    fig = plt.figure(figsize=(8, 4))
    plt.plot(Amp[0])
    plt.xlabel("Subcarrier Index")
    plt.ylabel("Amplitude")
    plt.title("CSI Amplitude – Frame 1")
    plt.grid(True)
    save_plot(fig, out_dir, "amp_frame1.png")

    # ---------------------------------------------------------
    #   PLOT: PHASE OF FIRST FRAME (Frame 1)
    # ---------------------------------------------------------
    fig = plt.figure(figsize=(8, 4))
    plt.plot(Phase[0])
    plt.xlabel("Subcarrier Index")
    plt.ylabel("Phase (radians)")
    plt.title("CSI Phase – Frame 1")
    plt.grid(True)
    save_plot(fig, out_dir, "phase_frame1.png")

    # ---------------------------------------------------------
    #   NEW #1: AMPLITUDE OVER TIME (mean amplitude per frame)
    # ---------------------------------------------------------
    mean_amp = Amp.mean(axis=1)
    fig = plt.figure(figsize=(8, 4))
    plt.plot(mean_amp)
    plt.xlabel("Frame Index")
    plt.ylabel("Mean Amplitude")
    plt.title("Mean CSI Amplitude Over Time")
    plt.grid(True)
    save_plot(fig, out_dir, "amplitude_over_time.png")

    # ---------------------------------------------------------
    #   NEW #2: PHASE OVER TIME (mean phase per frame)
    # ---------------------------------------------------------
    mean_phase = Phase.mean(axis=1)
    fig = plt.figure(figsize=(8, 4))
    plt.plot(mean_phase)
    plt.xlabel("Frame Index")
    plt.ylabel("Mean Phase (rad)")
    plt.title("Mean CSI Phase Over Time")
    plt.grid(True)
    save_plot(fig, out_dir, "phase_over_time.png")

    # ---------------------------------------------------------
    #   NEW #3: AMPLITUDE HEATMAP
    # ---------------------------------------------------------
    fig = plt.figure(figsize=(8, 5))
    plt.imshow(Amp, aspect="auto")
    plt.xlabel("Subcarrier Index")
    plt.ylabel("Frame Index")
    plt.title("CSI Amplitude Over Time (Heatmap)")
    plt.colorbar(label="Amplitude")
    save_plot(fig, out_dir, "amplitude_heatmap.png")

    # ---------------------------------------------------------
    #   NEW #6: FREQUENCY MAPPING FOR TONES
    # ---------------------------------------------------------
    freq_path = os.path.join(out_dir, "frequency_map.csv")
    try:
        raw_idx = csi_meta.get("SubcarrierIndex")
        if raw_idx is None:
            raise ValueError("SubcarrierIndex missing from CSI block.")

        sub_idx = np.array(raw_idx).astype(int).flatten()
        if sub_idx.size == 0:
            raise ValueError("SubcarrierIndex array is empty.")

        delta_f = float(csi_meta.get("SubcarrierBandwidth", 0.0))
        freq_offsets = sub_idx * delta_f  # Hz

        # Build 2-column array for CSV (robust for 1 or many tones)
        if sub_idx.size == 1:
            data = np.array([[sub_idx[0], freq_offsets[0]]], dtype=float)
        else:
            data = np.column_stack((sub_idx, freq_offsets.astype(float)))

        np.savetxt(
            freq_path,
            data,
            delimiter=",",
            header="SubcarrierIndex,FreqOffset(Hz)",
            fmt="%.0f,%.6f",
            comments=""
        )
        print(f"[+] Saved tone frequency map → {freq_path}")

        # Plot mean amplitude vs frequency offset
        fig = plt.figure(figsize=(8, 4))
        # For safety, if Amp has different #tones than subcarriers, slice
        K_eff = min(Amp.shape[1], freq_offsets.size)
        plt.plot(freq_offsets[:K_eff], Amp.mean(axis=0)[:K_eff])
        plt.xlabel("Frequency Offset (Hz)")
        plt.ylabel("Mean Amplitude")
        plt.title("Mean CSI Amplitude vs Frequency Offset")
        plt.grid(True)
        save_plot(fig, out_dir, "freq_amp_plot.png")

    except Exception as e:
        print(f"[!] Frequency mapping skipped: {e}")

    # ---------------------------------------------------------
    #   TIMELINE PLOT (original feature, now saved)
    # ---------------------------------------------------------
    if timestamps:
        ts_sorted = sorted(timestamps)
        t0 = ts_sorted[0]
        t_rel = [(t - t0) / 1e6 for t in ts_sorted]  # seconds
        fig = plt.figure(figsize=(8, 4))
        plt.plot(t_rel, range(1, len(t_rel) + 1))
        plt.xlabel("Time since first CSI frame (s)")
        plt.ylabel("Cumulative CSI packets")
        plt.title("CSI Packet Timeline")
        plt.grid(True)
        save_plot(fig, out_dir, "timeline.png")

    # ---------------------------------------------------------
    #   NEW #7: CSI SUMMARY REPORT FILE
    # ---------------------------------------------------------
    summary_path = os.path.join(out_dir, "csi_summary.txt")
    with open(summary_path, "w") as f:
        f.write("========== CSI SUMMARY REPORT ==========\n")
        f.write(f"Filename: {path}\n")
        f.write(f"Total frames parsed      : {len(frames)}\n")
        f.write(f"Frames with CSI          : {num_csi}\n")
        f.write(f"Subcarriers per frame    : {num_sub}\n")

        f.write("\n---- Timing ----\n")
        if time_span_sec is not None:
            f.write(f"Capture duration         : {time_span_sec:.3f} s\n")
        else:
            f.write("Capture duration         : N/A\n")
        if csi_rate is not None:
            f.write(f"Average CSI rate         : {csi_rate:.2f} packets/s\n")
        else:
            f.write("Average CSI rate         : N/A\n")
        if fps is not None:
            f.write(f"Derived FPS (from dt)    : {fps:.2f} Hz\n")
        else:
            f.write("Derived FPS (from dt)    : N/A\n")

        f.write("\n---- MAC Addresses ----\n")
        if all_macs:
            for m in sorted(all_macs):
                f.write(m + "\n")
        else:
            f.write("<none>\n")
        f.write("\nPrimary TX MAC: " + str(tx_primary) + "\n")
        f.write("Primary RX MAC: " + str(rx_primary) + "\n")

        # ---------- NEW: TX/RX Antenna Count + MAC ----------
        tx_ant = csi_meta.get("numTx")
        rx_ant = csi_meta.get("numRx")

        try:
            tx_ant = int(tx_ant)
        except:
            tx_ant = "N/A"
        try:
            rx_ant = int(rx_ant)
        except:
            rx_ant = "N/A"

        f.write("\n---- Antenna Information ----\n")
        f.write(f"TX Antennas (numTx): {tx_ant}    MAC: {tx_primary}\n")
        f.write(f"RX Antennas (numRx): {rx_ant}    MAC: {rx_primary}\n")

        # ---------- NEW: CSI matrix info ----------
        f.write("\n---- CSI Matrix ----\n")
        f.write(
            f"CSI matrix shape (frames x tones): {Amp.shape[0]} x {Amp.shape[1]}\n"
        )

        # first few rows of data (amplitude)
        preview_rows = min(5, Amp.shape[0])
        f.write(f"\nFirst {preview_rows} rows of amplitude matrix:\n")
        for i in range(preview_rows):
            row_str = ", ".join(f"{v:.4f}" for v in Amp[i])
            f.write(f"Row {i}: {row_str}\n")

        # value of all subcarriers
        f.write("\nSubcarrier indices (all tones):\n")
        if sub_idx.size:
            f.write(", ".join(str(int(x)) for x in sub_idx) + "\n")
        else:
            f.write("N/A\n")

        f.write("=========================================\n")


    print(f"[+] Saved CSI summary report → {summary_path}")
    print("\nDone.\n")


# -------------------------------------------------------------
#                   ENTRY POINT
# -------------------------------------------------------------
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
