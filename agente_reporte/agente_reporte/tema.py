"""Tema visual del reporte PDF: colores, logotipo y estilos de texto.

Para cambiar la apariencia de TODOS los reportes basta con editar este archivo.
IMPORTANTE: los valores hexadecimales son aproximados; sustitúyelos por los del manual de marca oficial.
"""
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT
from reportlab.lib.styles import ParagraphStyle

# ------------------------------------------------------------------ paleta
ROJO = colors.HexColor("#E4002B")          # color principal de marca (aprox.)
ROJO_OSCURO = colors.HexColor("#B0001F")
GRIS_OSCURO = colors.HexColor("#2B2B2B")
GRIS_MEDIO = colors.HexColor("#9A9A9A")
GRIS_CLARO = colors.HexColor("#E6E6E6")
GRIS_MUY_CLARO = colors.HexColor("#F6F6F6")
BLANCO = colors.white
VERDE = colors.HexColor("#1B873F")         # estado aprobado
AMBAR = colors.HexColor("#F2A900")         # advertencias

LOGO = Path(__file__).parent / "assets" / "logo_banamex.png"
META_CITAS = 0.90                          # meta de tasa de citas correctas

TITULO_ENCABEZADO = "Auditoría de contrataciones públicas"
AVISO_PIE = "Las señales de riesgo requieren revisión humana y no constituyen una determinación de irregularidad."


def hexstr(c) -> str:
    """Color de reportlab -> '#rrggbb' (para etiquetas <font color=...>)."""
    return "#" + c.hexval()[2:]


def estilos() -> dict[str, ParagraphStyle]:
    base = dict(fontName="Helvetica", textColor=GRIS_OSCURO)
    E = {
        "Titulo": ParagraphStyle("Titulo", fontName="Helvetica-Bold", fontSize=24, leading=28, textColor=GRIS_OSCURO),
        "Subtitulo": ParagraphStyle("Subtitulo", fontName="Helvetica-Bold", fontSize=12, leading=15, textColor=ROJO, spaceBefore=2),
        "Meta": ParagraphStyle("Meta", fontName="Helvetica", fontSize=8, leading=11, textColor=GRIS_MEDIO, spaceAfter=8),
        "EtiquetaVerif": ParagraphStyle("EtiquetaVerif", fontName="Helvetica-Bold", fontSize=8, leading=10, textColor=BLANCO, alignment=TA_CENTER),
        "EstadoGrande": ParagraphStyle("EstadoGrande", fontName="Helvetica-Bold", fontSize=34, leading=40, textColor=BLANCO, alignment=TA_CENTER),
        "EstadoSub": ParagraphStyle("EstadoSub", fontName="Helvetica", fontSize=9, leading=11, textColor=BLANCO, alignment=TA_CENTER),
        "MetricaValor": ParagraphStyle("MetricaValor", fontName="Helvetica-Bold", fontSize=15, leading=18, alignment=TA_CENTER, textColor=GRIS_OSCURO),
        "MetricaEtiqueta": ParagraphStyle("MetricaEtiqueta", fontName="Helvetica", fontSize=7, leading=9, alignment=TA_CENTER, textColor=GRIS_MEDIO),
        "H1": ParagraphStyle("H1", fontName="Helvetica-Bold", fontSize=15, leading=18, textColor=GRIS_OSCURO, spaceBefore=14, spaceAfter=2, keepWithNext=1),
        "H2": ParagraphStyle("H2", fontName="Helvetica-Bold", fontSize=11.5, leading=14, textColor=ROJO, spaceBefore=10, spaceAfter=4, keepWithNext=1),
        "TocTitulo": ParagraphStyle("TocTitulo", fontName="Helvetica-Bold", fontSize=15, leading=18, textColor=GRIS_OSCURO, spaceBefore=6, spaceAfter=4),
        "Cuerpo": ParagraphStyle("Cuerpo", fontSize=9.5, leading=13.5, alignment=TA_LEFT, spaceAfter=4, **base),
        "Pequeno": ParagraphStyle("Pequeno", fontSize=8, leading=11, **base),
        "Nota": ParagraphStyle("Nota", fontName="Helvetica-Oblique", fontSize=8, leading=11, textColor=GRIS_MEDIO, spaceAfter=4),
        "Etiqueta": ParagraphStyle("Etiqueta", fontName="Helvetica-Bold", fontSize=8.5, leading=11, textColor=GRIS_OSCURO, spaceBefore=4, spaceAfter=2),
        "Celda": ParagraphStyle("Celda", fontSize=7.5, leading=9.5, **base),
        "CeldaNegrita": ParagraphStyle("CeldaNegrita", fontName="Helvetica-Bold", fontSize=7.5, leading=9.5, textColor=GRIS_OSCURO),
        "CeldaEnc": ParagraphStyle("CeldaEnc", fontName="Helvetica-Bold", fontSize=7.5, leading=9.5, textColor=BLANCO),
        "Aviso": ParagraphStyle("Aviso", fontSize=9.5, leading=13.5, **base),
        "Vineta": ParagraphStyle("Vineta", fontSize=9, leading=12.5, leftIndent=10, bulletIndent=0, spaceAfter=2, **base),
    }
    E["TOC0"] = ParagraphStyle("TOC0", fontName="Helvetica-Bold", fontSize=9.5, leading=11.5, leftIndent=0, spaceBefore=0, textColor=GRIS_OSCURO)
    E["TOC1"] = ParagraphStyle("TOC1", fontName="Helvetica", fontSize=8.5, leading=10.5, leftIndent=16, spaceBefore=0, textColor=GRIS_OSCURO)
    return E
