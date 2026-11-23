"""Endpoints de casos y estados (docs/contratos/api_casos.md)."""

from __future__ import annotations

import time
from datetime import datetime, timezone
from urllib.parse import urlencode
from typing import Any

from flask import Blueprint, Response, current_app, jsonify, redirect, request
from sqlalchemy.exc import OperationalError

from backend.casos.decisiones import CasoCerrado, DecisionInvalida, SenalNoEncontrada
from backend.casos.estados import ESTADOS, TransicionInvalida
from backend.casos.repositorio import CasoNoEncontrado, RepositorioCasos, ReporteNoEncontrado
from backend.reportes.almacen import AlmacenNoDisponible, ArchivoNoEncontrado
from backend.reportes.servicio import ReporteCorrupto, leer_reporte
from backend.usuarios.auth import usuario_actual
from backend.usuarios.seguridad import firmar_descarga

EXPIRA_ENLACE_S = 300

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
    caso = _repo().crear(solicitud, creado_por=usuario_actual())
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


@bp.get("/casos/<caso_id>/bitacora")
def bitacora_caso(caso_id: str):
    try:
        eventos = _repo().listar_eventos(caso_id)
    except CasoNoEncontrado:
        return _error(404, "caso_no_encontrado", f"No existe el caso {caso_id}.")
    return jsonify(eventos=[_caso_json(ev) for ev in eventos])


def _senal_json(senal: dict[str, Any]) -> dict[str, Any]:
    datos = _caso_json(senal)
    if senal.get("decision"):
        datos["decision"] = _caso_json(senal["decision"])
    return datos


@bp.get("/casos/<caso_id>/senales")
def senales_caso(caso_id: str):
    try:
        senales = _repo().listar_senales(caso_id)
    except CasoNoEncontrado:
        return _error(404, "caso_no_encontrado", f"No existe el caso {caso_id}.")
    return jsonify(senales=[_senal_json(s) for s in senales])


@bp.post("/casos/<caso_id>/senales/<senal_id>/decision")
def decidir_senal(caso_id: str, senal_id: str):
    datos = _cuerpo()
    if datos is None:
        return _error(400, "solicitud_invalida", "El cuerpo debe ser un objeto JSON.")
    try:
        decision = _repo().decidir(caso_id, senal_id, datos.get("decision"),
                                   datos.get("comentario"), decidido_por=usuario_actual())
    except DecisionInvalida as exc:
        return _error(400, "solicitud_invalida", str(exc))
    except CasoNoEncontrado:
        return _error(404, "caso_no_encontrado", f"No existe el caso {caso_id}.")
    except SenalNoEncontrada:
        return _error(404, "senal_no_encontrada",
                      f"No existe la señal {senal_id} en el caso {caso_id}.")
    except CasoCerrado:
        return _error(409, "caso_cerrado", "El caso está cerrado; no acepta decisiones.")
    return jsonify(_caso_json(decision)), 201


@bp.get("/casos/<caso_id>/reportes")
def reportes_caso(caso_id: str):
    try:
        reportes = _repo().listar_reportes(caso_id)
    except CasoNoEncontrado:
        return _error(404, "caso_no_encontrado", f"No existe el caso {caso_id}.")
    # La uri es interna: el front descarga por /archivo.
    return jsonify(reportes=[
        _caso_json({k: v for k, v in r.items() if k != "uri"}) for r in reportes
    ])


def _resumen(llamadas: list[dict]) -> dict:
    return {
        "llamadas": len(llamadas),
        "errores": sum(1 for l in llamadas if l["estado"] != "ok"),
        "tokens_entrada": sum(l["tokens_entrada"] or 0 for l in llamadas),
        "tokens_salida": sum(l["tokens_salida"] or 0 for l in llamadas),
        "latencia_ms": round(sum(l["latencia_ms"] or 0 for l in llamadas), 1),
    }


