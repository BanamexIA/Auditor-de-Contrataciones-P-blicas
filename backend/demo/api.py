"""Endpoint de demo: el front escribe una pregunta y el Agente Consulta la contesta.

POST /demo/preguntar {"pregunta": "..."} crea un caso, corre el Agente Consulta en la laptop
disponible y devuelve el SQL y las filas. El caso queda en ``consultado`` (o ``bloqueado``
con el motivo), así que todo queda en la bitácora igual que con el orquestador.

CORS: el front de demo se sirve aparte; define CORS_ORIGENES (separados por coma),
p. ej. ``http://localhost:8080``. Sin la variable no se agregan cabeceras CORS.
"""

from __future__ import annotations

import os
from datetime import date, datetime
from decimal import Decimal

from backend.usuarios.auth import puede_ver_sql
from flask import Blueprint, Flask, current_app, jsonify, request

from backend.agentes.servicio import AgenteNoDisponible, seleccionar_agente
from backend.usuarios.auth import usuario_actual
from llm.ollama_client import OllamaClient

demo_bp = Blueprint("demo", __name__)
MAX_FILAS = 200
MAX_PREGUNTA = 1000
USUARIO = "orquestador-demo"


def _json(valor):
    if isinstance(valor, (date, datetime)):
        return valor.isoformat()
    if isinstance(valor, Decimal):
        return float(valor)
    return valor


def _error(codigo: str, mensaje: str, http: int):
    return jsonify(error={"codigo": codigo, "mensaje": mensaje}), http


@demo_bp.post("/demo/preguntar")
def preguntar():
    from backend.demo.__main__ import Bloqueo, etapa_consulta

    cuerpo = request.get_json(silent=True) or {}
    pregunta = cuerpo.get("pregunta")
    if not isinstance(pregunta, str) or not pregunta.strip():
        return _error("solicitud_invalida", "Escribe una pregunta.", 400)
    if len(pregunta) > MAX_PREGUNTA:
        return _error("solicitud_invalida", f"La pregunta pasa de {MAX_PREGUNTA} caracteres.", 400)

    repo = current_app.extensions["repositorio_casos"]
    usuario = usuario_actual()
    caso = repo.crear(pregunta.strip(), creado_por=usuario)
    base = {"caso_id": caso["id"]}

    def bloquear(motivo: str, http: int, codigo: str):
        repo.transitar(caso["id"], "bloqueado", motivo[:1000], usuario=USUARIO)
        return jsonify(**base, tipo="bloqueado", motivo=motivo, codigo=codigo), http

    try:
        agente = seleccionar_agente(current_app.extensions["repositorio_agentes"], usuario=usuario)
    except AgenteNoDisponible as exc:
        return bloquear(str(exc), 503, "agente_no_disponible")
    cliente = OllamaClient(base_url=agente["url"], model=agente["modelo"])

    try:
        filas = etapa_consulta(repo, caso, cliente)
    except Bloqueo as exc:  # aclaración, sin datos o SQL inválido: es una respuesta, no un error
        return bloquear(str(exc), 200, "sin_respuesta")
    except Exception as exc:
        current_app.logger.exception("Agente Consulta falló")
        repo.registrar_evento(caso["id"], "error", {"tipo": type(exc).__name__, "mensaje": str(exc)[:300]})
        return bloquear(f"El Agente Consulta falló: {type(exc).__name__}. Intenta de nuevo.", 502,
                        "agente_fallo")
    repo.transitar(caso["id"], "consultado", None, usuario=USUARIO)

    sql = next((e["detalle"] for e in reversed(repo.listar_eventos(caso["id"]))
                if e["evento"] == "sql_generado"), {})
    return jsonify(
        **base, tipo="sql", sql=sql.get("sql") if puede_ver_sql() else None, supuestos=sql.get("supuestos", []),
        equipo=agente["nombre_tailnet"], modelo=cliente.model, total_filas=len(filas),
        filas=[{k: _json(v) for k, v in f.items()} for f in filas[:MAX_FILAS]],
    )


