"""CLI del administrador para el registro de agentes.

En la EC2:
    docker compose exec backend python -m backend.agentes alta --usuario alean --nombre laptop-alean
    docker compose exec backend python -m backend.agentes listar
    docker compose exec backend python -m backend.agentes verificar
    docker compose exec backend python -m backend.agentes baja --nombre laptop-alean
    docker compose exec backend python -m backend.agentes calentar      # antes de una demo
"""

from __future__ import annotations

import argparse
import sys

from backend.agentes.repositorio import (
    AgenteDuplicado,
    AgenteNoEncontrado,
    RepositorioAgentes,
    RepositorioAgentesSQL,
)
from backend.agentes.servicio import verificar_agente, verificar_todos
from backend.agentes.verificacion import ClienteHttp, NombreInvalido, _get_json


def _linea(a: dict) -> str:
    estado = a["estado"] if a["activo"] else "baja"
    verificado = a["ultima_verificacion"] or "nunca"
    return (f"{a['id']:>3}  {a['nombre_tailnet']:<24} {a['usuario']:<12} {estado:<11} "
            f"{a['modelo'] or '(AGENT_MODEL)':<16} {verificado}")


def main(
    argv: list[str] | None = None,
    repo: RepositorioAgentes | None = None,
    http: ClienteHttp = _get_json,
) -> int:
    parser = argparse.ArgumentParser(prog="python -m backend.agentes")
    sub = parser.add_subparsers(dest="comando", required=True)
    p_alta = sub.add_parser("alta", help="Registrar una laptop con Ollama")
    p_alta.add_argument("--usuario", required=True)
    p_alta.add_argument("--nombre", required=True, help="Nombre del equipo en Tailscale")
    p_alta.add_argument("--modelo", help="Modelo preferido (por defecto AGENT_MODEL)")
    p_baja = sub.add_parser("baja", help="Dar de baja (no se borra)")
    p_baja.add_argument("--nombre", required=True)
    p_listar = sub.add_parser("listar")
    p_listar.add_argument("--todos", action="store_true", help="Incluir dados de baja")
    p_ver = sub.add_parser("verificar", help="Verificar ahora")
    p_ver.add_argument("--nombre", help="Solo este agente")
    p_cal = sub.add_parser("calentar", help="Cargar los modelos en la GPU de cada laptop disponible")
    p_cal.add_argument("--nombre", help="Solo este agente")
    args = parser.parse_args(argv)

    if repo is None:
        from backend.app import engine_desde_entorno
        repo = RepositorioAgentesSQL(engine_desde_entorno())

    try:
        if args.comando == "alta":
            a = repo.alta(args.usuario, args.nombre, args.modelo)
            print(f"Alta: {a['nombre_tailnet']} de {a['usuario']}. Verificando...")
            print(_linea(verificar_agente(repo, a, http)))
        elif args.comando == "baja":
            print("Baja:", _linea(repo.baja(args.nombre)))
        elif args.comando == "listar":
            for a in repo.listar(incluir_inactivos=args.todos):
                print(_linea(a))
        elif args.comando == "verificar":
            agentes = repo.listar()
            if args.nombre:
                agentes = [a for a in agentes if a["nombre_tailnet"] == args.nombre.lower()]
                if not agentes:
                    raise AgenteNoEncontrado(args.nombre)
                resultados = [verificar_agente(repo, a, http) for a in agentes]
            else:
                resultados = verificar_todos(repo, http)
            for a in resultados:
                print(_linea(a) + (f"  error={a['ultimo_error']}" if a["ultimo_error"] else ""))
        elif args.comando == "calentar":
            from backend.agentes.calentar import calentar, resumen
            from backend.agentes.verificacion import modelo_requerido, url_de
            agentes = [a for a in verificar_todos(repo, http)
                       if not args.nombre or a["nombre_tailnet"] == args.nombre.lower()]
            if not agentes:
                raise AgenteNoEncontrado(args.nombre or "(ninguno activo)")
            for a in agentes:
                if a["estado"] != "disponible":
                    print(f"{a['nombre_tailnet']}: se omite ({a['estado']})")
                    continue
                try:
                    print(resumen(a["nombre_tailnet"], calentar(url_de(a["nombre_tailnet"]), modelo_requerido(a))))
                except Exception as exc:  # una laptop que falla no detiene a las demás
                    print(f"{a['nombre_tailnet']}: no se pudo calentar ({type(exc).__name__}: {exc})")
    except (NombreInvalido, AgenteDuplicado, ValueError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 2
    except AgenteNoEncontrado as exc:
        print(f"Error: no existe el agente {exc}.", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
