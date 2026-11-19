"""Endpoints de consulta del registro de agentes. El alta y la baja son solo por CLI."""

from __future__ import annotations

from typing import Any

from flask import Blueprint, current_app, jsonify

from backend.agentes.repositorio import AgenteNoEncontrado
from backend.agentes.servicio import verificar_agente
from backend.casos.api import _caso_json, _error

bp = Blueprint("agentes", __name__)


def _repo():
    return current_app.extensions.get("repositorio_agentes")


def _agente_json(agente: dict[str, Any]) -> dict[str, Any]:
    return _caso_json(agente)


@bp.get("/agentes")
def listar_agentes():
    repo = _repo()
    if repo is None:
        return _error(503, "bd_no_disponible", "El registro de agentes no está configurado.")
    return jsonify(agentes=[_agente_json(a) for a in repo.listar()])


@bp.get("/agentes/<int:agente_id>")
def obtener_agente(agente_id: int):
    repo = _repo()
    if repo is None:
        return _error(503, "bd_no_disponible", "El registro de agentes no está configurado.")
    try:
        return jsonify(_agente_json(repo.obtener(agente_id)))
    except AgenteNoEncontrado:
        return _error(404, "agente_no_encontrado", f"No existe el agente {agente_id}.")


@bp.post("/agentes/<int:agente_id>/verificar")
def verificar_ahora(agente_id: int):
    """Verifica un agente registrado. Usa el nombre guardado; nunca una URL del cliente."""
    repo = _repo()
    if repo is None:
        return _error(503, "bd_no_disponible", "El registro de agentes no está configurado.")
    try:
        agente = repo.obtener(agente_id)
    except AgenteNoEncontrado:
        return _error(404, "agente_no_encontrado", f"No existe el agente {agente_id}.")
    http = current_app.extensions.get("http_agentes")
    actualizado = verificar_agente(repo, agente, http) if http else verificar_agente(repo, agente)
    return jsonify(_agente_json(actualizado))
