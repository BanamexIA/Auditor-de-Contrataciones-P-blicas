"""Plantilla PDF fija del reporte (ReportLab). Todos los reportes salen con el mismo formato:

  1. Título           4. Índice (con enlaces)
  2. Verificación     5. Aviso, resumen ejecutivo, contratos, señales, limitaciones, verificación detallada
  3. Resumen visual

La estructura vive aquí; los colores y estilos viven en tema.py.
"""
from __future__ import annotations

import io
from pathlib import Path
from typing import Any, Union
from xml.sax.saxutils import escape

from reportlab.graphics.charts.piecharts import Pie
from reportlab.graphics.shapes import Circle, Drawing, Line, Rect, String
from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.lib.units import cm
from reportlab.pdfgen import canvas
from reportlab.platypus import (
    BaseDocTemplate, CondPageBreak, Frame, HRFlowable, PageBreak, PageTemplate, Paragraph, Spacer, Table, TableStyle,
)
from reportlab.platypus.tableofcontents import TableOfContents

from . import tema
from .schemas import Reporte

TIPO_LIMITACION = {
    "registro_excluido": "Registro excluido",
    "dato_contradictorio": "Dato contradictorio",
    "senal_no_evaluable": "Señal no evaluable",
    "confianza_baja": "Confianza baja",
    "sin_norma_aplicable": "Sin norma aplicable",
    "sin_senales": "Sin señales",
    "verificacion": "Verificación",
}


# --------------------------------------------------------------------------- utilidades
def _t(x: Any) -> str:
    """Texto seguro para Paragraph (escapa XML y maneja vacíos)."""
    if x is None or x == "":
        return "No disponible"
    return escape(str(x)).replace("\n", "<br/>")


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


def _color(c, texto: str) -> str:
    return f'<font color="{tema.hexstr(c)}"><b>{texto}</b></font>'


class Encabezado(Paragraph):
    """Título de sección que alimenta el índice y los marcadores del PDF."""

    def __init__(self, texto: str, estilo, nivel: int, clave: str):
        super().__init__(texto, estilo)
        self.nivel, self.clave = nivel, clave


class _Doc(BaseDocTemplate):
    def __init__(self, ruta, reporte: Reporte, decorar, **kw):
        super().__init__(
            ruta, pagesize=letter, leftMargin=2 * cm, rightMargin=2 * cm, topMargin=2.5 * cm, bottomMargin=2.3 * cm,
            title=f"Reporte de señales de riesgo — {reporte.consulta_id}",
            author="Agente Auditor de Contrataciones Públicas", subject="Señales de riesgo (revisión humana)", **kw,
        )
        self.addPageTemplates([PageTemplate(id="p", frames=[Frame(self.leftMargin, self.bottomMargin, self.width, self.height, id="f")], onPage=decorar)])

    def afterFlowable(self, fl):
        if isinstance(fl, Encabezado):
            self.canv.bookmarkPage(fl.clave)
            self.canv.addOutlineEntry(fl.getPlainText(), fl.clave, level=fl.nivel, closed=False)
            self.notify("TOCEntry", (fl.nivel, fl.getPlainText(), self.page, fl.clave))


def _decorar(reporte: Reporte, total: int | None):
    """Devuelve el callback que dibuja encabezado y pie en cada página."""

    def _fn(c: canvas.Canvas, doc) -> None:
        w, h = letter
        c.saveState()
        c.setFillColor(tema.ROJO)
        c.rect(0, h - 1.3 * cm, w, 1.3 * cm, stroke=0, fill=1)
        x = 2 * cm
        if tema.LOGO.exists():
            c.drawImage(str(tema.LOGO), x, h - 1.15 * cm, height=0.9 * cm, width=3.2 * cm,
                        preserveAspectRatio=True, mask="auto")
            x += 3.6 * cm
        else:
            c.setFillColor(tema.BLANCO)
            c.setFont("Helvetica-Bold", 14)
            c.drawString(x, h - 0.88 * cm, "Banamex")
            x += 2.5 * cm
        c.setFont("Helvetica", 9)
        c.setFillColor(tema.BLANCO)
        c.drawString(x, h - 0.85 * cm, tema.TITULO_ENCABEZADO)
        c.drawRightString(w - 2 * cm, h - 0.85 * cm, "Reporte de señales de riesgo")

        c.setStrokeColor(tema.GRIS_CLARO)
        c.setLineWidth(0.6)
        c.line(2 * cm, 1.6 * cm, w - 2 * cm, 1.6 * cm)
        c.setFillColor(tema.GRIS_MEDIO)
        c.setFont("Helvetica", 7)
        c.drawString(2 * cm, 1.2 * cm, f"Consulta {reporte.consulta_id} · Plantilla v{reporte.version_plantilla} · Reglas {reporte.version_reglas}")
        c.drawString(2 * cm, 0.8 * cm, tema.AVISO_PIE)
        c.setFont("Helvetica-Bold", 8)
        c.setFillColor(tema.GRIS_OSCURO)
        c.drawRightString(w - 2 * cm, 1.2 * cm, f"Página {doc.page}" + (f" de {total}" if total else ""))
        c.restoreState()

    return _fn


