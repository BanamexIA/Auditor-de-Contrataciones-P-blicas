"""El grafo del orquestador (LangGraph) y la función para correr un caso.

Forma del grafo (flujo fijo; cualquier nodo puede desviarse a "bloquear"):

    START
      │
      ▼
    elegir_agente ◀──────────────┐  (la laptop no respondió: se elige otra vez, máx. 1 reintento)
      │                          │
      ▼                          │
    consulta ────────────────────┘
      │
      ▼
    deteccion ──▶ normativo ──▶ reportes ──▶ entregar ──▶ END   (caso en "en_revision")
      │              │             │
      └──────────────┴─────────────┴──────▶ bloquear ──▶ END    (caso en "bloqueado" + motivo)

Los estados del caso (recibido → consultado → detectado → normado → reportado → en_revision)
los avanza cada nodo al terminar su etapa; ver docs/contratos/estado_caso.md.

La definición de nodos y aristas está en ``NODOS`` y ``RUTAS``. ``construir_grafo`` arma con ellas
el grafo de LangGraph. Si LangGraph no está instalado (p. ej. en una laptop sin el entorno del
backend), ``EjecutorSimple`` recorre exactamente las mismas aristas, para que las pruebas y el
grafo nunca se separen.
"""

from __future__ import annotations

from typing import Any, Callable

from backend.casos import estados as e
from backend.orquestador.estado import REDUCTORES, EstadoOrquestador, Limites
from backend.orquestador.nodos import (
    Dependencias,
    nodo_bloquear,
    nodo_consulta,
    nodo_deteccion,
    nodo_elegir_agente,
    nodo_entregar,
    nodo_normativo,
    nodo_reportes,
    vigilar,
)

INICIO = "elegir_agente"
FIN = "__fin__"

# nombre -> fábrica del nodo
NODOS: dict[str, Callable] = {
    "elegir_agente": nodo_elegir_agente,
    "consulta": nodo_consulta,
    "deteccion": nodo_deteccion,
    "normativo": nodo_normativo,
    "reportes": nodo_reportes,
    "entregar": nodo_entregar,
    "bloquear": nodo_bloquear,
}


def _siguiente(destino: str) -> Callable[[EstadoOrquestador], str]:
    def ruta(estado: EstadoOrquestador) -> str:
        return "bloquear" if estado.get("motivo_bloqueo") else destino
    return ruta


def _ruta_consulta(estado: EstadoOrquestador) -> str:
    if estado.get("motivo_bloqueo"):
        return "bloquear"
    return "elegir_agente" if estado.get("reintentar_consulta") else "deteccion"


# nombre -> (función de ruta, destinos posibles). "entregar" y "bloquear" terminan.
RUTAS: dict[str, tuple[Callable[[EstadoOrquestador], str], list[str]]] = {
    "elegir_agente": (_siguiente("consulta"), ["consulta", "bloquear"]),
    "consulta": (_ruta_consulta, ["deteccion", "elegir_agente", "bloquear"]),
    "deteccion": (_siguiente("normativo"), ["normativo", "bloquear"]),
    "normativo": (_siguiente("reportes"), ["reportes", "bloquear"]),
    "reportes": (_siguiente("entregar"), ["entregar", "bloquear"]),
}
TERMINALES = ("entregar", "bloquear")


def _nodos_listos(deps: Dependencias, limites: Limites) -> dict[str, Callable]:
    listos = {}
    for nombre, fabrica in NODOS.items():
        nodo = fabrica(deps, limites)
        # "bloquear" no se vigila: siempre tiene que poder correr, aun pasado el límite.
        listos[nombre] = nodo if nombre == "bloquear" else vigilar(nombre, nodo, deps, limites)
    return listos


def construir_grafo(deps: Dependencias, limites: Limites | None = None):
    """Grafo compilado de LangGraph. Requiere ``pip install langgraph``."""
    from langgraph.graph import END, START, StateGraph

    limites = limites or Limites.desde_entorno()
    g = StateGraph(EstadoOrquestador)
    for nombre, nodo in _nodos_listos(deps, limites).items():
        g.add_node(nombre, nodo)
    g.add_edge(START, INICIO)
    for origen, (ruta, destinos) in RUTAS.items():
        g.add_conditional_edges(origen, ruta, destinos)
    for terminal in TERMINALES:
        g.add_edge(terminal, END)
    return g.compile()


class EjecutorSimple:
    """Recorre NODOS y RUTAS igual que LangGraph (mismos reductores). Solo si LangGraph falta."""

    def __init__(self, deps: Dependencias, limites: Limites):
        self.nodos = _nodos_listos(deps, limites)
        self.limite = limites.max_pasos + 5

    def invoke(self, estado: dict, config: dict | None = None) -> dict:
        estado, actual = dict(estado), INICIO
        for _ in range(self.limite):
            cambios = self.nodos[actual](estado)
            for llave, valor in cambios.items():
                reductor = REDUCTORES.get(llave)
                estado[llave] = reductor(estado.get(llave) or [], valor) if reductor else valor
            if actual in TERMINALES:
                return estado
            actual = RUTAS[actual][0](estado)
        raise RecursionError(f"El grafo pasó de {self.limite} pasos.")


def _grafo(deps: Dependencias, limites: Limites):
    try:
        return construir_grafo(deps, limites)
    except ImportError:
        deps.log("(LangGraph no está instalado: se usa el ejecutor simple con las mismas aristas)")
        return EjecutorSimple(deps, limites)


def orquestar_caso(caso_id: str, deps: Dependencias, limites: Limites | None = None) -> dict[str, Any]:
    """Corre un caso en estado ``recibido`` hasta ``en_revision`` o ``bloqueado``.

    Devuelve el estado final del grafo (con ``motivo_bloqueo`` si se bloqueó, ``parciales``,
    ``reporte``...). Es síncrona: el endpoint la lanza en un hilo para no detener la petición.
    """
    limites = limites or Limites.desde_entorno()
    caso = deps.repo.obtener(caso_id)
    if caso["estado"] != e.RECIBIDO:
        raise ValueError(f"El caso está en '{caso['estado']}'; el orquestador empieza en 'recibido'.")
    inicial: EstadoOrquestador = {
        "caso_id": caso_id, "solicitud": caso["solicitud"], "usuario": caso.get("creado_por"),
        "inicio": deps.reloj(), "pasos": 0, "selecciones_agente": 0,
        "completadas": [], "parciales": [], "motivo_bloqueo": None,
    }
    grafo = _grafo(deps, limites)
    try:
        # recursion_limit es la red de seguridad de LangGraph; el límite "bonito" lo pone vigilar().
        return grafo.invoke(inicial, config={"recursion_limit": limites.max_pasos + 5})
    except Exception as exc:  # GraphRecursionError u otra falla del propio grafo
        motivo = f"El orquestador se detuvo: {type(exc).__name__}: {str(exc)[:200]}"
        bloquear = NODOS["bloquear"](deps, limites)
        return {**inicial, **bloquear({**inicial, "motivo_bloqueo": motivo})}
