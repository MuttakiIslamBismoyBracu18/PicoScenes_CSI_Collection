#!/usr/bin/env python3
"""
csi_inspector_merged.py — Extensive CSI metadata + visualization toolkit for PicoScenes .csi files

This script MERGES (and preserves) everything from:
  1) csi_metadata.py (Target TX filter + RX unicast counting + plots + timestamps + csi_summary.txt)
  2) complete_csi.py (full MAC list + primary TX/RX + rates + frequency mapping + timeline + antenna info + CSI matrix info)

It ALSO ADDS additional learning/insights from a single .csi file:
  - Robust metadata dump (CarrierFreq, CBW, SamplingRate, NumTones, SubcarrierBandwidth, etc. when present)
  - Per-frame amplitude/phase statistics (mean/std) exported to CSV
  - Mean amplitude vs subcarrier index plot
  - Mean phase vs subcarrier index plot
  - Inter-arrival time (dt) histogram/plot (helps validate capture regularity)
  - Phase unwrapping option for more interpretable phase trends (saved as plot)
  - Clean, conventional output naming under a single output folder

Requirements:
  - Python 3.11+
  - numpy, matplotlib
  - tkinter (optional; used for file picker if no CLI path)
  - picoscenes Python module providing: from picoscenes import Picoscenes

Usage:
  python csi_inspector_merged.py
  python csi_inspector_merged.py /path/to/file.csi
  python csi_inspector_merged.py /path/to/file.csi --tx-mac 24:4B:FE:BE:FF:DC
  python csi_inspector_merged.py /path/to/file.csi --no-tx-filter

Outputs (inside output folder named after the .csi file):
  - timestamps.txt
  - csi_summary.txt
  - frequency_map.csv (if SubcarrierIndex + SubcarrierBandwidth exist)
  - frame_stats.csv
  - Plots:
      amp_frame1.png
      phase_frame1.png
      amplitude_over_time.png
      phase_over_time.png
      amplitude_heatmap.png
      phase_heatmap.png
      phase_unwrapped_over_time.png
      mean_amplitude_vs_subcarrier.png
      mean_phase_vs_subcarrier.png
      timeline.png
      freq_amp_plot.png (if frequency map computed)
      inter_arrival_dt.png

Notes:
  - Addr1 is Receiver (RA), Addr2 is Transmitter (TA) in 802.11 StandardHeader.
  - “Primary RX” is selected as the unicast receiver with the most CSI frames after TX filtering (when enabled).
  - “Primary TX/RX” (from complete_csi.py behavior) is the first non-broadcast TX/RX pair observed in frames.
"""

import sys
import os
import argparse
from collections import Counter
import numpy as np
import matplotlib.pyplot as plt

# Optional GUI file picker
try:
    import tkinter as tk
    from tkinter import filedialog, messagebox
    TK_AVAILABLE = True
except Exception:
    TK_AVAILABLE = False

from picoscenes import Picoscenes


# -----------------------------
# Defaults
# -----------------------------
DEFAULT_TARGET_TX_MAC = "24:4B:FE:BE:FF:DC"


# -------------------------------------------------------------
#                   FILE PICKER (GUI)
# -------------------------------------------------------------
def pick_file_gui():
    if not TK_AVAILABLE:
        raise SystemExit("Tkinter not available. Please pass the .csi path as a CLI argument.")
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
#                   SAFE DICT GETTERS
# -------------------------------------------------------------
def get_dict_any(frame, keys):
    """Return the first dict found among keys in frame, else None."""
    for k in keys:
        v = frame.get(k)
        if isinstance(v, dict):
            return v
    return None


def get_any(d, keys, default=None):
    """Return first present key in dict d, else default."""
    if not isinstance(d, dict):
        return default
    for k in keys:
        if k in d:
            return d.get(k)
    return default