# --------------------------------------------------------------------------- tablas
def _tabla(filas: list[list], anchos: list[float], encabezado: bool = True) -> Table:
    t = Table(filas, colWidths=anchos, repeatRows=1 if encabezado else 0)
    est = [
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 5), ("RIGHTPADDING", (0, 0), (-1, -1), 5),
        ("TOPPADDING", (0, 0), (-1, -1), 3.5), ("BOTTOMPADDING", (0, 0), (-1, -1), 3.5),
        ("LINEBELOW", (0, 0), (-1, -1), 0.4, tema.GRIS_CLARO),
    ]
    if encabezado:
        est += [("BACKGROUND", (0, 0), (-1, 0), tema.GRIS_OSCURO),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [tema.BLANCO, tema.GRIS_MUY_CLARO])]
    else:
        est += [("BACKGROUND", (0, 0), (0, -1), tema.GRIS_MUY_CLARO)]
    t.setStyle(TableStyle(est))
    return t


def _h1(texto: str, E, claves: list[int]) -> list:
    claves[0] += 1
    hr = HRFlowable(width="100%", thickness=1.4, color=tema.ROJO, spaceBefore=0, spaceAfter=6)
    hr.keepWithNext = 1
    return [Encabezado(_t(texto), E["H1"], 0, f"sec{claves[0]}"), hr]


def _h2(texto: str, E, claves: list[int]) -> Encabezado:
    claves[0] += 1
    return Encabezado(_t(texto), E["H2"], 1, f"sec{claves[0]}")


# --------------------------------------------------------------------------- bloques de la primera página
def _bloque_titulo(r: Reporte, E) -> list:
    return [
        Paragraph("Reporte de señales de riesgo", E["Titulo"]),
        Paragraph(f"Consulta {_t(r.consulta_id)}", E["Subtitulo"]),
        Paragraph(f"Generado: {_t(r.generado_en)} · Plantilla v{_t(r.version_plantilla)} · "
                  f"Reglas {_t(r.version_reglas)} · Modelo: {_t(r.modelo)}", E["Meta"]),
    ]


