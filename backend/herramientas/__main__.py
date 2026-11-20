"""Arranca el servidor MCP del Data Steward.

  docker compose exec -T backend python -m backend.herramientas          # stdio (por defecto)
  docker compose exec backend python -m backend.herramientas --http      # HTTP en 127.0.0.1:8765/mcp

stdio es lo recomendado: el cliente (orquestador o agente) lanza el proceso y no se abre ningún
puerto. El modo HTTP no tiene autenticación propia, así que solo escucha en 127.0.0.1.
"""

from __future__ import annotations

import argparse
import os
import sys

from backend.app import engine_desde_entorno
from backend.casos.repositorio import RepositorioCasosSQL
from backend.herramientas.servicio import Herramientas, cargar_contratos_con
from backend.herramientas.servidor import crear_servidor


def _describir() -> dict:
    from eval.run_benchmark import schema_context
    return {"vistas_y_columnas": schema_context(), "cobertura": _cobertura().describe()}


def _cobertura():
    from agents.consulta.coverage import COVERAGE_QUERY, Coverage
    from eval.run_benchmark import connect_agent_ro
    with connect_agent_ro() as conn, conn.cursor() as cur:
        cur.execute(COVERAGE_QUERY)
        return Coverage.from_rows(cur.fetchall())


def _recuperador(engine):
    """RAG con embeddings en una laptop disponible (o en OLLAMA_EMBED_BASE_URL)."""
    def crear():
        from agente_deteccion.normativo import RecuperadorPgvector
        from eval.run_benchmark import connect_agent_ro
        if not os.environ.get("OLLAMA_EMBED_BASE_URL"):
            from backend.agentes.repositorio import RepositorioAgentesSQL
            from backend.agentes.servicio import seleccionar_agente
            os.environ["OLLAMA_EMBED_BASE_URL"] = seleccionar_agente(RepositorioAgentesSQL(engine))["url"]
        return RecuperadorPgvector(conn=connect_agent_ro())
    return crear


def herramientas_desde_entorno(origen: str = "mcp") -> Herramientas:
    from eval.run_benchmark import connect_agent_ro, execute_read_only
    engine = engine_desde_entorno()
    return Herramientas(
        repo=RepositorioCasosSQL(engine),
        ejecutar_sql=execute_read_only,
        cargar_contratos=cargar_contratos_con(connect_agent_ro),
        describir=_describir,
        cobertura=_cobertura,
        recuperador=_recuperador(engine),
        origen=origen,
    )


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="python -m backend.herramientas")
    p.add_argument("--http", action="store_true", help="HTTP en 127.0.0.1 en vez de stdio")
    p.add_argument("--puerto", type=int, default=8765)
    a = p.parse_args(argv)
    servidor = crear_servidor(herramientas_desde_entorno())
    if a.http:
        servidor.run("streamable-http", host="127.0.0.1", port=a.puerto)
    else:
        servidor.run("stdio")
    return 0


if __name__ == "__main__":
    sys.exit(main())
