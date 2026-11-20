"""Orquestador de demo: lleva un caso de ``recibido`` a ``en_revision`` con los agentes reales.

Recorrido fijo (sin LangGraph ni reintentos entre etapas; eso es O1–O8):

  1. Consulta    agents.consulta.answer_question: pregunta -> SQL validado -> filas (agent_ro).
  2. Calidad     revisa los contratos (calidad_evaluada en la bitácora); informativa, no detiene.
     Detección   agente_deteccion.ejecutar sobre los contratos que devolvió la consulta.
     Normativo   RAG (rag.chunks) con embeddings en la laptop del agente; si falla, el reporte
                 lo declara como limitación en vez de inventar normas.
  3. Reportes    agente_reporte.generar_reporte -> PDF -> almacén (S3 en la EC2).

Cada llamada al modelo queda en la bitácora y en telemetry.llm_calls. Cualquier falla
bloquea el caso con el motivo, como lo hará el orquestador.

Uso:
  docker compose exec backend python -m backend.demo --solicitud "Contratos de 2026 con proveedores en el 69-B" --usuario emiliano
  docker compose exec backend python -m backend.demo <caso_id>
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
import time
from contextlib import contextmanager

from backend.agentes.repositorio import RepositorioAgentesSQL
from backend.agentes.servicio import AgenteNoDisponible, seleccionar_agente
from backend.app import engine_desde_entorno
from backend.casos.repositorio import RepositorioCasosSQL
from backend.herramientas.servicio import SQL_COINCIDENCIAS, SQL_CONTRATOS
from backend.demo.adaptadores import (
    ClienteConBitacora,
    entrada_reporte,
    ids_de_contratos,
    llm_fn_redactor,
    senales_para_backend,
)
from backend.reportes.almacen import almacen_desde_entorno
from backend.reportes.servicio import guardar_reporte
from llm.ollama_client import OllamaClient

USUARIO = "orquestador-demo"
MAX_CONTRATOS = 500

class Bloqueo(Exception):
    """Motivo legible para bloquear el caso (lo verá el auditor)."""


def _paso(texto: str) -> None:
    print(f"[{time.strftime('%H:%M:%S')}] {texto}", flush=True)


@contextmanager
def _cronometro():
    inicio = time.perf_counter()
    medida = {}
    yield medida
    medida["ms"] = round((time.perf_counter() - inicio) * 1000, 1)


# --------------------------------------------------------------------- 1. Consulta
def etapa_consulta(repo, caso, cliente_base) -> list[dict]:
    from agents.consulta.agent import answer_question
    from agents.consulta.coverage import COVERAGE_QUERY, Coverage
    from agents.consulta.prompt import build_system_prompt
    from eval.run_benchmark import (connect_agent_ro, execute_read_only, load_examples,
                                    load_golden_set, schema_context)

    caso_id = caso["id"]
    system = build_system_prompt(schema_context(), load_examples(load_golden_set()))
    with connect_agent_ro() as conn, conn.cursor() as cur:
        cur.execute(COVERAGE_QUERY)
        cobertura = Coverage.from_rows(cur.fetchall())

    cliente = ClienteConBitacora(cliente_base, repo.registrar_evento, caso_id, "consultas")
    with _cronometro() as t:
        r = answer_question(caso["solicitud"], cliente, system, cobertura, execute=execute_read_only)
    _paso(f"  {len(cliente.llamadas)} llamada(s) al modelo, respuesta tipo '{r['tipo']}'")

    if r["tipo"] == "aclaracion":
        raise Bloqueo(f"El Agente Consulta pide aclarar: {r['pregunta']} "
                      f"Opciones: {' / '.join(r['opciones'])}. Reformula la solicitud.")
    if r["tipo"] == "sin_datos":
        raise Bloqueo(f"Sin datos para responder: {r['motivo']}")
    if r["tipo"] == "error":
        if r.get("sql_rechazado"):
            repo.registrar_evento(caso_id, "sql_rechazado",
                                  {"sql": r["sql_rechazado"], "motivo": r["motivo"]})
        raise Bloqueo(r["motivo"])

    filas = r["filas"]
    repo.registrar_evento(caso_id, "sql_generado", {
        "sql": r["sql"], "filtros": r.get("filtros", []), "supuestos": r.get("supuestos", []),
        "intentos": r.get("intentos")})
    repo.registrar_evento(caso_id, "sql_ejecutado", {
        "sql": r["sql"], "vistas": ["clean"], "filas": len(filas), "duracion_ms": t["ms"],
        "truncado": False})
    _paso(f"  SQL: {r['sql'][:160]}{'…' if len(r['sql']) > 160 else ''}")
    _paso(f"  {len(filas)} fila(s)")
    return filas


# --------------------------------------------------------------------- 2. Detección + Normativo
def _recuperador(agente_url: str, registrar):
    """RAG con embeddings en la laptop del agente. Devuelve None si no se puede preparar."""
    try:
        from agente_deteccion.normativo import RecuperadorPgvector
        from eval.run_benchmark import connect_agent_ro
        os.environ.setdefault("OLLAMA_EMBED_BASE_URL", agente_url)
        base = RecuperadorPgvector(conn=connect_agent_ro(dict_rows=True))
    except Exception as exc:
        registrar("error", {"tipo": type(exc).__name__, "mensaje": f"RAG no disponible: {exc}"[:300]})
        return None

    def recuperar(consulta, fecha, top_k):
        try:
            return base(consulta, fecha, top_k)
        except Exception as exc:  # una búsqueda fallida no tumba el caso: queda sin norma
            registrar("error", {"tipo": type(exc).__name__, "mensaje": f"RAG: {exc}"[:300]})
            try:
                base.conn.rollback()
            except Exception:
                pass
            return []
    return recuperar


def etapa_calidad(repo, caso_id: str, ids: list[str]) -> dict | None:
    """Revisa la calidad de los contratos y la deja en la bitácora (calidad_evaluada).

    Es informativa: NO detiene el caso. Si se debe detener por mala calidad, y con qué umbral,
    es una decisión pendiente del equipo (ver docs/propuestas/calidad-revision-humana.md).
    """
    from backend.herramientas.servicio import Herramientas, cargar_contratos_con
    from eval.run_benchmark import connect_agent_ro, execute_read_only

    herramientas = Herramientas(repo, execute_read_only, cargar_contratos_con(connect_agent_ro),
                                describir=dict, origen=USUARIO)
    try:
        r = herramientas.evaluar_calidad(caso_id, ids)
    except Exception as exc:  # la revisión de calidad nunca tumba el caso
        repo.registrar_evento(caso_id, "error", {"tipo": type(exc).__name__,
                                                 "mensaje": f"Calidad no evaluada: {str(exc)[:200]}"})
        _paso(f"  calidad no evaluada: {type(exc).__name__}")
        return None
    problemas = ", ".join(f"{n} {m}" for m, n in r["problemas_por_motivo"].items()) or "sin problemas"
    _paso(f"  calidad: {r['contratos_revisados']} contrato(s) revisados; {problemas}; "
          f"{len(r['contradicciones'])} contradicción(es)")
    return r


def etapa_deteccion(repo, caso_id, filas_consulta, agente_url, avanzar) -> dict:
    from agente_deteccion.agente import ejecutar
    from agente_deteccion.esquema import validar_resultado
    from eval.run_benchmark import connect_agent_ro

    ids = ids_de_contratos(filas_consulta)[:MAX_CONTRATOS]
    if not ids:
        raise Bloqueo("La consulta no devolvió códigos de contrato, así que no hay contratos que "
                      "analizar. Reformula pidiendo los contratos (p. ej. «lista los contratos…»).")
    etapa_calidad(repo, caso_id, ids)
    with connect_agent_ro() as conn, conn.cursor() as cur:
        cur.execute(SQL_CONTRATOS, (ids,))
        filas = list(cur.fetchall())
        cur.execute(SQL_COINCIDENCIAS, (ids,))
        coincidencias = list(cur.fetchall())
    _paso(f"  {len(filas)} contrato(s), {len(coincidencias)} coincidencia(s) con el 69-B")

    def registrar(evento, detalle):
        repo.registrar_evento(caso_id, evento, detalle)

    recuperador = _recuperador(agente_url, registrar)
    resultado = ejecutar(filas, coincidencias, recuperador=recuperador, consulta_id=caso_id)
    resultado = json.loads(json.dumps(resultado, default=str))  # fechas y Decimal -> texto
    problemas = validar_resultado(resultado)
    if problemas:
        raise Bloqueo("La salida de Detección no cumple su contrato: " + "; ".join(problemas[:3]))

    senales = repo.registrar_senales(caso_id, senales_para_backend(resultado))
    c = resultado["calidad"]
    repo.registrar_evento(caso_id, "reglas_evaluadas", {
        "reglas": sorted({s["codigo"] for s in resultado["senales"]}),
        "senales": len(senales), "version_reglas": resultado["version_reglas"],
        "evaluadas": c["senales_evaluadas"], "no_evaluables": c["senales_no_evaluables"],
        "excluidos": len(resultado["excluidos"])})
    _paso(f"  {c['senales_evaluadas']} señal(es) evaluada(s), {c['senales_no_evaluables']} no evaluable(s)")
    avanzar("detectado")

    normas = resultado["normas_recuperadas"]
    repo.registrar_evento(caso_id, "normas_recuperadas", {
        "normas": [{k: n.get(k) for k in ("fragmento_id", "senal_id", "norma", "articulo", "version")}
                   for n in normas],
        "sin_soporte": resultado["sin_norma_aplicable"],
        "rag": recuperador is not None})
    _paso(f"  {len(normas)} fragmento(s) de norma, {len(resultado['sin_norma_aplicable'])} señal(es) sin norma")
    avanzar("normado")
    return resultado


# --------------------------------------------------------------------- 3. Reportes
def etapa_reportes(repo, caso_id, deteccion, cliente_base, agente) -> dict:
    from agente_reporte.agente import exportar, generar_reporte
    from agente_reporte.redactor import Redactor

    cliente = ClienteConBitacora(cliente_base, repo.registrar_evento, caso_id, "reportes")
    redactor = Redactor(llm_fn_redactor(cliente), cliente.model)
    reporte = generar_reporte(entrada_reporte(deteccion), redactor)
    v = reporte.verificacion
    _paso(f"  {len(cliente.llamadas)} llamada(s) al modelo; citas correctas "
          f"{v.citas_correctas}/{v.total_citas}; verificación "
          f"{'APROBADA' if v.aprobado else 'NO aprobada (queda como limitación)'}")
    with tempfile.TemporaryDirectory() as tmp:
        rutas = exportar(reporte, tmp, ("pdf",))
        pdf = rutas["pdf"].read_bytes()
    return guardar_reporte(repo, almacen_desde_entorno(), caso_id, pdf, "pdf",
                           modelo=cliente.model, equipo=agente["nombre_tailnet"])


# --------------------------------------------------------------------- guion
def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="python -m backend.demo")
    p.add_argument("caso_id", nargs="?", help="Caso en estado 'recibido' (si no, se crea uno)")
    p.add_argument("--solicitud", default="Lista los contratos de 2026 cuyos proveedores aparecen en el listado 69-B del SAT")
    p.add_argument("--usuario", help="Usuario del caso: se prefiere su laptop")
    p.add_argument("--modelo", help="Modelo a usar (por defecto el del agente)")
    p.add_argument("--pausa", type=float, default=2.0, help="Segundos entre etapas, para verlo en el front")
    a = p.parse_args(argv)

    engine = engine_desde_entorno()
    repo, repo_agentes = RepositorioCasosSQL(engine), RepositorioAgentesSQL(engine)
    if a.caso_id:
        caso = repo.obtener(a.caso_id)
    else:
        caso = repo.crear(a.solicitud, creado_por=a.usuario)
        _paso(f"Caso creado: {caso['id']}")
    caso_id = caso["id"]
    if caso["estado"] != "recibido":
        print(f"Error: el caso está en '{caso['estado']}'; el guion empieza en 'recibido'.", file=sys.stderr)
        return 2

    def avanzar(estado: str) -> None:
        repo.transitar(caso_id, estado, None, usuario=USUARIO)
        _paso(f"→ {estado}")
        time.sleep(a.pausa)

    def bloquear(motivo: str) -> int:
        repo.transitar(caso_id, "bloqueado", motivo[:1000], usuario=USUARIO)
        _paso(f"BLOQUEADO: {motivo}")
        return 1

    try:
        agente = seleccionar_agente(repo_agentes, usuario=a.usuario or caso.get("creado_por"))
    except AgenteNoDisponible as exc:
        return bloquear(str(exc))
    cliente = OllamaClient(base_url=agente["url"], model=a.modelo or agente["modelo"])
    _paso(f"Agente: {agente['nombre_tailnet']} ({cliente.model})")

    try:
        _paso("1. Agente Consulta")
        filas = etapa_consulta(repo, caso, cliente)
        avanzar("consultado")
        _paso("2. Agente Detección y Normativo")
        deteccion = etapa_deteccion(repo, caso_id, filas, agente["url"], avanzar)
        _paso("3. Agente Reportes")
        reporte = etapa_reportes(repo, caso_id, deteccion, cliente, agente)
        _paso(f"  reporte v{reporte['version']} guardado")
        avanzar("reportado")
        avanzar("en_revision")
    except Bloqueo as exc:
        return bloquear(str(exc))
    except Exception as exc:  # cualquier otra falla bloquea con motivo, como hará el orquestador
        repo.registrar_evento(caso_id, "error", {"tipo": type(exc).__name__, "mensaje": str(exc)[:300]})
        return bloquear(f"Falla en el orquestador de demo: {type(exc).__name__}: {str(exc)[:200]}")

    _paso(f"Listo. Caso {caso_id} en 'en_revision': decide las señales en el front y ciérralo.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
