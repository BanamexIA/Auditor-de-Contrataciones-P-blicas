"""Eventos de bitácora (docs/contratos/evento_bitacora.md)."""

from __future__ import annotations

import time
from typing import Any, Callable, Protocol
from urllib.parse import urlparse

from telemetry.tracking import contexto_llamada

TRANSICION = "transicion"
SOLICITUD = "solicitud"
LLAMADA_LLM = "llamada_llm"
SQL_GENERADO = "sql_generado"
SQL_RECHAZADO = "sql_rechazado"
SQL_EJECUTADO = "sql_ejecutado"
CALIDAD_EVALUADA = "calidad_evaluada"
REGLAS_EVALUADAS = "reglas_evaluadas"
NORMAS_RECUPERADAS = "normas_recuperadas"
REPORTE_GUARDADO = "reporte_guardado"
DECISION = "decision"
ERROR = "error"

# Campos obligatorios de `detalle` por tipo de evento.
CAMPOS_OBLIGATORIOS: dict[str, frozenset[str]] = {
    TRANSICION: frozenset({"de", "a"}),
    SOLICITUD: frozenset({"texto"}),
    LLAMADA_LLM: frozenset({"agente", "tokens_entrada", "tokens_salida", "latencia_ms", "estado"}),
    SQL_GENERADO: frozenset({"sql"}),
    SQL_RECHAZADO: frozenset({"sql", "motivo"}),
    SQL_EJECUTADO: frozenset({"sql", "vistas", "filas", "duracion_ms", "truncado"}),
    CALIDAD_EVALUADA: frozenset({"contratos", "problemas"}),
    REGLAS_EVALUADAS: frozenset({"reglas", "senales"}),
    NORMAS_RECUPERADAS: frozenset({"normas", "sin_soporte"}),
    REPORTE_GUARDADO: frozenset({"ruta", "sha256", "version"}),
    DECISION: frozenset({"senal_id", "decision"}),
    ERROR: frozenset({"tipo", "mensaje"}),
}
TIPOS_EVENTO = frozenset(CAMPOS_OBLIGATORIOS)

# Claves que nunca deben guardarse (regla 4 del contrato).
CLAVES_PROHIBIDAS = frozenset({
    "password", "contrasena", "contraseña", "secret", "token", "api_key",
    "prompt", "system", "mensajes", "messages",
})


class EventoInvalido(ValueError):
    """El evento no cumple el contrato de bitácora."""


def validar_evento(evento: str, detalle: Any) -> None:
    if evento not in TIPOS_EVENTO:
        raise EventoInvalido(f"Tipo de evento desconocido: {evento!r}.")
    if not isinstance(detalle, dict):
        raise EventoInvalido("El detalle del evento debe ser un objeto JSON.")
    faltan = CAMPOS_OBLIGATORIOS[evento] - detalle.keys()
    if faltan:
        raise EventoInvalido(
            f"Al evento {evento!r} le faltan campos: {', '.join(sorted(faltan))}."
        )
    prohibidas = _claves_prohibidas(detalle)
    if prohibidas:
        raise EventoInvalido(
            f"El detalle no puede contener: {', '.join(sorted(prohibidas))}."
        )


def _claves_prohibidas(valor: Any) -> set[str]:
    encontradas: set[str] = set()
    if isinstance(valor, dict):
        for clave, contenido in valor.items():
            if str(clave).lower() in CLAVES_PROHIBIDAS:
                encontradas.add(str(clave))
            encontradas |= _claves_prohibidas(contenido)
    elif isinstance(valor, list):
        for contenido in valor:
            encontradas |= _claves_prohibidas(contenido)
    return encontradas


class RegistrarEvento(Protocol):
    def __call__(
        self,
        caso_id: str,
        evento: str,
        detalle: dict[str, Any],
        modelo: str | None = None,
        equipo: str | None = None,
    ) -> dict[str, Any]: ...


def equipo_de_cliente(client: Any) -> str | None:
    """Equipo que ejecuta la inferencia: el host de la URL del agente (B7)."""
    base_url = getattr(client, "base_url", None)
    if not base_url:
        return None
    return urlparse(base_url).hostname


def llamar_llm(
    registrar: RegistrarEvento,
    caso_id: str,
    agente: str,
    client: Any,
    system: str,
    prompt: str,
    temperature: float = 0.0,
    reloj: Callable[[], float] = time.perf_counter,
):
    """Llama al modelo y registra un evento ``llamada_llm`` por intento.

    Si la llamada falla, registra el error y vuelve a lanzar la excepción para
    que el orquestador decida si reintenta o bloquea el caso.
    """
    modelo = getattr(client, "model", None)
    equipo = equipo_de_cliente(client)
    inicio = reloj()
    try:
        with contexto_llamada(caso_id, agente):  # telemetry.llm_calls queda ligada al caso
            respuesta = client.generate(system=system, prompt=prompt, temperature=temperature)
    except Exception as exc:
        registrar(caso_id, LLAMADA_LLM, {
            "agente": agente,
            "cuantizacion": getattr(client, "model_quantization", None),
            "version_ollama": getattr(client, "ollama_version", None),
            "tokens_entrada": None,
            "tokens_salida": None,
            "latencia_ms": round((reloj() - inicio) * 1000, 1),
            "estado": "error",
            "tipo_error": type(exc).__name__,
        }, modelo=modelo, equipo=equipo)
        raise
    registrar(caso_id, LLAMADA_LLM, {
        "agente": agente,
        "cuantizacion": respuesta.model_quantization,
        "version_ollama": respuesta.ollama_version,
        "tokens_entrada": respuesta.input_tokens,
        "tokens_salida": respuesta.output_tokens,
        "latencia_ms": respuesta.latency_ms,
        "estado": "ok",
        "tipo_error": None,
    }, modelo=modelo, equipo=equipo)
    return respuesta
