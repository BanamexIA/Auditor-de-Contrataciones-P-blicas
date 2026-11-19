"""Persistencia de casos (audit.casos) y de su bitácora (audit.bitacora)."""

from __future__ import annotations

import json
import uuid
from typing import Any, Protocol

from sqlalchemy import Connection, Engine, text

from backend.casos.bitacora import (
    DECISION,
    REPORTE_GUARDADO,
    SOLICITUD,
    TRANSICION,
    validar_evento,
)
from backend.casos.decisiones import CasoCerrado, SenalNoEncontrada, validar_decision
from backend.casos.estados import CERRADO, RECIBIDO, transitar


class CasoNoEncontrado(LookupError):
    pass


class ReporteNoEncontrado(LookupError):
    pass


class RepositorioCasos(Protocol):
    def crear(self, solicitud: str, creado_por: str | None = None) -> dict[str, Any]: ...
    def obtener(self, caso_id: str) -> dict[str, Any]: ...
    def listar(self, estado: str | None, limite: int) -> list[dict[str, Any]]: ...
    def transitar(self, caso_id: str, destino: str, motivo: str | None) -> dict[str, Any]: ...
    def registrar_evento(
        self,
        caso_id: str,
        evento: str,
        detalle: dict[str, Any],
        modelo: str | None = None,
        equipo: str | None = None,
    ) -> dict[str, Any]: ...
    def listar_eventos(self, caso_id: str) -> list[dict[str, Any]]: ...
    def registrar_senales(
        self, caso_id: str, senales: list[dict[str, Any]]
    ) -> list[dict[str, Any]]: ...
    def listar_senales(self, caso_id: str) -> list[dict[str, Any]]: ...
    def decidir(
        self,
        caso_id: str,
        senal_id: str,
        decision: str,
        comentario: str | None,
        decidido_por: str | None = None,
    ) -> dict[str, Any]: ...


_COLUMNAS = (
    "id, solicitud, estado, estado_previo, motivo_bloqueo, creado_por, created_at, updated_at"
)
_COLUMNAS_EVENTO = "id, etapa, evento, detalle, modelo, equipo, created_at"
_COLUMNAS_REPORTE = (
    "version, uri, sha256, formato, content_type, tamano_bytes, modelo, equipo, created_at"
)

_CONTAR_SIN_DECISION = text(
    """
    SELECT count(*) FROM audit.senales s
    WHERE s.caso_id = :id
      AND NOT EXISTS (SELECT 1 FROM audit.decisiones d WHERE d.senal_id = s.id)
    """
)

_DECISION_VIGENTE = text(
    """
    SELECT decision FROM audit.decisiones
    WHERE senal_id = :senal_id
    ORDER BY created_at DESC, id DESC
    LIMIT 1
    """
)


def _estado_bloqueando(conn: Connection, caso_id: str) -> str:
    """Estado del caso, bloqueando su fila hasta el fin de la transacción."""
    estado = conn.execute(
        text("SELECT estado FROM audit.casos WHERE id = :id FOR UPDATE"),
        {"id": caso_id},
    ).scalar_one_or_none()
    if estado is None:
        raise CasoNoEncontrado(caso_id)
    return estado


