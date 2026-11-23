"""Runs the Escenario 1 questions once with the full agent and saves the evidence (A6).

Unlike eval/run_consulta.py this does not grade the answers: it keeps what the
auditor would see (type, SQL, notes, record count, failed attempts and the first
rows) so the evidence can be reviewed by hand.

    python -m eval.run_escenario
"""
from __future__ import annotations

import argparse
import json
import time
from datetime import datetime
from pathlib import Path
from typing import Any

import yaml


ROOT = Path(__file__).resolve().parents[1]
SCENARIO_PATH = ROOT / "eval" / "escenario1.yaml"
RESULTS_PATH = ROOT / "eval" / "results"
SHOWN_ROWS = 5
# Columns that can hold names of people; they never go into the evidence.
HIDDEN_COLUMN_WORDS = ("proveedor", "rfc", "contribuyente")


def load_scenario(path: Path = SCENARIO_PATH) -> list[dict[str, Any]]:
    items = yaml.safe_load(path.read_text(encoding="utf-8"))
    for item in items:
        for key in ("id", "criterio", "pregunta", "esperado"):
            if not isinstance(item.get(key), str) or not item[key].strip():
                raise ValueError(f"{item.get('id', '?')}: falta {key}.")
    return items


def visible_rows(rows: list[dict[str, Any]], limit: int = SHOWN_ROWS) -> list[dict[str, Any]]:
    return [
        {key: value for key, value in row.items() if not any(word in key.lower() for word in HIDDEN_COLUMN_WORDS)}
        for row in rows[:limit]
    ]


def evidence_entry(item: dict[str, Any], answer: dict[str, Any], seconds: float) -> dict[str, Any]:
    entry = {
        "id": item["id"],
        "criterio": item["criterio"],
        "pregunta": item["pregunta"],
        "esperado": item["esperado"],
        "tipo": answer["tipo"],
        "intentos": answer.get("intentos"),
        "segundos": round(seconds, 1),
        "intentos_fallidos": answer.get("intentos_fallidos", []),
    }
    for key in ("sql", "supuestos", "conteo", "motivo", "pregunta_aclaracion", "opciones", "sql_descartado"):
        if key in answer:
            entry[key] = answer[key]
    if answer["tipo"] == "aclaracion":
        entry["pregunta_aclaracion"] = answer.get("pregunta")
    if "filas" in answer:
        entry["primeras_filas"] = visible_rows(answer["filas"])
    return entry


def to_markdown(entries: list[dict[str, Any]], model: str, started: str) -> str:
    lines = [
        "# Evidencia del Escenario 1 (A6)",
        "",
        f"Modelo: `{model}` · Fecha: {started} · Preguntas: [`eval/escenario1.yaml`](../../escenario1.yaml)",
        "",
        "Cada pregunta se corrió una vez con el agente completo (prompt, validador, cobertura, "
        "ejecución y conteo). Las columnas con nombres de proveedores no se muestran.",
        "",
    ]
    for entry in entries:
        lines += [f"## {entry['id']}. {entry['pregunta']}", "", f"**Criterio:** {entry['criterio']}", ""]
        lines += [f"**Se esperaba:** {entry['esperado']}", ""]
        lines.append(f"**Respuesta:** `{entry['tipo']}` en {entry['intentos']} intento(s), {entry['segundos']} s.")
        lines.append("")
        if entry.get("motivo"):
            lines += [f"> {entry['motivo']}", ""]
        if entry.get("pregunta_aclaracion"):
            lines += [f"> {entry['pregunta_aclaracion']}", ""]
            lines += [f"> - {option}" for option in entry.get("opciones", [])] + [""]
        if entry.get("sql"):
            lines += ["```sql", entry["sql"], "```", ""]
        for note in entry.get("supuestos", []):
            lines.append(f"- Supuesto: {note}")
        if entry.get("supuestos"):
            lines.append("")
        if entry.get("conteo"):
            count = entry["conteo"]
            lines += [
                f"**Conteo:** {count['filas']} filas devueltas, {count['filas_totales']} sin el LIMIT, "
                f"truncado: {'sí' if count['truncado'] else 'no'}, {count['registros']} registros detrás.",
                "",
            ]
        if entry.get("primeras_filas"):
            columns = list(entry["primeras_filas"][0])
            lines += ["| " + " | ".join(columns) + " |", "|" + "---|" * len(columns)]
            lines += ["| " + " | ".join(str(row[c]) for c in columns) + " |" for row in entry["primeras_filas"]]
            lines.append("")
        for failed in entry["intentos_fallidos"]:
            lines.append(f"- Intento {failed['intento']} rechazado ({failed['etapa']}): {failed['error']}")
        if entry["intentos_fallidos"]:
            lines.append("")
    return "\n".join(lines)


def run(output_root: Path, model: str | None = None) -> Path:
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

    items = load_scenario()
    client = OllamaClient(base_url=benchmark_ollama_base_url(), model=model)
    system_prompt = build_system_prompt(schema_context(), load_examples(items))
    with connect_agent_ro() as connection, connection.cursor() as cursor:
        cursor.execute(COVERAGE_QUERY)
        coverage = Coverage.from_rows(cursor.fetchall())
    started = datetime.now()
    entries = []
    for item in items:
        start = time.perf_counter()
        answer = answer_question(item["pregunta"], client, system_prompt, coverage, execute=execute_read_only)
        entries.append(evidence_entry(item, answer, time.perf_counter() - start))
        print(f"{item['id']}: {answer['tipo']} ({answer.get('intentos')} intento(s))")
    output_dir = output_root / f"escenario1_{started:%Y%m%d_%H%M%S}"
    output_dir.mkdir(parents=True, exist_ok=False)
    (output_dir / "evidencia.json").write_text(
        json.dumps(entries, ensure_ascii=False, indent=2, default=str), encoding="utf-8"
    )
    (output_dir / "evidencia.md").write_text(
        to_markdown(entries, client.model, started.isoformat(timespec="seconds")), encoding="utf-8"
    )
    return output_dir


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--modelo", help="Modelo de Ollama; por defecto AGENT_MODEL.")
    parser.add_argument("--output-dir", type=Path, default=RESULTS_PATH)
    args = parser.parse_args()
    print(f"Evidencia en {run(args.output_dir, args.modelo)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
