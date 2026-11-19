"""Verificar si un agente (Ollama en una laptop) responde y tiene el modelo."""

from __future__ import annotations

import json
import os
import re
import time
import urllib.request
from dataclasses import dataclass, field
from typing import Any, Callable

DISPONIBLE = "disponible"
SIN_MODELO = "sin_modelo"
APAGADO = "apagado"
DESCONOCIDO = "desconocido"
ESTADOS = frozenset({DISPONIBLE, SIN_MODELO, APAGADO, DESCONOCIDO})

PUERTO_OLLAMA = 11434
_NOMBRE_VALIDO = re.compile(r"^[a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?$")

# (url, timeout_s) -> JSON decodificado. Se inyecta en las pruebas.
ClienteHttp = Callable[[str, float], Any]


class NombreInvalido(ValueError):
    pass


def validar_nombre(nombre: str) -> str:
    """Solo nombres de equipo de Tailscale: minúsculas, dígitos y guiones. Nunca una URL."""
    nombre = (nombre or "").strip().lower()
    if not _NOMBRE_VALIDO.match(nombre):
        raise NombreInvalido(
            f"Nombre de Tailscale inválido: {nombre!r}. Usa solo el nombre del equipo "
            "(por ejemplo laptop-alean), sin http://, puntos ni puerto."
        )
    return nombre


def url_de(nombre: str) -> str:
    return f"http://{validar_nombre(nombre)}:{PUERTO_OLLAMA}"


def modelo_requerido(agente: dict[str, Any]) -> str:
    return agente.get("modelo") or os.environ.get("AGENT_MODEL", "qwen2.5:7b")


def _get_json(url: str, timeout_s: float) -> Any:
    with urllib.request.urlopen(url, timeout=timeout_s) as respuesta:  # noqa: S310 (URL armada por el backend)
        return json.loads(respuesta.read().decode("utf-8"))


def _tiene_modelo(instalados: list[str], requerido: str) -> bool:
    nombres = set(instalados)
    if ":" not in requerido:
        nombres |= {n.removesuffix(":latest") for n in instalados}
    return requerido in nombres


@dataclass(frozen=True)
class Resultado:
    estado: str
    modelos: list[str] = field(default_factory=list)
    version_ollama: str | None = None
    latencia_ms: float | None = None
    error: str | None = None


def verificar(
    nombre: str,
    modelo: str,
    http: ClienteHttp = _get_json,
    timeout_s: float = 3.0,
    reloj: Callable[[], float] = time.perf_counter,
) -> Resultado:
    """Consulta /api/version y /api/tags del agente. Nunca lanza: devuelve el estado."""
    base = url_de(nombre)
    inicio = reloj()
    try:
        version = http(f"{base}/api/version", timeout_s).get("version")
        etiquetas = http(f"{base}/api/tags", timeout_s).get("models", [])
    except Exception as exc:  # red caída, DNS, timeout, JSON inválido
        return Resultado(APAGADO, error=type(exc).__name__)
    latencia = round((reloj() - inicio) * 1000, 1)
    modelos = sorted(m.get("name", "") for m in etiquetas if isinstance(m, dict))
    estado = DISPONIBLE if _tiene_modelo(modelos, modelo) else SIN_MODELO
    return Resultado(estado, modelos, version, latencia)
