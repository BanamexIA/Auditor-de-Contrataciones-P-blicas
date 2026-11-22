"""Measures the Agente Consulta on the golden set (A4).

Unlike eval/run_benchmark.py, which compares models, this runs the full agent
(prompt, validator, coverage check and execution, with the retry when
PostgreSQL rejects the SQL) with one model, does not pass the case notes to the
model, and compares results ignoring column aliases and column order.

    python -m eval.run_consulta --repeticiones 3
    python -m eval.run_consulta --casos eval/casos_consulta.yaml
    python -m eval.run_consulta --casos eval/casos_empresa.yaml
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
        case.setdefault("dificultad", "sin_clasificar")
        if case["tipo_esperado"] == "sql" and not case.get("sql_esperado"):
            raise ValueError(f"{case['id']}: un caso que espera SQL necesita sql_esperado.")
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
        # sql_rechazado: the model's last SQL was rejected by PostgreSQL, not by the validator.
        error = "error_ejecucion" if execution_error or answer.get("sql_rechazado") else "error_modelo"
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
        # A5, mejora 9: why each failed attempt was rejected (q13 needed two and we did not know why).
        "errores_intentos": " | ".join(
            f"{item['intento']} {item['etapa']}: {item['error']}" for item in answer.get("intentos_fallidos", [])
        ),
        "sql": answer.get("sql") or answer.get("sql_descartado") or answer.get("sql_rechazado"),
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
        "consistencia": consistency(results),
        # A5, mejora 8: an empty expected result lets any wrong SQL without rows count as right.
        "esperados_vacios": sorted({
            row["id"] for row in results if row["tipo_esperado"] == "sql" and row["filas_esperadas"] == 0
        }),
    }


def consistency(results: list[dict[str, Any]]) -> dict[str, Any] | None:
    """Cases that gave the same SQL and the same verdict in every repetition (A5, mejora 9)."""
    by_case: dict[str, list[dict[str, Any]]] = {}
    for row in results:
        by_case.setdefault(row["id"], []).append(row)
    if all(len(rows) < 2 for rows in by_case.values()):
        return None
    varying = sorted(
        case_id for case_id, rows in by_case.items()
        if len({(row["sql"], row["correcto"], row["error"]) for row in rows}) > 1
    )
    return {
        "casos": len(by_case),
        "consistentes": len(by_case) - len(varying),
        "pct": round(100 * (len(by_case) - len(varying)) / len(by_case), 1),
        "casos_que_variaron": varying,
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
        "# Medición del Agente Consulta",
        "",
        f"Archivo: `{metadata.get('archivo', 'golden_set.yaml')}` · Modelo: `{metadata['modelo']}` · Casos: {metadata['casos']} · Repeticiones: {metadata['repeticiones']} · Fecha: {metadata['fecha']}",
        "",
        "| Indicador | Valor |",
        "|---|---:|",
        f"| Exactitud del SQL (casos que esperan SQL) | {summary['exactitud_sql_pct']} % |",
        f"| Acierto global (incluye aclaración y sin datos) | {summary['acierto_global_pct']} % |",
    ]
    lines += [f"| Exactitud SQL, dificultad {level} | {value} % |" for level, value in summary["por_dificultad"].items()]
    lines += [f"| Acierto en casos `{kind}` | {value} % |" for kind, value in summary["por_tipo_esperado"].items()]
    same = summary.get("consistencia")
    if same:
        lines.append(
            f"| Consistencia entre repeticiones (mismo SQL y mismo veredicto) | "
            f"{same['consistentes']} de {same['casos']} casos ({same['pct']} %) |"
        )
    if same and same["casos_que_variaron"]:
        lines += ["", f"Casos que variaron entre repeticiones: {', '.join(same['casos_que_variaron'])}."]
    if summary.get("esperados_vacios"):
        lines += [
            "",
            f"> **Aviso:** {', '.join(summary['esperados_vacios'])} tienen un resultado esperado vacío: "
            "cualquier SQL que no devuelva filas cuenta como acierto. Cambia esos casos.",
        ]
    lines += ["", "## Tipos de error", "", "| Error | Respuestas |", "|---|---:|"]
    lines += [f"| {error} | {count} |" for error, count in sorted(summary["errores"].items())] or ["| — | 0 |"]
    lines += ["", "## Respuestas incorrectas", "", "| Caso | Esperado | Obtenido | Error |", "|---|---|---|---|"]
    lines += [
        f"| {row['id']} | {row['tipo_esperado']} | {row['tipo_obtenido']} | {row['error']} |"
        for row in results if not row["correcto"]
    ]
    (output_dir / "resumen.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def ask_and_execute(question: str, answer_fn) -> tuple[dict[str, Any], Any, str | None]:
    """Runs the agent with execution, as in production, so PostgreSQL errors get the retry.

    answer_fn(question) calls answer_question with an executor. Returns the
    answer, the rows (only for a sql answer) and the error of a database failure
    that the agent does not retry, such as a timeout.
    """
    import psycopg

    try:
        answer = answer_fn(question)
    except psycopg.Error as exc:
        detail = f"{type(exc).__name__}: {exc}"
        return {"tipo": "error", "motivo": detail}, None, detail
    return answer, answer.get("filas") if answer["tipo"] == "sql" else None, None


def run(model: str | None, repetitions: int, output_root: Path, cases_path: Path = GOLDEN_SET_PATH) -> Path:
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

    cases = load_cases(cases_path)
    client = OllamaClient(base_url=benchmark_ollama_base_url(), model=model)
    system_prompt = build_system_prompt(schema_context(), load_examples(cases))
    with connect_agent_ro() as connection, connection.cursor() as cursor:
        cursor.execute(COVERAGE_QUERY)
        coverage = Coverage.from_rows(cursor.fetchall())
    expected = {
        case["id"]: execute_read_only(case["sql_esperado"])
        for case in cases if case["tipo_esperado"] == "sql"
    }

    def answer_fn(question: str) -> dict[str, Any]:
        # The count (HU-01) changes neither the SQL nor the verdict; it stays off so the
        # time per question remains comparable with A4 and A5.
        return answer_question(question, client, system_prompt, coverage, execute=execute_read_only,
                               count_records=False)

    results = []
    for repetition in range(1, repetitions + 1):
        for case in cases:
            started = time.perf_counter()
            answer, actual_rows, execution_error = ask_and_execute(case["pregunta"], answer_fn)
            row = evaluate(case, answer, expected.get(case["id"]), actual_rows, execution_error)
            row["repeticion"] = repetition
            row["latencia_ms"] = round((time.perf_counter() - started) * 1000, 1)
            results.append(row)
            print(f"[{repetition}] {case['id']}: {'ok' if row['correcto'] else row['error']}")

    summary = summarize(results)
    metadata = {
        "archivo": cases_path.name,
        "modelo": client.model,
        "casos": len(cases),
        "repeticiones": repetitions,
        "fecha": datetime.now().isoformat(timespec="seconds"),
        "comparacion": "filas normalizadas; ignora alias, orden de columnas y orden de filas",
    }
    prefix = "consulta" if cases_path == GOLDEN_SET_PATH else f"consulta_{cases_path.stem}"
    output_dir = output_root / f"{prefix}_{datetime.now():%Y%m%d_%H%M%S}"
    write_report(output_dir, results, summary, metadata)
    return output_dir


def main() -> int:
    parser = argparse.ArgumentParser(description="Mide la exactitud del Agente Consulta (A4).")
    parser.add_argument("--modelo", help="Modelo de Ollama; por defecto AGENT_MODEL.")
    parser.add_argument("--repeticiones", type=int, default=1)
    parser.add_argument("--casos", type=Path, default=GOLDEN_SET_PATH,
                        help="Archivo YAML de casos; por defecto el golden set.")
    parser.add_argument("--output-dir", type=Path, default=RESULTS_PATH)
    args = parser.parse_args()
    output_dir = run(args.modelo, args.repeticiones, args.output_dir, args.casos.resolve())
    print(f"Resultados: {output_dir.resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