def _bloque_verificacion(r: Reporte, E, ancho: float) -> list:
    v = r.verificacion
    if v is None:
        texto, sub, color = "SIN VERIFICAR", "La verificación automática no se ejecutó", tema.GRIS_MEDIO
    elif v.aprobado:
        texto, sub, color = "APROBADO", "El reporte superó la verificación automática", tema.VERDE
    else:
        texto, sub, color = "NO APROBADO", "Requiere revisión antes de distribuirse", tema.ROJO

    def metrica(valor: str, etiqueta: str, alerta: bool = False):
        c = tema.ROJO if alerta else tema.GRIS_OSCURO
        return [Paragraph(f'<font color="{tema.hexstr(c)}">{valor}</font>', E["MetricaValor"]),
                Paragraph(etiqueta, E["MetricaEtiqueta"])]

    if v is not None:
        cel = [
            metrica(f"{v.citas_correctas}/{v.total_citas}", "Citas correctas"),
            metrica(f"{v.tasa_citas_correctas:.0%}", "Tasa de citas correctas", v.tasa_citas_correctas < tema.META_CITAS),
            metrica(str(len(v.articulos_no_respaldados)), "Artículos sin respaldo", bool(v.articulos_no_respaldados)),
            metrica(str(len(v.terminos_prohibidos)), "Términos no permitidos", bool(v.terminos_prohibidos)),
            metrica(str(len(v.numeros_no_respaldados)), "Cifras a revisar", bool(v.numeros_no_respaldados)),
        ]
    else:
        cel = [metrica("—", "Sin datos")] * 5

    filas = [
        [Paragraph("VERIFICACIÓN AUTOMÁTICA", E["EtiquetaVerif"])] + [""] * 4,
        [[Paragraph(texto, E["EstadoGrande"]), Paragraph(sub, E["EstadoSub"])]] + [""] * 4,
        cel,
    ]
    t = Table(filas, colWidths=[ancho / 5] * 5)
    t.setStyle(TableStyle([
        ("SPAN", (0, 0), (-1, 0)), ("SPAN", (0, 1), (-1, 1)),
        ("BACKGROUND", (0, 0), (-1, 0), tema.GRIS_OSCURO),
        ("BACKGROUND", (0, 1), (-1, 1), color),
        ("BACKGROUND", (0, 2), (-1, 2), tema.GRIS_MUY_CLARO),
        ("BOX", (0, 0), (-1, -1), 0.6, tema.GRIS_CLARO),
        ("LINEAFTER", (0, 2), (-2, 2), 0.4, tema.GRIS_CLARO),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, 0), 4), ("BOTTOMPADDING", (0, 0), (-1, 0), 4),
        ("TOPPADDING", (0, 1), (-1, 1), 12), ("BOTTOMPADDING", (0, 1), (-1, 1), 12),
        ("TOPPADDING", (0, 2), (-1, 2), 8), ("BOTTOMPADDING", (0, 2), (-1, 2), 8),
    ]))
    return [t, Spacer(1, 10)]


def _conteos(r: Reporte) -> tuple[int, int, int]:
    ok = sum(1 for s in r.senales if s.estado == "activa" and s.confianza != "baja")
    baja = sum(1 for s in r.senales if s.estado == "activa" and s.confianza == "baja")
    noev = sum(1 for s in r.senales if s.estado == "no_evaluable")
    return ok, baja, noev


def _barra(d: Drawing, x: float, y: float, w: float, frac: float, color, etiqueta: str, valor: str,
           meta: float | None = None) -> None:
    h = 11
    d.add(String(x, y + h + 5, etiqueta, fontName="Helvetica", fontSize=8, fillColor=tema.GRIS_OSCURO))
    d.add(String(x + w, y + h + 5, valor, fontName="Helvetica-Bold", fontSize=8, fillColor=tema.GRIS_OSCURO, textAnchor="end"))
    d.add(Rect(x, y, w, h, fillColor=tema.GRIS_CLARO, strokeColor=None))
    if frac > 0:
        d.add(Rect(x, y, w * min(frac, 1.0), h, fillColor=color, strokeColor=None))
    if meta is not None:
        d.add(Line(x + w * meta, y - 3, x + w * meta, y + h + 3, strokeColor=tema.GRIS_OSCURO, strokeWidth=1))
        d.add(String(x + w * meta, y - 11, f"meta {meta:.0%}", fontName="Helvetica", fontSize=6.5,
                     fillColor=tema.GRIS_MEDIO, textAnchor="middle"))


