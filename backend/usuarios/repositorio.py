"""Usuarios de la API en audit.usuarios."""

from __future__ import annotations

import re
from typing import Any, Protocol

from sqlalchemy import Engine, text
from sqlalchemy.exc import IntegrityError

from backend.usuarios.seguridad import ROLES, hashear

_USUARIO_VALIDO = re.compile(r"^[a-z0-9][a-z0-9._-]{1,39}$")
_COLUMNAS = "id, usuario, nombre, rol, activo, created_at, ultimo_acceso"


class UsuarioNoEncontrado(LookupError):
    pass


class UsuarioDuplicado(ValueError):
    pass


def validar_usuario(usuario: str) -> str:
    usuario = (usuario or "").strip().lower()
    if not _USUARIO_VALIDO.match(usuario):
        raise ValueError("Usuario inválido: 2 a 40 caracteres, minúsculas, números, '.', '_' o '-'.")
    return usuario


def validar_rol(rol: str) -> str:
    if rol not in ROLES:
        raise ValueError(f"Rol inválido: {rol!r}. Usa: {', '.join(ROLES)}.")
    return rol


class RepositorioUsuarios(Protocol):
    def alta(self, usuario: str, nombre: str | None, rol: str, contrasena: str) -> dict[str, Any]: ...
    def baja(self, usuario: str) -> dict[str, Any]: ...
    def cambiar_rol(self, usuario: str, rol: str) -> dict[str, Any]: ...
    def cambiar_contrasena(self, usuario: str, contrasena: str) -> dict[str, Any]: ...
    def listar(self, incluir_inactivos: bool = False) -> list[dict[str, Any]]: ...
    def credenciales(self, usuario: str) -> dict[str, Any] | None:
        """Fila con ``hash_contrasena`` (solo para el login), o None."""
        ...
    def activo(self, usuario: str) -> dict[str, Any] | None: ...
    def registrar_acceso(self, usuario: str) -> None: ...


class RepositorioUsuariosSQL:
    def __init__(self, engine: Engine) -> None:
        self.engine = engine

    def _actualizar(self, usuario: str, asignaciones: str, valores: dict[str, Any]) -> dict[str, Any]:
        with self.engine.begin() as conn:
            fila = conn.execute(
                text(f"UPDATE audit.usuarios SET {asignaciones} WHERE usuario = :usuario "
                     f"RETURNING {_COLUMNAS}"),
                {"usuario": validar_usuario(usuario), **valores},
            ).mappings().one_or_none()
        if fila is None:
            raise UsuarioNoEncontrado(usuario)
        return dict(fila)

    def alta(self, usuario: str, nombre: str | None, rol: str, contrasena: str) -> dict[str, Any]:
        usuario, rol, hash_ = validar_usuario(usuario), validar_rol(rol), hashear(contrasena)
        try:
            with self.engine.begin() as conn:
                fila = conn.execute(
                    text(f"""
                        INSERT INTO audit.usuarios (usuario, nombre, rol, hash_contrasena)
                        VALUES (:usuario, :nombre, :rol, :hash)
                        ON CONFLICT (usuario) DO UPDATE
                            SET nombre = EXCLUDED.nombre, rol = EXCLUDED.rol,
                                hash_contrasena = EXCLUDED.hash_contrasena, activo = TRUE
                            WHERE audit.usuarios.activo = FALSE
                        RETURNING {_COLUMNAS}"""),
                    {"usuario": usuario, "nombre": nombre, "rol": rol, "hash": hash_},
                ).mappings().one_or_none()
        except IntegrityError as exc:
            raise ValueError(str(exc.orig)) from exc
        if fila is None:
            raise UsuarioDuplicado(usuario)
        return dict(fila)

    def baja(self, usuario: str) -> dict[str, Any]:
        return self._actualizar(usuario, "activo = FALSE", {})

    def cambiar_rol(self, usuario: str, rol: str) -> dict[str, Any]:
        return self._actualizar(usuario, "rol = :rol", {"rol": validar_rol(rol)})

    def cambiar_contrasena(self, usuario: str, contrasena: str) -> dict[str, Any]:
        return self._actualizar(usuario, "hash_contrasena = :hash", {"hash": hashear(contrasena)})

    def listar(self, incluir_inactivos: bool = False) -> list[dict[str, Any]]:
        filtro = "" if incluir_inactivos else "WHERE activo"
        with self.engine.connect() as conn:
            filas = conn.execute(text(
                f"SELECT {_COLUMNAS} FROM audit.usuarios {filtro} ORDER BY usuario"
            )).mappings().all()
        return [dict(f) for f in filas]

    def credenciales(self, usuario: str) -> dict[str, Any] | None:
        with self.engine.connect() as conn:
            fila = conn.execute(
                text(f"SELECT {_COLUMNAS}, hash_contrasena FROM audit.usuarios "
                     "WHERE usuario = :usuario AND activo"),
                {"usuario": (usuario or "").strip().lower()},
            ).mappings().one_or_none()
        return dict(fila) if fila else None

    def activo(self, usuario: str) -> dict[str, Any] | None:
        with self.engine.connect() as conn:
            fila = conn.execute(
                text(f"SELECT {_COLUMNAS} FROM audit.usuarios WHERE usuario = :usuario AND activo"),
                {"usuario": usuario},
            ).mappings().one_or_none()
        return dict(fila) if fila else None

    def registrar_acceso(self, usuario: str) -> None:
        with self.engine.begin() as conn:
            conn.execute(text("UPDATE audit.usuarios SET ultimo_acceso = NOW() WHERE usuario = :u"),
                         {"u": usuario})
