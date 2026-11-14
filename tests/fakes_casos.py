"""Repositorio de casos en memoria para pruebas sin base de datos."""

import uuid
from datetime import datetime, timezone

from backend.casos import estados as e
from backend.casos.bitacora import SOLICITUD, TRANSICION, validar_evento
from backend.casos.estados import transitar
from backend.casos.repositorio import CasoNoEncontrado


class RepositorioEnMemoria:
    def __init__(self):
        self.casos = {}
        self.bitacora = []

    def _evento(self, caso_id, etapa, evento, detalle, modelo=None, equipo=None):
        validar_evento(evento, detalle)
        fila = {"id": len(self.bitacora) + 1, "caso_id": caso_id, "etapa": etapa,
                "evento": evento, "detalle": detalle, "modelo": modelo, "equipo": equipo,
                "created_at": datetime.now(timezone.utc)}
        self.bitacora.append(fila)
        return {k: v for k, v in fila.items() if k != "caso_id"}

    def crear(self, solicitud, creado_por=None):
        ahora = datetime.now(timezone.utc)
        caso = {"id": str(uuid.uuid4()), "solicitud": solicitud, "estado": e.RECIBIDO,
                "estado_previo": None, "motivo_bloqueo": None, "creado_por": creado_por,
                "created_at": ahora, "updated_at": ahora}
        self.casos[caso["id"]] = caso
        self._evento(caso["id"], e.RECIBIDO, SOLICITUD, {"texto": solicitud})
        self._evento(caso["id"], e.RECIBIDO, TRANSICION, {"de": None, "a": e.RECIBIDO})
        return dict(caso)

    def obtener(self, caso_id):
        if caso_id not in self.casos:
            raise CasoNoEncontrado(caso_id)
        return dict(self.casos[caso_id])

    def listar(self, estado, limite):
        casos = [c for c in self.casos.values() if estado is None or c["estado"] == estado]
        return [dict(c) for c in reversed(casos)][:limite]

    def transitar(self, caso_id, destino, motivo):
        caso = self.casos.get(caso_id)
        if caso is None:
            raise CasoNoEncontrado(caso_id)
        nuevo = transitar(caso["estado"], caso["estado_previo"], destino, motivo)
        detalle = {"de": caso["estado"], "a": nuevo.estado}
        if nuevo.motivo_bloqueo:
            detalle["motivo"] = nuevo.motivo_bloqueo
        elif caso["motivo_bloqueo"]:
            detalle["motivo_desbloqueado"] = caso["motivo_bloqueo"]
        self._evento(caso_id, caso["estado"], TRANSICION, detalle)
        caso.update(estado=nuevo.estado, estado_previo=nuevo.estado_previo,
                    motivo_bloqueo=nuevo.motivo_bloqueo)
        return dict(caso)

    def registrar_evento(self, caso_id, evento, detalle, modelo=None, equipo=None):
        caso = self.casos.get(caso_id)
        if caso is None:
            raise CasoNoEncontrado(caso_id)
        return self._evento(caso_id, caso["estado"], evento, detalle, modelo, equipo)

    def listar_eventos(self, caso_id):
        if caso_id not in self.casos:
            raise CasoNoEncontrado(caso_id)
        return [{k: v for k, v in ev.items() if k != "caso_id"}
                for ev in self.bitacora if ev["caso_id"] == caso_id]

    def eventos(self, caso_id, tipo=None):
        return [ev for ev in self.bitacora
                if ev["caso_id"] == caso_id and (tipo is None or ev["evento"] == tipo)]
