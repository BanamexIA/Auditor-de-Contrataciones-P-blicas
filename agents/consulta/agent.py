from __future__ import annotations

from typing import Any, Sequence

from agents.consulta.coverage import Coverage, check_coverage
from agents.consulta.prompt import ResponseFormatError, build_user_prompt, parse_response
from agents.consulta.validator import SQLValidationError
from llm.base import LLMClient


MAX_ATTEMPTS = 2


def answer_question(
    question: str,
    client: LLMClient,
    system_prompt: str,
    coverage: Coverage,
    clarifications: Sequence[tuple[str, str]] = (),
) -> dict[str, Any]:
    """Turns a question into a checked response; it never executes SQL.

    Returns tipo "sql", "aclaracion", "sin_datos" or "error". An invalid answer is
    retried once with the error; a second failure returns "error" so the
    orchestrator can block the case with that reason. Model connection errors
    propagate to the orchestrator.
    """
    user_prompt = build_user_prompt(question, clarifications)
    prompt = user_prompt
    error = ""
    for attempt in range(1, MAX_ATTEMPTS + 1):
        response = client.generate(system_prompt, prompt, temperature=0.0)
        try:
            result = parse_response(response.text)
        except (ResponseFormatError, SQLValidationError) as exc:
            error = str(exc)
            prompt = (
                f"{user_prompt}\n\nTu respuesta anterior no fue válida: {error} "
                "Corrígela y responde solo con el objeto JSON."
            )
            continue
        result["intentos"] = attempt
        if result["tipo"] == "sql":
            return _apply_coverage(result, coverage)
        return result
    return {
        "tipo": "error",
        "motivo": (
            f"El modelo no dio una respuesta válida en {MAX_ATTEMPTS} intentos. "
            f"Último error: {error}"
        ),
        "intentos": MAX_ATTEMPTS,
    }


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
