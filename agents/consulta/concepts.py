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


def plain_text(text: str) -> str:
    """Lowercase text without accents, so "Cancelación" and "cancelacion" match."""
    decomposed = unicodedata.normalize("NFKD", text.casefold())
    return "".join(char for char in decomposed if not unicodedata.combining(char))


def missing_concept(question: str) -> str | None:
    """Returns what the sources lack if the question asks about it, or None."""
    plain = plain_text(question)
    for pattern, concept in MISSING_CONCEPTS:
        if pattern.search(plain):
            return concept
    return None


def missing_concept_reason(concept: str) -> str:
    return (
        f"Las fuentes no registran {concept}. No hay un dato equivalente en las vistas, "
        "y ninguna otra columna lo sustituye."
    )
