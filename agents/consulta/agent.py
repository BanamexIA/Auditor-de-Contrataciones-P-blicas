from __future__ import annotations

import re
from typing import Any, Callable, Sequence

from psycopg import DataError, Error, ProgrammingError

from agents.consulta.concepts import missing_concept, missing_concept_reason, plain_text
from agents.consulta.counts import count_support, empty_count, truncation_note
from agents.consulta.coverage import Coverage, check_coverage, contradicted_no_data
from agents.consulta.prompt import (
    ResponseFormatError,
    build_user_prompt,
    is_system_note,
    parse_response,
    proposed_sql,
)
from agents.consulta.validator import SQLValidationError
from llm.base import LLMClient


MAX_ATTEMPTS = 2
# PostgreSQL rejected the SQL itself (unknown column, GROUP BY mistake, bad date...),
# so the model can fix it. Connection problems and timeouts are not retried.
SQL_REJECTED_ERRORS = (ProgrammingError, DataError)
MAX_DB_ERROR_CHARS = 500
# Words of a note about coverage, over the text without accents and in lowercase.
_COVERAGE_TALK = re.compile(
    r"\b(in)?complet[oa]s?\b|\bcobertura\b|\bparcial(es|mente)?\b"
    r"|\b(no hay|sin|faltan?) (datos|registros|contratos)\b"
)

Executor = Callable[[str], list[dict[str, Any]]]


def answer_question(
    question: str,
    client: LLMClient,
    system_prompt: str,
    coverage: Coverage,
    clarifications: Sequence[tuple[str, str]] = (),
    execute: Executor | None = None,
    count_records: bool = True,
) -> dict[str, Any]:
    """Turns a question into a checked response.

    Returns tipo "sql", "aclaracion", "sin_datos" or "error". An invalid answer is
    retried once with the error; a second failure returns "error" so the
    orchestrator can block the case with that reason. Model connection errors
    propagate to the orchestrator.

    Without ``execute`` nothing is run. With it (for example execute_read_only),
    a SQL that passes the coverage check is also executed: if PostgreSQL rejects
    it, the model gets the database error in that same single retry, and a
    successful answer carries the rows in "filas". Other database errors, such
    as a lost connection or the time limit, propagate.

    With ``execute`` and ``count_records``, the answer also carries "conteo"
    (HU-01): rows returned, rows without the LIMIT, whether the LIMIT cut the
    result and how many view records the answer summarizes (see counts.py). A
    cut result also gets a note in "supuestos". If the counting queries fail,
    the counts are None and the answer is still returned.

    A "sin_datos" whose reason names years that do have contracts is also
    retried (stage "cobertura", A5, mejora 17).

    Every answer carries "intentos_fallidos": for each failed attempt, its
    number, the stage that rejected it ("formato", "validador", "cobertura" or
    "base"), the error and the SQL the model proposed, if any (A5, mejora 9).
    """
    user_prompt = build_user_prompt(question, clarifications)
    prompt = user_prompt
    error = ""
    rejected_sql = None
    failed: list[dict[str, Any]] = []
    for attempt in range(1, MAX_ATTEMPTS + 1):
        response = client.generate(system_prompt, prompt, temperature=0.0)
        try:
            result = parse_response(response.text)
        except (ResponseFormatError, SQLValidationError) as exc:
            error = str(exc)
            rejected_sql = None
            stage = "formato" if isinstance(exc, ResponseFormatError) else "validador"
            failed.append(_failed_attempt(attempt, stage, error, proposed_sql(response.text)))
            prompt = (
                f"{user_prompt}\n\nTu respuesta anterior no fue válida: {error} "
                "Corrígela y responde solo con el objeto JSON."
            )
            continue
        result["intentos"] = attempt
        concept = missing_concept(question)
        if concept:
            # A5, mejora 5: the sources lack the concept, whatever the model proposed. The
            # reason comes from code even when the model said "sin_datos": on c10 its own
            # reason also claimed, wrongly, that end dates are not recorded.
            no_data = {"tipo": "sin_datos", "motivo": missing_concept_reason(concept), "intentos": attempt}
            if result["tipo"] == "sql":
                no_data["sql_descartado"] = result["sql"]
            return {**no_data, "intentos_fallidos": failed}
        contradiction = (
            contradicted_no_data(result["motivo"], coverage) if result["tipo"] == "sin_datos" else None
        )
        if contradiction:
            # A5, mejora 17: periods without data are the coverage check's call, from the SQL.
            error = f"La respuesta dice que no hay datos, pero {contradiction}."
            rejected_sql = None
            failed.append(_failed_attempt(attempt, "cobertura", error, None))
            prompt = (
                f"{user_prompt}\n\nTu respuesta anterior dijo que no hay datos, pero {contradiction}. "
                "Escribe el SQL: si el periodo está incompleto, el sistema agrega el aviso. "
                "Responde solo con el objeto JSON."
            )
            continue
        if result["tipo"] != "sql":
            return {**result, "intentos_fallidos": failed}
        result = _apply_coverage(result, coverage)
        if result["tipo"] != "sql" or execute is None:
            return {**result, "intentos_fallidos": failed}
        try:
            result["filas"] = execute(result["sql"])
        except SQL_REJECTED_ERRORS as exc:
            error = f"PostgreSQL rechazó la consulta: {_database_message(exc)}"
            rejected_sql = result["sql"]
            failed.append(_failed_attempt(attempt, "base", error, rejected_sql))
            prompt = (
                f"{user_prompt}\n\nTu SQL anterior fue:\n{rejected_sql}\n{error} "
                "Corrígelo y responde solo con el objeto JSON."
            )
            continue
        if count_records:
            result = _add_count(result, execute)
        return {**result, "intentos_fallidos": failed}
    failure = {
        "tipo": "error",
        "motivo": (
            f"El modelo no dio una respuesta válida en {MAX_ATTEMPTS} intentos. "
            f"Último error: {error}"
        ),
        "intentos": MAX_ATTEMPTS,
        "intentos_fallidos": failed,
    }
    if rejected_sql:
        failure["sql_rechazado"] = rejected_sql
    return failure


