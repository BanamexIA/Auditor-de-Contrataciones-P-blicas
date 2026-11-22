"""Contrato JSON entre el Agente 2 (este paquete) y el Agente 3 (Reporte, Mich).

Es un superconjunto del ejemplo acordado: mantiene sus llaves y agrega campos que el plan pide
(nivel y periodo para el ranking HU-08, senal_id para las decisiones HU-07, umbral estructurado,
bandera de contradicción) y las llaves 'sin_norma_aplicable', 'calidad' y 'aviso'.
Cámbialo solo de acuerdo con Mich, Ana Pau y Emiliano.
"""
from dataclasses import dataclass, field, asdict

VERSION_REGLAS = "catalogo-senales-v0.2"
AVISO = ("Las señales son indicios para revisión humana; no constituyen una determinación de fraude, "
         "corrupción ni responsabilidad legal.")
NIVELES = ("alto", "medio", "bajo")
CONFIANZAS = ("alta", "media", "baja")
ESTADOS = ("evaluada", "no_evaluable")


@dataclass
class Senal:
    senal_id: str
    codigo: str
    nombre: str
    criterio: str
    umbral: dict | str | None
    estado: str = "evaluada"
    nivel: str | None = None
    confianza: str | None = None
    periodo: dict | None = None            # {"desde": "AAAA-MM-DD", "hasta": "AAAA-MM-DD"}
    valores_calculados: dict = field(default_factory=dict)
    contratos_ids: list = field(default_factory=list)
    campos_faltantes: list = field(default_factory=list)
    motivo: str | None = None
    requiere_revision_humana: bool = True   # siempre: la decisión final es de una persona
    afectada_por_contradiccion: bool = False

    def problemas(self) -> list[str]:
        p = []
        if self.estado not in ESTADOS:
            p.append(f"estado inválido: {self.estado}")
        if not self.contratos_ids:
            p.append("sin contratos_ids")
        if self.estado == "evaluada":
            if self.nivel not in NIVELES:
                p.append("falta nivel")
            if self.confianza not in CONFIANZAS:
                p.append("falta confianza")
            if not self.valores_calculados:
                p.append("falta valores_calculados")
        elif not (self.campos_faltantes or self.motivo):
            p.append("una señal no evaluable debe indicar campos_faltantes o motivo")
        return p


def validar_resultado(res: dict) -> list[str]:
    """Devuelve la lista de problemas del JSON final; vacía si cumple el contrato."""
    p = []
    for llave in ("consulta_id", "version_reglas", "contratos", "senales", "normas_recuperadas",
                  "sin_norma_aplicable", "excluidos", "contradicciones", "concentracion",
                  "patrones_adjudicacion", "calidad", "aviso"):
        if llave not in res:
            p.append(f"falta la llave '{llave}'")
    ids = {c["id"] for c in res.get("contratos", [])}
    vistos = set()
    for s in res.get("senales", []):
        sen = Senal(**s)
        p += [f"{sen.senal_id}: {x}" for x in sen.problemas()]
        if sen.senal_id in vistos:
            p.append(f"{sen.senal_id}: senal_id repetido")
        vistos.add(sen.senal_id)
        p += [f"{sen.senal_id}: contrato {c} no está en 'contratos'" for c in sen.contratos_ids if c not in ids]
    senal_ids = {s["senal_id"] for s in res.get("senales", [])}
    for n in res.get("normas_recuperadas", []):
        if n.get("senal_id") not in senal_ids:
            p.append(f"norma {n.get('fragmento_id')} ligada a una señal inexistente")
    return p


def a_dict(s: Senal) -> dict:
    return asdict(s)