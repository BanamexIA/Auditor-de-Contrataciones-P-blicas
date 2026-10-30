from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import os
import platform
import re
import statistics
import subprocess
import time
import urllib.parse
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

import psycopg
import sqlglot
import yaml
from psycopg.rows import dict_row, tuple_row
from sqlglot import exp

from etl.db_config import database_settings
from llm.base import LLMClient, LLMResponse, get_json, post_json, setting
from llm.cloud_client import CloudClient
from llm.ollama_client import OllamaClient
from rag.core import (
    OllamaEmbeddingClient,
    check_embedding_configuration,
    ollama_settings,
    retrieve,
)
from telemetry.gpu import GPUUsageSampler


ROOT = Path(__file__).resolve().parents[1]
GOLDEN_SET_PATH = ROOT / "eval" / "golden_set.yaml"
EXAMPLES_PATH = ROOT / "eval" / "examples.yaml"
RETRIEVAL_QUERIES_PATH = ROOT / "rag" / "test_queries.json"
RESULTS_PATH = ROOT / "eval" / "results"
ALLOWED_TABLES = {
    "v_contratos_agente",
    "v_coincidencias_69b_agente",
}
MAX_SQL_ROWS = 200
QUERY_TIMEOUT_MS = 60_000
REPETITIONS = 3
CONCURRENCY_LEVELS = (1, 2, 4, 8)
RETRIEVAL_TOP_K = 3


class SQLValidationError(ValueError):
    pass


def load_yaml_list(path: Path) -> list[dict[str, Any]]:
    try:
        content = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as exc:
        raise ValueError(f"No se pudo leer YAML {path}: {exc}") from exc
    if not isinstance(content, list) or not all(isinstance(item, dict) for item in content):
        raise ValueError(f"{path} debe contener una lista de objetos YAML.")
    return content


def load_golden_set(path: Path = GOLDEN_SET_PATH) -> list[dict[str, Any]]:
    cases = load_yaml_list(path)
    if len(cases) < 20:
        raise ValueError(f"El golden set requiere al menos 20 casos; contiene {len(cases)}.")
    required = {"id", "pregunta", "dificultad", "sql_esperado", "notas"}
    identifiers: set[str] = set()
    for case in cases:
        if not required.issubset(case):
            raise ValueError(f"Faltan campos requeridos en un caso del golden set: {case!r}.")
        if any(not isinstance(case[key], str) or not case[key].strip() for key in required):
            raise ValueError(f"Los campos del golden set deben ser texto no vacío: {case!r}.")
        if case["id"] in identifiers:
            raise ValueError(f"ID de caso repetido en el golden set: {case['id']}.")
        identifiers.add(case["id"])
        validate_sql(case["sql_esperado"])
    return cases


def load_examples(cases: list[dict[str, Any]]) -> list[dict[str, Any]]:
    examples = load_yaml_list(EXAMPLES_PATH)
    golden_questions = {case["pregunta"].strip().casefold() for case in cases}
    for example in examples:
        if not isinstance(example.get("pregunta"), str) or not example["pregunta"].strip():
            raise ValueError("Cada ejemplo requiere una pregunta no vacía.")
        if not isinstance(example.get("sql"), str) or not example["sql"].strip():
            raise ValueError("Cada ejemplo requiere SQL no vacío.")
        if example["pregunta"].strip().casefold() in golden_questions:
            raise ValueError("Los ejemplos del prompt deben ser distintos del golden set.")
        validate_sql(example["sql"])
    return examples


def extract_sql(response: str) -> str:
    fences = re.findall(r"```(?:sql)?\s*(.*?)```", response, flags=re.IGNORECASE | re.DOTALL)
    if len(fences) > 1:
        raise SQLValidationError("La respuesta contiene más de un bloque de código.")
    candidate = fences[0] if fences else response
    candidate = candidate.strip()
    if candidate[:4].upper() == "SQL ":
        candidate = candidate[4:].lstrip()
    return candidate