def to_int_safe(x):
    try:
        if x is None:
            return None
        arr = np.array(x).flatten()
        if arr.size == 0:
            return None
        return int(arr[0])
    except Exception:
        try:
            return int(x)
        except Exception:
            return None


def to_float_safe(x):
    try:
        if x is None:
            return None
        arr = np.array(x).flatten()
        if arr.size == 0:
            return None
        return float(arr[0])
    except Exception:
        try:
            return float(x)
        except Exception:
            return None


# -------------------------------------------------------------
#                   MAC UTILITIES
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


def norm_mac(mac):
    if mac is None:
        return None
    return mac.strip().upper()


def is_valid_unicast(mac):
    """
    Returns True for a valid unicast MAC:
      - Not all-zero, not broadcast
      - Multicast bit must be 0
    """
    if mac in (None, "00:00:00:00:00:00", "FF:FF:FF:FF:FF:FF"):
        return False
    try:
        first_octet = int(mac.split(":")[0], 16)
    except Exception:
        return False
    return (first_octet & 1) == 0


# -------------------------------------------------------------
#                   TIMESTAMP EXTRACTOR
# -------------------------------------------------------------
def get_timestamp_us(rx_basic):
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
                try:
                    return int(arr[0])
                except Exception:
                    return None
    return None


# -------------------------------------------------------------
#                   SAVE UTILITIES
# -------------------------------------------------------------
def ensure_dir(path):
    os.makedirs(path, exist_ok=True)


def save_plot(fig, folder, name):
    ensure_dir(folder)
    out_path = os.path.join(folder, name)
    fig.savefig(out_path, dpi=200, bbox_inches="tight")
    plt.close(fig)
    print(f"[+] Saved plot: {out_path}")
    return out_path


def write_lines(path, lines):
    ensure_dir(os.path.dirname(path))
    with open(path, "w", encoding="utf-8") as f:
        for line in lines:
            f.write(line + "\n")