def _insertar_evento(
    conn: Connection,
    caso_id: str,
    etapa: str,
    evento: str,
    detalle: dict[str, Any],
    modelo: str | None = None,
    equipo: str | None = None,
) -> dict[str, Any]:
    validar_evento(evento, detalle)
    fila = conn.execute(
        text(
            f"""
            INSERT INTO audit.bitacora (caso_id, etapa, evento, detalle, modelo, equipo)
            VALUES (:caso_id, :etapa, :evento, CAST(:detalle AS JSONB), :modelo, :equipo)
            RETURNING {_COLUMNAS_EVENTO}
            """
        ),
        {"caso_id": caso_id, "etapa": etapa, "evento": evento,
         "detalle": json.dumps(detalle, ensure_ascii=False),
         "modelo": modelo, "equipo": equipo},
    ).mappings().one()
    return dict(fila)


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
            _insertar_evento(conn, caso_id, RECIBIDO, SOLICITUD, {"texto": solicitud})
            _insertar_evento(conn, caso_id, RECIBIDO, TRANSICION, {"de": None, "a": RECIBIDO})
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

            sin_decision = 0
            if destino == CERRADO:
                sin_decision = conn.execute(_CONTAR_SIN_DECISION, {"id": caso_id}).scalar_one()
            nuevo = transitar(actual["estado"], actual["estado_previo"], destino, motivo,
                              senales_sin_decision=sin_decision)
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
            _insertar_evento(conn, caso_id, actual["estado"], TRANSICION, detalle)
        return dict(fila)

    def registrar_evento(
        self,
        caso_id: str,
        evento: str,
        detalle: dict[str, Any],
        modelo: str | None = None,
        equipo: str | None = None,
    ) -> dict[str, Any]:
        """Agrega un evento; la etapa es el estado actual del caso."""
        with self.engine.begin() as conn:
            etapa = conn.execute(
                text("SELECT estado FROM audit.casos WHERE id = :id"),
                {"id": caso_id},
            ).scalar_one_or_none()
            if etapa is None:
                raise CasoNoEncontrado(caso_id)
            return _insertar_evento(conn, caso_id, etapa, evento, detalle, modelo, equipo)

    def listar_eventos(self, caso_id: str) -> list[dict[str, Any]]:
        with self.engine.connect() as conn:
            existe = conn.execute(
                text("SELECT 1 FROM audit.casos WHERE id = :id"), {"id": caso_id}
            ).scalar_one_or_none()
            if existe is None:
                raise CasoNoEncontrado(caso_id)
            filas = conn.execute(
                text(
                    f"SELECT {_COLUMNAS_EVENTO} FROM audit.bitacora "
                    "WHERE caso_id = :id ORDER BY created_at, id"
                ),
                {"id": caso_id},
            ).mappings().all()
        return [dict(f) for f in filas]

    def registrar_senales(
        self, caso_id: str, senales: list[dict[str, Any]]
    ) -> list[dict[str, Any]]:
        """Guarda las señales de la Tool 1. Cada una necesita ``tipo``; ``datos`` es libre."""
        with self.engine.begin() as conn:
            if _estado_bloqueando(conn, caso_id) == CERRADO:
                raise CasoCerrado(caso_id)
            guardadas = []
            for senal in senales:
                fila = conn.execute(
                    text(
                        """
                        INSERT INTO audit.senales (id, caso_id, tipo, datos)
                        VALUES (:id, :caso_id, :tipo, CAST(:datos AS JSONB))
                        RETURNING id, tipo, datos, created_at
                        """
                    ),
                    {"id": str(uuid.uuid4()), "caso_id": caso_id, "tipo": senal["tipo"],
                     "datos": json.dumps(senal.get("datos", {}), ensure_ascii=False)},
                ).mappings().one()
                guardadas.append({**fila, "decision": None})
        return guardadas

    def listar_senales(self, caso_id: str) -> list[dict[str, Any]]:
        with self.engine.connect() as conn:
            existe = conn.execute(
                text("SELECT 1 FROM audit.casos WHERE id = :id"), {"id": caso_id}
            ).scalar_one_or_none()
            if existe is None:
                raise CasoNoEncontrado(caso_id)
            filas = conn.execute(
                text(
                    """
                    SELECT s.id, s.tipo, s.datos, s.created_at,
                           d.decision, d.comentario, d.decidido_por,
                           d.created_at AS decidido_at
                    FROM audit.senales s
                    LEFT JOIN LATERAL (
                        SELECT decision, comentario, decidido_por, created_at
                        FROM audit.decisiones
                        WHERE senal_id = s.id
                        ORDER BY created_at DESC, id DESC
                        LIMIT 1
                    ) d ON TRUE
                    WHERE s.caso_id = :id
                    ORDER BY s.created_at, s.id
                    """
                ),
                {"id": caso_id},
            ).mappings().all()
        senales = []
        for f in filas:
            decision = None
            if f["decision"] is not None:
                decision = {"decision": f["decision"], "comentario": f["comentario"],
                            "decidido_por": f["decidido_por"], "created_at": f["decidido_at"]}
            senales.append({"id": f["id"], "tipo": f["tipo"], "datos": f["datos"],
                            "created_at": f["created_at"], "decision": decision})
        return senales

    def decidir(
        self,
        caso_id: str,
        senal_id: str,
        decision: str,
        comentario: str | None,
        decidido_por: str | None = None,
    ) -> dict[str, Any]:
        decision, comentario = validar_decision(decision, comentario)
        with self.engine.begin() as conn:
            etapa = _estado_bloqueando(conn, caso_id)
            if etapa == CERRADO:
                raise CasoCerrado(caso_id)
            existe = conn.execute(
                text("SELECT 1 FROM audit.senales WHERE id = :sid AND caso_id = :id"),
                {"sid": senal_id, "id": caso_id},
            ).scalar_one_or_none()
            if existe is None:
                raise SenalNoEncontrada(senal_id)
            anterior = conn.execute(_DECISION_VIGENTE, {"senal_id": senal_id}).scalar_one_or_none()
            fila = conn.execute(
                text(
                    """
                    INSERT INTO audit.decisiones
                        (caso_id, senal_id, decision, comentario, decidido_por)
                    VALUES (:caso_id, :senal_id, :decision, :comentario, :decidido_por)
                    RETURNING id, senal_id, decision, comentario, decidido_por, created_at
                    """
                ),
                {"caso_id": caso_id, "senal_id": senal_id, "decision": decision,
                 "comentario": comentario, "decidido_por": decidido_por},
            ).mappings().one()
            _insertar_evento(conn, caso_id, etapa, DECISION, {
                "senal_id": senal_id, "decision": decision,
                "comentario": comentario, "anterior": anterior,
            })
        return dict(fila)

    def siguiente_version_reporte(self, caso_id: str) -> int:
        with self.engine.connect() as conn:
            estado = conn.execute(
                text("SELECT estado FROM audit.casos WHERE id = :id"), {"id": caso_id}
            ).scalar_one_or_none()
            if estado is None:
                raise CasoNoEncontrado(caso_id)
            if estado == CERRADO:
                raise CasoCerrado(caso_id)
            return conn.execute(
                text("SELECT coalesce(max(version), 0) + 1 FROM audit.reportes "
                     "WHERE caso_id = :id"),
                {"id": caso_id},
            ).scalar_one()

    def registrar_reporte(
        self,
        caso_id: str,
        version: int,
        uri: str,
        sha256: str,
        formato: str,
        content_type: str,
        tamano_bytes: int,
        modelo: str | None = None,
        equipo: str | None = None,
    ) -> dict[str, Any]:
        """Registra un reporte ya guardado en el almacén, con su evento de bitácora."""
        with self.engine.begin() as conn:
            etapa = _estado_bloqueando(conn, caso_id)
            if etapa == CERRADO:
                raise CasoCerrado(caso_id)
            fila = conn.execute(
                text(
                    f"""
                    INSERT INTO audit.reportes (caso_id, version, uri, sha256, formato,
                        content_type, tamano_bytes, modelo, equipo)
                    VALUES (:caso_id, :version, :uri, :sha256, :formato,
                        :content_type, :tamano_bytes, :modelo, :equipo)
                    RETURNING {_COLUMNAS_REPORTE}
                    """
                ),
                {"caso_id": caso_id, "version": version, "uri": uri, "sha256": sha256,
                 "formato": formato, "content_type": content_type,
                 "tamano_bytes": tamano_bytes, "modelo": modelo, "equipo": equipo},
            ).mappings().one()
            _insertar_evento(conn, caso_id, etapa, REPORTE_GUARDADO,
                             {"ruta": uri, "sha256": sha256, "version": version},
                             modelo=modelo, equipo=equipo)
        return dict(fila)

    def listar_reportes(self, caso_id: str) -> list[dict[str, Any]]:
        with self.engine.connect() as conn:
            existe = conn.execute(
                text("SELECT 1 FROM audit.casos WHERE id = :id"), {"id": caso_id}
            ).scalar_one_or_none()
            if existe is None:
                raise CasoNoEncontrado(caso_id)
            filas = conn.execute(
                text(f"SELECT {_COLUMNAS_REPORTE} FROM audit.reportes "
                     "WHERE caso_id = :id ORDER BY version"),
                {"id": caso_id},
            ).mappings().all()
        return [dict(f) for f in filas]

    def obtener_reporte(self, caso_id: str, version: int) -> dict[str, Any]:
        with self.engine.connect() as conn:
            fila = conn.execute(
                text(f"SELECT {_COLUMNAS_REPORTE} FROM audit.reportes "
                     "WHERE caso_id = :id AND version = :version"),
                {"id": caso_id, "version": version},
            ).mappings().one_or_none()
        if fila is None:
            raise ReporteNoEncontrado(f"{caso_id} v{version}")
        return dict(fila)

    def listar_llamadas_llm(self, caso_id: str) -> list[dict[str, Any]]:
        """Llamadas al modelo del caso, de telemetry.llm_calls (B9)."""
        with self.engine.connect() as conn:
            existe = conn.execute(
                text("SELECT 1 FROM audit.casos WHERE id = :id"), {"id": caso_id}
            ).scalar_one_or_none()
            if existe is None:
                raise CasoNoEncontrado(caso_id)
            filas = conn.execute(text(
                "SELECT started_at, agent AS agente, model AS modelo, equipment AS equipo, "
                "input_tokens AS tokens_entrada, output_tokens AS tokens_salida, latency_ms AS latencia_ms, "
                "tokens_per_second AS tokens_por_segundo, CASE status WHEN 'success' THEN 'ok' ELSE status END AS estado, "
                "error_type AS tipo_error "
                "FROM telemetry.llm_calls WHERE caso_id = :id ORDER BY started_at, id"
            ), {"id": caso_id}).mappings().all()
        return [dict(f) for f in filas]
