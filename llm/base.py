from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.request
from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_TIMEOUT_SECONDS = 120


@dataclass(frozen=True)
class LLMResponse:
    text: str
    input_tokens: int
    output_tokens: int
    latency_ms: float
    tokens_per_second: float | None = None
    time_to_first_token_ms: float | None = None
    model_quantization: str | None = None
    ollama_version: str | None = None
    gpu_utilization_percent: float | None = None
    vram_used_mb: float | None = None


class LLMClient(ABC):
    provider: str
    model: str

    @abstractmethod
    def generate(
        self,
        system: str,
        prompt: str,
        temperature: float = 0.0,
    ) -> LLMResponse:
        raise NotImplementedError


def setting(name: str, default: str = "") -> str:
    value = os.getenv(name)
    if value:
        return value

    dotenv_path = ROOT / ".env"
    if not dotenv_path.is_file():
        return default
    for line in dotenv_path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        key, separator, raw_value = stripped.partition("=")
        if separator and key.strip() == name:
            raw_value = raw_value.strip()
            if len(raw_value) >= 2 and raw_value[0] == raw_value[-1] and raw_value[0] in {"'", '"'}:
                raw_value = raw_value[1:-1]
            return raw_value or default
    return default


def post_json(
    url: str,
    payload: dict[str, Any],
    headers: dict[str, str] | None = None,
) -> tuple[dict[str, Any], float]:
    request_headers = {"Content-Type": "application/json"}
    if headers:
        request_headers.update(headers)
    request = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers=request_headers,
        method="POST",
    )
    started = time.perf_counter()
    try:
        with urllib.request.urlopen(request, timeout=DEFAULT_TIMEOUT_SECONDS) as response:
            body = response.read()
    except urllib.error.HTTPError as exc:
        raise RuntimeError(f"LLM request failed with HTTP {exc.code} at {url}.") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"Could not reach LLM endpoint {url}: {exc.reason}.") from exc
    latency_ms = (time.perf_counter() - started) * 1000

    try:
        decoded = json.loads(body)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"LLM endpoint {url} returned invalid JSON.") from exc
    if not isinstance(decoded, dict):
        raise RuntimeError(f"LLM endpoint {url} returned a JSON value that is not an object.")
    return decoded, latency_ms


def token_count(value: Any, field: str, provider: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        raise RuntimeError(f"{provider} returned a missing or invalid {field} token count.")
    return value


def get_json(url: str) -> dict[str, Any]:
    request = urllib.request.Request(url, method="GET")
    try:
        with urllib.request.urlopen(request, timeout=10) as response:
            body = response.read()
    except urllib.error.HTTPError as exc:
        raise RuntimeError(f"LLM metadata request failed with HTTP {exc.code} at {url}.") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"Could not reach LLM endpoint {url}: {exc.reason}.") from exc
    try:
        decoded = json.loads(body)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"LLM endpoint {url} returned invalid JSON.") from exc
    if not isinstance(decoded, dict):
        raise RuntimeError(f"LLM endpoint {url} returned a JSON value that is not an object.")
    return decoded