# -------------------------------------------------------------
#                   MAIN ANALYSIS
# -------------------------------------------------------------
def analyze_csi(path, target_tx_mac, use_tx_filter=True):
    print(f"\nOpening file: {path}")
    print(f"File size: {os.path.getsize(path) / (1024 * 1024):.2f} MB\n")

    # Output directory: named after file base name (conventional)
    out_dir = os.path.splitext(os.path.basename(path))[0]
    ensure_dir(out_dir)

    # Load PicoScenes file
    ps = Picoscenes(path)
    frames = ps.raw
    total_frames = len(frames)

    # CSI-bearing frames only (as in both original scripts)
    csi_frames_all = [f for f in frames if isinstance(f.get("CSI"), dict)]
    if not csi_frames_all:
        print("No CSI frames found (no frames containing a 'CSI' dict).")
        return

    # ---------------------------------------------------------
    #   MAC EXTRACTION OVER ALL FRAMES (complete_csi.py behavior)
    # ---------------------------------------------------------
    all_macs = set()
    tx_primary_firstpair = None
    rx_primary_firstpair = None

    for f in frames:
        sh = get_dict_any(f, ["StandardHeader", "standardHeader"])
        if not isinstance(sh, dict):
            continue

        A1 = sh.get("Addr1") or sh.get("addr1")   # receiver
        A2 = sh.get("Addr2") or sh.get("addr2")   # transmitter
        A3 = sh.get("Addr3") or sh.get("addr3")   # BSSID / routing

        for addr in (A1, A2, A3):
            mac = mac_to_str(addr)
            if mac is None:
                continue
            if mac in ("00:00:00:00:00:00", "FF:FF:FF:FF:FF:FF"):
                continue
            all_macs.add(norm_mac(mac))

        # first non-broadcast TX/RX pair as "primary" (original complete_csi.py logic)
        if tx_primary_firstpair is None and A1 is not None and A2 is not None:
            rx_mac = norm_mac(mac_to_str(A1))
            tx_mac = norm_mac(mac_to_str(A2))
            if (
                rx_mac not in (None, "00:00:00:00:00:00", "FF:FF:FF:FF:FF:FF")
                and tx_mac not in (None, "00:00:00:00:00:00", "FF:FF:FF:FF:FF:FF")
            ):
                tx_primary_firstpair, rx_primary_firstpair = tx_mac, rx_mac

    # ---------------------------------------------------------
    #   FILTER CSI BY TARGET TX (csi_metadata.py behavior)
    # ---------------------------------------------------------
    TARGET = norm_mac(target_tx_mac) if target_tx_mac else None
    csi_frames_used = []
    rx_list_unicast = []

    if use_tx_filter and TARGET:
        # Determine if target is in observed MACs (csi_metadata.py behavior)
        if TARGET in all_macs:
            for f in csi_frames_all:
                sh = get_dict_any(f, ["StandardHeader", "standardHeader"])
                if not isinstance(sh, dict):
                    continue

                tx = norm_mac(mac_to_str(sh.get("Addr2") or sh.get("addr2")))
                rx = norm_mac(mac_to_str(sh.get("Addr1") or sh.get("addr1")))

                if tx == TARGET:
                    csi_frames_used.append(f)
                    if is_valid_unicast(rx):
                        rx_list_unicast.append(rx)

            print("==========================================")
            print(" Target TX filtering ENABLED")
            print("==========================================")
            print(f"Forced TX MAC : {TARGET}\n")
        else:
            # If target not found, use all CSI frames (original csi_metadata.py behavior)
            csi_frames_used = csi_frames_all
            print("Target TX not found in observed MACs; using all CSI frames.\n")
    else:
        csi_frames_used = csi_frames_all
        if use_tx_filter:
            print("TX filtering requested but no TARGET TX MAC provided; using all CSI frames.\n")
        else:
            print("Target TX filtering DISABLED; using all CSI frames.\n")

    if not csi_frames_used:
        print("No CSI frames after TX filtering.")
        return

    num_csi_used = len(csi_frames_used)
    num_csi_all = len(csi_frames_all)

    # RX selection: most CSI, unicast only (csi_metadata.py behavior)
    rx_counter = Counter(rx_list_unicast)
    rx_primary_bycount = rx_counter.most_common(1)[0][0] if rx_counter else None

    print(f"Total frames parsed      : {total_frames}")
    print(f"Frames with CSI (all)    : {num_csi_all}")
    print(f"Frames with CSI (used)   : {num_csi_used}")

    if use_tx_filter and TARGET in all_macs:
        print("\nRX CSI counts (unicast only) after TX filtering:")
        if rx_counter:
            for mac, cnt in rx_counter.most_common():
                print(f"  {mac} : {cnt}")
        else:
            print("  <none> (no unicast RX observed after filter)")
        print(f"Primary RX (by count)    : {rx_primary_bycount}\n")

    # ---------------------------------------------------------
    #   TIMESTAMPS & RATES (complete_csi.py behavior; on used frames)
    # ---------------------------------------------------------
    timestamps = []
    for f in csi_frames_used:
        rx_basic = get_dict_any(f, ["RxSBasic", "rxSBasic"])
        ts = get_timestamp_us(rx_basic)
        if ts is not None:
            timestamps.append(ts)

    timestamps_path = os.path.join(out_dir, "timestamps.txt")
    write_lines(timestamps_path, [str(t) for t in timestamps])
    print(f"[+] Saved timestamp list → {timestamps_path}")

    time_span_sec = None
    csi_rate = None
    fps = None
    dt_stats = {}

    if len(timestamps) >= 2:
        t_min = min(timestamps)
        t_max = max(timestamps)
        time_span_sec = (t_max - t_min) / 1e6  # microseconds → seconds
        if time_span_sec and time_span_sec > 0:
            csi_rate = num_csi_used / time_span_sec

        ts_sec = np.array(timestamps, dtype=np.float64) / 1e6
        dt = np.diff(np.sort(ts_sec))
        if dt.size > 0 and np.mean(dt) > 0:
            fps = 1.0 / np.mean(dt)

        if dt.size > 0:
            dt_stats = {
                "dt_count": int(dt.size),
                "dt_mean_s": float(np.mean(dt)),
                "dt_std_s": float(np.std(dt)),
                "dt_min_s": float(np.min(dt)),
                "dt_max_s": float(np.max(dt)),
                "dt_median_s": float(np.median(dt)),
            }

            # Inter-arrival plot (ADDED)
            fig = plt.figure(figsize=(8, 4))
            plt.plot(dt)
            plt.xlabel("Interval Index")
            plt.ylabel("Inter-arrival dt (s)")
            plt.title("CSI Timestamp Inter-arrival (dt)")
            plt.grid(True)
            save_plot(fig, out_dir, "inter_arrival_dt.png")

    # ---------------------------------------------------------
    #   BUILD AMPLITUDE / PHASE MATRICES (both scripts)
    # ---------------------------------------------------------
    Amp_list = []
    Phase_list = []
    csi_meta = None

    for f in csi_frames_used:
        c = f.get("CSI")
        if not isinstance(c, dict):
            continue

        if csi_meta is None:
            csi_meta = c  # first CSI block used for metadata

        mag = np.array(c.get("Mag"))
        ph = np.array(c.get("Phase"))

        if mag.size == 0 or ph.size == 0:
            continue

        mag = mag.flatten()
        ph = ph.flatten()

        # Ensure consistent tone count across frames
        if Amp_list and mag.size != Amp_list[0].size:
            continue

        Amp_list.append(mag)
        Phase_list.append(ph)

    if not Amp_list:
        raise RuntimeError("No valid CSI Mag/Phase arrays found in frames used.")

    Amp = np.vstack(Amp_list)      # shape: (N, K)
    Phase = np.vstack(Phase_list)  # shape: (N, K)
    N, K = Amp.shape

    # Subcarrier indices
    sub_idx = np.array(get_any(csi_meta, ["SubcarrierIndex", "subcarrierIndex"], default=[])).flatten()
    num_sub = int(sub_idx.size) if sub_idx.size else int(K)

    # ---------------------------------------------------------
    #   PLOTS (unique, conventionally named)
    # ---------------------------------------------------------
    # Amp frame 1
    fig = plt.figure(figsize=(8, 4))
    plt.plot(Amp[0]); plt.grid(True)
    plt.xlabel("Tone / Subcarrier Bin")
    plt.ylabel("Amplitude")
    plt.title("CSI Amplitude — Frame 1")
    save_plot(fig, out_dir, "amp_frame1.png")

    # Phase frame 1
    fig = plt.figure(figsize=(8, 4))
    plt.plot(Phase[0]); plt.grid(True)
    plt.xlabel("Tone / Subcarrier Bin")
    plt.ylabel("Phase (rad)")
    plt.title("CSI Phase — Frame 1")
    save_plot(fig, out_dir, "phase_frame1.png")

    # Mean amplitude over time
    mean_amp = Amp.mean(axis=1)
    fig = plt.figure(figsize=(8, 4))
    plt.plot(mean_amp); plt.grid(True)
    plt.xlabel("Frame Index")
    plt.ylabel("Mean Amplitude")
    plt.title("Mean CSI Amplitude Over Time")
    save_plot(fig, out_dir, "amplitude_over_time.png")

    # Mean phase over time
    mean_phase = Phase.mean(axis=1)
    fig = plt.figure(figsize=(8, 4))
    plt.plot(mean_phase); plt.grid(True)
    plt.xlabel("Frame Index")
    plt.ylabel("Mean Phase (rad)")
    plt.title("Mean CSI Phase Over Time")
    save_plot(fig, out_dir, "phase_over_time.png")

    # Amplitude heatmap
    fig = plt.figure(figsize=(8, 5))
    plt.imshow(Amp, aspect="auto")
    plt.xlabel("Tone / Subcarrier Bin")
    plt.ylabel("Frame Index")
    plt.title("CSI Amplitude Heatmap (Frames × Tones)")
    plt.colorbar(label="Amplitude")
    save_plot(fig, out_dir, "amplitude_heatmap.png")

    # Phase heatmap (ADDED, unique plot)
    fig = plt.figure(figsize=(8, 5))
    plt.imshow(Phase, aspect="auto")
    plt.xlabel("Tone / Subcarrier Bin")
    plt.ylabel("Frame Index")
    plt.title("CSI Phase Heatmap (Frames × Tones)")
    plt.colorbar(label="Phase (rad)")
    save_plot(fig, out_dir, "phase_heatmap.png")

    # Mean amplitude vs subcarrier bin (ADDED)
    fig = plt.figure(figsize=(8, 4))
    plt.plot(Amp.mean(axis=0)); plt.grid(True)
    plt.xlabel("Tone / Subcarrier Bin")
    plt.ylabel("Mean Amplitude")
    plt.title("Mean CSI Amplitude vs Tone/Subcarrier Bin")
    save_plot(fig, out_dir, "mean_amplitude_vs_subcarrier.png")

    # Mean phase vs subcarrier bin (ADDED)
    fig = plt.figure(figsize=(8, 4))
    plt.plot(Phase.mean(axis=0)); plt.grid(True)
    plt.xlabel("Tone / Subcarrier Bin")
    plt.ylabel("Mean Phase (rad)")
    plt.title("Mean CSI Phase vs Tone/Subcarrier Bin")
    save_plot(fig, out_dir, "mean_phase_vs_subcarrier.png")

    # Phase unwrapping trend (ADDED)
    # Unwrap along tones, then average per frame.
    phase_unwrapped = np.unwrap(Phase, axis=1)
    mean_phase_unwrapped = phase_unwrapped.mean(axis=1)
    fig = plt.figure(figsize=(8, 4))
    plt.plot(mean_phase_unwrapped); plt.grid(True)
    plt.xlabel("Frame Index")
    plt.ylabel("Mean Unwrapped Phase (rad)")
    plt.title("Mean CSI Unwrapped Phase Over Time")
    save_plot(fig, out_dir, "phase_unwrapped_over_time.png")

    # Timeline plot (complete_csi.py behavior, based on timestamps)
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
    #   FREQUENCY MAPPING FOR TONES (complete_csi.py behavior)
    # ---------------------------------------------------------
    freq_map_path = os.path.join(out_dir, "frequency_map.csv")
    freq_amp_plot_saved = False
    freq_mapping_msg = None

    try:
        raw_idx = get_any(csi_meta, ["SubcarrierIndex", "subcarrierIndex"], default=None)
        if raw_idx is None:
            raise ValueError("SubcarrierIndex missing from CSI block.")

        sub_idx_int = np.array(raw_idx).astype(int).flatten()
        if sub_idx_int.size == 0:
            raise ValueError("SubcarrierIndex array is empty.")

        delta_f = to_float_safe(get_any(csi_meta, ["SubcarrierBandwidth", "subcarrierBandwidth"], default=0.0))
        if delta_f is None or delta_f == 0.0:
            raise ValueError("SubcarrierBandwidth missing or zero; cannot compute frequency offsets.")

        freq_offsets = sub_idx_int * float(delta_f)  # Hz

        if sub_idx_int.size == 1:
            data = np.array([[sub_idx_int[0], freq_offsets[0]]], dtype=float)
        else:
            data = np.column_stack((sub_idx_int, freq_offsets.astype(float)))

        np.savetxt(
            freq_map_path,
            data,
            delimiter=",",
            header="SubcarrierIndex,FreqOffset(Hz)",
            fmt="%.0f,%.6f",
            comments=""
        )
        print(f"[+] Saved tone frequency map → {freq_map_path}")

        # Plot mean amplitude vs frequency offset
        fig = plt.figure(figsize=(8, 4))
        K_eff = min(Amp.shape[1], freq_offsets.size)
        plt.plot(freq_offsets[:K_eff], Amp.mean(axis=0)[:K_eff])
        plt.xlabel("Frequency Offset (Hz)")
        plt.ylabel("Mean Amplitude")
        plt.title("Mean CSI Amplitude vs Frequency Offset")
        plt.grid(True)
        save_plot(fig, out_dir, "freq_amp_plot.png")
        freq_amp_plot_saved = True

    except Exception as e:
        freq_mapping_msg = f"Frequency mapping skipped: {e}"
        print(f"[!] {freq_mapping_msg}")

    # ---------------------------------------------------------
    #   PER-FRAME STATS EXPORT (ADDED)
    # ---------------------------------------------------------
    frame_stats_path = os.path.join(out_dir, "frame_stats.csv")
    # columns: frame_index, mean_amp, std_amp, mean_phase, std_phase, mean_unwrapped_phase
    mean_amp_f = Amp.mean(axis=1)
    std_amp_f = Amp.std(axis=1)
    mean_phase_f = Phase.mean(axis=1)
    std_phase_f = Phase.std(axis=1)
    mean_unwrap_f = mean_phase_unwrapped

    header = "frame_index,mean_amp,std_amp,mean_phase,std_phase,mean_unwrapped_phase"
    data = np.column_stack((
        np.arange(N, dtype=int),
        mean_amp_f.astype(float),
        std_amp_f.astype(float),
        mean_phase_f.astype(float),
        std_phase_f.astype(float),
        mean_unwrap_f.astype(float),
    ))
    np.savetxt(frame_stats_path, data, delimiter=",", header=header, comments="", fmt="%.0f,%.6f,%.6f,%.6f,%.6f,%.6f")
    print(f"[+] Saved per-frame stats → {frame_stats_path}")

    # ---------------------------------------------------------
    #   METADATA EXTRACTION (ADDED, robust)
    # ---------------------------------------------------------
    # Try common PicoScenes CSI metadata keys (case variations)
    meta_carrier = to_float_safe(get_any(csi_meta, ["CarrierFreq", "CarrierFreq2", "carrierFreq", "carrierFreq2"]))
    meta_cbw = to_int_safe(get_any(csi_meta, ["CBW", "cbw"]))
    meta_sr = to_float_safe(get_any(csi_meta, ["SamplingRate", "samplingRate"]))
    meta_num_tones = to_int_safe(get_any(csi_meta, ["NumTones", "numTones"]))
    meta_sc_bw = to_float_safe(get_any(csi_meta, ["SubcarrierBandwidth", "subcarrierBandwidth"]))
    meta_num_tx = to_int_safe(get_any(csi_meta, ["NumTx", "numTx"]))
    meta_num_rx = to_int_safe(get_any(csi_meta, ["NumRx", "numRx"]))
    meta_is_merged = to_int_safe(get_any(csi_meta, ["IsMerged", "isMerged"]))

    # ---------------------------------------------------------
    #   SUMMARY FILE (MERGED: includes EVERYTHING both scripts wrote, plus added fields)
    # ---------------------------------------------------------
    summary_path = os.path.join(out_dir, "csi_summary.txt")

    # TX MAC to report:
    # - If TX filter enabled and target was used, report TARGET
    # - Else report tx_primary_firstpair (if available)
    reported_tx_mac = None
    if use_tx_filter and TARGET and (TARGET in all_macs):
        reported_tx_mac = TARGET
    else:
        reported_tx_mac = tx_primary_firstpair

    # RX MAC to report:
    # - Prefer rx_primary_bycount (from filtered unicast counting)
    # - Else fall back to rx_primary_firstpair
    reported_rx_mac = rx_primary_bycount or rx_primary_firstpair

    # Antenna counts (from CSI meta): keep the exact "numTx/numRx" text like your prior summary
    tx_ant = meta_num_tx if meta_num_tx is not None else "N/A"
    rx_ant = meta_num_rx if meta_num_rx is not None else "N/A"

    with open(summary_path, "w", encoding="utf-8") as f:
        f.write("========== CSI SUMMARY REPORT ==========\n")
        f.write(f"File                      : {path}\n")
        f.write(f"Output Folder             : {out_dir}\n\n")

        f.write("---- Frame Counts ----\n")
        f.write(f"Total frames parsed       : {total_frames}\n")
        f.write(f"Frames with CSI (all)     : {num_csi_all}\n")
        f.write(f"Frames with CSI (used)    : {num_csi_used}\n")
        f.write(f"Subcarriers / tones used  : {num_sub}\n")
        f.write(f"CSI matrix shape (N x K)  : {Amp.shape[0]} x {Amp.shape[1]}\n\n")

        f.write("---- Timing ----\n")
        if time_span_sec is not None:
            f.write(f"Capture duration          : {time_span_sec:.6f} s\n")
        else:
            f.write("Capture duration          : N/A\n")
        if csi_rate is not None:
            f.write(f"Average CSI rate          : {csi_rate:.6f} packets/s\n")
        else:
            f.write("Average CSI rate          : N/A\n")
        if fps is not None:
            f.write(f"Derived FPS (from dt)     : {fps:.6f} Hz\n")
        else:
            f.write("Derived FPS (from dt)     : N/A\n")
        if dt_stats:
            f.write("\nInter-arrival dt stats (seconds):\n")
            f.write(f"  count   : {dt_stats['dt_count']}\n")
            f.write(f"  mean    : {dt_stats['dt_mean_s']:.9f}\n")
            f.write(f"  std     : {dt_stats['dt_std_s']:.9f}\n")
            f.write(f"  min     : {dt_stats['dt_min_s']:.9f}\n")
            f.write(f"  median  : {dt_stats['dt_median_s']:.9f}\n")
            f.write(f"  max     : {dt_stats['dt_max_s']:.9f}\n")
        f.write("\n")

        f.write("---- MAC Addresses (Unique) ----\n")
        if all_macs:
            for m in sorted(all_macs):
                f.write(m + "\n")
        else:
            f.write("<none>\n")
        f.write("\n")

        f.write("---- Primary TX / RX (First non-broadcast pair) ----\n")
        f.write(f"Primary TX MAC (first pair): {tx_primary_firstpair}\n")
        f.write(f"Primary RX MAC (first pair): {rx_primary_firstpair}\n\n")

        f.write("---- Target TX Filtering ----\n")
        f.write(f"TX filtering enabled       : {bool(use_tx_filter)}\n")
        f.write(f"Target TX MAC requested    : {TARGET}\n")
        f.write(f"Target TX present in MACs  : {bool(TARGET and TARGET in all_macs)}\n")
        f.write(f"Reported TX MAC            : {reported_tx_mac}\n")
        f.write(f"Reported RX MAC            : {reported_rx_mac}\n\n")

        f.write("RX CSI Counts (Unicast Only, after TX filter when applicable):\n")
        if rx_counter:
            for mac, cnt in rx_counter.most_common():
                f.write(f"{mac} : {cnt}\n")
        else:
            f.write("<none>\n")
        f.write("\n")

        f.write("---- Antenna Information ----\n")
        f.write(f"TX Antennas (numTx): {tx_ant}    MAC: {reported_tx_mac}\n")
        f.write(f"RX Antennas (numRx): {rx_ant}    MAC: {reported_rx_mac}\n\n")

        f.write("---- CSI Metadata (if available) ----\n")
        f.write(f"CarrierFreq (Hz)           : {meta_carrier}\n")
        f.write(f"CBW (MHz)                  : {meta_cbw}\n")
        f.write(f"SamplingRate (Hz)          : {meta_sr}\n")
        f.write(f"NumTones                   : {meta_num_tones}\n")
        f.write(f"SubcarrierBandwidth (Hz)   : {meta_sc_bw}\n")
        f.write(f"IsMerged                   : {meta_is_merged}\n\n")

        f.write("---- CSI Matrix Preview (Amplitude) ----\n")
        preview_rows = min(5, Amp.shape[0])
        f.write(f"First {preview_rows} rows of amplitude matrix:\n")
        for i in range(preview_rows):
            row_str = ", ".join(f"{v:.4f}" for v in Amp[i])
            f.write(f"Row {i}: {row_str}\n")
        f.write("\n")

        f.write("Subcarrier indices (all tones):\n")
        if sub_idx.size:
            f.write(", ".join(str(int(x)) for x in sub_idx) + "\n")
        else:
            f.write("N/A\n")
        f.write("\n")

        f.write("---- Frequency Mapping ----\n")
        if freq_amp_plot_saved:
            f.write(f"frequency_map.csv          : {freq_map_path}\n")
            f.write("freq_amp_plot.png          : saved\n")
        else:
            f.write("frequency_map.csv          : not created\n")
            if freq_mapping_msg:
                f.write(f"Reason                     : {freq_mapping_msg}\n")
        f.write("\n")

        f.write("---- Generated Files (Key Outputs) ----\n")
        f.write(f"timestamps.txt             : {timestamps_path}\n")
        f.write(f"frame_stats.csv            : {frame_stats_path}\n")
        f.write("amp_frame1.png             : saved\n")
        f.write("phase_frame1.png           : saved\n")
        f.write("amplitude_over_time.png    : saved\n")
        f.write("phase_over_time.png        : saved\n")
        f.write("amplitude_heatmap.png      : saved\n")
        f.write("phase_heatmap.png          : saved\n")
        f.write("phase_unwrapped_over_time.png : saved\n")
        f.write("mean_amplitude_vs_subcarrier.png : saved\n")
        f.write("mean_phase_vs_subcarrier.png : saved\n")
        f.write("timeline.png               : saved if timestamps exist\n")
        f.write("inter_arrival_dt.png       : saved if timestamps have dt\n")
        f.write("=========================================\n")

    print(f"[+] Saved CSI summary → {summary_path}")
    print("\nDone.\n")


