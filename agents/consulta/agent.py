from __future__ import annotations

from typing import Any, Callable, Sequence

from psycopg import DataError, ProgrammingError

from agents.consulta.coverage import Coverage, check_coverage
from agents.consulta.prompt import ResponseFormatError, build_user_prompt, parse_response
from agents.consulta.validator import SQLValidationError
from llm.base import LLMClient


MAX_ATTEMPTS = 2
# PostgreSQL rejected the SQL itself (unknown column, GROUP BY mistake, bad date...),
# so the model can fix it. Connection problems and timeouts are not retried.
SQL_REJECTED_ERRORS = (ProgrammingError, DataError)
MAX_DB_ERROR_CHARS = 500

Executor = Callable[[str], list[dict[str, Any]]]


def answer_question(
    question: str,
    client: LLMClient,
    system_prompt: str,
    coverage: Coverage,
    clarifications: Sequence[tuple[str, str]] = (),
    execute: Executor | None = None,
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
    """
    user_prompt = build_user_prompt(question, clarifications)
    prompt = user_prompt
    error = ""
    rejected_sql = None
    for attempt in range(1, MAX_ATTEMPTS + 1):
        response = client.generate(system_prompt, prompt, temperature=0.0)
        try:
            result = parse_response(response.text)
        except (ResponseFormatError, SQLValidationError) as exc:
            error = str(exc)
            rejected_sql = None
            prompt = (
                f"{user_prompt}\n\nTu respuesta anterior no fue válida: {error} "
                "Corrígela y responde solo con el objeto JSON."
            )
            continue
        result["intentos"] = attempt
        if result["tipo"] != "sql":
            return result
        result = _apply_coverage(result, coverage)
        if result["tipo"] != "sql" or execute is None:
            return result
        try:
            result["filas"] = execute(result["sql"])
        except SQL_REJECTED_ERRORS as exc:
            error = f"PostgreSQL rechazó la consulta: {_database_message(exc)}"
            rejected_sql = result["sql"]
            prompt = (
                f"{user_prompt}\n\nTu SQL anterior fue:\n{rejected_sql}\n{error} "
                "Corrígelo y responde solo con el objeto JSON."
            )
            continue
        return result
    failure = {
        "tipo": "error",
        "motivo": (
            f"El modelo no dio una respuesta válida en {MAX_ATTEMPTS} intentos. "
            f"Último error: {error}"
        ),
        "intentos": MAX_ATTEMPTS,
    }
    if rejected_sql:
        failure["sql_rechazado"] = rejected_sql
    return failure


def _database_message(exc: Exception) -> str:
    message = str(exc).strip() or type(exc).__name__
    return message[:MAX_DB_ERROR_CHARS]


def _apply_coverage(result: dict[str, Any], coverage: Coverage) -> dict[str, Any]:
    check = check_coverage(result["sql"], coverage)
    if check.sin_datos:
        return {
            "tipo": "sin_datos",
            "motivo": check.sin_datos,
            "sql_descartado": result["sql"],
            "intentos": result["intentos"],
        }
    supuestos = list(result["supuestos"])
    supuestos.extend(item for item in check.supuestos if item not in supuestos)
    return {**result, "supuestos": supuestos}
