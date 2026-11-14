"""Persistencia de casos en audit.casos, con su evento en audit.bitacora."""

from __future__ import annotations

import json
import uuid
from typing import Any, Protocol

from sqlalchemy import Engine, text

from backend.casos.estados import RECIBIDO, transitar


class CasoNoEncontrado(LookupError):
    pass


class RepositorioCasos(Protocol):
    def crear(self, solicitud: str, creado_por: str | None = None) -> dict[str, Any]: ...
    def obtener(self, caso_id: str) -> dict[str, Any]: ...
    def listar(self, estado: str | None, limite: int) -> list[dict[str, Any]]: ...
    def transitar(self, caso_id: str, destino: str, motivo: str | None) -> dict[str, Any]: ...


_COLUMNAS = (
    "id, solicitud, estado, estado_previo, motivo_bloqueo, creado_por, created_at, updated_at"
)

_INSERT_BITACORA = text(
    """
    INSERT INTO audit.bitacora (caso_id, etapa, evento, detalle)
    VALUES (:caso_id, :etapa, 'transicion', CAST(:detalle AS JSONB))
    """
)


class RepositorioCasosSQL:
    """Casos en PostgreSQL. Cada cambio de estado y su evento van en una transacción."""

    def __init__(self, engine: Engine) -> None:
        self.engine = engine

    def crear(self, solicitud: str, creado_por: str | None = None) -> dict[str, Any]:
        caso_id = str(uuid.uuid4())
        with self.engine.begin() as conn:
            fila = conn.execute(
                text(
                    f"""
                    INSERT INTO audit.casos (id, solicitud, estado, creado_por)
                    VALUES (:id, :solicitud, :estado, :creado_por)
                    RETURNING {_COLUMNAS}
                    """
                ),
                {"id": caso_id, "solicitud": solicitud, "estado": RECIBIDO,
                 "creado_por": creado_por},
            ).mappings().one()
            conn.execute(_INSERT_BITACORA, {
                "caso_id": caso_id, "etapa": RECIBIDO,
                "detalle": json.dumps({"de": None, "a": RECIBIDO}),
            })
        return dict(fila)

    def obtener(self, caso_id: str) -> dict[str, Any]:
        with self.engine.connect() as conn:
            fila = conn.execute(
                text(f"SELECT {_COLUMNAS} FROM audit.casos WHERE id = :id"),
                {"id": caso_id},
            ).mappings().one_or_none()
        if fila is None:
            raise CasoNoEncontrado(caso_id)
        return dict(fila)

    def listar(self, estado: str | None, limite: int) -> list[dict[str, Any]]:
        filtro = "WHERE estado = :estado" if estado else ""
        with self.engine.connect() as conn:
            filas = conn.execute(
                text(
                    f"SELECT {_COLUMNAS} FROM audit.casos {filtro} "
                    "ORDER BY created_at DESC LIMIT :limite"
                ),
                {"estado": estado, "limite": limite},
            ).mappings().all()
        return [dict(f) for f in filas]

    def transitar(self, caso_id: str, destino: str, motivo: str | None) -> dict[str, Any]:
        with self.engine.begin() as conn:
            actual = conn.execute(
                text(
                    "SELECT estado, estado_previo, motivo_bloqueo FROM audit.casos "
                    "WHERE id = :id FOR UPDATE"
                ),
                {"id": caso_id},
            ).mappings().one_or_none()
            if actual is None:
                raise CasoNoEncontrado(caso_id)

            nuevo = transitar(actual["estado"], actual["estado_previo"], destino, motivo)
            fila = conn.execute(
                text(
                    f"""
                    UPDATE audit.casos
                    SET estado = :estado, estado_previo = :estado_previo,
                        motivo_bloqueo = :motivo_bloqueo, updated_at = NOW()
                    WHERE id = :id
                    RETURNING {_COLUMNAS}
                    """
                ),
                {"id": caso_id, "estado": nuevo.estado,
                 "estado_previo": nuevo.estado_previo,
                 "motivo_bloqueo": nuevo.motivo_bloqueo},
            ).mappings().one()

            detalle: dict[str, Any] = {"de": actual["estado"], "a": nuevo.estado}
            if nuevo.motivo_bloqueo:
                detalle["motivo"] = nuevo.motivo_bloqueo
            elif actual["motivo_bloqueo"]:
                detalle["motivo_desbloqueado"] = actual["motivo_bloqueo"]
            conn.execute(_INSERT_BITACORA, {
                "caso_id": caso_id, "etapa": actual["estado"],
                "detalle": json.dumps(detalle, ensure_ascii=False),
            })
        return dict(fila)
