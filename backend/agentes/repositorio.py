"""Persistencia del registro de agentes (audit.agentes)."""

from __future__ import annotations

import json
from typing import Any, Protocol

from sqlalchemy import Engine, text
from sqlalchemy.exc import IntegrityError

from backend.agentes.verificacion import Resultado, validar_nombre


class AgenteNoEncontrado(LookupError):
    pass


class AgenteDuplicado(ValueError):
    pass


class RepositorioAgentes(Protocol):
    def alta(self, usuario: str, nombre: str, modelo: str | None = None) -> dict[str, Any]: ...
    def baja(self, nombre: str) -> dict[str, Any]: ...
    def listar(self, incluir_inactivos: bool = False) -> list[dict[str, Any]]: ...
    def obtener(self, agente_id: int) -> dict[str, Any]: ...
    def guardar_verificacion(self, agente_id: int, resultado: Resultado) -> dict[str, Any]: ...


_COLUMNAS = (
    "id, usuario, nombre_tailnet, modelo, estado, activo, modelos, version_ollama, "
    "latencia_ms, ultimo_error, ultima_verificacion, created_at"
)


class RepositorioAgentesSQL:
    def __init__(self, engine: Engine) -> None:
        self.engine = engine

    def alta(self, usuario: str, nombre: str, modelo: str | None = None) -> dict[str, Any]:
        """Registra un agente, o reactiva uno dado de baja con el mismo nombre."""
        nombre = validar_nombre(nombre)
        usuario = (usuario or "").strip()
        if not usuario:
            raise ValueError("El usuario es obligatorio.")
        with self.engine.begin() as conn:
            existente = conn.execute(
                text("SELECT activo FROM audit.agentes WHERE nombre_tailnet = :n FOR UPDATE"),
                {"n": nombre},
            ).scalar_one_or_none()
            if existente is True:
                raise AgenteDuplicado(f"El agente {nombre} ya está registrado.")
            try:
                fila = conn.execute(
                    text(
                        f"""
                        INSERT INTO audit.agentes (usuario, nombre_tailnet, modelo)
                        VALUES (:u, :n, :m)
                        ON CONFLICT (nombre_tailnet) DO UPDATE
                        SET usuario = EXCLUDED.usuario, modelo = EXCLUDED.modelo,
                            activo = TRUE, estado = 'desconocido'
                        RETURNING {_COLUMNAS}
                        """
                    ),
                    {"u": usuario, "n": nombre, "m": modelo},
                ).mappings().one()
            except IntegrityError as exc:
                raise AgenteDuplicado(f"El agente {nombre} ya está registrado.") from exc
        return dict(fila)

    def baja(self, nombre: str) -> dict[str, Any]:
        with self.engine.begin() as conn:
            fila = conn.execute(
                text(
                    f"UPDATE audit.agentes SET activo = FALSE "
                    f"WHERE nombre_tailnet = :n RETURNING {_COLUMNAS}"
                ),
                {"n": validar_nombre(nombre)},
            ).mappings().one_or_none()
        if fila is None:
            raise AgenteNoEncontrado(nombre)
        return dict(fila)

    def listar(self, incluir_inactivos: bool = False) -> list[dict[str, Any]]:
        filtro = "" if incluir_inactivos else "WHERE activo"
        with self.engine.connect() as conn:
            filas = conn.execute(
                text(f"SELECT {_COLUMNAS} FROM audit.agentes {filtro} ORDER BY usuario, id")
            ).mappings().all()
        return [dict(f) for f in filas]

    def obtener(self, agente_id: int) -> dict[str, Any]:
        with self.engine.connect() as conn:
            fila = conn.execute(
                text(f"SELECT {_COLUMNAS} FROM audit.agentes WHERE id = :id"),
                {"id": agente_id},
            ).mappings().one_or_none()
        if fila is None:
            raise AgenteNoEncontrado(str(agente_id))
        return dict(fila)

    def guardar_verificacion(self, agente_id: int, resultado: Resultado) -> dict[str, Any]:
        with self.engine.begin() as conn:
            fila = conn.execute(
                text(
                    f"""
                    UPDATE audit.agentes
                    SET estado = :estado, modelos = CAST(:modelos AS JSONB),
                        version_ollama = coalesce(:version, version_ollama),
                        latencia_ms = :latencia, ultimo_error = :error,
                        ultima_verificacion = NOW()
                    WHERE id = :id
                    RETURNING {_COLUMNAS}
                    """
                ),
                {"id": agente_id, "estado": resultado.estado,
                 "modelos": json.dumps(resultado.modelos), "version": resultado.version_ollama,
                 "latencia": resultado.latencia_ms, "error": resultado.error},
            ).mappings().one_or_none()
        if fila is None:
            raise AgenteNoEncontrado(str(agente_id))
        return dict(fila)