# -------------------------------------------------------------
#                   ENTRY POINT
# -------------------------------------------------------------
def main():
    parser = argparse.ArgumentParser(
        description="Merged CSI metadata + visualization inspector for PicoScenes .csi files."
    )
    parser.add_argument(
        "path",
        nargs="?",
        default=None,
        help="Path to PicoScenes .csi file (if omitted, GUI picker is used when available)."
    )
    parser.add_argument(
        "--tx-mac",
        default=DEFAULT_TARGET_TX_MAC,
        help=f"Target TX MAC for filtering (default: {DEFAULT_TARGET_TX_MAC}). Use with --no-tx-filter to disable filtering."
    )
    parser.add_argument(
        "--no-tx-filter",
        action="store_true",
        help="Disable target TX filtering and use all CSI frames."
    )

    args = parser.parse_args()

    # Resolve path
    if args.path:
        path = args.path
    else:
        path = pick_file_gui()

    if not os.path.isfile(path):
        print(f"File not found: {path}")
        return

    use_tx_filter = not args.no_tx_filter

    try:
        analyze_csi(path, target_tx_mac=args.tx_mac, use_tx_filter=use_tx_filter)
    except Exception as e:
        # GUI error dialog if possible (like complete_csi.py behavior)
        if TK_AVAILABLE:
            try:
                root = tk.Tk()
                root.withdraw()
                messagebox.showerror("Error", f"Failed to parse CSI file:\n{e}")
                root.destroy()
            except Exception:
                pass
        print(f"\nERROR while parsing: {e}")
        raise


if __name__ == "__main__":
    main()
