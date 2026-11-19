"""Verificar agentes, elegir uno para un caso y revisarlos periódicamente."""

from __future__ import annotations

import logging
import threading
from typing import Any

from backend.agentes.repositorio import RepositorioAgentes
from backend.agentes.verificacion import (
    DISPONIBLE,
    SIN_MODELO,
    ClienteHttp,
    _get_json,
    modelo_requerido,
    url_de,
    verificar,
)

log = logging.getLogger(__name__)


class AgenteNoDisponible(RuntimeError):
    """Ningún agente respondió. El mensaje sirve como motivo de BLOQUEADO."""


def verificar_agente(
    repo: RepositorioAgentes, agente: dict[str, Any], http: ClienteHttp = _get_json
) -> dict[str, Any]:
    resultado = verificar(agente["nombre_tailnet"], modelo_requerido(agente), http=http)
    return repo.guardar_verificacion(agente["id"], resultado)


def verificar_todos(repo: RepositorioAgentes, http: ClienteHttp = _get_json) -> list[dict[str, Any]]:
    return [verificar_agente(repo, a, http) for a in repo.listar()]


def _orden(agentes: list[dict[str, Any]], usuario: str | None) -> list[dict[str, Any]]:
    """Primero los del usuario; dentro de cada grupo, los que estaban disponibles."""
    return sorted(
        agentes,
        key=lambda a: (a["usuario"] != usuario, a["estado"] != DISPONIBLE, a["id"]),
    )


def seleccionar_agente(
    repo: RepositorioAgentes,
    usuario: str | None = None,
    http: ClienteHttp = _get_json,
) -> dict[str, Any]:
    """Elige un agente para un caso, verificándolo justo antes de usarlo.

    Devuelve el agente con ``url`` y ``modelo`` listos para ``OllamaClient``. Si
    ninguno responde, lanza ``AgenteNoDisponible`` con el estado de cada uno.
    """
    probados = []
    pasos = []
    for agente in _orden(repo.listar(), usuario):
        actualizado = verificar_agente(repo, agente, http)
        if actualizado["estado"] == DISPONIBLE:
            return {**actualizado, "url": url_de(actualizado["nombre_tailnet"]),
                    "modelo": modelo_requerido(actualizado)}
        nombre, estado = actualizado["nombre_tailnet"], actualizado["estado"]
        if estado == SIN_MODELO:
            modelo = modelo_requerido(actualizado)
            probados.append(f"{nombre} (sin_modelo: falta {modelo})")
            pasos.append(f"en {nombre} ejecuta 'ollama pull {modelo}'")
        else:
            probados.append(f"{nombre} ({estado})")
            pasos.append(f"enciende {nombre} con Tailscale conectado y Ollama abierto")
    if not probados:
        raise AgenteNoDisponible("No hay agentes registrados. Pide al administrador que dé de alta uno.")
    raise AgenteNoDisponible(
        "Ningún agente de inferencia disponible: " + ", ".join(probados)
        + ". Para continuar, " + " o ".join(dict.fromkeys(pasos))
        + "; después desbloquea el caso."
    )


class MonitorAgentes:
    """Hilo que verifica todos los agentes cada ``intervalo_s`` segundos."""

    def __init__(self, repo: RepositorioAgentes, intervalo_s: float,
                 http: ClienteHttp = _get_json) -> None:
        self.repo, self.intervalo_s, self.http = repo, intervalo_s, http
        self._detener = threading.Event()
        self._hilo = threading.Thread(target=self._correr, name="monitor-agentes", daemon=True)

    def iniciar(self) -> "MonitorAgentes":
        self._hilo.start()
        return self

    def detener(self) -> None:
        self._detener.set()
        self._hilo.join(timeout=5)

    def _correr(self) -> None:
        while not self._detener.is_set():
            try:
                verificar_todos(self.repo, self.http)
            except Exception:  # la BD caída no debe matar el hilo
                log.exception("Falló la verificación periódica de agentes")
            self._detener.wait(self.intervalo_s)
