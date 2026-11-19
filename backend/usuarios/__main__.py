"""CLI del administrador para los usuarios de la API.

En la EC2 (pide la contraseña sin mostrarla; por eso -it):
    docker compose exec -it backend python -m backend.usuarios alta --usuario ana --rol auditor --nombre "Ana P."
    docker compose exec backend python -m backend.usuarios listar
    docker compose exec -it backend python -m backend.usuarios contrasena --usuario ana
    docker compose exec backend python -m backend.usuarios rol --usuario ana --rol admin
    docker compose exec backend python -m backend.usuarios baja --usuario ana

Para scripts: --contrasena-stdin lee la contraseña de la entrada estándar.
"""

from __future__ import annotations

import argparse
import getpass
import sys

from backend.usuarios.repositorio import (
    RepositorioUsuarios,
    RepositorioUsuariosSQL,
    UsuarioDuplicado,
    UsuarioNoEncontrado,
)
from backend.usuarios.seguridad import ROLES, validar_contrasena


def _linea(u: dict) -> str:
    estado = "activo" if u["activo"] else "baja"
    acceso = u["ultimo_acceso"] or "nunca"
    return f"{u['usuario']:<20} {u['rol']:<8} {estado:<7} {u['nombre'] or '':<24} último acceso: {acceso}"


def _contrasena(desde_stdin: bool, leer=getpass.getpass, entrada=sys.stdin) -> str:
    if desde_stdin:
        return entrada.readline().rstrip("\r\n")
    primera = leer("Contraseña: ")
    validar_contrasena(primera)
    if leer("Repite la contraseña: ") != primera:
        raise ValueError("Las contraseñas no coinciden.")
    return primera


def main(argv: list[str] | None = None, repo: RepositorioUsuarios | None = None,
         leer=getpass.getpass, entrada=sys.stdin) -> int:
    p = argparse.ArgumentParser(prog="python -m backend.usuarios")
    sub = p.add_subparsers(dest="comando", required=True)
    alta = sub.add_parser("alta", help="Crear (o reactivar) un usuario")
    alta.add_argument("--usuario", required=True)
    alta.add_argument("--rol", required=True, choices=ROLES)
    alta.add_argument("--nombre")
    alta.add_argument("--contrasena-stdin", action="store_true")
    cambio = sub.add_parser("contrasena", help="Cambiar la contraseña")
    cambio.add_argument("--usuario", required=True)
    cambio.add_argument("--contrasena-stdin", action="store_true")
    rol = sub.add_parser("rol", help="Cambiar el rol")
    rol.add_argument("--usuario", required=True)
    rol.add_argument("--rol", required=True, choices=ROLES)
    baja = sub.add_parser("baja", help="Desactivar (no se borra; su sesión deja de servir)")
    baja.add_argument("--usuario", required=True)
    listar = sub.add_parser("listar")
    listar.add_argument("--todos", action="store_true", help="Incluir dados de baja")
    a = p.parse_args(argv)

    if repo is None:
        from backend.app import engine_desde_entorno
        repo = RepositorioUsuariosSQL(engine_desde_entorno())

    try:
        if a.comando == "alta":
            u = repo.alta(a.usuario, a.nombre, a.rol, _contrasena(a.contrasena_stdin, leer, entrada))
            print("Alta:", _linea(u))
        elif a.comando == "contrasena":
            u = repo.cambiar_contrasena(a.usuario, _contrasena(a.contrasena_stdin, leer, entrada))
            print("Contraseña cambiada:", u["usuario"])
        elif a.comando == "rol":
            print("Rol:", _linea(repo.cambiar_rol(a.usuario, a.rol)))
        elif a.comando == "baja":
            print("Baja:", _linea(repo.baja(a.usuario)))
        else:
            for u in repo.listar(incluir_inactivos=a.todos):
                print(_linea(u))
    except UsuarioDuplicado as exc:
        print(f"Error: el usuario {exc} ya existe y está activo.", file=sys.stderr)
        return 2
    except UsuarioNoEncontrado as exc:
        print(f"Error: no existe el usuario {exc}.", file=sys.stderr)
        return 2
    except ValueError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
