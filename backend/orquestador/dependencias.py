"""Dependencias reales: conecta los nodos con la BD, las laptops y los 3 agentes del equipo.

Reusa las etapas que ya probó el orquestador de demo (``backend/demo``) para no duplicar lógica:
la preparación del Agente Consulta, la revisión de calidad, el RAG y el guardado del reporte.
Los imports pesados (psycopg, agentes) van dentro de las funciones para que importar el paquete
no requiera la base.
"""

from __future__ import annotations

import os
from typing import Any, Callable

from backend.orquestador.nodos import Dependencias


def dependencias_reales(repo, repo_agentes, log: Callable[[str], None] | None = None,
                        modelo: str | None = None) -> Dependencias:
    from backend.agentes.servicio import seleccionar_agente
    from backend.herramientas.servicio import cargar_contratos_con
    from eval.run_benchmark import connect_agent_ro
    from llm.ollama_client import OllamaClient

    def elegir(usuario: str | None) -> dict:
        return seleccionar_agente(repo_agentes, usuario=usuario)

    def crear_cliente(agente: dict):
        return OllamaClient(base_url=agente["url"], model=modelo or agente["modelo"])

    def consultar(solicitud: str, cliente) -> dict:
        from agents.consulta.agent import answer_question
        from agents.consulta.coverage import COVERAGE_QUERY, Coverage
        from agents.consulta.prompt import build_system_prompt
        from eval.run_benchmark import execute_read_only, load_examples, load_golden_set, schema_context

        system = build_system_prompt(schema_context(), load_examples(load_golden_set()))
        with connect_agent_ro() as conn, conn.cursor() as cur:
            cur.execute(COVERAGE_QUERY)
            cobertura = Coverage.from_rows(cur.fetchall())
        return answer_question(solicitud, cliente, system, cobertura, execute=execute_read_only)

    def evaluar_calidad(caso_id: str, ids: list[str]) -> Any:
        from backend.demo.__main__ import etapa_calidad
        return etapa_calidad(repo, caso_id, ids)

    def crear_recuperador(agente: dict | None):
        if not agente and not os.environ.get("OLLAMA_EMBED_BASE_URL"):
            raise RuntimeError("no hay laptop para calcular embeddings")
        from agente_deteccion.normativo import RecuperadorPgvector
        if agente:  # los embeddings se calculan en la misma laptop elegida para el caso
            os.environ["OLLAMA_EMBED_BASE_URL"] = agente["url"]
        base = RecuperadorPgvector(conn=connect_agent_ro(dict_rows=True))

        def recuperar(consulta, fecha, top_k):
            try:
                return base(consulta, fecha, top_k)
            except Exception:
                try:  # deja la conexión usable para la siguiente señal
                    base.conn.rollback()
                except Exception:
                    pass
                raise
        return recuperar

    def generar_reporte(caso_id: str, deteccion: dict, cliente, agente: dict | None) -> dict:
        from backend.demo.__main__ import etapa_reportes
        return etapa_reportes(repo, caso_id, deteccion, cliente, agente)

    return Dependencias(
        repo=repo,
        seleccionar_agente=elegir,
        crear_cliente=crear_cliente,
        consultar=consultar,
        cargar_contratos=cargar_contratos_con(connect_agent_ro),
        crear_recuperador=crear_recuperador,
        generar_reporte=generar_reporte,
        evaluar_calidad=evaluar_calidad,
        log=log or (lambda texto: None),
    )
