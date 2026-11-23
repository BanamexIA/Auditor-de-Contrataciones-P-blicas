"""Correr el orquestador desde la terminal (reemplaza a ``python -m backend.demo``).

  docker compose exec backend python -m backend.orquestador --solicitud "Contratos de 2026 con proveedores en el 69-B" --usuario emiliano
  docker compose exec backend python -m backend.orquestador <caso_id>
  docker compose exec backend python -m backend.orquestador --dibujar      # imprime el grafo en Mermaid
"""

from __future__ import annotations

import argparse
import sys
import time


def _log(texto: str) -> None:
    print(f"[{time.strftime('%H:%M:%S')}] {texto}", flush=True)


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="python -m backend.orquestador")
    p.add_argument("caso_id", nargs="?", help="Caso en estado 'recibido' (si no, se crea uno)")
    p.add_argument("--solicitud", default="Lista los contratos de 2026 cuyos proveedores aparecen en el listado 69-B del SAT")
    p.add_argument("--usuario", help="Usuario del caso: se prefiere su laptop")
    p.add_argument("--modelo", help="Modelo a usar (por defecto el del agente)")
    p.add_argument("--dibujar", action="store_true", help="Solo imprime el grafo en Mermaid")
    a = p.parse_args(argv)

    if a.dibujar:
        from backend.orquestador.grafo import construir_grafo
        from backend.orquestador.nodos import Dependencias
        vacio = Dependencias(*(None,) * 7)
        print(construir_grafo(vacio).get_graph().draw_mermaid())
        return 0

    from backend.agentes.repositorio import RepositorioAgentesSQL
    from backend.app import engine_desde_entorno
    from backend.casos.repositorio import RepositorioCasosSQL
    from backend.orquestador.dependencias import dependencias_reales
    from backend.orquestador.grafo import orquestar_caso

    engine = engine_desde_entorno()
    repo = RepositorioCasosSQL(engine)
    caso_id = a.caso_id or repo.crear(a.solicitud, creado_por=a.usuario)["id"]
    _log(f"Caso {caso_id}")
    deps = dependencias_reales(repo, RepositorioAgentesSQL(engine), log=_log, modelo=a.modelo)
    final = orquestar_caso(caso_id, deps)
    for aviso in final.get("parciales") or []:
        _log(f"  aviso: {aviso}")
    if final.get("motivo_bloqueo"):
        return 1
    _log(f"Listo. Caso {caso_id} en 'en_revision': decide las señales en el front y ciérralo.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
