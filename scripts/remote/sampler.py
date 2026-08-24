#!/usr/bin/env python3
"""Sample GPU VRAM, host RAM, power, CPU during a timed block."""

from __future__ import annotations

import json
import os
import subprocess
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass, field

try:
    import psutil
except ImportError:
    psutil = None


@dataclass
class SamplePeak:
    peak_vram_mib: list[int] = field(default_factory=list)
    peak_host_ram_used_gb: float = 0.0
    peak_rss_gb: float = 0.0
    mean_gpu_power_w: list[float] = field(default_factory=list)
    peak_gpu_temp_c: list[float] = field(default_factory=list)
    mean_cpu_pct: float = 0.0
    samples: list[dict] = field(default_factory=list)
    memory_type: str = "discrete"


class Sampler:
    def __init__(self, interval: float = 1.5, pid: int | None = None, unified: bool = False):
        self.interval = interval
        self.pid = pid
        self.unified = unified
        self.peak = SamplePeak(memory_type="unified" if unified else "discrete")
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def _nvidia_smi(self) -> list[dict]:
        try:
            out = subprocess.check_output(
                [
                    "nvidia-smi",
                    "--query-gpu=index,memory.used,power.draw,temperature.gpu",
                    "--format=csv,noheader,nounits",
                ],
                text=True,
                timeout=10,
            )
        except (subprocess.CalledProcessError, FileNotFoundError):
            return []
        rows = []
        for line in out.strip().splitlines():
            parts = [p.strip() for p in line.split(",")]
            if len(parts) >= 4:
                rows.append(
                    {
                        "gpu_index": int(parts[0]),
                        "vram_mib": float(parts[1]),
                        "power_w": float(parts[2]) if parts[2] not in ("N/A", "[Not Supported]") else 0.0,
                        "temp_c": float(parts[3]) if parts[3] not in ("N/A",) else 0.0,
                    }
                )
        return rows

    def _host_ram_gb(self) -> tuple[float, float]:
        if psutil is None:
            return 0.0, 0.0
        vm = psutil.virtual_memory()
        return vm.total / (1024**3), (vm.total - vm.available) / (1024**3)

    def _rss_gb(self) -> float:
        if psutil is None or self.pid is None:
            return 0.0
        try:
            return psutil.Process(self.pid).memory_info().rss / (1024**3)
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            return 0.0

    def _loop(self) -> None:
        cpu_samples = []
        while not self._stop.is_set():
            gpus = self._nvidia_smi()
            total, used = self._host_ram_gb()
            rss = self._rss_gb()
            cpu = psutil.cpu_percent(interval=None) if psutil else 0.0
            cpu_samples.append(cpu)

            for g in gpus:
                self.peak.peak_vram_mib.append(int(g["vram_mib"]))
                self.peak.mean_gpu_power_w.append(g["power_w"])
                self.peak.peak_gpu_temp_c.append(g["temp_c"])

            self.peak.peak_host_ram_used_gb = max(self.peak.peak_host_ram_used_gb, used)
            self.peak.peak_rss_gb = max(self.peak.peak_rss_gb, rss)

            self.peak.samples.append(
                {
                    "t": time.time(),
                    "gpus": gpus,
                    "host_ram_used_gb": used,
                    "host_ram_total_gb": total,
                    "rss_gb": rss,
                    "cpu_pct": cpu,
                }
            )
            time.sleep(self.interval)

        if cpu_samples:
            self.peak.mean_cpu_pct = sum(cpu_samples) / len(cpu_samples)

    def start(self) -> None:
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()

    def stop(self) -> SamplePeak:
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=5)
        return self.peak

    def summary_dict(self) -> dict:
        p = self.peak
        return {
            "memory_type": p.memory_type,
            "peak_vram_mib_per_gpu": p.peak_vram_mib[-1:] if p.peak_vram_mib else [],
            "peak_vram_mib_max": max(p.peak_vram_mib) if p.peak_vram_mib else 0,
            "peak_host_ram_used_gb": round(p.peak_host_ram_used_gb, 2),
            "peak_rss_gb": round(p.peak_rss_gb, 2),
            "mean_gpu_power_w": round(sum(p.mean_gpu_power_w) / len(p.mean_gpu_power_w), 1) if p.mean_gpu_power_w else 0,
            "peak_gpu_temp_c": max(p.peak_gpu_temp_c) if p.peak_gpu_temp_c else 0,
            "mean_cpu_pct": round(p.mean_cpu_pct, 1),
        }


def timed_run(fn: Callable[[], None], interval: float = 1.5, unified: bool = False) -> tuple[float, dict]:
    sampler = Sampler(interval=interval, pid=os.getpid(), unified=unified)
    sampler.start()
    t0 = time.perf_counter()
    err = None
    try:
        fn()
    except Exception as e:
        err = str(e)
        raise
    finally:
        elapsed = time.perf_counter() - t0
        sampler.stop()
        summary = sampler.summary_dict()
        summary["wall_sec"] = round(elapsed, 3)
        summary["error"] = err
    return elapsed, summary


if __name__ == "__main__":
    def work():
        time.sleep(2)

    sec, s = timed_run(work)
    print(json.dumps(s, indent=2))
