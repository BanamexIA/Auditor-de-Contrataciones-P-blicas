"""Sección de limitaciones: 100 % determinista (el LLM no interviene)."""
from __future__ import annotations

from .schemas import EntradaReporte, Limitacion


def construir_limitaciones(entrada: EntradaReporte) -> list[Limitacion]:
    lims: list[Limitacion] = []

    for e in entrada.excluidos:
        lims.append(Limitacion(
            tipo="registro_excluido",
            descripcion=f"El contrato {e.contrato_id} fue excluido del análisis: {e.motivo}.",
            referencia=e.contrato_id,
        ))

    for c in entrada.contradicciones:
        lims.append(Limitacion(
            tipo="dato_contradictorio",
            descripcion=(
                f"Contrato {c.contrato_id}, campo '{c.campo}': {c.fuente_a} indica '{c.valor_a}' y "
                f"{c.fuente_b} indica '{c.valor_b}'. El sistema no eligió un valor; requiere revisión humana."
            ),
            referencia=c.contrato_id,
        ))

    con_norma = {f.senal_codigo for f in entrada.normas_recuperadas}
    for s in entrada.senales:
        if s.estado == "no_evaluable":
            faltan = ", ".join(s.campos_faltantes) or "datos no especificados"
            lims.append(Limitacion(
                tipo="senal_no_evaluable",
                descripcion=(
                    f"La señal '{s.nombre}' no pudo evaluarse por falta de: {faltan}. "
                    "Esto NO equivale a ausencia de riesgo."
                ),
                referencia=s.codigo,
            ))
            continue
        if s.confianza == "baja":
            lims.append(Limitacion(
                tipo="confianza_baja",
                descripcion=f"La señal '{s.nombre}' tiene coincidencias o datos de baja confianza; verifique antes de usarla.",
                referencia=s.codigo,
            ))
        if s.codigo not in con_norma:
            lims.append(Limitacion(
                tipo="sin_norma_aplicable",
                descripcion=f"No se recuperó una norma aplicable para la señal '{s.nombre}' en esta consulta.",
                referencia=s.codigo,
            ))

    if not entrada.senales:
        lims.append(Limitacion(
            tipo="sin_senales",
            descripcion=(
                "No se detectaron señales con el catálogo y umbrales vigentes. "
                "Esto no significa que no exista riesgo."
            ),
        ))
    return lims