@demo_bp.post("/demo/casos/<caso_id>/analizar")
def analizar(caso_id: str):
    """Calidad, Detección, Normativo y Reportes sobre un caso ya consultado.

    No confía en filas enviadas por el navegador: vuelve a ejecutar (solo lectura) el SQL que
    quedó en la bitácora del caso. Con ``narrativa_llm: false`` (por defecto) el reporte usa el
    texto de respaldo y tarda segundos; las señales, normas y cifras son las reales.
    """
    from backend.casos.repositorio import CasoNoEncontrado
    from backend.demo.__main__ import Bloqueo, etapa_deteccion, etapa_reportes
    from eval.run_benchmark import execute_read_only

    repo = current_app.extensions["repositorio_casos"]
    try:
        caso = repo.obtener(caso_id)
    except CasoNoEncontrado:
        return _error("caso_no_encontrado", f"No existe el caso {caso_id}.", 404)
    if caso["estado"] != "consultado":
        return _error("transicion_invalida",
                      f"El caso está en '{caso['estado']}'; solo se analiza un caso 'consultado'.", 409)
    sql = next((e["detalle"].get("sql") for e in reversed(repo.listar_eventos(caso_id))
                if e["evento"] == "sql_ejecutado"), None)
    if not sql:
        return _error("sin_consulta", "El caso no tiene una consulta ejecutada que analizar.", 409)
    con_llm = bool((request.get_json(silent=True) or {}).get("narrativa_llm"))

    def bloquear(motivo: str, http: int, codigo: str):
        repo.transitar(caso_id, "bloqueado", motivo[:1000], usuario=USUARIO)
        return jsonify(caso_id=caso_id, estado="bloqueado", motivo=motivo, codigo=codigo), http

    try:
        agente = seleccionar_agente(current_app.extensions["repositorio_agentes"],
                                    usuario=usuario_actual() or caso.get("creado_por"))
    except AgenteNoDisponible:
        agente = None  # sin laptop: sin RAG y con narrativas de respaldo
    if con_llm and agente is None:
        return bloquear("Se pidió redactar con el modelo, pero no hay ninguna laptop disponible.",
                        503, "agente_no_disponible")
    cliente = OllamaClient(base_url=agente["url"], model=agente["modelo"]) if con_llm else None

    def avanzar(estado: str) -> None:
        repo.transitar(caso_id, estado, None, usuario=USUARIO)

    try:
        filas = execute_read_only(sql)
        deteccion = etapa_deteccion(repo, caso_id, filas, agente["url"] if agente else None, avanzar)
        reporte = etapa_reportes(repo, caso_id, deteccion, cliente, agente)
        avanzar("reportado")
        avanzar("en_revision")
    except Bloqueo as exc:
        return bloquear(str(exc), 200, "sin_respuesta")
    except Exception as exc:
        current_app.logger.exception("Análisis falló")
        repo.registrar_evento(caso_id, "error", {"tipo": type(exc).__name__, "mensaje": str(exc)[:300]})
        return bloquear(f"El análisis falló: {type(exc).__name__}. Revisa la bitácora del caso.", 502,
                        "analisis_fallo")

    calidad = deteccion["calidad"]
    return jsonify(
        caso_id=caso_id, estado="en_revision",
        senales=len(deteccion["senales"]), evaluadas=calidad["senales_evaluadas"],
        no_evaluables=calidad["senales_no_evaluables"], normas=len(deteccion["normas_recuperadas"]),
        narrativa_llm=con_llm, rag=agente is not None,
        reporte={"version": reporte["version"], "formato": reporte.get("formato", "pdf"),
                 "tamano_bytes": reporte["tamano_bytes"], "sha256": reporte["sha256"]},
    )


def configurar_cors(app: Flask) -> None:
    origenes = {o.strip().rstrip("/") for o in os.environ.get("CORS_ORIGENES", "").split(",") if o.strip()}
    if not origenes:
        return

    @app.before_request
    def preflight():  # antes de la autenticación: el navegador no manda el token en OPTIONS
        if request.method == "OPTIONS" and request.headers.get("Origin") in origenes:
            return "", 204

    @app.after_request
    def cabeceras(respuesta):
        origen = request.headers.get("Origin")
        if origen in origenes:
            respuesta.headers["Access-Control-Allow-Origin"] = origen
            respuesta.headers["Access-Control-Allow-Headers"] = "Authorization, Content-Type"
            respuesta.headers["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS"
            respuesta.headers["Vary"] = "Origin"
        return respuesta
