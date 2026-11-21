"""Concepts the sources never record (A5, mejora 5).

A question about one of them gets "sin_datos" from code, whatever the model
answered, so no other column is passed off as that concept. On 2026-11-17 the
model listed contracts whose end date comes before the start date as if they
were cancellations (case c10).
"""
from __future__ import annotations

import re
import unicodedata

# (pattern over the question without accents and in lowercase, what the sources lack)
MISSING_CONCEPTS = (
    (re.compile(r"\bcancel\w*"), "cancelaciones de contratos"),
    (re.compile(r"\bresci[ns]\w*"), "rescisiones de contratos"),
    (re.compile(r"\bmodific\w*"), "convenios modificatorios ni modificaciones de contratos"),
    (
        re.compile(r"\bpag(o|os|ad[oa]s?|aron|ar|aba|aban)\b"),
        "pagos ni fechas de pago (el importe es importe registrado, no gasto pagado)",
    ),
    (
        re.compile(r"\bsancion\w*|\binhabilit\w*"),
        "sanciones ni inhabilitaciones de proveedores (el listado 69-B es una presunción fiscal, no una sanción)",
    ),
    (re.compile(r"\bpenaliz\w*|\bmulta(s|d[oa]s?)?\b"), "penalizaciones ni multas"),
)

# Data that exists in a source but not in the agent's views (A5, mejora 18). On
# 2026-11-20 f04 asked for a company's situation in the 69-B and the model
# listed its matches instead. Remove an entry when the views gain the data
# (decision 7 of docs/vistas_estrella.md).
_SITUATION_WORDS = r"(situacion|estatus|status|presunt\w*|definitiv\w*|desvirtu\w*|sentencia favorable)"
VIEW_GAPS = (
    (
        re.compile(rf"\b{_SITUATION_WORDS}\b.*\b69\W?b\b|\b69\W?b\b.*\b{_SITUATION_WORDS}\b"),
        "la situación del contribuyente en el listado 69-B (presunto, definitivo, desvirtuado o sentencia favorable)",
    ),
)


def plain_text(text: str) -> str:
    """Lowercase text without accents, so "Cancelación" and "cancelacion" match."""
    decomposed = unicodedata.normalize("NFKD", text.casefold())
    return "".join(char for char in decomposed if not unicodedata.combining(char))


def missing_concept(question: str) -> str | None:
    """Returns what the sources or the views lack if the question asks about it, or None."""
    plain = plain_text(question)
    for pattern, concept in MISSING_CONCEPTS + VIEW_GAPS:
        if pattern.search(plain):
            return concept
    return None


def missing_concept_reason(concept: str) -> str:
    if concept in {gap for _, gap in VIEW_GAPS}:
        return (
            f"Las vistas del agente no tienen {concept}, así que no se puede afirmar. "
            "Una coincidencia con el listado es una señal para revisión humana; la situación "
            "se confirma en el listado publicado por el SAT."
        )
    return (
        f"Las fuentes no registran {concept}. No hay un dato equivalente en las vistas, "
        "y ninguna otra columna lo sustituye."
    )
