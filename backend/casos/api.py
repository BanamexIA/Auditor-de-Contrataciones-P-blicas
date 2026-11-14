"""Endpoints de casos y estados (docs/contratos/api_casos.md)."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from flask import Blueprint, current_app, jsonify, request
from sqlalchemy.exc import OperationalError

from backend.casos.estados import ESTADOS, TransicionInvalida
from backend.casos.repositorio import CasoNoEncontrado, RepositorioCasos

LIMITE_DEFECTO = 50
LIMITE_MAXIMO = 100

bp = Blueprint("casos", __name__)


def _error(http: int, codigo: str, mensaje: str):
    return jsonify(error={"codigo": codigo, "mensaje": mensaje}), http


def _repo() -> RepositorioCasos:
    return current_app.extensions["repositorio_casos"]


def _iso(valor: Any) -> Any:
    if isinstance(valor, datetime):
        return valor.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
    return valor


def _caso_json(caso: dict[str, Any]) -> dict[str, Any]:
    return {k: _iso(v) for k, v in caso.items()}


def _cuerpo() -> dict[str, Any] | None:
    datos = request.get_json(silent=True)
    return datos if isinstance(datos, dict) else None


@bp.errorhandler(OperationalError)
def _bd_no_disponible(_exc):
    current_app.logger.exception("Base de datos no disponible")
    return _error(503, "bd_no_disponible", "La base de datos no responde.")


@bp.post("/casos")
def crear_caso():
    datos = _cuerpo()
    solicitud = datos.get("solicitud") if datos else None
    if not isinstance(solicitud, str) or not solicitud.strip():
        return _error(400, "solicitud_invalida", "El campo 'solicitud' es obligatorio.")
    caso = _repo().crear(solicitud)
    respuesta = jsonify(_caso_json(caso))
    respuesta.status_code = 201
    respuesta.headers["Location"] = f"/casos/{caso['id']}"
    return respuesta


@bp.get("/casos/<caso_id>")
def obtener_caso(caso_id: str):
    try:
        return jsonify(_caso_json(_repo().obtener(caso_id)))
    except CasoNoEncontrado:
        return _error(404, "caso_no_encontrado", f"No existe el caso {caso_id}.")


@bp.get("/casos")
def listar_casos():
    estado = request.args.get("estado") or None
    if estado is not None and estado not in ESTADOS:
        return _error(400, "solicitud_invalida", f"Estado desconocido: {estado!r}.")
    try:
        limite = int(request.args.get("limite", LIMITE_DEFECTO))
    except ValueError:
        limite = 0
    if not 1 <= limite <= LIMITE_MAXIMO:
        return _error(400, "solicitud_invalida",
                      f"'limite' debe estar entre 1 y {LIMITE_MAXIMO}.")
    casos = _repo().listar(estado, limite)
    return jsonify(casos=[_caso_json(c) for c in casos])


@bp.post("/casos/<caso_id>/transiciones")
def transitar_caso(caso_id: str):
    datos = _cuerpo()
    destino = datos.get("estado") if datos else None
    motivo = datos.get("motivo") if datos else None
    if not isinstance(destino, str) or not destino:
        return _error(400, "solicitud_invalida", "El campo 'estado' es obligatorio.")
    if motivo is not None and not isinstance(motivo, str):
        return _error(400, "solicitud_invalida", "El campo 'motivo' debe ser texto.")
    try:
        caso = _repo().transitar(caso_id, destino, motivo)
    except CasoNoEncontrado:
        return _error(404, "caso_no_encontrado", f"No existe el caso {caso_id}.")
    except TransicionInvalida as exc:
        return _error(409, "transicion_invalida", str(exc))
    return jsonify(_caso_json(caso))
