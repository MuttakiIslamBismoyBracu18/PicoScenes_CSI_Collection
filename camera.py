#!/usr/bin/env python3
import os
import time
import csv
import signal
from pathlib import Path

import cv2
import numpy as np

# =========================
# User settings
# =========================
DURATION_SECONDS = float(os.environ.get("CAM_DURATION", "30.0"))
SAVE_EVERY_N_FRAMES = 1
PREVIEW = True
DEPTH_VIS_ALPHA = 0.03

COLOR_DEV = "/dev/video2"
DEPTH_DEV = "/dev/video4"
IR_DEV    = "/dev/video6"

COLOR_W, COLOR_H, COLOR_FPS = 1280, 720, 30
DEPTH_W, DEPTH_H, DEPTH_FPS = 640, 576, 30
IR_W, IR_H, IR_FPS = 640, 576, 30

VIDEO_CODEC = "mp4v"

# =========================
# Signal handling (CRITICAL)
# =========================
STOP_REQUESTED = False

def _handle_stop(signum, frame):
    global STOP_REQUESTED
    STOP_REQUESTED = True
    print(f"[INFO] Stop requested (signal={signum}). Finishing cleanly...", flush=True)

signal.signal(signal.SIGINT, _handle_stop)
signal.signal(signal.SIGTERM, _handle_stop)

# =========================
# Helpers
# =========================
def now_ms():
    return int(time.time() * 1000)

def mono_s():
    return time.monotonic()

def ensure_dirs(session_dir: Path):
    (session_dir / "video").mkdir(parents=True, exist_ok=True)
    (session_dir / "images" / "rgb").mkdir(parents=True, exist_ok=True)
    (session_dir / "images" / "depth").mkdir(parents=True, exist_ok=True)
    (session_dir / "images" / "ir").mkdir(parents=True, exist_ok=True)

def as_gray(frame):
    if frame is None:
        return frame
    if frame.ndim == 2:
        return frame
    if frame.ndim == 3:
        return cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    return frame

def devnode_to_index(devnode: str) -> int:
    base = os.path.basename(devnode)
    return int(base.replace("video", ""))

def open_v4l2(devnode, w, h, fps):
    idx = devnode_to_index(devnode)
    cap = cv2.VideoCapture(idx, cv2.CAP_V4L2)
    if not cap.isOpened():
        raise RuntimeError(f"Failed to open {devnode}")
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, w)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, h)
    cap.set(cv2.CAP_PROP_FPS, fps)
    cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
    return cap

def clamp(x, lo, hi):
    return max(lo, min(hi, x))

def compute_measured_fps(csv_path: Path):
    ts = []
    with open(csv_path) as f:
        r = csv.DictReader(f)
        for row in r:
            if row["rgb_png"]:
                ts.append(int(row["unix_ms"]))
    if len(ts) < 2:
        return float(COLOR_FPS)
    dur = (ts[-1] - ts[0]) / 1000.0
    return clamp((len(ts) - 1) / dur if dur > 0 else COLOR_FPS, 1.0, 120.0)

def encode_rgb_video_from_png(rgb_dir: Path, out_path: Path, fps: float):
    frames = sorted(rgb_dir.glob("rgb_*.png"))
    first = cv2.imread(str(frames[0]))
    h, w = first.shape[:2]
    vw = cv2.VideoWriter(
        str(out_path),
        cv2.VideoWriter_fourcc(*VIDEO_CODEC),
        fps,
        (w, h),
    )
    for p in frames:
        img = cv2.imread(str(p))
        if img is not None:
            vw.write(img)
    vw.release()
    return len(frames)

# =========================
# Main
# =========================
def main():
    script_dir = Path(__file__).resolve().parent
    root = script_dir / "captured"
    root.mkdir(exist_ok=True)

    session = time.strftime("%Y%m%d_%H%M%S")
    session_dir = root / session
    ensure_dirs(session_dir)

    video_dir = session_dir / "video"
    rgb_dir = session_dir / "images" / "rgb"
    depth_dir = session_dir / "images" / "depth"
    ir_dir = session_dir / "images" / "ir"

    session_start_ms = now_ms()
    (session_dir / "session_start_ms.txt").write_text(str(session_start_ms))

    color_cap = open_v4l2(COLOR_DEV, COLOR_W, COLOR_H, COLOR_FPS)
    depth_cap = open_v4l2(DEPTH_DEV, DEPTH_W, DEPTH_H, DEPTH_FPS)
    ir_cap    = open_v4l2(IR_DEV, IR_W, IR_H, IR_FPS)

    csv_path = session_dir / "frames.csv"

    with open(csv_path, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow([
            "frame_idx","unix_ms",
            "rgb_ok","depth_ok","ir_ok",
            "rgb_png","depth_png","ir_png"
        ])

        print(f"[INFO] Session directory: {session_dir}")
        print(f"[INFO] Capture duration target: {DURATION_SECONDS}s")

        deadline = mono_s() + DURATION_SECONDS
        frame_idx = 0

        try:
            while mono_s() < deadline and not STOP_REQUESTED:
                ok_c, color = color_cap.read()
                ok_d, depth = depth_cap.read()
                ok_i, ir    = ir_cap.read()

                if not (ok_c or ok_d or ok_i):
                    time.sleep(0.001)
                    continue

                t = now_ms()
                rgb_p = depth_p = ir_p = ""

                if frame_idx % SAVE_EVERY_N_FRAMES == 0:
                    if ok_c:
                        rgb_p = rgb_dir / f"rgb_{frame_idx:06d}_{t}.png"
                        cv2.imwrite(str(rgb_p), color)
                    if ok_d:
                        depth_p = depth_dir / f"depth_{frame_idx:06d}_{t}.png"
                        cv2.imwrite(str(depth_p), as_gray(depth))
                    if ok_i:
                        ir_p = ir_dir / f"ir_{frame_idx:06d}_{t}.png"
                        cv2.imwrite(str(ir_p), as_gray(ir))

                writer.writerow([
                    frame_idx, t,
                    int(ok_c), int(ok_d), int(ok_i),
                    str(rgb_p), str(depth_p), str(ir_p)
                ])

                frame_idx += 1

                if PREVIEW:
                    if ok_c:
                        cv2.imshow("RGB", color)
                    if ok_d:
                        dv = cv2.applyColorMap(
                            cv2.convertScaleAbs(as_gray(depth), alpha=DEPTH_VIS_ALPHA),
                            cv2.COLORMAP_JET
                        )
                        cv2.imshow("Depth", dv)
                    if ok_i:
                        iv = cv2.normalize(as_gray(ir), None, 0, 255, cv2.NORM_MINMAX).astype(np.uint8)
                        cv2.imshow("IR", iv)
                    if cv2.waitKey(1) == 27:
                        break

        finally:
            color_cap.release()
            depth_cap.release()
            ir_cap.release()
            if PREVIEW:
                cv2.destroyAllWindows()

    print("[POST] Computing measured FPS...")
    fps = compute_measured_fps(csv_path)
    out_video = video_dir / "rgb_measured_fps.mp4"
    written = encode_rgb_video_from_png(rgb_dir, out_video, fps)

    print(f"[DONE] Encoded {written} frames @ {fps:.3f} fps")
    print(f"[DONE] RGB video: {out_video}")
    print(f"[DONE] Images root: {session_dir / 'images'}")
    print(f"[DONE] Log: {csv_path}")
    print(f"[DONE] Session start ms: {session_start_ms}")

if __name__ == "__main__":
    main()