def validate_sql(query: str, max_rows: int = MAX_SQL_ROWS) -> str:
    try:
        statements = sqlglot.parse(query, read="postgres")
    except sqlglot.errors.ParseError as exc:
        raise SQLValidationError(f"SQL no válido: {exc}") from exc
    if len(statements) != 1 or statements[0] is None:
        raise SQLValidationError("Se permite exactamente una sentencia SQL.")
    tree = statements[0]
    if not isinstance(tree, exp.Select):
        raise SQLValidationError("Solo se permiten consultas SELECT.")
    if tree.find(exp.Into) or tree.find(exp.Lock):
        raise SQLValidationError("No se permiten INTO ni bloqueos de filas.")
    for table in tree.find_all(exp.Table):
        if table.db.lower() != "clean" or table.name.lower() not in ALLOWED_TABLES:
            raise SQLValidationError(
                f"Tabla no permitida: {table.sql(dialect='postgres')}."
            )
    for function in tree.find_all(exp.Anonymous):
        raise SQLValidationError(f"No se permiten funciones SQL no reconocidas: {function.name}.")
    limit = tree.args.get("limit")
    if limit is None or not isinstance(limit.expression, exp.Literal):
        raise SQLValidationError("La consulta debe incluir un LIMIT entero explícito.")
    try:
        row_limit = int(limit.expression.this)
    except (TypeError, ValueError) as exc:
        raise SQLValidationError("El LIMIT debe ser un entero literal.") from exc
    if not 1 <= row_limit <= max_rows:
        raise SQLValidationError(f"El LIMIT debe estar entre 1 y {max_rows}.")
    return tree.sql(dialect="postgres")


def is_single_select(query: str) -> bool:
    try:
        statements = sqlglot.parse(query, read="postgres")
    except sqlglot.errors.ParseError:
        return False
    return len(statements) == 1 and isinstance(statements[0], exp.Select)


def connect_agent_ro(*, dict_rows: bool = True):
    settings = database_settings()
    username = setting("AGENT_RO_USER", "agent_ro")
    password = setting("AGENT_RO_PASSWORD")
    if not password:
        raise RuntimeError(
            "Falta AGENT_RO_PASSWORD. Configura las credenciales de solo lectura en .env."
        )
    settings["user"] = username
    settings["password"] = password
    row_factory = dict_row if dict_rows else tuple_row
    return psycopg.connect(**settings, row_factory=row_factory)


def execute_read_only(query: str) -> list[dict[str, Any]]:
    safe_query = validate_sql(query)
    with connect_agent_ro() as connection, connection.cursor() as cursor:
        cursor.execute("SET TRANSACTION READ ONLY")
        cursor.execute("SELECT set_config('statement_timeout', %s, true)", (f"{QUERY_TIMEOUT_MS}ms",))
        cursor.execute(safe_query)
        return list(cursor.fetchall())


def schema_context() -> str:
    with connect_agent_ro() as connection, connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT n.nspname AS schema_name,
                   c.relname AS view_name,
                   obj_description(c.oid, 'pg_class') AS view_comment,
                   a.attname AS column_name,
                   col_description(c.oid, a.attnum) AS column_comment
            FROM pg_class AS c
            JOIN pg_namespace AS n ON n.oid = c.relnamespace
            JOIN pg_attribute AS a ON a.attrelid = c.oid
            WHERE n.nspname = 'clean'
              AND c.relkind IN ('v', 'm')
              AND c.relname = ANY(%s)
              AND a.attnum > 0
              AND NOT a.attisdropped
            ORDER BY c.relname, a.attnum
            """,
            (list(ALLOWED_TABLES),),
        )
        rows = cursor.fetchall()
    grouped: dict[str, dict[str, Any]] = {}
    for row in rows:
        view = row["view_name"]
        grouped.setdefault(
            view,
            {"view_comment": row["view_comment"], "columns": []},
        )["columns"].append(
            {"name": row["column_name"], "comment": row["column_comment"]}
        )
    missing = ALLOWED_TABLES.difference(grouped)
    if missing:
        raise RuntimeError(
            "No se encontraron vistas aprobadas en clean: " + ", ".join(sorted(missing))
        )
    return json.dumps(grouped, ensure_ascii=False, indent=2)


def build_system_prompt(schema: str, examples: list[dict[str, Any]]) -> str:
    example_text = "\n".join(
        f"Pregunta: {item['pregunta']}\nSQL:\n{item['sql']}" for item in examples
    )
    return f"""Eres un traductor de preguntas a SQL PostgreSQL para análisis de contrataciones.
Devuelve exclusivamente una consulta SQL SELECT; no uses Markdown ni explicaciones.
Seguridad obligatoria: consulta solo clean.v_contratos_agente y
clean.v_coincidencias_69b_agente; incluye LIMIT entre 1 y {MAX_SQL_ROWS};
no uses funciones SQL no estándar ni varias sentencias.
No infieras que un campo NULL significa cero actividad. Institución y unidad
compradora solo están disponibles en ComprasMX. El importe de ComprasMX tiene
semántica por confirmar y no es evidencia de pago. Las coincidencias 69-B son
señales para revisión humana, no determinaciones de irregularidad.
El estado de tipo de procedimiento puede ser preliminar. No inventes columnas.

