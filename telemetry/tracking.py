from __future__ import annotations

import csv
import functools
import json
import os
import platform
import threading
import time
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, ParamSpec, TypeVar, cast

import psycopg

from llm.base import LLMResponse, ROOT, setting
from telemetry.gpu import GPUUsageSampler


P = ParamSpec("P")
R = TypeVar("R")
CSV_FIELDS = (
    "started_at",
    "agent",
    "provider",
    "model",
    "model_quantization",
    "ollama_version",
    "equipment",
    "input_tokens",
    "output_tokens",
    "latency_ms",
    "tokens_per_second",
    "time_to_first_token_ms",
    "gpu_utilization_percent",
    "vram_used_mb",
    "status",
    "error_type",
)
_CSV_LOCK = threading.Lock()


def track_llm_call(
    function: Callable[P, R] | None = None,
    *,
    agent: str | None = None,
) -> Callable[P, R] | Callable[[Callable[P, R]], Callable[P, R]]:
    def decorate(method: Callable[P, R]) -> Callable[P, R]:
        @functools.wraps(method)
        def wrapped(*args: P.args, **kwargs: P.kwargs) -> R:
            started_at = datetime.now(timezone.utc)
            started = time.perf_counter()
            client = args[0] if args else None
            selected_agent = agent or setting("TELEMETRY_AGENT", "unspecified")
            sample_gpu = setting("TELEMETRY_COLLECT_GPU", "0").lower() in {"1", "true", "yes"}
            sampler = GPUUsageSampler() if sample_gpu else None
            try:
                if sampler is None:
                    response = method(*args, **kwargs)
                else:
                    with sampler:
                        response = method(*args, **kwargs)
            except Exception as exc:
                record = _base_record(started_at, selected_agent, client)
                record.update(
                    latency_ms=(time.perf_counter() - started) * 1000,
                    status="error",
                    error_type=type(exc).__name__,
                    gpu_utilization_percent=(
                        sampler.gpu_utilization_percent if sampler else None
                    ),
                    vram_used_mb=sampler.vram_used_mb if sampler else None,
                )
                record_llm_call(record)
                raise

            if not isinstance(response, LLMResponse):
                record = _base_record(started_at, selected_agent, client)
                record.update(
                    latency_ms=(time.perf_counter() - started) * 1000,
                    status="error",
                    error_type="TypeError",
                )
                record_llm_call(record)
                raise TypeError(
                    f"{method.__qualname__} must return LLMResponse for telemetry tracking."
                )
            record = _base_record(started_at, selected_agent, client)
            record.update(
                model_quantization=response.model_quantization,
                ollama_version=response.ollama_version,
                input_tokens=response.input_tokens,
                output_tokens=response.output_tokens,
                latency_ms=response.latency_ms,
                tokens_per_second=_tokens_per_second(response),
                time_to_first_token_ms=response.time_to_first_token_ms,
                gpu_utilization_percent=(
                    sampler.gpu_utilization_percent if sampler else None
                ),
                vram_used_mb=sampler.vram_used_mb if sampler else None,
                status="success",
                error_type=None,
            )
            record_llm_call(record)
            if sampler is not None:
                response = replace(
                    response,
                    gpu_utilization_percent=sampler.gpu_utilization_percent,
                    vram_used_mb=sampler.vram_used_mb,
                )
            return cast(R, response)

        return wrapped

    if function is not None:
        return decorate(function)
    return decorate


def _base_record(
    started_at: datetime,
    agent: str,
    client: Any,
) -> dict[str, Any]:
    return {
        "started_at": started_at,
        "agent": agent,
        "provider": getattr(client, "provider", "unknown"),
        "model": getattr(client, "model", "unknown"),
        "model_quantization": getattr(client, "model_quantization", None),
        "ollama_version": getattr(client, "ollama_version", None),
        "equipment": _equipment_description(),
        "input_tokens": None,
        "output_tokens": None,
        "latency_ms": None,
        "tokens_per_second": None,
        "time_to_first_token_ms": None,
        "gpu_utilization_percent": None,
        "vram_used_mb": None,
        "status": "error",
        "error_type": None,
    }


def _equipment_description() -> str:
    processor = platform.processor() or platform.machine()
    return f"{platform.node()} | {platform.system()} {platform.release()} | {processor}"


