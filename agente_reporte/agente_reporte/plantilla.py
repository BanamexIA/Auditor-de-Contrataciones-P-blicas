"""Plantilla fija del reporte. Los datos los inyecta el código; el LLM solo aporta narrativa."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from .schemas import (
    EntradaReporte, Limitacion, Reporte, ResumenEjecutivo, SeccionSenal,
)

VERSION_PLANTILLA = "0.1"

AVISO_REVISION_HUMANA = (
    "AVISO: este reporte presenta señales de riesgo calculadas con reglas y umbrales versionados. "
    "No constituye una determinación de irregularidad ni de responsabilidad legal. "
    "Toda señal requiere la revisión y la decisión final de una persona."
)


def ensamblar(
    entrada: EntradaReporte,
    secciones: list[SeccionSenal],
    resumen: ResumenEjecutivo | None,
    limitaciones: list[Limitacion],
    modelo: str,
    trazabilidad: list[dict[str, Any]],
) -> Reporte:
    return Reporte(
        consulta_id=entrada.consulta_id,
        generado_en=datetime.now(timezone.utc).isoformat(timespec="seconds"),
        version_plantilla=VERSION_PLANTILLA,
        version_reglas=entrada.version_reglas,
        modelo=modelo,
        aviso=AVISO_REVISION_HUMANA,
        contratos=entrada.contratos,
        contradicciones=entrada.contradicciones,
        senales=secciones,
        limitaciones=limitaciones,
        resumen_ejecutivo=resumen,
        trazabilidad=trazabilidad,
    )


# --------------------------------------------------------------------------- Markdown
def _v(x: Any) -> str:
    return "No disponible" if x in (None, "") else str(x).replace("|", "\\|")


def _monto(m: float | None, moneda: str = "MXN") -> str:
    return "No disponible" if m is None else f"${m:,.2f} {moneda}"


def _num(x: Any) -> str:
    if isinstance(x, bool):
        return str(x)
    if isinstance(x, float):
        return f"{x:,.2f}"
    if isinstance(x, int):
        return f"{x:,}"
    return str(x)


def render_markdown(r: Reporte) -> str:
    L: list[str] = []
    L.append(f"# Reporte de señales de riesgo — consulta `{r.consulta_id}`")
    L.append("")
    L.append(f"> {r.aviso}")
    L.append("")
    L.append(
        f"_Generado: {r.generado_en} · Plantilla v{r.version_plantilla} · "
        f"Reglas {r.version_reglas} · Modelo: {r.modelo}_"
    )

    if r.resumen_ejecutivo and r.resumen_ejecutivo.texto:
        re_ = r.resumen_ejecutivo
        L += ["", "## Resumen ejecutivo", "", re_.texto]
        if re_.concentracion:
            L += ["", "| Proveedor | RFC | Contratos | Monto total | % del monto | % adj. directas |",
                  "|---|---|---|---|---|---|"]
            for c in re_.concentracion:
                ad = "No disponible" if c.porcentaje_adjudicaciones_directas is None else f"{c.porcentaje_adjudicaciones_directas:.1f}%"
                L.append(f"| {_v(c.proveedor)} | {_v(c.rfc)} | {c.num_contratos} | {_monto(c.monto_total)} | {c.porcentaje_monto:.1f}% | {ad} |")
        if not re_.generado_por_llm:
            L += ["", "_Resumen generado con plantilla determinista (sin modelo)._"]

    L += ["", "## Contratos involucrados", ""]
    if r.contratos:
        L += ["| ID | Proveedor | RFC | Monto | Dependencia | Procedimiento | Fecha | Fuente |",
              "|---|---|---|---|---|---|---|---|"]
        for c in r.contratos:
            L.append(
                f"| {_v(c.id)} | {_v(c.proveedor)} | {_v(c.rfc)} | {_monto(c.monto, c.moneda)} | "
                f"{_v(c.dependencia)} | {_v(c.tipo_procedimiento)} | {_v(c.fecha)} | {_v(c.fuente)} |"
            )
    else:
        L.append("_Sin contratos en esta consulta._")

    if r.contradicciones:
        L += ["", "## Datos contradictorios", ""]
        for c in r.contradicciones:
            L.append(f"- **{c.contrato_id} · {c.campo}**: `{c.valor_a}` ({c.fuente_a}) vs `{c.valor_b}` ({c.fuente_b})")

    L += ["", "## Señales detectadas"]
    if not r.senales:
        L += ["", "_No se detectaron señales con las reglas vigentes. Esto no equivale a ausencia de riesgo._"]
    for s in r.senales:
        L += ["", f"### {s.nombre} (`{s.codigo}`)", "",
              f"- **Estado:** {'activa' if s.estado == 'activa' else 'NO EVALUABLE'}",
              f"- **Confianza:** {s.confianza}",
              f"- **Criterio:** {s.criterio}",
              f"- **Umbral:** {s.umbral}",
              f"- **Contratos:** {', '.join(s.contratos_ids) or 'No disponible'}"]
        if s.campos_faltantes:
            L.append(f"- **Campos faltantes:** {', '.join(s.campos_faltantes)}")
        if s.valores_calculados:
            L += ["", "| Valor calculado | Resultado |", "|---|---|"]
            for k, v in s.valores_calculados.items():
                L.append(f"| {_v(k)} | {_v(_num(v))} |")
        L += ["", s.narrativa]
        if not s.narrativa_generada_por_llm and s.estado == "activa":
            L += ["", "_Narrativa generada con plantilla determinista (sin modelo)._"]
        L += ["", "**Normas citadas:**"]
        if s.citas:
            for c in s.citas:
                L.append(f"- {c.norma}, art. {c.articulo} (versión {c.version}) · fragmento `{c.fragmento_id}`")
        else:
            L.append("- _Sin norma aplicable en los fragmentos recuperados para esta consulta._")

    L += ["", "## Limitaciones", ""]
    if r.limitaciones:
        L += [f"- **{l.tipo.replace('_', ' ')}**: {l.descripcion}" for l in r.limitaciones]
    else:
        L.append("- Sin limitaciones declaradas.")

    if r.verificacion:
        v = r.verificacion
        L += ["", "## Verificación automática", "",
              f"- Citas correctas: {v.citas_correctas}/{v.total_citas} ({v.tasa_citas_correctas:.0%})",
              f"- Estado: {'APROBADO' if v.aprobado else 'REQUIERE REVISIÓN'}"]
        for campo, titulo in (("citas_invalidas", "Citas inválidas"),
                              ("articulos_no_respaldados", "Artículos sin respaldo"),
                              ("terminos_prohibidos", "Términos no permitidos"),
                              ("numeros_no_respaldados", "Cifras a revisar")):
            vals = getattr(v, campo)
            if vals:
                L.append(f"- {titulo}: " + "; ".join(vals))

    L += ["", "---", f"> {r.aviso}", ""]
    return "\n".join(L)
