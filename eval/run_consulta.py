"""Measures the Agente Consulta on the golden set (A4).

Unlike eval/run_benchmark.py, which compares models, this runs the full agent
(prompt, validator, coverage check) with one model, does not pass the case notes
to the model, and compares results ignoring column aliases and column order.

    python -m eval.run_consulta --repeticiones 3
"""
from __future__ import annotations

import argparse
import csv
import json
import time
from collections import Counter
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

import yaml


ROOT = Path(__file__).resolve().parents[1]
GOLDEN_SET_PATH = ROOT / "eval" / "golden_set.yaml"
RESULTS_PATH = ROOT / "eval" / "results"
RESPONSE_TYPES = {"sql", "aclaracion", "sin_datos"}


def load_cases(path: Path = GOLDEN_SET_PATH) -> list[dict[str, Any]]:
    cases = yaml.safe_load(path.read_text(encoding="utf-8"))
    for case in cases:
        case.setdefault("tipo_esperado", "sql")
        if case["tipo_esperado"] not in RESPONSE_TYPES:
            raise ValueError(f"{case['id']}: tipo_esperado no válido: {case['tipo_esperado']!r}.")
    return cases


def _canonical(value: Any) -> str:
    if value is None:
        return "null"
    if isinstance(value, bool):
        return f"bool:{str(value).lower()}"
    if isinstance(value, (int, float, Decimal)):
        number = Decimal(str(value)).normalize()
        return f"num:{format(number, 'f')}"
    if isinstance(value, (date, datetime)):
        return f"fecha:{value.isoformat()}"
    return f"texto:{value}"


def canonical_rows(rows: list[dict[str, Any]]) -> Counter:
    """Rows as a multiset that ignores column names, column order and row order."""
    return Counter(tuple(sorted(_canonical(value) for value in row.values())) for row in rows)


def compare_results(expected: list[dict[str, Any]], actual: list[dict[str, Any]]) -> str | None:
    """Returns None when equal, or the kind of difference."""
    if canonical_rows(expected) == canonical_rows(actual):
        return None
    if expected and actual and len(expected[0]) != len(actual[0]):
        return "columnas_distintas"
    if len(expected) != len(actual):
        return "filas_distintas"
    return "valores_distintos"


def evaluate(case: dict[str, Any], answer: dict[str, Any], expected_rows=None, actual_rows=None,
             execution_error: str | None = None) -> dict[str, Any]:
    expected_type = case["tipo_esperado"]
    obtained_type = answer["tipo"]
    if obtained_type == "error":
        error = "error_modelo"
    elif obtained_type != expected_type:
        error = "tipo_incorrecto"
    elif expected_type != "sql":
        error = None
    elif execution_error:
        error = "error_ejecucion"
    else:
        error = compare_results(expected_rows or [], actual_rows or [])
    return {
        "id": case["id"],
        "dificultad": case["dificultad"],
        "tipo_esperado": expected_type,
        "tipo_obtenido": obtained_type,
        "correcto": error is None,
        "error": error,
        "detalle_error": execution_error or answer.get("motivo"),
        "intentos": answer.get("intentos"),
        "sql": answer.get("sql") or answer.get("sql_descartado"),
        "supuestos": answer.get("supuestos", []),
        "filas_esperadas": len(expected_rows) if expected_rows is not None else None,
        "filas_obtenidas": len(actual_rows) if actual_rows is not None else None,
    }


def summarize(results: list[dict[str, Any]]) -> dict[str, Any]:
    def share(rows):
        return round(100 * sum(row["correcto"] for row in rows) / len(rows), 1) if rows else None

    sql_rows = [row for row in results if row["tipo_esperado"] == "sql"]
    return {
        "respuestas": len(results),
        "exactitud_sql_pct": share(sql_rows),
        "acierto_global_pct": share(results),
        "por_dificultad": {
            level: share([row for row in sql_rows if row["dificultad"] == level])
            for level in sorted({row["dificultad"] for row in sql_rows})
        },
        "por_tipo_esperado": {
            kind: share([row for row in results if row["tipo_esperado"] == kind])
            for kind in sorted({row["tipo_esperado"] for row in results})
        },
        "errores": dict(Counter(row["error"] for row in results if row["error"])),
    }