def _dibujo_resumen(r: Reporte, ancho: float) -> Drawing:
    H = 5.9 * cm
    d = Drawing(ancho, H)
    ok, baja, noev = _conteos(r)
    total = ok + baja + noev
    cats = [("Activas, alta/media", ok, tema.ROJO), ("Activas, baja", baja, tema.AMBAR), ("No evaluables", noev, tema.GRIS_MEDIO)]

    d.add(String(0, H - 11, "Señales por estado", fontName="Helvetica-Bold", fontSize=9.5, fillColor=tema.GRIS_OSCURO))
    size = 118
    cx, cy = size / 2 + 6, (H - 20) / 2
    if total:
        pie = Pie()
        pie.x, pie.y, pie.width, pie.height = cx - size / 2, cy - size / 2, size, size
        vivas = [c for c in cats if c[1] > 0]
        pie.data = [c[1] for c in vivas]
        for i, c in enumerate(vivas):
            pie.slices[i].fillColor = c[2]
        pie.slices.strokeColor = colors.white
        pie.slices.strokeWidth = 1.5
        d.add(pie)
        d.add(Circle(cx, cy, size * 0.30, fillColor=colors.white, strokeColor=colors.white))
        d.add(String(cx, cy - 2, str(total), fontName="Helvetica-Bold", fontSize=20, fillColor=tema.GRIS_OSCURO, textAnchor="middle"))
        d.add(String(cx, cy - 13, "señales", fontName="Helvetica", fontSize=7, fillColor=tema.GRIS_MEDIO, textAnchor="middle"))
    else:
        d.add(String(cx, cy, "Sin señales detectadas", fontName="Helvetica", fontSize=8, fillColor=tema.GRIS_MEDIO, textAnchor="middle"))
    lx, ly = size + 22, cy + 22
    for i, (nombre, n, c) in enumerate(cats):
        y = ly - i * 17
        d.add(Rect(lx, y - 1, 8, 8, fillColor=c, strokeColor=None))
        d.add(String(lx + 13, y, f"{nombre}: {n}", fontName="Helvetica", fontSize=8, fillColor=tema.GRIS_OSCURO))

    x0 = ancho * 0.66
    w = ancho - x0 - 4
    d.add(String(x0, H - 11, "Indicadores", fontName="Helvetica-Bold", fontSize=9.5, fillColor=tema.GRIS_OSCURO))
    v = r.verificacion
    if v and v.total_citas:
        _barra(d, x0, H - 62, w, v.tasa_citas_correctas, tema.VERDE if v.tasa_citas_correctas >= tema.META_CITAS else tema.ROJO,
               "Citas correctas", f"{v.citas_correctas}/{v.total_citas} ({v.tasa_citas_correctas:.0%})", meta=tema.META_CITAS)
    else:
        _barra(d, x0, H - 62, w, 0, tema.GRIS_MEDIO, "Citas correctas", "Sin citas")
    n_sen, act = len(r.senales), ok + baja
    _barra(d, x0, H - 104, w, act / n_sen if n_sen else 0, tema.GRIS_OSCURO, "Señales evaluadas",
           f"{act}/{n_sen}" if n_sen else "Sin señales")
    llm = sum(1 for s in r.senales if s.estado == "activa" and s.narrativa_generada_por_llm)
    _barra(d, x0, H - 146, w, llm / act if act else 0, tema.AMBAR, "Narrativas redactadas con el modelo",
           f"{llm}/{act}" if act else "—")
    return d


# --------------------------------------------------------------------------- secciones
def _seccion_aviso(r: Reporte, E, claves) -> list:
    caja = Table([[Paragraph(_t(r.aviso), E["Aviso"])]], colWidths=[None])
    caja.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), tema.GRIS_MUY_CLARO), ("LINEBEFORE", (0, 0), (0, -1), 3, tema.ROJO),
        ("LEFTPADDING", (0, 0), (-1, -1), 10), ("RIGHTPADDING", (0, 0), (-1, -1), 10),
        ("TOPPADDING", (0, 0), (-1, -1), 8), ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
    ]))
    return _h1("Aviso de revisión humana", E, claves) + [caja]


def _seccion_resumen(r: Reporte, E, claves, ancho) -> list:
    res = r.resumen_ejecutivo
    if not res or not res.texto:
        return []
    out = _h1("Resumen ejecutivo", E, claves) + [Paragraph(_t(res.texto), E["Cuerpo"])]
    if res.concentracion:
        filas = [[Paragraph(h, E["CeldaEnc"]) for h in ("Proveedor", "RFC", "Contratos", "Monto total", "% del monto", "% adj. directas")]]
        for c in res.concentracion:
            ad = "No disponible" if c.porcentaje_adjudicaciones_directas is None else f"{c.porcentaje_adjudicaciones_directas:.1f}%"
            filas.append([Paragraph(_t(x), E["Celda"]) for x in (c.proveedor, c.rfc, c.num_contratos, _monto(c.monto_total), f"{c.porcentaje_monto:.1f}%", ad)])
        out += [Spacer(1, 4), _tabla(filas, [5.0 * cm, 2.8 * cm, 1.8 * cm, 3.2 * cm, 2.2 * cm, 2.6 * cm])]
    if not res.generado_por_llm:
        out.append(Paragraph("Resumen generado con plantilla determinista (sin modelo).", E["Nota"]))
    return out