Vistas y comentarios de PostgreSQL:
{schema}

Ejemplos:
{example_text}
"""


def normalize_value(value: Any) -> Any:
    if isinstance(value, Decimal):
        normalized = value.normalize()
        return str(normalized) if normalized else "0"
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    if isinstance(value, float) and not math.isfinite(value):
        return str(value)
    if isinstance(value, dict):
        return {key: normalize_value(item) for key, item in sorted(value.items())}
    if isinstance(value, (list, tuple)):
        return [normalize_value(item) for item in value]
    return value


def result_digest(rows: list[dict[str, Any]]) -> str:
    normalized = [
        {key: normalize_value(value) for key, value in sorted(row.items())}
        for row in rows
    ]
    normalized.sort(key=lambda row: json.dumps(row, ensure_ascii=False, sort_keys=True))
    payload = json.dumps(normalized, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def percentile(values: list[float], quantile: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    index = (len(ordered) - 1) * quantile
    lower = math.floor(index)
    upper = math.ceil(index)
    if lower == upper:
        return ordered[lower]
    return ordered[lower] * (upper - index) + ordered[upper] * (index - lower)


def discover_ollama_models(base_url: str) -> list[dict[str, Any]]:
    payload = get_json(f"{base_url.rstrip('/')}/api/tags")
    models = payload.get("models")
    if not isinstance(models, list):
        raise RuntimeError("Ollama no devolvió la lista de modelos de /api/tags.")
    discovered = [
        item for item in models if isinstance(item, dict) and isinstance(item.get("name"), str)
    ]
    for model in discovered:
        details, _ = post_json(
            f"{base_url.rstrip('/')}/api/show",
            {"model": model["name"]},
        )
        capabilities = details.get("capabilities")
        if isinstance(capabilities, list):
            model["capabilities"] = capabilities
    return discovered


def benchmark_ollama_base_url() -> str:
    base_url = setting("AGENT_BASE_URL", "http://localhost:11434").rstrip("/")
    parsed = urllib.parse.urlsplit(base_url)
    if not Path("/.dockerenv").exists() and parsed.hostname == "host.docker.internal":
        host = "localhost"
        if parsed.port:
            host = f"{host}:{parsed.port}"
        return urllib.parse.urlunsplit(
            (parsed.scheme, host, parsed.path, parsed.query, parsed.fragment)
        )
    return base_url


def choose_ollama_models(models: list[dict[str, Any]]) -> list[str]:
    text_models = [
        model for model in models
        if (
            "completion" in model["capabilities"]
            if isinstance(model.get("capabilities"), list)
            else not re.search(r"embed|embedding", model["name"], flags=re.IGNORECASE)
        )
    ]
    configured = setting("BENCHMARK_OLLAMA_MODELS")
    if configured:
        selected = [model.strip() for model in configured.split(",") if model.strip()]
        installed_names = {item["name"] for item in models}
        missing = set(selected).difference(installed_names)
        if missing:
            raise RuntimeError(
                "Modelos configurados no instalados en Ollama: " + ", ".join(sorted(missing))
            )
        not_generators = set(selected).difference(item["name"] for item in text_models)
        if not_generators:
            raise RuntimeError(
                "Modelos configurados sin capacidad de generación: "
                + ", ".join(sorted(not_generators))
            )
        if len(set(selected)) < 2:
            raise RuntimeError("Fija al menos dos modelos locales distintos en BENCHMARK_OLLAMA_MODELS.")
        return selected
    installed = sorted(text_models, key=lambda item: int(item.get("size", 0) or 0))
    if len(installed) < 2:
        raise RuntimeError(
            "Se requieren dos modelos locales. Instala los modelos y vuelve a ejecutar."
        )
    seven_b = [
        item for item in installed
        if re.search(r"(^|[^0-9])(7|8)b([^0-9]|$)", item["name"].lower())
    ]
    first = seven_b[0] if seven_b else min(
        installed, key=lambda item: abs(int(item.get("size", 0) or 0) - 5_000_000_000)
    )
    larger = [
        item for item in installed
        if item["name"] != first["name"] and int(item.get("size", 0) or 0) > int(first.get("size", 0) or 0)
    ]
    second = larger[-1] if larger else next(item for item in installed if item["name"] != first["name"])
    return [first["name"], second["name"]]


def build_clients(ollama_models: list[str], include_cloud: bool) -> list[LLMClient]:
    base_url = benchmark_ollama_base_url()
    clients: list[LLMClient] = [OllamaClient(base_url=base_url, model=name) for name in ollama_models]
    if include_cloud:
        if not setting("CLOUD_API_KEY") or not setting("CLOUD_MODEL"):
            raise RuntimeError(
                "La referencia cloud es obligatoria: configura CLOUD_API_KEY y CLOUD_MODEL."
            )
        if (
            _optional_float(setting("CLOUD_INPUT_USD_PER_1M_TOKENS")) is None
            or _optional_float(setting("CLOUD_OUTPUT_USD_PER_1M_TOKENS")) is None
        ):
            raise RuntimeError(
                "Configura los precios vigentes de entrada y salida del modelo cloud "
                "en USD por millón de tokens."
            )
        clients.append(CloudClient())
    return clients


def run_case(
    client: LLMClient,
    case: dict[str, Any],
    system_prompt: str,
    expected_digest: str,
    queued_at: float | None = None,
) -> dict[str, Any]:
    queue_wait_ms = max(0.0, time.perf_counter() - queued_at) * 1000 if queued_at else 0.0
    started = time.perf_counter()
    response: LLMResponse | None = None
    sql_text = ""
    error: str | None = None
    sql_valid = False
    safety_compliant = False
    correct: bool | None = None
    actual_digest: str | None = None
    result_rows: int | None = None
    try:
        response = client.generate(
            system_prompt,
            f"Notas del conjunto de datos: {case['notas']}\nPregunta: {case['pregunta']}",
            temperature=0.0,
        )
        sql_text = extract_sql(response.text)
        sql_valid = is_single_select(sql_text)
        if not sql_valid:
            raise SQLValidationError("La respuesta no contiene un único SELECT sintácticamente válido.")
        safe_sql = validate_sql(sql_text)
        safety_compliant = True
        result = execute_read_only(safe_sql)
        actual_digest = result_digest(result)
        result_rows = len(result)
        correct = actual_digest == expected_digest
    except Exception as exc:
        error = f"{type(exc).__name__}: {exc}"
    return {
        "id": case["id"],
        "dificultad": case["dificultad"],
        "pregunta": case["pregunta"],
        "model": client.model,
        "provider": client.provider,
        "sql_generado": sql_text,
        "sql_valido": sql_valid,
        "reglas_seguridad_respetadas": safety_compliant,
        "resultado_correcto": correct,
        "expected_digest": expected_digest,
        "actual_digest": actual_digest,
        "result_rows": result_rows,
        "latency_ms": response.latency_ms if response else (time.perf_counter() - started) * 1000,
        "input_tokens": response.input_tokens if response else None,
        "output_tokens": response.output_tokens if response else None,
        "tokens_per_second": response.tokens_per_second if response else None,
        "model_quantization": response.model_quantization if response else None,
        "ollama_version": response.ollama_version if response else None,
        "queue_wait_ms": queue_wait_ms,
        "error": error,
        "repetition": None,
    }


def summarize_model(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    summaries = [_summarize_group(rows, "global")]
    difficulties = sorted({row["dificultad"] for row in rows})
    summaries.extend(
        _summarize_group(
            [row for row in rows if row["dificultad"] == difficulty],
            difficulty,
        )
        for difficulty in difficulties
    )
    return summaries


def _summarize_group(rows: list[dict[str, Any]], difficulty: str) -> dict[str, Any]:
    completed = [row for row in rows if row["input_tokens"] is not None]
    latencies = [float(row["latency_ms"]) for row in rows]
    valid_count = sum(bool(row["sql_valido"]) for row in rows)
    correct_count = sum(row["resultado_correcto"] is True for row in rows)
    safe_count = sum(bool(row["reglas_seguridad_respetadas"]) for row in rows)
    consistency_by_case: dict[str, list[str | None]] = {}
    for row in rows:
        consistency_by_case.setdefault(row["id"], []).append(row["actual_digest"])
    consistent_cases = sum(
        len(digests) == REPETITIONS
        and all(digest is not None for digest in digests)
        and len(set(digests)) == 1
        for digests in consistency_by_case.values()
    )
    total_cases = len(consistency_by_case)
    input_tokens = sum(row["input_tokens"] or 0 for row in rows)
    output_tokens = sum(row["output_tokens"] or 0 for row in rows)
    token_rates = [row["tokens_per_second"] for row in completed if row["tokens_per_second"] is not None]
    provider = rows[0]["provider"]
    model = rows[0]["model"]
    input_rate = _optional_float(setting("CLOUD_INPUT_USD_PER_1M_TOKENS")) if provider == "cloud" else None
    output_rate = _optional_float(setting("CLOUD_OUTPUT_USD_PER_1M_TOKENS")) if provider == "cloud" else None
    cost_per_1000 = None
    if provider == "cloud" and input_rate is not None and output_rate is not None and completed:
        cost_per_1000 = 1000 * (
            (input_tokens / len(completed) * input_rate)
            + (output_tokens / len(completed) * output_rate)
        ) / 1_000_000
    return {
        "provider": provider,
        "model": model,
        "difficulty": difficulty,
        "model_quantization": rows[0]["model_quantization"],
        "ollama_version": rows[0]["ollama_version"],
        "repetitions": len(rows),
        "sql_valid_pct": 100 * valid_count / len(rows) if rows else 0,
        "result_correct_pct": 100 * correct_count / len(rows) if rows else None,
        "safety_compliant_pct": 100 * safe_count / len(rows) if rows else 0,
        "latency_p50_ms": percentile(latencies, 0.50),
        "latency_p95_ms": percentile(latencies, 0.95),
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "tokens_per_second_mean": statistics.mean(token_rates) if token_rates else None,
        "consistency_pct": (
            100 * consistent_cases / total_cases if total_cases else None
        ),
        "cloud_cost_usd_per_1000_queries": cost_per_1000,
    }


def _optional_float(value: str) -> float | None:
    if not value:
        return None
    try:
        parsed = float(value)
    except ValueError as exc:
        raise ValueError(f"Valor de precio no numérico en configuración: {value!r}.") from exc
    if parsed < 0:
        raise ValueError("Los precios por token no pueden ser negativos.")
    return parsed


def _write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    if not rows:
        path.write_text("", encoding="utf-8")
        return
    with path.open("w", encoding="utf-8-sig", newline="") as output:
        writer = csv.DictWriter(output, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def _system_memory_bytes() -> int | None:
    if platform.system() == "Windows":
        import ctypes

        class MemoryStatus(ctypes.Structure):
            _fields_ = [
                ("dwLength", ctypes.c_ulong),
                ("dwMemoryLoad", ctypes.c_ulong),
                ("ullTotalPhys", ctypes.c_ulonglong),
                ("ullAvailPhys", ctypes.c_ulonglong),
                ("ullTotalPageFile", ctypes.c_ulonglong),
                ("ullAvailPageFile", ctypes.c_ulonglong),
                ("ullTotalVirtual", ctypes.c_ulonglong),
                ("ullAvailVirtual", ctypes.c_ulonglong),
                ("ullAvailExtendedVirtual", ctypes.c_ulonglong),
            ]

        status = MemoryStatus()
        status.dwLength = ctypes.sizeof(status)
        if ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(status)):
            return int(status.ullTotalPhys)
        return None
    try:
        return int(os.sysconf("SC_PAGE_SIZE") * os.sysconf("SC_PHYS_PAGES"))
    except (AttributeError, OSError, ValueError):
        return None


def hardware_metadata(base_url: str) -> dict[str, Any]:
    metadata: dict[str, Any] = {
        "host": platform.node(),
        "os": platform.platform(),
        "cpu": platform.processor() or platform.machine(),
        "cpu_count": os.cpu_count(),
        "ram_bytes": _system_memory_bytes(),
        "ollama_base_url": _redact_url(base_url),
        "ollama_parallelism_env": setting("OLLAMA_NUM_PARALLEL") or None,
    }
    try:
        result = subprocess.run(
            ["nvidia-smi", "--query-gpu=name,memory.total", "--format=csv,noheader,nounits"],
            capture_output=True,
            check=False,
            text=True,
            timeout=3,
        )
        metadata["gpus"] = (
            [line.strip() for line in result.stdout.splitlines() if line.strip()]
            if result.returncode == 0 else []
        )
    except (OSError, subprocess.TimeoutExpired):
        metadata["gpus"] = []
    metadata["gpu_measurement"] = "nvidia-smi; peak sampled during each model run"
    metadata["ollama_parallelism_note"] = (
        "Solo se reporta OLLAMA_NUM_PARALLEL del entorno; no se infiere la configuración "
        "interna del servicio Ollama."
    )
    return metadata


def _redact_url(url: str) -> str:
    parsed = urllib.parse.urlsplit(url)
    host = parsed.hostname or ""
    if ":" in host and not host.startswith("["):
        host = f"[{host}]"
    if parsed.port:
        host = f"{host}:{parsed.port}"
    return urllib.parse.urlunsplit((parsed.scheme, host, parsed.path, "", ""))


def run_concurrency(
    client: LLMClient,
    cases: list[dict[str, Any]],
    expected: dict[str, str],
    prompt: str,
) -> list[dict[str, Any]]:
    representative = [cases[index] for index in (0, 3, 6, 9)]
    output: list[dict[str, Any]] = []
    for workers in CONCURRENCY_LEVELS:
        jobs = representative * workers
        started = time.perf_counter()
        with GPUUsageSampler() as gpu:
            with ThreadPoolExecutor(max_workers=workers) as pool:
                futures = []
                for case in jobs:
                    queued_at = time.perf_counter()
                    futures.append(
                        pool.submit(
                            run_case,
                            client,
                            case,
                            prompt,
                            expected[case["id"]],
                            queued_at,
                        )
                    )
                results = [future.result() for future in as_completed(futures)]
        elapsed = time.perf_counter() - started
        latencies = [float(item["latency_ms"]) for item in results]
        queue_waits = [float(item["queue_wait_ms"]) for item in results]
        errors = sum(item["error"] is not None for item in results)
        output.append(
            {
                "model": client.model,
                "provider": client.provider,
                "concurrency": workers,
                "requests": len(results),
                "throughput_requests_per_second": len(results) / elapsed if elapsed else 0,
                "latency_p50_ms": percentile(latencies, 0.50),
                "latency_p95_ms": percentile(latencies, 0.95),
                "queue_wait_p95_ms": percentile(queue_waits, 0.95),
                "errors": errors,
                "timeouts": sum(
                    any(
                        marker in (item["error"] or "").lower()
                        for marker in ("timeout", "timed out")
                    )
                    for item in results
                ),
                "gpu_utilization_peak_pct": gpu.gpu_utilization_percent,
                "vram_peak_mb": gpu.vram_used_mb,
                "elapsed_seconds": elapsed,
            }
        )
    return output


def run_embedding_evaluation(output_dir: Path) -> dict[str, Any]:
    base_url, model = ollama_settings()
    client = OllamaEmbeddingClient(base_url, model)
    try:
        queries = json.loads(RETRIEVAL_QUERIES_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"No se pudieron leer consultas RAG {RETRIEVAL_QUERIES_PATH}: {exc}") from exc
    if not isinstance(queries, list) or not queries:
        raise ValueError("El archivo de consultas RAG debe contener una lista no vacía.")
    rows: list[dict[str, Any]] = []
    query_rows: list[dict[str, Any]] = []
    judged_recalls: list[float] = []
    dimension: int | None = None
    for item in queries:
        if not isinstance(item, dict) or not isinstance(item.get("pregunta"), str):
            raise ValueError("Cada consulta RAG debe tener el campo pregunta.")
        contract_date = date.fromisoformat(item["fecha_contrato"])
        with GPUUsageSampler() as gpu:
            vectors, embedding_ms = client.embed([item["pregunta"]])
        dimension = len(vectors[0])
        with connect_agent_ro(dict_rows=False) as connection:
            check_embedding_configuration(connection, client.model, dimension)
            matches, retrieval_ms = retrieve(
                connection, vectors[0], RETRIEVAL_TOP_K, contract_date
            )
        relevant_articles = item.get("articulos_relevantes")
        recall: float | None = None
        if relevant_articles is not None:
            if not isinstance(relevant_articles, list) or not all(
                isinstance(article, str) for article in relevant_articles
            ):
                raise ValueError("articulos_relevantes debe ser una lista de etiquetas de artículo.")
            if relevant_articles:
                found = {
                    str((match.get("metadata") or {}).get("articulo", "")).casefold()
                    for match in matches
                }
                recall = len(found.intersection(article.casefold() for article in relevant_articles)) / len(
                    set(article.casefold() for article in relevant_articles)
                )
                judged_recalls.append(recall)
        query_rows.append(
            {
                "pregunta": item["pregunta"],
                "fecha_contrato": contract_date.isoformat(),
                "embedding_ms": round(embedding_ms, 3),
                "embedding_dimension": dimension,
                "retrieval_db_ms": round(retrieval_ms, 3),
                "top_k": RETRIEVAL_TOP_K,
                "result_count": len(matches),
                "recall_at_k": recall,
                "gpu_utilization_peak_pct": gpu.gpu_utilization_percent,
                "vram_peak_mb": gpu.vram_used_mb,
            }
        )
        for rank, match in enumerate(matches, start=1):
            rows.append(
                {
                    "pregunta": item["pregunta"],
                    "fecha_contrato": contract_date.isoformat(),
                    "rank": rank,
                    "chunk_id": match["id"],
                    "titulo": match["titulo"],
                    "articulo": (match.get("metadata") or {}).get("articulo"),
                    "distancia_coseno": match["distancia_coseno"],
                    "embedding_ms_por_consulta": round(embedding_ms, 3),
                    "embedding_dimension": dimension,
                    "retrieval_db_ms": round(retrieval_ms, 3),
                    "recall_at_k": recall,
                    "gpu_utilization_peak_pct": gpu.gpu_utilization_percent,
                    "vram_peak_mb": gpu.vram_used_mb,
                }
            )
    _write_csv(output_dir / "embeddings.csv", rows)
    _write_csv(output_dir / "embedding_queries.csv", query_rows)
    return {
        "model": model,
        "dimension": dimension,
        "queries": len(queries),
        "embedding_latency_ms_mean": statistics.mean(
            [row["embedding_ms"] for row in query_rows]
        ) if query_rows else None,
        "retrieval_latency_ms_mean": statistics.mean(
            [row["retrieval_db_ms"] for row in query_rows]
        ) if query_rows else None,
        "judged_queries": len(judged_recalls),
        "recall_at_k_mean": statistics.mean(judged_recalls) if judged_recalls else None,
        "quality_status": (
            "measured_on_human_labels"
            if judged_recalls
            else "not_measured_no_human_relevance_labels"
        ),
    }


def write_markdown_summary(
    path: Path,
    summaries: list[dict[str, Any]],
    concurrency: list[dict[str, Any]],
) -> None:
    columns = [
        ("Modelo", "model"),
        ("Proveedor", "provider"),
        ("SQL válido %", "sql_valid_pct"),
        ("Resultado correcto %", "result_correct_pct"),
        ("Seguridad %", "safety_compliant_pct"),
        ("p50 ms", "latency_p50_ms"),
        ("p95 ms", "latency_p95_ms"),
        ("Consistencia %", "consistency_pct"),
        ("USD/1000 consultas", "cloud_cost_usd_per_1000_queries"),
    ]
    lines = ["# Benchmark text-to-SQL", "", "| " + " | ".join(title for title, _ in columns) + " |"]
    lines.append("| " + " | ".join("---" for _ in columns) + " |")
    for summary in summaries:
        if summary["difficulty"] != "global":
            continue
        lines.append(
            "| " + " | ".join(
                str(summary[key]) if summary.get(key) is not None else "No medido"
                for _, key in columns
            ) + " |"
        )
    difficulty_rows = [summary for summary in summaries if summary["difficulty"] != "global"]
    lines.extend(
        [
            "",
            "## Métricas por dificultad",
            "",
            "| Modelo | Proveedor | Dificultad | SQL válido % | Resultado correcto % | Seguridad % | p50 ms | p95 ms | Consistencia % |",
            "| --- | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |",
        ]
    )
    for summary in difficulty_rows:
        lines.append(
            f"| {summary['model']} | {summary['provider']} | {summary['difficulty']} | "
            f"{summary['sql_valid_pct']:.2f} | {summary['result_correct_pct']:.2f} | "
            f"{summary['safety_compliant_pct']:.2f} | {summary['latency_p50_ms']} | "
            f"{summary['latency_p95_ms']} | {summary['consistency_pct']} |"
        )
    lines.extend(["", "## Concurrencia", "", "| Modelo | Proveedor | Solicitudes simultáneas | Throughput req/s | p50 ms | p95 ms | Espera p95 ms | Errores | Timeouts |"])
    lines.append("| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |")
    for row in concurrency:
        lines.append(
            f"| {row['model']} | {row['provider']} | {row['concurrency']} | "
            f"{row['throughput_requests_per_second']:.3f} | {row['latency_p50_ms']} | "
            f"{row['latency_p95_ms']} | {row['queue_wait_p95_ms']} | "
            f"{row['errors']} | {row['timeouts']} |"
        )
    lines.extend(
        [
            "",
            "Las respuestas se comparan por columnas y filas normalizadas, no por el texto SQL. "
            "Los porcentajes no constituyen una conclusión sobre modelos fuera de este conjunto.",
            "El costo cloud solo se estima si se configuran tarifas vigentes del modelo.",
        ]
    )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def run_benchmark(
    ollama_models: list[str],
    include_cloud: bool = True,
    output_root: Path = RESULTS_PATH,
    skip_embeddings: bool = False,
) -> Path:
    cases = load_golden_set()
    examples = load_examples(cases)
    clients = build_clients(ollama_models, include_cloud)
    if len({client.model for client in clients if client.provider == "ollama"}) < 2:
        raise RuntimeError("El benchmark exige al menos dos modelos locales Ollama distintos.")
    output_dir = output_root / datetime.now().strftime("%Y%m%d_%H%M%S")
    output_dir.mkdir(parents=True, exist_ok=False)

    schema = schema_context()
    system_prompt = build_system_prompt(schema, examples)
    expected_results = {
        case["id"]: result_digest(execute_read_only(case["sql_esperado"]))
        for case in cases
    }
    details: list[dict[str, Any]] = []
    summaries: list[dict[str, Any]] = []
    concurrency_results: list[dict[str, Any]] = []
    hardware = hardware_metadata(benchmark_ollama_base_url())

    for client in clients:
        model_rows: list[dict[str, Any]] = []
        with GPUUsageSampler() as gpu:
            for repetition in range(1, REPETITIONS + 1):
                for case in cases:
                    row = run_case(client, case, system_prompt, expected_results[case["id"]])
                    row["repetition"] = repetition
                    model_rows.append(row)
                    details.append(row)
        model_summaries = summarize_model(model_rows)
        for summary in model_summaries:
            summary["gpu_utilization_peak_pct"] = gpu.gpu_utilization_percent
            summary["vram_peak_mb"] = gpu.vram_used_mb
        summaries.extend(model_summaries)
        concurrency_results.extend(
            run_concurrency(client, cases, expected_results, system_prompt)
        )

    embedding_summary = None
    if not skip_embeddings:
        embedding_summary = run_embedding_evaluation(output_dir)
    _write_csv(output_dir / "details.csv", details)
    _write_csv(output_dir / "summary.csv", summaries)
    _write_csv(output_dir / "concurrency.csv", concurrency_results)
    metadata = {
        "started_at": output_dir.name,
        "golden_set_path": str(GOLDEN_SET_PATH),
        "golden_cases": len(cases),
        "repetitions": REPETITIONS,
        "max_rows": MAX_SQL_ROWS,
        "statement_timeout_ms": QUERY_TIMEOUT_MS,
        "hardware": hardware,
        "models": summaries,
        "embeddings": embedding_summary,
        "cloud_prices_usd_per_1m_tokens": {
            "input": _optional_float(setting("CLOUD_INPUT_USD_PER_1M_TOKENS")),
            "output": _optional_float(setting("CLOUD_OUTPUT_USD_PER_1M_TOKENS")),
        },
        "results_comparison": "normalized rows and column names; row order ignored",
    }
    (output_dir / "metadata.json").write_text(
        json.dumps(metadata, ensure_ascii=False, indent=2, default=str) + "\n",
        encoding="utf-8",
    )
    write_markdown_summary(output_dir / "summary.md", summaries, concurrency_results)
    return output_dir


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Ejecuta benchmark text-to-SQL seguro con vistas del agente y agente de solo lectura."
    )
    parser.add_argument(
        "--validate-only",
        action="store_true",
        help="Valida YAML, cobertura mínima y SQL esperado sin conectar a modelos o PostgreSQL.",
    )
    parser.add_argument(
        "--ollama-models",
        help="Modelos locales separados por coma; por defecto se eligen de /api/tags.",
    )
    parser.add_argument(
        "--skip-embeddings",
        action="store_true",
        help="Omite el benchmark de retrieval RAG.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=RESULTS_PATH,
        help="Directorio base para los artefactos (por defecto eval/results).",
    )
    args = parser.parse_args()
    if args.validate_only:
        cases = load_golden_set()
        examples = load_examples(cases)
        print(f"YAML y SQL válidos: {len(cases)} casos y {len(examples)} ejemplos.")
        return 0
    base_url = benchmark_ollama_base_url()
    available = discover_ollama_models(base_url)
    models = (
        [model.strip() for model in args.ollama_models.split(",") if model.strip()]
        if args.ollama_models
        else choose_ollama_models(available)
    )
    if args.ollama_models:
        names = {item["name"] for item in available}
        missing = set(models).difference(names)
        if missing:
            raise RuntimeError("Modelos Ollama no instalados: " + ", ".join(sorted(missing)))
        if len(set(models)) < 2:
            raise RuntimeError("--ollama-models requiere al menos dos nombres distintos.")
    output_dir = run_benchmark(
        models,
        include_cloud=True,
        output_root=args.output_dir,
        skip_embeddings=args.skip_embeddings,
    )
    print(f"Benchmark terminado. Resultados: {output_dir.resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
