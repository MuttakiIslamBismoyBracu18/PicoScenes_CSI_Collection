#!/usr/bin/env python3
"""
csi_viz.py — Advanced CSI visualizations for PicoScenes .csi files

Features:
    - Tkinter file picker if no path is given on the command line
    - Loads CSI (Mag, Phase) using the PicoScenes Python API
    - Builds amplitude and phase matrices: Amp (N x K), Phase (N x K)
    - Generates 4 visualizations to highlight motion / gesture patterns:

        1. Amplitude heatmap       → {base}_AmplitudeHeatmap.png
        2. Phase heatmap           → {base}_PhaseHeatmap.png
        3. Variance over time      → {base}_VariancePlot.png
        4. PCA waveform over time  → {base}_PCAPlot.png

    - All plots are saved into: {base}+Visuals/

Run:
    python csi_viz.py
    python csi_viz.py /path/to/file.csi
"""

import os
import sys
import numpy as np
import matplotlib.pyplot as plt

import tkinter as tk
from tkinter import filedialog, messagebox

from picoscenes import Picoscenes


# ---------------------------------------------------------------------
#   FILE PICKER
# ---------------------------------------------------------------------
def pick_file() -> str:
    """Open a Tkinter dialog to pick a .csi file."""
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


# ---------------------------------------------------------------------
#   TIMESTAMP HELPER (OPTIONAL, for future use)
# ---------------------------------------------------------------------
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


# ---------------------------------------------------------------------
#   LOAD CSI → Amp, Phase (N x K)
# ---------------------------------------------------------------------
def load_csi(path):
    """
    Load a PicoScenes .csi file and build amplitude & phase matrices.

    Returns:
        Amp   : ndarray, shape (N_frames, N_subcarriers)
        Phase : ndarray, shape (N_frames, N_subcarriers)
    """
    ps = Picoscenes(path)
    frames = ps.raw

    # CSI-bearing frames only
    csi_frames = [f for f in frames if isinstance(f.get("CSI"), dict)]
    if not csi_frames:
        raise RuntimeError("No frames with 'CSI' field found in this file.")

    Amp_list = []
    Phase_list = []

    for f in csi_frames:
        c = f.get("CSI")
        if not isinstance(c, dict):
            continue

        mag = np.array(c.get("Mag"))
        ph = np.array(c.get("Phase"))

        if mag.size == 0 or ph.size == 0:
            continue

        mag = mag.flatten()
        ph = ph.flatten()

        # Ensure consistent subcarrier count
        if Amp_list and mag.size != Amp_list[0].size:
            # Skip frames with mismatched size
            continue

        Amp_list.append(mag)
        Phase_list.append(ph)

    if not Amp_list:
        raise RuntimeError("No valid CSI Mag/Phase arrays found in frames.")

    Amp = np.vstack(Amp_list)
    Phase = np.vstack(Phase_list)

    return Amp, Phase


# ---------------------------------------------------------------------
#   SAVE FIGURE UTILITY
# ---------------------------------------------------------------------
def save_fig(fig, out_dir, filename):
    os.makedirs(out_dir, exist_ok=True)
    path = os.path.join(out_dir, filename)
    fig.savefig(path, dpi=200, bbox_inches="tight")
    plt.close(fig)
    print(f"[+] Saved: {path}")


# ---------------------------------------------------------------------
#   VISUALIZATIONS
# ---------------------------------------------------------------------
def plot_amplitude_heatmap(Amp, out_dir, base_name):
    """
    Heatmap: Frame index vs Subcarrier index, color = amplitude.
    This is great for seeing gesture-induced distortions.
    """
    N, K = Amp.shape
    fig, ax = plt.subplots(figsize=(10, 5))
    im = ax.imshow(
        Amp,
        aspect="auto",
        origin="lower",
        interpolation="nearest"
    )
    ax.set_xlabel("Subcarrier Index")
    ax.set_ylabel("Frame Index")
    ax.set_title("CSI Amplitude Heatmap")
    cbar = fig.colorbar(im)
    cbar.set_label("Amplitude")

    fname = f"{base_name}_AmplitudeHeatmap.png"
    save_fig(fig, out_dir, fname)


