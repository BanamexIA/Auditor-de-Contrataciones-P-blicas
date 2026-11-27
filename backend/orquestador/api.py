"""Endpoint para que el front lance el orquestador sobre un caso.

POST /casos/<caso_id>/orquestar  -> 202 {"caso_id", "estado": "recibido", "mensaje"}
     cuerpo opcional: {"narrativa_llm": false} -> reporte con narrativas de respaldo (rápido)
GET  /casos/<caso_id>/resultados -> filas de la consulta del caso (re-ejecuta su SQL, solo lectura)

El caso tarda minutos (modelo local), así que el grafo corre en un hilo y el front sigue el avance
con GET /casos/<id> y GET /casos/<id>/bitacora, igual que hoy. Los estados que va poniendo el
orquestador y el motivo de bloqueo son los del contrato (docs/contratos/estado_caso.md).

Para pruebas, ``app.extensions["orquestador_deps"]`` puede traer una función
``(app) -> Dependencias`` y ``app.extensions["lanzar_orquestador"]`` una función que corra el
trabajo sin hilo.
"""

from __future__ import annotations

import threading

from flask import Blueprint, current_app, jsonify, request

from backend.casos import estados as e
from backend.casos.repositorio import CasoNoEncontrado

bp = Blueprint("orquestador", __name__)
_en_curso: set[str] = set()
_candado = threading.Lock()


def _error(http: int, codigo: str, mensaje: str):
    return jsonify(error={"codigo": codigo, "mensaje": mensaje}), http


def _deps(app):
    fabrica = app.extensions.get("orquestador_deps")
    if fabrica:
        return fabrica(app)
    from backend.orquestador.dependencias import dependencias_reales
    return dependencias_reales(app.extensions["repositorio_casos"],
                               app.extensions["repositorio_agentes"],
                               log=lambda texto: app.logger.info("[orquestador] %s", texto))


def _lanzar_hilo(trabajo) -> None:
    threading.Thread(target=trabajo, name="orquestador", daemon=True).start()


@bp.post("/casos/<caso_id>/orquestar")
def orquestar(caso_id: str):
    from backend.orquestador.grafo import orquestar_caso

    repo = current_app.extensions["repositorio_casos"]
    try:
        caso = repo.obtener(caso_id)
    except CasoNoEncontrado:
        return _error(404, "caso_no_encontrado", f"No existe el caso {caso_id}.")
    if caso["estado"] != e.RECIBIDO:
        return _error(409, "transicion_invalida",
                      f"El caso está en '{caso['estado']}'; el orquestador solo arranca en 'recibido'.")
    with _candado:
        if caso_id in _en_curso:
            return _error(409, "en_curso", "El orquestador ya está trabajando en este caso.")
        _en_curso.add(caso_id)

    app = current_app._get_current_object()
    deps = _deps(app)
    cuerpo = request.get_json(silent=True) or {}
    if isinstance(cuerpo.get("narrativa_llm"), bool):
        deps.narrativa_llm = cuerpo["narrativa_llm"]

    def trabajo():
        try:
            orquestar_caso(caso_id, deps)
        except Exception:
            app.logger.exception("El orquestador falló en el caso %s", caso_id)
        finally:
            with _candado:
                _en_curso.discard(caso_id)

    app.extensions.get("lanzar_orquestador", _lanzar_hilo)(trabajo)
    return jsonify(caso_id=caso_id, estado=e.RECIBIDO,
                   mensaje="El orquestador empezó. Sigue el avance en /casos/<id> y su bitácora."), 202


MAX_FILAS_RESULTADOS = 200


def _ejecutar_solo_lectura(sql: str) -> list[dict]:
    from eval.run_benchmark import execute_read_only  # agent_ro, solo lectura y con tiempo límite
    return execute_read_only(sql)


def _a_json(valor):
    """Decimal -> número (montos); fechas y lo demás -> texto."""
    from decimal import Decimal
    return float(valor) if isinstance(valor, Decimal) else str(valor)


@bp.get("/casos/<caso_id>/resultados")
def resultados(caso_id: str):
    """Filas que devolvió el Agente Consulta, para mostrarlas en el front.

    No se guardan: se vuelve a ejecutar (con agent_ro) el SQL que quedó en la bitácora del caso,
    así la tabla siempre sale de la misma consulta auditada.
    """
    import json

    repo = current_app.extensions["repositorio_casos"]
    try:
        eventos = repo.listar_eventos(caso_id)
    except CasoNoEncontrado:
        return _error(404, "caso_no_encontrado", f"No existe el caso {caso_id}.")
    ejecutado = next((ev["detalle"] for ev in reversed(eventos) if ev["evento"] == "sql_ejecutado"), None)
    if not ejecutado or not ejecutado.get("sql"):
        return _error(409, "sin_consulta", "El caso todavía no tiene una consulta ejecutada.")
    supuestos = next((ev["detalle"].get("supuestos", []) for ev in reversed(eventos)
                      if ev["evento"] == "sql_generado"), [])
    ejecutar = current_app.extensions.get("ejecutar_solo_lectura", _ejecutar_solo_lectura)
    try:
        filas = ejecutar(ejecutado["sql"])
    except Exception:
        current_app.logger.exception("No se pudieron recuperar los resultados del caso %s", caso_id)
        return _error(503, "resultados_no_disponibles",
                      "No se pudo volver a ejecutar la consulta del caso. Intenta más tarde.")
    filas = json.loads(json.dumps(filas, default=_a_json))
    from backend.usuarios.auth import puede_ver_sql
    return jsonify(caso_id=caso_id, sql=ejecutado["sql"] if puede_ver_sql() else None, supuestos=supuestos,
                   total_filas=len(filas), filas=filas[:MAX_FILAS_RESULTADOS])
