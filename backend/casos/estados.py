"""Máquina de estados del caso (docs/contratos/estado_caso.md)."""

from __future__ import annotations

from dataclasses import dataclass

RECIBIDO = "recibido"
CONSULTADO = "consultado"
DETECTADO = "detectado"
NORMADO = "normado"
REPORTADO = "reportado"
EN_REVISION = "en_revision"
CERRADO = "cerrado"
BLOQUEADO = "bloqueado"

FLUJO = (RECIBIDO, CONSULTADO, DETECTADO, NORMADO, REPORTADO, EN_REVISION, CERRADO)
ESTADOS = frozenset(FLUJO + (BLOQUEADO,))
TERMINALES = frozenset({CERRADO})
SIGUIENTE = dict(zip(FLUJO, FLUJO[1:]))


class TransicionInvalida(ValueError):
    """La transición pedida no está permitida desde el estado actual."""


@dataclass(frozen=True)
class Resultado:
    estado: str
    estado_previo: str | None
    motivo_bloqueo: str | None


def transitar(
    estado_actual: str,
    estado_previo: str | None,
    destino: str,
    motivo: str | None = None,
) -> Resultado:
    """Valida una transición y devuelve los campos nuevos del caso.

    - Avance: solo al siguiente estado del flujo.
    - Bloqueo: desde cualquier estado excepto ``cerrado``, con motivo obligatorio.
    - Desbloqueo: desde ``bloqueado`` solo al estado en que se bloqueó.
    """
    if destino not in ESTADOS:
        raise TransicionInvalida(f"Estado desconocido: {destino!r}.")
    if estado_actual in TERMINALES:
        raise TransicionInvalida(f"El caso está {estado_actual!r}; no admite transiciones.")

    motivo = (motivo or "").strip() or None

    if destino == BLOQUEADO:
        if estado_actual == BLOQUEADO:
            raise TransicionInvalida("El caso ya está bloqueado.")
        if motivo is None:
            raise TransicionInvalida("Bloquear un caso requiere un motivo.")
        return Resultado(BLOQUEADO, estado_actual, motivo)

    if estado_actual == BLOQUEADO:
        if destino != estado_previo:
            raise TransicionInvalida(
                f"Un caso bloqueado solo puede volver a {estado_previo!r}; "
                "primero hay que desbloquearlo."
            )
        return Resultado(destino, None, None)

    siguiente = SIGUIENTE.get(estado_actual)
    if destino != siguiente:
        raise TransicionInvalida(
            f"No se puede pasar de {estado_actual!r} a {destino!r}; "
            f"el siguiente estado es {siguiente!r}."
        )
    return Resultado(destino, None, None)