def _seccion_contratos(r: Reporte, E, claves) -> list:
    out = _h1("Contratos involucrados", E, claves)
    if not r.contratos:
        return out + [Paragraph("Sin contratos en esta consulta.", E["Cuerpo"])]
    filas = [[Paragraph(h, E["CeldaEnc"]) for h in ("ID / fuente", "Proveedor", "RFC", "Monto", "Dependencia", "Procedimiento", "Fecha")]]
    for c in r.contratos:
        filas.append([
            Paragraph(f"<b>{_t(c.id)}</b><br/><font color='{tema.hexstr(tema.GRIS_MEDIO)}'>{_t(c.fuente)}</font>", E["Celda"]),
            *[Paragraph(_t(x), E["Celda"]) for x in (c.proveedor, c.rfc, _monto(c.monto, c.moneda), c.dependencia, c.tipo_procedimiento, c.fecha)],
        ])
    return out + [_tabla(filas, [2.9 * cm, 3.3 * cm, 2.3 * cm, 2.6 * cm, 2.4 * cm, 2.4 * cm, 1.7 * cm])]


def _seccion_contradicciones(r: Reporte, E, claves) -> list:
    if not r.contradicciones:
        return []
    filas = [[Paragraph(h, E["CeldaEnc"]) for h in ("Contrato", "Campo", "Valor A (fuente)", "Valor B (fuente)")]]
    for c in r.contradicciones:
        filas.append([Paragraph(_t(c.contrato_id), E["Celda"]), Paragraph(_t(c.campo), E["Celda"]),
                      Paragraph(f"<b>{_t(c.valor_a)}</b><br/>{_t(c.fuente_a)}", E["Celda"]),
                      Paragraph(f"<b>{_t(c.valor_b)}</b><br/>{_t(c.fuente_b)}", E["Celda"])])
    return (_h1("Datos contradictorios", E, claves)
            + [Paragraph("El sistema no eligió ningún valor; ambos se muestran con su fuente.", E["Nota"]),
               _tabla(filas, [3.0 * cm, 2.2 * cm, 6.2 * cm, 6.2 * cm])])


def _seccion_senales(r: Reporte, E, claves) -> list:
    out = _h1("Señales detectadas", E, claves)
    if not r.senales:
        return out + [Paragraph("No se detectaron señales con las reglas vigentes. Esto no equivale a ausencia de riesgo.", E["Cuerpo"])]
    colores_conf = {"alta": tema.VERDE, "media": tema.AMBAR, "baja": tema.ROJO}
    for s in r.senales:
        out.append(_h2(s.nombre, E, claves))
        estado = _color(tema.GRIS_OSCURO, "Activa") if s.estado == "activa" else _color(tema.ROJO, "NO EVALUABLE")
        ficha = [
            ("Código", _t(s.codigo)), ("Estado", estado),
            ("Confianza", _color(colores_conf[s.confianza], s.confianza.capitalize())),
            ("Criterio", _t(s.criterio)), ("Umbral", _t(s.umbral)), ("Contratos", _t(", ".join(s.contratos_ids))),
        ]
        if s.campos_faltantes:
            ficha.append(("Campos faltantes", _t(", ".join(s.campos_faltantes))))
        out.append(_tabla([[Paragraph(k, E["CeldaNegrita"]), Paragraph(v, E["Celda"])] for k, v in ficha],
                          [3.2 * cm, 14.4 * cm], encabezado=False))
        if s.valores_calculados:
            filas = [[Paragraph("Valor calculado", E["CeldaEnc"]), Paragraph("Resultado", E["CeldaEnc"])]]
            filas += [[Paragraph(_t(k), E["Celda"]), Paragraph(_t(_num(v)), E["Celda"])] for k, v in s.valores_calculados.items()]
            out += [Spacer(1, 5), _tabla(filas, [9.0 * cm, 8.6 * cm])]
        out += [Spacer(1, 6), Paragraph(_t(s.narrativa), E["Cuerpo"])]
        if s.estado == "activa" and not s.narrativa_generada_por_llm:
            out.append(Paragraph("Narrativa generada con plantilla determinista (sin modelo).", E["Nota"]))
        out.append(Paragraph("Normas citadas", E["Etiqueta"]))
        if s.citas:
            out += [Paragraph(f"{_t(c.norma)}, art. {_t(c.articulo)} (versión {_t(c.version)}) · fragmento {_t(c.fragmento_id)}",
                              E["Vineta"], bulletText="•") for c in s.citas]
        else:
            out.append(Paragraph("Sin norma aplicable en los fragmentos recuperados para esta consulta.", E["Nota"]))
    return out


