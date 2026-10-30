from __future__ import annotations

import json
import os
import platform
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

os.environ["TELEMETRY_SINK"] = "csv"
os.environ.setdefault("TELEMETRY_COLLECT_GPU", "1")
os.environ.setdefault("AGENT_BASE_URL", "http://localhost:11434")

from llm.base import get_json, setting
from llm.ollama_client import OllamaClient


def _total_memory_bytes() -> int | None:
    if sys.platform == "win32":
        import ctypes

        class MemoryStatus(ctypes.Structure):
            _fields_ = [
                ("length", ctypes.c_ulong),
                ("memory_load", ctypes.c_ulong),
                ("total_physical", ctypes.c_ulonglong),
                ("available_physical", ctypes.c_ulonglong),
                ("total_page_file", ctypes.c_ulonglong),
                ("available_page_file", ctypes.c_ulonglong),
                ("total_virtual", ctypes.c_ulonglong),
                ("available_virtual", ctypes.c_ulonglong),
                ("available_extended_virtual", ctypes.c_ulonglong),
            ]

        status = MemoryStatus()
        status.length = ctypes.sizeof(status)
        if ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(status)):
            return status.total_physical
    if hasattr(os, "sysconf"):
        try:
            return os.sysconf("SC_PAGE_SIZE") * os.sysconf("SC_PHYS_PAGES")
        except (ValueError, OSError):
            return None
    return None


def main() -> int:
    client = OllamaClient()
    tags = get_json(f"{client.base_url}/api/tags")
    models = tags.get("models")
    if not isinstance(models, list):
        raise RuntimeError("Ollama /api/tags returned no model list.")
    installed_names = {
        item.get("name") or item.get("model")
        for item in models
        if isinstance(item, dict)
    }
    if client.model not in installed_names:
        raise RuntimeError(
            f"Model {client.model!r} is not installed. Run `ollama pull {client.model}` "
            "or set AGENT_MODEL to a name from `ollama list`."
        )

    response = client.generate(
        "Responde en español, solo una palabra.",
        "Di: listo.",
        temperature=0.0,
    )
    total_memory = _total_memory_bytes()
    result = {
        "host": platform.node(),
        "platform": platform.platform(),
        "cpu": platform.processor() or platform.machine(),
        "ram_gb": round(total_memory / (1024**3), 2) if total_memory else None,
        "provider": client.provider,
        "model": client.model,
        "quantization": response.model_quantization,
        "ollama_version": response.ollama_version,
        "response": response.text,
        "input_tokens": response.input_tokens,
        "output_tokens": response.output_tokens,
        "tokens_per_second": response.tokens_per_second,
        "latency_ms": response.latency_ms,
        "time_to_first_token_ms": response.time_to_first_token_ms,
        "gpu_utilization_percent": response.gpu_utilization_percent,
        "vram_used_mb": response.vram_used_mb,
        "telemetry_sink": setting("TELEMETRY_SINK", "csv"),
        "telemetry_csv": setting(
            "TELEMETRY_CSV_PATH",
            str(ROOT / "telemetry" / "results" / "llm_calls.csv"),
        ),
    }
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