def plot_phase_heatmap(Phase, out_dir, base_name):
    """
    Heatmap: Frame index vs Subcarrier index, color = phase.
    Phase is highly sensitive to motion; visual structure changes a lot.
    """
    N, K = Phase.shape
    fig, ax = plt.subplots(figsize=(10, 5))
    im = ax.imshow(
        Phase,
        aspect="auto",
        origin="lower",
        interpolation="nearest"
    )
    ax.set_xlabel("Subcarrier Index")
    ax.set_ylabel("Frame Index")
    ax.set_title("CSI Phase Heatmap")
    cbar = fig.colorbar(im)
    cbar.set_label("Phase (rad)")

    fname = f"{base_name}_PhaseHeatmap.png"
    save_fig(fig, out_dir, fname)


def plot_variance_over_time(Amp, out_dir, base_name):
    """
    Short-term variance of amplitude over frames:
        Var(t) = variance across subcarriers at frame t
    Static environments → low, flat variance.
    Gesture motion     → clear spikes during movement.
    """
    var_over_time = np.var(Amp, axis=1)

    fig, ax = plt.subplots(figsize=(10, 4))
    ax.plot(var_over_time)
    ax.set_xlabel("Frame Index")
    ax.set_ylabel("Variance (across subcarriers)")
    ax.set_title("CSI Amplitude Variance Over Time")
    ax.grid(True)

    fname = f"{base_name}_VariancePlot.png"
    save_fig(fig, out_dir, fname)


def plot_pca_over_time(Amp, out_dir, base_name):
    """
    PCA on CSI amplitude matrix (frames x subcarriers).
    We project onto the first principal component:

        X_centered = Amp - mean(Amp, axis=0)
        PC1 scores = X_centered @ v1

    For static CSI → PC1 is nearly flat.
    For gesture CSI → clear oscillatory patterns.
    """
    # Center the data along subcarrier axis
    X = Amp - Amp.mean(axis=0, keepdims=True)

    # SVD-based PCA (no sklearn dependency)
    # X = U S V^T → first principal component direction is V[0]
    U, S, Vt = np.linalg.svd(X, full_matrices=False)

    # Scores along first PC:
    pc1_scores = U[:, 0] * S[0]

    # Normalize for nicer plotting
    if np.max(np.abs(pc1_scores)) > 0:
        pc1_scores = pc1_scores / np.max(np.abs(pc1_scores))

    fig, ax = plt.subplots(figsize=(10, 4))
    ax.plot(pc1_scores)
    ax.set_xlabel("Frame Index")
    ax.set_ylabel("PC1 (normalized)")
    ax.set_title("PCA of CSI Amplitude (First Component)")
    ax.grid(True)

    fname = f"{base_name}_PCAPlot.png"
    save_fig(fig, out_dir, fname)


# ---------------------------------------------------------------------
#   MAIN ANALYSIS FUNCTION
# ---------------------------------------------------------------------
def analyze_csi(path):
    base_name = os.path.splitext(os.path.basename(path))[0]
    out_dir = f"{base_name}+Visuals"

    print(f"\n[+] Loading CSI from: {path}")
    print(f"[+] Output folder   : {out_dir}\n")

    Amp, Phase = load_csi(path)
    print(f"[i] CSI shape (Amp): {Amp.shape[0]} frames x {Amp.shape[1]} subcarriers")

    # Generate the four visualizations
    plot_amplitude_heatmap(Amp, out_dir, base_name)
    plot_phase_heatmap(Phase, out_dir, base_name)
    plot_variance_over_time(Amp, out_dir, base_name)
    plot_pca_over_time(Amp, out_dir, base_name)

    print("\n[✓] All visualizations generated.\n")


# ---------------------------------------------------------------------
#   ENTRY POINT
# ---------------------------------------------------------------------
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
        # Optional: show a small completion popup
        try:
            root = tk.Tk()
            root.withdraw()
            messagebox.showinfo(
                "CSI Visualizations",
                "Visualizations generated successfully.\n"
                f"Check the folder:\n{os.path.splitext(os.path.basename(path))[0]}+Visuals"
            )
            root.destroy()
        except Exception:
            # If Tk fails (e.g., no DISPLAY), just ignore
            pass
    except Exception as e:
        try:
            root = tk.Tk()
            root.withdraw()
            messagebox.showerror("Error", f"Failed to process CSI file:\n{e}")
            root.destroy()
        except Exception:
            pass
        print(f"\nERROR while processing CSI file: {e}\n")


if __name__ == "__main__":
    main()

# CSI Collection SSH for 300 seconds
# Use 6 Devices - 1 AP, 1 Sniffer, 2 BFI, 2 CSI [Different NIC]
# Use the Camera to collect Data
# Make a Digital Image of the Room