def _seccion_limitaciones(r: Reporte, E, claves) -> list:
    out = _h1("Limitaciones", E, claves)
    if not r.limitaciones:
        return out + [Paragraph("Sin limitaciones declaradas.", E["Cuerpo"])]
    filas = [[Paragraph("Tipo", E["CeldaEnc"]), Paragraph("Descripción", E["CeldaEnc"])]]
    filas += [[Paragraph(_t(TIPO_LIMITACION.get(l.tipo, l.tipo)), E["CeldaNegrita"]), Paragraph(_t(l.descripcion), E["Celda"])]
              for l in r.limitaciones]
    return out + [_tabla(filas, [4.0 * cm, 13.6 * cm])]


def _seccion_verificacion(r: Reporte, E, claves) -> list:
    v = r.verificacion
    out = _h1("Verificación detallada", E, claves)
    if v is None:
        return out + [Paragraph("La verificación automática no se ejecutó.", E["Cuerpo"])]
    estado = _color(tema.VERDE, "APROBADO") if v.aprobado else _color(tema.ROJO, "NO APROBADO")
    ok, baja, _ = _conteos(r)
    llm = sum(1 for s in r.senales if s.estado == "activa" and s.narrativa_generada_por_llm)
    regen = sum(1 for e in r.trazabilidad if e.get("evento") == "validacion_fallida")
    filas = [
        ("Resultado", estado),
        ("Citas correctas", f"{v.citas_correctas} de {v.total_citas} ({v.tasa_citas_correctas:.0%}); meta {tema.META_CITAS:.0%}"),
        ("Narrativas con modelo", f"{llm} de {ok + baja} señales activas"),
        ("Validaciones fallidas del modelo", str(regen)),
    ]
    out.append(_tabla([[Paragraph(k, E["CeldaNegrita"]), Paragraph(val, E["Celda"])] for k, val in filas],
                      [5.0 * cm, 12.6 * cm], encabezado=False))
    for titulo, items in (("Citas inválidas", v.citas_invalidas), ("Artículos sin respaldo", v.articulos_no_respaldados),
                          ("Términos no permitidos", v.terminos_prohibidos), ("Cifras a revisar", v.numeros_no_respaldados)):
        if items:
            out.append(Paragraph(titulo, E["Etiqueta"]))
            out += [Paragraph(_t(i), E["Vineta"], bulletText="•") for i in items]
    return out


# --------------------------------------------------------------------------- API pública
def _construir(reporte: Reporte, destino, total: int | None, comprimir: bool) -> int:
    E = tema.estilos()
    doc = _Doc(destino, reporte, _decorar(reporte, total), pageCompression=1 if comprimir else 0)
    claves = [0]

    toc = TableOfContents(dotsMinLevel=0)
    toc.levelStyles = [E["TOC0"], E["TOC1"]]

    historia: list = []
    historia += _bloque_titulo(reporte, E)
    historia += _bloque_verificacion(reporte, E, doc.width)
    historia += _h1("Resumen visual", E, claves)
    historia.append(_dibujo_resumen(reporte, doc.width))
    historia += [CondPageBreak(5.5 * cm), Paragraph("Índice", E["TocTitulo"]), toc, PageBreak()]
    historia += _seccion_aviso(reporte, E, claves)
    historia += _seccion_resumen(reporte, E, claves, doc.width)
    historia += _seccion_contratos(reporte, E, claves)
    historia += _seccion_contradicciones(reporte, E, claves)
    historia += _seccion_senales(reporte, E, claves)
    historia += _seccion_limitaciones(reporte, E, claves)
    historia += _seccion_verificacion(reporte, E, claves)

    doc.multiBuild(historia)
    return doc.page


def render_pdf(reporte: Reporte, ruta: Union[str, Path], comprimir: bool = True) -> Path:
    """Genera el PDF. Se arma dos veces: la primera solo para saber cuántas páginas tiene ('Página X de N')."""
    ruta = Path(ruta)
    ruta.parent.mkdir(parents=True, exist_ok=True)
    total = _construir(reporte, io.BytesIO(), None, comprimir)
    _construir(reporte, str(ruta), total, comprimir)
    return ruta
