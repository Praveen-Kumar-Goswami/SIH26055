"""CPU demo-profile wall time and peak RSS. 60 s at 1 ms = 60_000 steps."""

from __future__ import annotations

import os
import time
from typing import Any

from smartscan.config import SimulateConfig, load_yaml, project_root
from smartscan.receiver.detector import load_receiver_config
from smartscan.receiver.scanner import run_schedule
from smartscan.receiver.schedules import SequentialSchedule

DEMO_DURATION_S = 60.0
DEMO_DT_S = 0.001
TARGET_WALL_S = 60.0
TARGET_RSS_BYTES = 2 * 1024 * 1024 * 1024


def peak_rss_bytes() -> int | None:
    if os.name == "nt":
        import ctypes
        from ctypes import wintypes

        class PROCESS_MEMORY_COUNTERS(ctypes.Structure):
            _fields_ = [
                ("cb", wintypes.DWORD),
                ("PageFaultCount", wintypes.DWORD),
                ("PeakWorkingSetSize", ctypes.c_size_t),
                ("WorkingSetSize", ctypes.c_size_t),
                ("QuotaPeakPagedPoolUsage", ctypes.c_size_t),
                ("QuotaPagedPoolUsage", ctypes.c_size_t),
                ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t),
                ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
                ("PagefileUsage", ctypes.c_size_t),
                ("PeakPagefileUsage", ctypes.c_size_t),
            ]

        counters = PROCESS_MEMORY_COUNTERS()
        counters.cb = ctypes.sizeof(PROCESS_MEMORY_COUNTERS)
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel32.GetCurrentProcess.restype = wintypes.HANDLE
        handle = kernel32.GetCurrentProcess()
        try:
            psapi = ctypes.WinDLL("psapi", use_last_error=True)
        except OSError:
            psapi = kernel32
        getter = getattr(psapi, "GetProcessMemoryInfo", None)
        if getter is None:
            return None
        getter.argtypes = [wintypes.HANDLE, ctypes.c_void_p, wintypes.DWORD]
        getter.restype = wintypes.BOOL
        ok = getter(handle, ctypes.byref(counters), counters.cb)
        if not ok:
            return None
        return int(counters.PeakWorkingSetSize)
    try:
        import resource
        import sys

        getrusage = getattr(resource, "getrusage", None)
        rusage_self = getattr(resource, "RUSAGE_SELF", None)
        if getrusage is None or rusage_self is None:
            return None
        usage = getrusage(rusage_self).ru_maxrss
        if sys.platform == "darwin":
            return int(usage)
        return int(usage) * 1024
    except Exception:
        return None


def measure_demo_profile(*, duration_s: float = DEMO_DURATION_S) -> dict[str, Any]:
    """Sequential scan of the demo band plan. Does not train."""

    receiver = load_receiver_config(load_yaml(project_root() / "configs" / "receiver.yaml"))
    sim = SimulateConfig(
        seed=42,
        dt_s=DEMO_DT_S,
        duration_s=float(duration_s),
        band_plan_id="demo_2_18",
        scenario_id="sparse",
    )
    t0 = time.perf_counter()
    from smartscan.rf.environment import simulate

    truth = simulate(sim)
    run = run_schedule(
        truth,
        SequentialSchedule(dwell_steps=8),
        receiver,
        receiver_seed=42,
        default_dwell_steps=8,
    )
    wall_s = time.perf_counter() - t0
    rss = peak_rss_bytes()
    return {
        "duration_s": float(duration_s),
        "n_steps": int(truth.n_steps),
        "n_bands": int(truth.band_plan.n_bands),
        "n_decisions": len(run.decisions.rows),
        "wall_s": wall_s,
        "peak_rss_bytes": rss,
        "peak_rss_gb": None if rss is None else rss / (1024**3),
        "target_wall_s": TARGET_WALL_S,
        "target_rss_bytes": TARGET_RSS_BYTES,
        "wall_within_target": wall_s < TARGET_WALL_S,
        "rss_within_target": rss is None or rss < TARGET_RSS_BYTES,
        "strategy": "sequential",
        "scenario_id": "sparse",
        "seed": 42,
    }
