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
        **base, tipo="sql", sql=sql.get("sql"), supuestos=sql.get("supuestos", []),
        equipo=agente["nombre_tailnet"], modelo=cliente.model, total_filas=len(filas),
        filas=[{k: _json(v) for k, v in f.items()} for f in filas[:MAX_FILAS]],
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
