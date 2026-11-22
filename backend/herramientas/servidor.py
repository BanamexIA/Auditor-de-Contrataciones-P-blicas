"""Servidor MCP del Data Steward: expone las herramientas gobernadas de ``servicio.py``."""

from __future__ import annotations

from typing import Any

from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from mcp.types import ToolAnnotations

from backend.herramientas.servicio import (
    MAX_FILAS_RESPUESTA,
    HerramientaRechazada,
    Herramientas,
)

INSTRUCCIONES = f"""Herramientas gobernadas del Data Steward de contrataciones públicas.

- Empieza con describir_datos para conocer las vistas, el significado de cada columna y qué
  periodos están completos.
- Toda herramienta que lee datos pide un caso_id: el acceso queda registrado en la bitácora del caso.
- Los datos se leen con un rol de solo lectura y con tiempo límite. Solo se aceptan SELECT sobre
  las vistas permitidas; las respuestas traen como máximo {MAX_FILAS_RESPUESTA} filas.
- Antes de detectar señales, revisa la calidad de los contratos con evaluar_calidad.
- Las señales son propuestas: no hay herramienta para decidirlas; eso lo hace una persona.
- Cita solo las normas que devuelva buscar_norma. Nunca afirmes fraude ni responsabilidad legal.
"""

_LEE = ToolAnnotations(read_only_hint=True, open_world_hint=False)
# Escriben solo en la bitácora (auditoría); no modifican datos ni el estado del caso.
_LEE_Y_AUDITA = ToolAnnotations(read_only_hint=False, destructive_hint=False,
                                idempotent_hint=False, open_world_hint=False)


def crear_servidor(h: Herramientas) -> MCPServer:
    servidor = MCPServer("auditor-data-steward", instructions=INSTRUCCIONES, version="0.1.0")

    def protegido(funcion, *args, **kwargs) -> dict[str, Any]:
        try:
            return funcion(*args, **kwargs)
        except HerramientaRechazada as exc:
            raise ToolError(str(exc)) from None

    @servidor.tool(annotations=_LEE)
    def describir_datos() -> dict:
        """Vistas que se pueden consultar, significado de cada columna y cobertura por año y fuente."""
        return protegido(h.describir_datos)

    @servidor.tool(annotations=_LEE_Y_AUDITA)
    def consultar_contratos(caso_id: str, sql: str) -> dict:
        """Ejecuta un SELECT de solo lectura sobre las vistas clean.v_*_agente.

        El SQL se valida (una sola sentencia SELECT, vistas permitidas, LIMIT que se agrega si falta) y se
        revisa contra la cobertura de datos. Queda registrado en la bitácora del caso.
        """
        return protegido(h.consultar_contratos, caso_id, sql)

    @servidor.tool(annotations=_LEE_Y_AUDITA)
    def evaluar_calidad(caso_id: str, contratos_ids: list[str]) -> dict:
        """Revisa la calidad de hasta 500 contratos: montos, moneda, fechas, proveedor,
        RFC y contradicciones entre fuentes. Indica qué reglas no se pueden aplicar a cada uno."""
        return protegido(h.evaluar_calidad, caso_id, contratos_ids)

    @servidor.tool(annotations=_LEE_Y_AUDITA)
    def detectar_senales(caso_id: str, contratos_ids: list[str]) -> dict:
        """Aplica las reglas deterministas de riesgo (adjudicación directa recurrente, monto atípico,
        proveedor en el listado 69-B). Cada señal trae criterio, umbral, valores y confianza."""
        return protegido(h.detectar_senales, caso_id, contratos_ids)

    @servidor.tool(annotations=_LEE_Y_AUDITA)
    def buscar_norma(caso_id: str, texto: str, fecha: str | None = None, top_k: int = 3) -> dict:
        """Busca fragmentos de norma (LAASSP, CFF) vigentes a la fecha indicada (AAAA-MM-DD).

        Si no hay fragmento que respalde el tema, lo dice: no inventes normas.
        """
        return protegido(h.buscar_norma, caso_id, texto, fecha, top_k)

    return servidor
