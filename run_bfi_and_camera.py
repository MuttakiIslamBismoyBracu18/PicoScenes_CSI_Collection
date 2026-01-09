#!/usr/bin/env python3
import os
import sys
import time
import signal
import subprocess
from pathlib import Path
from datetime import datetime
import re

HERE = Path(__file__).resolve().parent

BFI_SCRIPT = HERE / "bfi_capture.py"
CAM_SCRIPT = HERE / "camera.py"

LOGS_DIR = HERE / "run_logs"
LOGS_DIR.mkdir(exist_ok=True)

# Strongly prefer explicit markers from bfi_capture.py:
#   print("[CAPTURE] Started", flush=True)
#   print(f"[CAPTURE] Saved: {final}", flush=True)
BFI_START_PATTERNS = [
    r"\[CAPTURE\]\s+Started",
]

BFI_STOP_PATTERNS = [
    r"\[CAPTURE\]\s+Saved:",
    r"No capture file\.",   # bfi_capture.py exits with this message
]

WAIT_BFI_START_TIMEOUT_S = 600
CAMERA_GRACEFUL_TIMEOUT_S = 180


def ts() -> str:
    return datetime.now().strftime("%Y%m%d_%H%M%S")


def is_root() -> bool:
    return os.geteuid() == 0


def maybe_sudo_exec():
    if is_root():
        return
    print("[INFO] Re-running with sudo to allow BFI capture...")
    os.execvp("sudo", ["sudo", "-E", sys.executable, str(Path(__file__).resolve())] + sys.argv[1:])


def start_process(cmd, log_path: Path, env: dict | None = None):
    """
    Start child process in its own process group; redirect stdout+stderr to log_path.
    """
    log_f = open(log_path, "w", buffering=1)
    p = subprocess.Popen(
        cmd,
        stdout=log_f,
        stderr=subprocess.STDOUT,
        text=True,
        preexec_fn=os.setsid,
        env=env,
    )
    return p, log_f


def terminate_process_group(p: subprocess.Popen | None, name: str, timeout: float = 8.0):
    """
    Hard stop fallback: SIGTERM then SIGKILL.
    """
    if p is None or p.poll() is not None:
        return
    try:
        os.killpg(p.pid, signal.SIGTERM)
        t0 = time.time()
        while time.time() - t0 < timeout:
            if p.poll() is not None:
                return
            time.sleep(0.1)
        os.killpg(p.pid, signal.SIGKILL)
    except ProcessLookupError:
        return
    except Exception as e:
        print(f"[WARN] Failed to terminate {name}: {e}", file=sys.stderr)


def interrupt_then_wait(p: subprocess.Popen | None, name: str, timeout: float):
    """
    Graceful stop: SIGINT (like Ctrl+C) then wait.
    Critical for camera.py to finalize MP4 safely.
    """
    if p is None or p.poll() is not None:
        return
    try:
        os.killpg(p.pid, signal.SIGINT)
    except ProcessLookupError:
        return
    except Exception as e:
        print(f"[WARN] Failed to SIGINT {name}: {e}", file=sys.stderr)
        terminate_process_group(p, name)
        return

    t0 = time.time()
    while time.time() - t0 < timeout:
        if p.poll() is not None:
            return
        time.sleep(0.1)

    print(f"[WARN] {name} did not exit after SIGINT; forcing termination...")
    terminate_process_group(p, name)


def print_save_locations():
    cam_root = CAM_SCRIPT.resolve().parent / "captured"
    user = os.environ.get("SUDO_USER") or os.environ.get("USER") or "unknown"
    bfi_outdir = Path("/home") / user / "captures"
    print("\n[SAVE LOCATIONS]")
    print(f"  Camera sessions root: {cam_root}")
    print(f"  BFI captures OUTDIR:  {bfi_outdir}")
    print("[END SAVE LOCATIONS]\n")


def _compiled(patterns):
    return [re.compile(p) for p in patterns]


