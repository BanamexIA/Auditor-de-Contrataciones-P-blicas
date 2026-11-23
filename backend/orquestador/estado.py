"""Estado que viaja por el grafo y límites de una ejecución.

LangGraph pasa este diccionario de nodo en nodo. Cada nodo devuelve SOLO las llaves que cambia;
LangGraph las mezcla con el estado. Las llaves con ``Annotated[..., operator.add]`` se acumulan
(cada nodo agrega elementos a la lista) en lugar de reemplazarse.

Todo lo que va aquí debe ser serializable (dicts, listas, texto, números): los clientes de modelo
y las conexiones NO viven en el estado, viven en ``Dependencias`` (ver nodos.py).
"""

from __future__ import annotations

import operator
import os
from dataclasses import dataclass
from typing import Annotated, Any, TypedDict


class EstadoOrquestador(TypedDict, total=False):
    # Entrada
    caso_id: str
    solicitud: str
    usuario: str | None
    inicio: float                      # reloj monotónico al empezar (para el límite de tiempo)

    # Laptop de inferencia
    agente: dict[str, Any] | None      # {"nombre_tailnet", "url", "modelo", ...}
    selecciones_agente: int            # cuántas veces se eligió laptop (reintentos de conexión)
    reintentar_consulta: bool          # el nodo consulta pide volver a elegir laptop

    # Resultados de cada etapa
    filas: list[dict[str, Any]]        # filas del Agente Consulta
    deteccion: dict[str, Any]          # JSON del Agente 2 (se completa con normas en "normativo")
    reporte: dict[str, Any]            # fila de audit.reportes

    # Control
    pasos: int                         # nodos ejecutados (límite O4)
    etapa: str                         # último nodo ejecutado
    completadas: Annotated[list[str], operator.add]   # etapas terminadas (para el motivo de bloqueo)
    parciales: Annotated[list[str], operator.add]     # avisos de resultado parcial (O4, O5, O6, O7)
    motivo_bloqueo: str | None         # si tiene texto, el grafo se va a "bloquear"


# Llaves que se acumulan; el ejecutor sin LangGraph usa esto para imitar los reductores.
REDUCTORES = {"completadas": operator.add, "parciales": operator.add}


def _entero(nombre: str, defecto: int) -> int:
    try:
        valor = int(os.getenv(nombre, "") or defecto)
    except ValueError:
        return defecto
    return valor if valor > 0 else defecto


@dataclass(frozen=True)
class Limites:
    """Límites de una ejecución (O4). Se leen de variables de entorno con valores por defecto.

    - max_pasos: nodos que puede ejecutar el grafo (incluye reintentos). Un recorrido normal usa 6.
    - tiempo_max_s: tiempo total del caso. Se revisa ANTES de cada nodo: un nodo que ya empezó no
      se interrumpe (Python no puede matar un hilo); lo acota ``LLM_TIMEOUT_S`` por llamada al modelo.
    - max_selecciones_agente: cuántas veces se elige laptop (1 = sin reintento; 2 = un reintento,
      posiblemente con otra laptop).
    """

    max_pasos: int = 12
    tiempo_max_s: int = 900
    max_selecciones_agente: int = 2

    @classmethod
    def desde_entorno(cls) -> "Limites":
        return cls(
            max_pasos=_entero("ORQ_MAX_PASOS", cls.max_pasos),
            tiempo_max_s=_entero("ORQ_TIEMPO_MAX_S", cls.tiempo_max_s),
            max_selecciones_agente=_entero("ORQ_MAX_SELECCIONES_AGENTE", cls.max_selecciones_agente),
        )