def _add_count(result: dict[str, Any], execute: Executor) -> dict[str, Any]:
    """HU-01: how many records back the answer, and whether the LIMIT cut it."""
    try:
        count = count_support(result["sql"], result["filas"], execute)
    except (Error, SQLValidationError):
        # The answer is already valid; a failed count (for example, the time limit)
        # leaves the counts empty instead of losing the rows.
        count = empty_count(result["filas"])
    supuestos = list(result.get("supuestos", []))
    note = truncation_note(count)
    if note:
        supuestos.append(note)
    return {**result, "conteo": count, "supuestos": supuestos}


def _failed_attempt(attempt: int, stage: str, error: str, sql: str | None) -> dict[str, Any]:
    return {"intento": attempt, "etapa": stage, "error": error, "sql": sql}


def _database_message(exc: Exception) -> str:
    message = str(exc).strip() or type(exc).__name__
    return message[:MAX_DB_ERROR_CHARS]


def talks_about_coverage(supuesto: str) -> bool:
    """True for a model note about complete or missing years or source coverage (A5, mejora 6)."""
    return bool(_COVERAGE_TALK.search(plain_text(supuesto)))


def _apply_coverage(result: dict[str, Any], coverage: Coverage) -> dict[str, Any]:
    check = check_coverage(result["sql"], coverage)
    if check.sin_datos:
        return {
            "tipo": "sin_datos",
            "motivo": check.sin_datos,
            "sql_descartado": result["sql"],
            "intentos": result["intentos"],
        }
    # Only the coverage check speaks about coverage: on 2026-11-17 the model wrote
    # "2024 está completo" next to the check's correct warning that it is not.
    supuestos = [
        item for item in result["supuestos"] if is_system_note(item) or not talks_about_coverage(item)
    ]
    supuestos.extend(item for item in check.supuestos if item not in supuestos)
    return {**result, "supuestos": supuestos}
