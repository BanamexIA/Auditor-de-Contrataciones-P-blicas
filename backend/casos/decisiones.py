"""Reglas de las decisiones humanas sobre señales (docs/contratos/decisiones.md)."""

from __future__ import annotations

RELEVANTE = "relevante"
DESCARTADA = "descartada"
PENDIENTE = "pendiente"
DECISIONES = frozenset({RELEVANTE, DESCARTADA, PENDIENTE})


class DecisionInvalida(ValueError):
    """La decisión no cumple el contrato (valor desconocido o descarte sin comentario)."""


class CasoCerrado(ValueError):
    """El caso está cerrado y ya no acepta decisiones."""


class SenalNoEncontrada(LookupError):
    """La señal no existe o no pertenece al caso."""


def validar_decision(decision: object, comentario: object) -> tuple[str, str | None]:
    """Devuelve ``(decision, comentario)`` normalizados o lanza ``DecisionInvalida``."""
    if decision not in DECISIONES:
        raise DecisionInvalida(
            f"Decisión desconocida: {decision!r}. Usa relevante, descartada o pendiente."
        )
    if comentario is not None and not isinstance(comentario, str):
        raise DecisionInvalida("El comentario debe ser texto.")
    comentario = (comentario or "").strip() or None
    if decision == DESCARTADA and comentario is None:
        raise DecisionInvalida("Descartar una señal requiere un comentario con el motivo.")
    return str(decision), comentario