def _tokens_per_second(response: LLMResponse) -> float | None:
    if response.tokens_per_second is not None:
        return response.tokens_per_second
    if response.latency_ms <= 0:
        return None
    return response.output_tokens / (response.latency_ms / 1000)


def record_llm_call(record: dict[str, Any]) -> None:
    sink = setting("TELEMETRY_SINK", "csv").lower()
    if sink == "database":
        _insert_database_record(record)
        return
    if sink == "csv":
        _append_csv_record(record)
        return
    raise RuntimeError("TELEMETRY_SINK must be 'database' or 'csv'.")


def _append_csv_record(record: dict[str, Any]) -> None:
    path = Path(setting("TELEMETRY_CSV_PATH", str(ROOT / "telemetry" / "results" / "llm_calls.csv")))
    path.parent.mkdir(parents=True, exist_ok=True)
    with _CSV_LOCK:
        write_header = not path.exists() or path.stat().st_size == 0
        with path.open("a", encoding="utf-8-sig", newline="") as output:
            writer = csv.DictWriter(output, fieldnames=CSV_FIELDS)
            if write_header:
                writer.writeheader()
            writer.writerow(
                {
                    **record,
                    "started_at": record["started_at"].isoformat(),
                }
            )


def _insert_database_record(record: dict[str, Any]) -> None:
    settings = _database_settings()
    with psycopg.connect(**settings) as conn:
        with conn.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO telemetry.llm_calls (
                    started_at, agent, provider, model, model_quantization,
                    ollama_version, equipment, input_tokens, output_tokens,
                    latency_ms, tokens_per_second, time_to_first_token_ms,
                    gpu_utilization_percent, vram_used_mb, status, error_type
                )
                VALUES (
                    %(started_at)s, %(agent)s, %(provider)s, %(model)s,
                    %(model_quantization)s, %(ollama_version)s, %(equipment)s,
                    %(input_tokens)s, %(output_tokens)s, %(latency_ms)s,
                    %(tokens_per_second)s, %(time_to_first_token_ms)s,
                    %(gpu_utilization_percent)s, %(vram_used_mb)s, %(status)s,
                    %(error_type)s
                )
                """,
                record,
            )


def _database_settings() -> dict[str, str]:
    host = setting("DB_HOST", "localhost")
    if host in {"db", "host.docker.internal"} and not Path("/.dockerenv").exists():
        host = "127.0.0.1"
    return {
        "host": host,
        "port": setting("DB_PORT_HOST", setting("DB_PORT", "5432")),
        "dbname": setting("DB_NAME", setting("POSTGRES_DB", "auditor_contrataciones")),
        "user": setting("DB_USER", setting("ETL_USER", "postgres")),
        "password": setting("DB_PASSWORD", setting("ETL_USER_PASSWORD")),
    }


def export_llm_calls_csv(output_path: Path) -> int:
    sink = setting("TELEMETRY_SINK", "csv").lower()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    if sink == "csv":
        source = Path(
            setting("TELEMETRY_CSV_PATH", str(ROOT / "telemetry" / "results" / "llm_calls.csv"))
        )
        if not source.exists():
            raise FileNotFoundError(f"No local telemetry CSV exists yet: {source}")
        if source.resolve() == output_path.resolve():
            with source.open("r", encoding="utf-8-sig", newline="") as input_file:
                return sum(1 for _ in csv.DictReader(input_file))
        with source.open("r", encoding="utf-8-sig", newline="") as input_file:
            rows = list(csv.DictReader(input_file))
        with output_path.open("w", encoding="utf-8-sig", newline="") as output:
            writer = csv.DictWriter(output, fieldnames=CSV_FIELDS)
            writer.writeheader()
            writer.writerows(rows)
        return len(rows)
    if sink != "database":
        raise RuntimeError("TELEMETRY_SINK must be 'database' or 'csv'.")

    with psycopg.connect(**_database_settings()) as conn, output_path.open(
        "w", encoding="utf-8-sig", newline=""
    ) as output:
        with conn.cursor() as cursor:
            cursor.execute(
                f"SELECT {', '.join(CSV_FIELDS)} FROM telemetry.llm_calls ORDER BY id"
            )
            writer = csv.DictWriter(output, fieldnames=CSV_FIELDS)
            writer.writeheader()
            count = 0
            for row in cursor:
                writer.writerow(dict(zip(CSV_FIELDS, row)))
                count += 1
    return count
