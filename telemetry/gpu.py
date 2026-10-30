from __future__ import annotations

import csv
import shutil
import subprocess
import threading


def read_gpu_metrics() -> tuple[float | None, float | None]:
    if shutil.which("nvidia-smi") is None:
        return None, None
    try:
        result = subprocess.run(
            [
                "nvidia-smi",
                "--query-gpu=utilization.gpu,memory.used",
                "--format=csv,noheader,nounits",
            ],
            capture_output=True,
            check=False,
            text=True,
            timeout=2,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None, None
    if result.returncode != 0 or not result.stdout.strip():
        return None, None

    utilizations: list[float] = []
    memory_used: list[float] = []
    for row in csv.reader(result.stdout.splitlines()):
        if len(row) != 2:
            return None, None
        try:
            utilizations.append(float(row[0].strip()))
            memory_used.append(float(row[1].strip()))
        except ValueError:
            return None, None
    return max(utilizations), sum(memory_used)


class GPUUsageSampler:
    def __init__(self, interval_seconds: float = 0.25) -> None:
        self.interval_seconds = interval_seconds
        self.gpu_utilization_percent: float | None = None
        self.vram_used_mb: float | None = None
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def __enter__(self) -> GPUUsageSampler:
        self._sample()
        if self.gpu_utilization_percent is not None:
            self._thread = threading.Thread(target=self._sample_until_stopped, daemon=True)
            self._thread.start()
        return self

    def __exit__(self, *_args: object) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=3)

    def _sample_until_stopped(self) -> None:
        while not self._stop.wait(self.interval_seconds):
            self._sample()

    def _sample(self) -> None:
        utilization, memory_used = read_gpu_metrics()
        if utilization is None:
            return
        self.gpu_utilization_percent = max(
            utilization,
            self.gpu_utilization_percent or 0.0,
        )
        self.vram_used_mb = max(memory_used or 0.0, self.vram_used_mb or 0.0)
