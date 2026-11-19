"""Registro de agentes en memoria y un Ollama simulado para pruebas."""

from datetime import datetime, timezone

from backend.agentes.repositorio import AgenteDuplicado, AgenteNoEncontrado
from backend.agentes.verificacion import DESCONOCIDO, validar_nombre


class RepositorioAgentesEnMemoria:
    def __init__(self):
        self.agentes = {}

    def alta(self, usuario, nombre, modelo=None):
        nombre = validar_nombre(nombre)
        if not (usuario or "").strip():
            raise ValueError("El usuario es obligatorio.")
        for a in self.agentes.values():
            if a["nombre_tailnet"] == nombre:
                if a["activo"]:
                    raise AgenteDuplicado(nombre)
                a.update(usuario=usuario, modelo=modelo, activo=True, estado=DESCONOCIDO)
                return dict(a)
        agente = {"id": len(self.agentes) + 1, "usuario": usuario, "nombre_tailnet": nombre,
                  "modelo": modelo, "estado": DESCONOCIDO, "activo": True, "modelos": [],
                  "version_ollama": None, "latencia_ms": None, "ultimo_error": None,
                  "ultima_verificacion": None, "created_at": datetime.now(timezone.utc)}
        self.agentes[agente["id"]] = agente
        return dict(agente)

    def baja(self, nombre):
        for a in self.agentes.values():
            if a["nombre_tailnet"] == validar_nombre(nombre):
                a["activo"] = False
                return dict(a)
        raise AgenteNoEncontrado(nombre)

    def listar(self, incluir_inactivos=False):
        return [dict(a) for a in sorted(self.agentes.values(), key=lambda a: (a["usuario"], a["id"]))
                if incluir_inactivos or a["activo"]]

    def obtener(self, agente_id):
        if agente_id not in self.agentes:
            raise AgenteNoEncontrado(str(agente_id))
        return dict(self.agentes[agente_id])

    def guardar_verificacion(self, agente_id, resultado):
        a = self.agentes[agente_id]
        a.update(estado=resultado.estado, modelos=resultado.modelos,
                 version_ollama=resultado.version_ollama or a["version_ollama"],
                 latencia_ms=resultado.latencia_ms, ultimo_error=resultado.error,
                 ultima_verificacion=datetime.now(timezone.utc))
        return dict(a)


class OllamaSimulado:
    """Responde como Ollama para los equipos de ``encendidos``: {nombre: [modelos]}."""

    def __init__(self, encendidos=None):
        self.encendidos = encendidos or {}
        self.urls = []

    def __call__(self, url, timeout_s):
        self.urls.append(url)
        host = url.split("//", 1)[1].split(":", 1)[0]
        if host not in self.encendidos:
            raise TimeoutError(f"{host} no responde")
        if url.endswith("/api/version"):
            return {"version": "0.12.3"}
        return {"models": [{"name": m} for m in self.encendidos[host]]}