def write_report(output_dir: Path, results: list[dict[str, Any]], summary: dict[str, Any],
                 metadata: dict[str, Any]) -> None:
    output_dir.mkdir(parents=True, exist_ok=False)
    with (output_dir / "detalle.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(results[0]))
        writer.writeheader()
        writer.writerows({**row, "supuestos": " | ".join(row["supuestos"])} for row in results)
    (output_dir / "resumen.json").write_text(
        json.dumps({"metadata": metadata, "resumen": summary}, ensure_ascii=False, indent=2, default=str),
        encoding="utf-8",
    )
    lines = [
        "# Exactitud del Agente Consulta (A4)",
        "",
        f"Modelo: `{metadata['modelo']}` · Casos: {metadata['casos']} · Repeticiones: {metadata['repeticiones']} · Fecha: {metadata['fecha']}",
        "",
        "| Indicador | Valor |",
        "|---|---:|",
        f"| Exactitud del SQL (casos que esperan SQL) | {summary['exactitud_sql_pct']} % |",
        f"| Acierto global (incluye aclaración y sin datos) | {summary['acierto_global_pct']} % |",
    ]
    lines += [f"| Exactitud SQL, dificultad {level} | {value} % |" for level, value in summary["por_dificultad"].items()]
    lines += [f"| Acierto en casos `{kind}` | {value} % |" for kind, value in summary["por_tipo_esperado"].items()]
    lines += ["", "## Tipos de error", "", "| Error | Respuestas |", "|---|---:|"]
    lines += [f"| {error} | {count} |" for error, count in sorted(summary["errores"].items())] or ["| — | 0 |"]
    lines += ["", "## Respuestas incorrectas", "", "| Caso | Esperado | Obtenido | Error |", "|---|---|---|---|"]
    lines += [
        f"| {row['id']} | {row['tipo_esperado']} | {row['tipo_obtenido']} | {row['error']} |"
        for row in results if not row["correcto"]
    ]
    (output_dir / "resumen.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def run(model: str | None, repetitions: int, output_root: Path) -> Path:
    from agents.consulta.agent import answer_question
    from agents.consulta.coverage import COVERAGE_QUERY, Coverage
    from agents.consulta.prompt import build_system_prompt
    from eval.run_benchmark import (
        benchmark_ollama_base_url,
        connect_agent_ro,
        execute_read_only,
        load_examples,
        schema_context,
    )
    from llm.ollama_client import OllamaClient

    cases = load_cases()
    client = OllamaClient(base_url=benchmark_ollama_base_url(), model=model)
    system_prompt = build_system_prompt(schema_context(), load_examples(cases))
    with connect_agent_ro() as connection, connection.cursor() as cursor:
        cursor.execute(COVERAGE_QUERY)
        coverage = Coverage.from_rows(cursor.fetchall())
    expected = {
        case["id"]: execute_read_only(case["sql_esperado"])
        for case in cases if case["tipo_esperado"] == "sql"
    }

    results = []
    for repetition in range(1, repetitions + 1):
        for case in cases:
            started = time.perf_counter()
            answer = answer_question(case["pregunta"], client, system_prompt, coverage)
            actual_rows, execution_error = None, None
            if answer["tipo"] == "sql" and case["tipo_esperado"] == "sql":
                try:
                    actual_rows = execute_read_only(answer["sql"])
                except Exception as exc:
                    execution_error = f"{type(exc).__name__}: {exc}"
            row = evaluate(case, answer, expected.get(case["id"]), actual_rows, execution_error)
            row["repeticion"] = repetition
            row["latencia_ms"] = round((time.perf_counter() - started) * 1000, 1)
            results.append(row)
            print(f"[{repetition}] {case['id']}: {'ok' if row['correcto'] else row['error']}")

    summary = summarize(results)
    metadata = {
        "modelo": client.model,
        "casos": len(cases),
        "repeticiones": repetitions,
        "fecha": datetime.now().isoformat(timespec="seconds"),
        "comparacion": "filas normalizadas; ignora alias, orden de columnas y orden de filas",
    }
    output_dir = output_root / f"consulta_{datetime.now():%Y%m%d_%H%M%S}"
    write_report(output_dir, results, summary, metadata)
    return output_dir


def main() -> int:
    parser = argparse.ArgumentParser(description="Mide la exactitud del Agente Consulta (A4).")
    parser.add_argument("--modelo", help="Modelo de Ollama; por defecto AGENT_MODEL.")
    parser.add_argument("--repeticiones", type=int, default=1)
    parser.add_argument("--output-dir", type=Path, default=RESULTS_PATH)
    args = parser.parse_args()
    output_dir = run(args.modelo, args.repeticiones, args.output_dir)
    print(f"Resultados: {output_dir.resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
