#!/usr/bin/env python3
"""
MATLAB-style CSI metadata printer with derived fields:
  CarrierFreq2, IsMerged, TimingOffsets, PhaseSlope, PhaseIntercept

Matches MATLAB parseCSIFile() behavior even though these fields
are NOT stored in the raw .csi file.
"""

import sys
import numpy as np
import tkinter as tk
from tkinter import filedialog
from picoscenes import Picoscenes


def pick_file():
    root = tk.Tk()
    root.withdraw()
    root.update()
    path = filedialog.askopenfilename(
        title="Select CSI File",
        filetypes=[("CSI Files", "*.csi"), ("All Files", "*.*")]
    )
    root.destroy()
    if not path:
        sys.exit("No file selected.")
    print(f"\nSelected File: {path}\n")
    return path


def print_kv(key, value):
    print(f"{key:<18} {value}")


def sci(x):
    return f"{float(x):.4e}"


def shape_desc(arr):
    arr = np.array(arr)
    dims = " x ".join(str(d) for d in arr.shape)
    if np.iscomplexobj(arr):
        return f"({dims}) complex double"
    return f"({dims}) double"


def compute_phase_regression(Phase, sc_idx, num_rx):
    """
    MATLAB-style PhaseSlope and PhaseIntercept computation:
    For each RX antenna, fit:
         phase = slope * sc_index + intercept
    """
    Phase = np.array(Phase)
    sc_idx = np.array(sc_idx)
    result = []

    for r in range(num_rx):
        y = Phase[:, r, 0]     # phase for RX r
        x = sc_idx.astype(float)

        # least squares: slope, intercept
        A = np.vstack([x, np.ones_like(x)]).T
        slope, intercept = np.linalg.lstsq(A, y, rcond=None)[0]
        result.append([slope, intercept])

    return np.array(result)


def show_metadata(path):
    ps = Picoscenes(path)
    frames = ps.raw

    # Find first CSI-bearing frame
    csi = None
    rx_basic = None
    for f in frames:
        if isinstance(f.get("CSI"), dict):
            csi = f["CSI"]
            rx_basic = f.get("RxSBasic")
            break

    if csi is None:
        print("No CSI found.")
        return

    print("\n========== CSI METADATA ==========\n")

    # Existing raw fields
    fields = {
        "DeviceType": csi.get("DeviceType"),
        "FirmwareVersion": csi.get("FirmwareVersion"),
        "PacketFormat": csi.get("PacketFormat"),
        "CBW": csi.get("CBW"),
        "CarrierFreq": sci(csi.get("CarrierFreq")),
        "SamplingRate": csi.get("SamplingRate"),
        "SubcarrierBandwidth": csi.get("SubcarrierBandwidth"),
        "NumTones": csi.get("numTones"),
        "NumTx": csi.get("numTx"),
        "NumRx": csi.get("numRx"),
        "NumESS": csi.get("numESS"),
        "NumCSI": csi.get("numCSI"),
        "ANTSEL": csi.get("ant_sel"),
    }

    # Derived MATLAB-style fields
    fields["CarrierFreq2"] = sci(csi.get("CarrierFreq"))
    fields["IsMerged"] = 0

    # TimingOffsets (MATLAB uses frame index or timestamp)
    if isinstance(rx_basic, dict) and "Timestamp" in rx_basic:
        fields["TimingOffsets"] = rx_basic["Timestamp"][0]
    else:
        fields["TimingOffsets"] = 0

    # Print all scalar metadata
    for key, val in fields.items():
        print_kv(key, val)

    # ---------- Build CSI matrices ----------
    CSI = np.array(csi["CSI"])
    Mag = np.array(csi["Mag"])
    Phase = np.array(csi["Phase"])
    sc_idx = np.array(csi["SubcarrierIndex"])

    num_tones = int(csi["numTones"])
    num_rx = int(csi["numRx"])
    num_tx = int(csi["numTx"])

    if CSI.ndim == 1:
        CSI = CSI.reshape(num_tones, num_rx, num_tx)
        Mag = Mag.reshape(num_tones, num_rx, num_tx)
        Phase = Phase.reshape(num_tones, num_rx, num_tx)

    print_kv("CSI", shape_desc(CSI))
    print_kv("Mag", shape_desc(Mag))
    print_kv("Phase", shape_desc(Phase))
    print_kv("SubcarrierIndex", f"(1 x {sc_idx.size}) double")

    # ---------- Compute MATLAB-style PhaseSlope & PhaseIntercept ----------
    PhaseSlopeIntercept = compute_phase_regression(Phase, sc_idx, num_rx)

    print_kv("PhaseSlope", str(PhaseSlopeIntercept[:,0])[:80] + "...")
    print_kv("PhaseIntercept", str(PhaseSlopeIntercept[:,1])[:80] + "...")

    print("\n=================================\n")


if __name__ == "__main__":
    filepath = sys.argv[1] if len(sys.argv) == 2 else pick_file()
    show_metadata(filepath)