def wait_for_log_pattern(log_path: Path, patterns, timeout_s: float | None):
    """
    Robust log watcher:
      - scans existing content from the beginning
      - then tails for new lines
    Returns the matching line (str) or None on timeout.
    """
    compiled = _compiled(patterns)
    start_t = time.time()

    # Wait for the file to exist
    while not log_path.exists():
        if timeout_s is not None and time.time() - start_t > timeout_s:
            return None
        time.sleep(0.05)

    with open(log_path, "r", errors="replace") as f:
        # 1) Scan existing content immediately (prevents race)
        existing = f.read()
        for line in existing.splitlines():
            for rgx in compiled:
                if rgx.search(line):
                    return line.strip()

        # 2) Tail for new lines
        while True:
            line = f.readline()
            if not line:
                if timeout_s is not None and time.time() - start_t > timeout_s:
                    return None
                time.sleep(0.05)
                continue

            for rgx in compiled:
                if rgx.search(line):
                    return line.strip()


def main():
    maybe_sudo_exec()

    if not BFI_SCRIPT.exists():
        sys.exit(f"[FATAL] BFI script not found: {BFI_SCRIPT}")
    if not CAM_SCRIPT.exists():
        sys.exit(f"[FATAL] Camera script not found: {CAM_SCRIPT}")

    run_id = ts()
    bfi_log = LOGS_DIR / f"bfi_{run_id}.log"
    cam_log = LOGS_DIR / f"camera_{run_id}.log"

    print(f"[INFO] Logs:\n  BFI:   {bfi_log}\n  Camera:{cam_log}")
    print_save_locations()

    bfi_p = cam_p = None
    bfi_f = cam_f = None

    # Unbuffered output is important because stdout is redirected to a file.
    base_env = os.environ.copy()
    base_env["PYTHONUNBUFFERED"] = "1"

    try:
        # 1) Start BFI first (GUI opens)
        bfi_cmd = [sys.executable, str(BFI_SCRIPT)]
        bfi_p, bfi_f = start_process(bfi_cmd, bfi_log, env=base_env)
        print(f"[INFO] BFI started (pid={bfi_p.pid})")
        print("[INFO] Waiting for BFI capture to START (click Start Capture in the GUI)...")

        start_line = wait_for_log_pattern(bfi_log, BFI_START_PATTERNS, timeout_s=WAIT_BFI_START_TIMEOUT_S)
        if start_line is None:
            print("[ERROR] Timed out waiting for BFI capture to start. Stopping BFI.")
            return
        print(f"[INFO] Detected BFI capture start: {start_line}")

        # 2) Start camera ONLY after BFI capture has truly started
        cam_env = base_env.copy()
        # Optional: run effectively "until stopped by SIGINT" from the launcher
        cam_env["CAM_DURATION"] = "999999"
        cam_cmd = [sys.executable, str(CAM_SCRIPT)]
        cam_p, cam_f = start_process(cam_cmd, cam_log, env=cam_env)
        print(f"[INFO] Camera started (pid={cam_p.pid})")

        # 3) Wait for BFI to stop/save
        print("[INFO] Waiting for BFI capture to STOP...")
        stop_line = wait_for_log_pattern(bfi_log, BFI_STOP_PATTERNS, timeout_s=None)
        print(f"[INFO] Detected BFI capture stop: {stop_line}")

        # 4) Gracefully stop camera (prevents MP4 corruption)
        print("[INFO] Requesting camera stop (SIGINT) so it can finalize MP4...")
        interrupt_then_wait(cam_p, "Camera", timeout=CAMERA_GRACEFUL_TIMEOUT_S)

    except KeyboardInterrupt:
        print("\n[INFO] Ctrl+C received. Stopping both...")
        interrupt_then_wait(cam_p, "Camera", timeout=CAMERA_GRACEFUL_TIMEOUT_S)

    finally:
        terminate_process_group(bfi_p, "BFI")

        try:
            if cam_f:
                cam_f.close()
        except Exception:
            pass
        try:
            if bfi_f:
                bfi_f.close()
        except Exception:
            pass

        print("[DONE] Session ended.")


if __name__ == "__main__":
    main()