@bp.get("/casos/<caso_id>/telemetria")
def telemetria_caso(caso_id: str):
    try:
        llamadas = _repo().listar_llamadas_llm(caso_id)
    except CasoNoEncontrado:
        return _error(404, "caso_no_encontrado", f"No existe el caso {caso_id}.")
    agentes = sorted({l["agente"] for l in llamadas})
    return jsonify(
        caso_id=caso_id,
        totales=_resumen(llamadas),
        por_agente=[{"agente": a, **_resumen([l for l in llamadas if l["agente"] == a])}
                    for a in agentes],
        llamadas=[_caso_json(l) for l in llamadas],
    )


@bp.get("/casos/<caso_id>/reportes/<int:version>/enlace")
def enlace_reporte(caso_id: str, version: int):
    """URL temporal para mostrar el reporte en un <iframe> o enlace (sin header)."""
    try:
        reporte = _repo().obtener_reporte(caso_id, version)
    except ReporteNoEncontrado:
        return _error(404, "reporte_no_encontrado",
                      f"No existe la versión {version} del reporte del caso {caso_id}.")
    try:
        url = current_app.extensions["almacen_reportes"].url_descarga(reporte["uri"], EXPIRA_ENLACE_S)
    except AlmacenNoDisponible:
        return _error(503, "almacen_no_disponible",
                      "El almacén de reportes no responde. Intenta más tarde.")
    exp = int(time.time()) + EXPIRA_ENLACE_S
    if not url:
        url = f"/casos/{caso_id}/reportes/{version}/archivo"
        cfg = current_app.extensions.get("auth")
        if cfg is not None:
            exp, firma = firmar_descarga(cfg.secreto, f"{caso_id}/{version}", EXPIRA_ENLACE_S)
            url += "?" + urlencode({"exp": exp, "firma": firma})
    return jsonify(url=url, expira=exp)


@bp.get("/casos/<caso_id>/reportes/<int:version>/archivo")
def archivo_reporte(caso_id: str, version: int):
    return _entregar_reporte(caso_id, version, redirigir=True)


@bp.get("/casos/<caso_id>/reportes/<int:version>/contenido")
def contenido_reporte(caso_id: str, version: int):
    """Los bytes del reporte siempre a través del backend (sin redirigir a S3).

    Para visores que leen el PDF con fetch (pdf.js): el navegador no puede leer S3 directo
    sin CORS en el bucket. Se verifica el SHA-256 antes de entregarlo.
    """
    return _entregar_reporte(caso_id, version, redirigir=False)


def _entregar_reporte(caso_id: str, version: int, redirigir: bool):
    try:
        reporte = _repo().obtener_reporte(caso_id, version)
    except ReporteNoEncontrado:
        return _error(404, "reporte_no_encontrado",
                      f"No existe la versión {version} del reporte del caso {caso_id}.")
    almacen = current_app.extensions["almacen_reportes"]
    try:
        url = almacen.url_descarga(reporte["uri"]) if redirigir else None
        if url:
            return redirect(url, code=302)
        contenido = leer_reporte(almacen, reporte)
    except AlmacenNoDisponible:
        current_app.logger.exception("Almacén no disponible: %s", reporte["uri"])
        return _error(503, "almacen_no_disponible",
                      "El almacén de reportes no responde. Intenta más tarde.")
    except (ReporteCorrupto, ArchivoNoEncontrado):
        current_app.logger.exception("Reporte ilegible: %s", reporte["uri"])
        return _error(500, "reporte_corrupto",
                      "El archivo del reporte no coincide con el registrado.")
    nombre = f"reporte_{caso_id}_v{version}.{reporte['formato']}"
    return Response(contenido, mimetype=reporte["content_type"], headers={
        "Content-Disposition": f'inline; filename="{nombre}"',
        "X-Content-SHA256": reporte["sha256"],
    })


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
        caso = _repo().transitar(caso_id, destino, motivo, usuario=usuario_actual())
    except CasoNoEncontrado:
        return _error(404, "caso_no_encontrado", f"No existe el caso {caso_id}.")
    except TransicionInvalida as exc:
        return _error(409, "transicion_invalida", str(exc))
    return jsonify(_caso_json(caso))
