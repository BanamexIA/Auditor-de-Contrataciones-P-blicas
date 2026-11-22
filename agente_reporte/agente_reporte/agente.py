"""Orquestación del Agente de Reporte: función que invoca el nodo de LangGraph."""
from __future__ import annotations

import re
from pathlib import Path
from typing import Optional, Union

from . import plantilla, plantilla_pdf
from .limitaciones import construir_limitaciones
from .redactor import Redactor
from .schemas import (
    Cita, EntradaReporte, FragmentoNorma, Limitacion, Reporte, ResumenEjecutivo, SeccionSenal, Senal,
)
from .verificador import verificar_reporte


def _cita(f: FragmentoNorma) -> Cita:
    return Cita(fragmento_id=f.fragmento_id, norma=f.norma, articulo=f.articulo, version=f.version)


def _seccion(senal: Senal, entrada: EntradaReporte, redactor: Redactor) -> SeccionSenal:
    base = senal.model_dump(include={
        "codigo", "nombre", "estado", "criterio", "umbral", "valores_calculados",
        "contratos_ids", "confianza", "campos_faltantes",
    })
    if senal.estado == "no_evaluable":
        faltan = ", ".join(senal.campos_faltantes) or "datos no especificados"
        return SeccionSenal(
            **base, narrativa_generada_por_llm=False, citas=[],
            narrativa=(f"Señal no evaluable: faltan {faltan}. Esto no debe interpretarse como "
                       "ausencia de riesgo; requiere revisión humana."),
        )

    ids = set(senal.contratos_ids)
    contratos = [c for c in entrada.contratos if c.id in ids]
    fragmentos = [f for f in entrada.normas_recuperadas if f.senal_codigo == senal.codigo]

    n = redactor.redactar_senal(senal, contratos, fragmentos)
    if n is None:
        return SeccionSenal(
            **base, narrativa=redactor.narrativa_respaldo(senal), narrativa_generada_por_llm=False,
            citas=[_cita(f) for f in fragmentos],
        )
    por_id = {f.fragmento_id: f for f in fragmentos}
    return SeccionSenal(
        **base, narrativa=n.narrativa, narrativa_generada_por_llm=True,
        citas=[_cita(por_id[i]) for i in n.fragmento_ids],
    )


def _resumen(entrada: EntradaReporte, limitaciones: list[Limitacion], redactor: Redactor) -> Optional[ResumenEjecutivo]:
    if not entrada.concentracion and not entrada.patrones_adjudicacion:
        return None
    res = ResumenEjecutivo(
        concentracion=entrada.concentracion,
        patrones_adjudicacion=entrada.patrones_adjudicacion,
        num_excluidos=len(entrada.excluidos),
        num_senales_confianza_baja=sum(1 for l in limitaciones if l.tipo == "confianza_baja"),
    )
    datos = res.model_dump(exclude={"texto", "generado_por_llm"})
    texto = redactor.redactar_resumen(datos)
    res.generado_por_llm = texto is not None
    res.texto = texto or redactor.resumen_respaldo(datos)
    return res


def generar_reporte(entrada: Union[EntradaReporte, dict], redactor: Optional[Redactor] = None) -> Reporte:
    """Convierte señales y normas ya calculadas en un reporte verificable."""
    if not isinstance(entrada, EntradaReporte):
        entrada = EntradaReporte.model_validate(entrada)  # falla pronto si el contrato de entrada no se cumple
    redactor = redactor or Redactor.desde_ollama()
    redactor.eventos = []

    limitaciones = construir_limitaciones(entrada)
    secciones = [_seccion(s, entrada, redactor) for s in entrada.senales]
    resumen = _resumen(entrada, limitaciones, redactor)

    reporte = plantilla.ensamblar(entrada, secciones, resumen, limitaciones, redactor.modelo, redactor.eventos)
    reporte.verificacion = verificar_reporte(reporte, entrada)
    if not reporte.verificacion.aprobado:
        reporte.limitaciones.append(Limitacion(
            tipo="verificacion",
            descripcion="El reporte no pasó la verificación automática; no debe distribuirse sin revisión.",
        ))
    return reporte


def exportar(
    reporte: Reporte, directorio: Union[str, Path], formatos: tuple[str, ...] = ("pdf", "json")
) -> dict[str, Path]:
    """Guarda el reporte localmente (pdf, json y/o md). El backend es quien lo sube a S3."""
    d = Path(directorio)
    d.mkdir(parents=True, exist_ok=True)
    nombre = re.sub(r"[^\w\-]", "_", reporte.consulta_id)
    rutas = {f: d / f"{nombre}.{f}" for f in formatos}
    if "json" in rutas:
        rutas["json"].write_text(reporte.model_dump_json(indent=2), encoding="utf-8")
    if "md" in rutas:
        rutas["md"].write_text(plantilla.render_markdown(reporte), encoding="utf-8")
    if "pdf" in rutas:
        plantilla_pdf.render_pdf(reporte, rutas["pdf"])
    return rutas
