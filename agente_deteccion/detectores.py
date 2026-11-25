"""Parte 1 (Mario) · Reglas de detección deterministas.

Cada detector recibe 'contratos' ya normalizados (ver normalizacion.py) y devuelve objetos Senal
con criterio, valores calculados y umbral visibles. Ninguno usa un LLM ni inventa datos: si falta
información, la señal queda 'no_evaluable' y dice qué falta.

Los umbrales NO están aprobados: el socio formador debe confirmarlos (umbral de adjudicaciones directas,
concentración, montos atípicos y el criterio de 'comparable'). Viven en la tabla config.umbrales (etl/sql/21_config_umbrales.sql),
cada uno con su motivo y su estado ('provisional' o 'confirmado'), y salen en el JSON dentro de 'umbrales'.
Los valores de Parametros son solo el RESPALDO para cuando no hay base (pruebas, CSV de demostración): en ese caso el JSON
declara origen 'codigo' y estado 'provisional'.
"""
import json
import math
import statistics
import unicodedata
from collections import Counter, defaultdict
from dataclasses import dataclass, asdict, fields

from .esquema import Senal
from .normalizacion import normalizar_proveedor, normalizar_rfc


@dataclass
class Parametros:
    adj_umbral_n: int = 2                  # señal si hay MÁS de n adjudicaciones directas en la ventana
    adj_ventana_dias: int = 30
    adj_agrupar_por_dependencia: bool = True
    adj_factor_nivel_alto: float = 2       # nivel alto si hay al menos factor x n adjudicaciones en la ventana
    monto_columnas_grupo: tuple = ("ley", "tipo_proc_norm", "anio")   # 'comparable' = misma ley, tipo de procedimiento y año (plan; pendiente del socio)
    monto_min_grupo: int = 5
    monto_umbral_z: float = 3.5            # puntaje z robusto (mediana y MAD)
    monto_escala_log: bool = True          # los montos son muy asimétricos: se compara sobre el logaritmo
    monto_factor_nivel_alto: float = 2     # nivel alto si |z| >= factor x umbral z
    comparables_confianza_alta: int = 30
    comparables_confianza_media: int = 10

    @classmethod
    def desde_json(cls, ruta: str) -> "Parametros":
        with open(ruta, encoding="utf-8") as f:
            datos = json.load(f)
        if "monto_columnas_grupo" in datos:
            datos["monto_columnas_grupo"] = tuple(datos["monto_columnas_grupo"])
        p = cls(**datos)
        p.origen = f"archivo:{ruta}"
        return p

    # --- procedencia de los umbrales (no son umbrales: no entran en a_dict)
    origen: str = "codigo"
    meta: dict | None = None

    def a_dict(self) -> dict:
        return {k: v for k, v in asdict(self).items() if k not in ("origen", "meta")}

    @classmethod
    def desde_filas(cls, filas: list[dict], origen: str = "config.umbrales") -> "Parametros":
        """filas de config.umbrales: clave, valor, unidad, motivo, estado. Una clave desconocida es un error (no se ignora)."""
        validas = {f.name for f in fields(cls)} - {"origen", "meta"}
        datos, meta = {}, {}
        for f in filas:
            if f["clave"] not in validas:
                raise ValueError(f"config.umbrales trae una clave que el agente no conoce: {f['clave']}")
            v = f["valor"]
            datos[f["clave"]] = tuple(v) if isinstance(v, list) else v
            meta[f["clave"]] = {"estado": f.get("estado") or "provisional", "unidad": f.get("unidad"), "motivo": f.get("motivo")}
        p = cls(**datos)
        p.origen, p.meta = origen, meta
        return p

    def detalle(self) -> dict:
        """Cada umbral con su valor, estado y motivo. Lo que no vino de la tabla se declara provisional."""
        out = {}
        for k, v in self.a_dict().items():
            m = (self.meta or {}).get(k) or {}
            out[k] = {"valor": list(v) if isinstance(v, tuple) else v, "estado": m.get("estado", "provisional"),
                      "unidad": m.get("unidad"), "motivo": m.get("motivo")}
        return out

    def resumen_umbrales(self) -> dict:
        det = self.detalle()
        provisionales = sorted(k for k, d in det.items() if d["estado"] != "confirmado")
        return {"origen": self.origen, "estado": "provisional" if provisionales else "confirmado",
                "provisionales": provisionales, "parametros": det,
                "nota": ("Los umbrales son provisionales: el socio formador aún no los confirma." if provisionales
                         else "Todos los umbrales están confirmados por el socio formador.")
                + ("" if self.origen == "config.umbrales" else
                   f" Se usaron los valores de respaldo ({self.origen}); config.umbrales no se consultó.")}


def _periodo(cs):
    f = [c["fecha"] for c in cs if c["fecha"]]
    return {"desde": min(f).isoformat(), "hasta": max(f).isoformat()} if f else None


def _confianza(problemas: int) -> str:
    return "alta" if problemas == 0 else ("media" if problemas == 1 else "baja")


def _sin_acentos(t) -> str:
    t = unicodedata.normalize("NFKD", str(t or "").lower())
    return "".join(ch for ch in t if unicodedata.category(ch) != "Mn")


# ------------------------------------------------------------------ ADJUDICACIONES DIRECTAS RECURRENTES (HU-02)
def detectar_adj_directa(contratos: list[dict], p: Parametros) -> list[Senal]:
    grupos = defaultdict(list)
    for c in contratos:
        if c["tipo_proc_norm"] == "adjudicacion_directa" and c["fecha"] and c["proveedor_key"]:
            grupos[(c["proveedor_key"], c["dependencia"] if p.adj_agrupar_por_dependencia else None)].append(c)
    senales = []
    for (prov, dep), cs in sorted(grupos.items(), key=lambda kv: str(kv[0])):
        cs.sort(key=lambda c: c["fecha"])
        mejor, j = [], 0
        for i in range(len(cs)):                                  # ventana deslizante
            while (cs[i]["fecha"] - cs[j]["fecha"]).days > p.adj_ventana_dias:
                j += 1
            if i - j + 1 > len(mejor):
                mejor = cs[j:i + 1]
        if len(mejor) <= p.adj_umbral_n:
            continue
        montos = [c["monto"] for c in mejor if c["monto"] is not None and c["moneda"] == "MXN"]
        problemas = (any(c["proveedor_key_tipo"] != "rfc" for c in mejor)
                     + any(c["en_contradiccion"] for c in mejor) + (len(montos) < len(mejor)))
        senales.append(Senal(
            senal_id=f"ADJ_DIRECTA_RECURRENTE-{len(senales) + 1:03d}", codigo="ADJ_DIRECTA_RECURRENTE",
            nombre="Adjudicaciones directas recurrentes al mismo proveedor",
            criterio="Más adjudicaciones directas al mismo proveedor (y dependencia) que el umbral dentro de la ventana de días",
            umbral={"operador": ">", "valor": p.adj_umbral_n, "unidad": "adjudicaciones_directas",
                    "ventana_dias": p.adj_ventana_dias},
            nivel="alto" if len(mejor) >= p.adj_factor_nivel_alto * p.adj_umbral_n else "medio",
            confianza=_confianza(problemas), periodo=_periodo(mejor),
            valores_calculados={
                "proveedor_key": prov, "proveedor_key_tipo": mejor[0]["proveedor_key_tipo"], "dependencia": dep,
                "num_adjudicaciones_directas": len(mejor),
                "ventana_dias": (mejor[-1]["fecha"] - mejor[0]["fecha"]).days,
                "monto_total": round(sum(montos), 2), "contratos_sin_monto_pesos": len(mejor) - len(montos)},
            contratos_ids=[c["id"] for c in mejor],
            afectada_por_contradiccion=any(c["en_contradiccion"] for c in mejor)))
    return senales


# ------------------------------------------------------------------ MONTOS ATÍPICOS (HU-03)
SIN_DATO = "sin_dato"


def _valor_grupo(c: dict, col: str):
    """Valor de una dimensión del grupo de comparación; si la fuente no la trae NO se adivina: queda 'sin_dato'."""
    v = c.get(col)
    return SIN_DATO if v is None or v == "" else v


def detectar_monto_atipico(contratos: list[dict], p: Parametros) -> list[Senal]:
    elegibles = [c for c in contratos if c["monto"] is not None and c["monto"] > 0 and c["moneda"] == "MXN"]
    if not contratos:
        return []
    grupos = defaultdict(list)
    for c in elegibles:
        grupos[tuple(_valor_grupo(c, col) for col in p.monto_columnas_grupo)].append(c)
    senales, evaluados = [], 0
    for clave, cs in sorted(grupos.items(), key=lambda kv: str(kv[0])):
        if len(cs) < p.monto_min_grupo:
            continue
        evaluados += 1
        montos = [c["monto"] for c in cs]
        f, inv = (math.log, math.exp) if p.monto_escala_log else (float, float)
        vals = [f(m) for m in montos]
        med = statistics.median(vals)
        mad = statistics.median(abs(v - med) for v in vals)
        if mad > 0:
            escala = mad / 0.6745
            inf, sup = med - p.monto_umbral_z * escala, med + p.monto_umbral_z * escala
            metodo = "mediana y MAD (puntaje z robusto)" + (" sobre el logaritmo del monto" if p.monto_escala_log else "")
        else:
            q = statistics.quantiles(vals, n=4, method="inclusive")
            iqr = q[2] - q[0]
            escala, inf, sup, metodo = None, q[0] - 1.5 * iqr, q[2] + 1.5 * iqr, "rango intercuartil (MAD=0)"
        for c in cs:
            v = f(c["monto"])
            if inf <= v <= sup:
                continue
            z = (v - med) / escala if escala else None
            base = 0 if len(cs) >= p.comparables_confianza_alta else (1 if len(cs) >= p.comparables_confianza_media else 2)
            problemas = base + (1 if c["en_contradiccion"] else 0)
            senales.append(Senal(
                senal_id=f"MONTO_ATIPICO-{len(senales) + 1:03d}", codigo="MONTO_ATIPICO",
                nombre="Monto atípico frente a contratos comparables",
                criterio=f"Monto fuera del umbral calculado con {metodo} dentro de su grupo de comparación",
                umbral={"operador": "|z|>", "valor": p.monto_umbral_z, "unidad": "puntaje_z_robusto"},
                nivel="alto" if (z is not None and abs(z) >= p.monto_factor_nivel_alto * p.monto_umbral_z) else "medio",
                confianza=_confianza(problemas), periodo=_periodo([c]),
                valores_calculados={
                    "monto": c["monto"], "direccion": "alto" if v > sup else "bajo",
                    "mediana_grupo": round(statistics.median(montos), 2), "mad": round(mad, 4),
                    "umbral_superior": round(inv(sup), 2), "umbral_inferior": round(inv(inf), 2),
                    "puntaje_z": None if z is None else round(z, 2), "tamano_grupo": len(cs), "metodo": metodo,
                    "grupo": dict(zip(p.monto_columnas_grupo, clave)),
                    "dimensiones_sin_dato": [col for col, v in zip(p.monto_columnas_grupo, clave) if v == SIN_DATO]},
                contratos_ids=[c["id"]], afectada_por_contradiccion=c["en_contradiccion"]))
    if not evaluados:
        motivo = (f"ningún grupo de comparación tiene al menos {p.monto_min_grupo} contratos con monto válido en pesos"
                  if elegibles else "ningún contrato tiene monto positivo en pesos")
        senales.append(Senal(
            senal_id="MONTO_ATIPICO-000", codigo="MONTO_ATIPICO", nombre="Monto atípico frente a contratos comparables",
            criterio="Comparación contra un grupo de contratos comparables",
            umbral={"operador": "|z|>", "valor": p.monto_umbral_z, "unidad": "puntaje_z_robusto"},
            estado="no_evaluable", motivo=motivo,
            campos_faltantes=["grupo_comparable_suficiente"] if elegibles else ["monto"],
            contratos_ids=[c["id"] for c in contratos]))
    return senales


# ------------------------------------------------------------------ INCONSISTENCIAS ENTRE FUENTES (HU-03)
_CAMPOS_INCONSISTENCIA = {"monto": "monto", "fecha": "fecha de inicio", "rfc": "RFC"}


def detectar_inconsistencias(contratos: list[dict], contradicciones: list[dict]) -> list[Senal]:
    """Una señal por contrato cuyas fuentes no coinciden en monto, fecha o RFC.

    No decide cuál valor es el correcto: muestra AMBOS valores con su fuente y deja el caso en revisión humana.
    El nivel es provisional: monto o RFC distintos -> medio; solo la fecha -> bajo.
    """
    por_id = {c["id"]: c for c in contratos}
    por_contrato = defaultdict(list)
    for d in contradicciones:
        if d["contrato_id"] in por_id:
            por_contrato[d["contrato_id"]].append(d)
    senales = []
    for cid, ds in sorted(por_contrato.items(), key=lambda kv: str(kv[0])):
        campos = sorted({d["campo"] for d in ds})
        c = por_id[cid]
        senales.append(Senal(
            senal_id=f"INCONSISTENCIA_FUENTES-{len(senales) + 1:03d}", codigo="INCONSISTENCIA_FUENTES",
            nombre="Inconsistencia entre fuentes de datos",
            criterio="El mismo contrato aparece en más de una fuente con valores distintos de monto, fecha o RFC",
            umbral="cualquier diferencia entre fuentes en monto, fecha de inicio o RFC",
            nivel="bajo" if campos == ["fecha"] else "medio", confianza="alta", periodo=_periodo([c]),
            valores_calculados={
                "campos_en_conflicto": campos,
                "diferencias": [{"campo": d["campo"], "valor_a": d["valor_a"], "fuente_a": d["fuente_a"],
                                 "valor_b": d["valor_b"], "fuente_b": d["fuente_b"]} for d in ds],
                "valor_usado_en_el_resto_de_las_reglas": {k: (c[k].isoformat() if k == "fecha" and c[k] else c[k]) for k in campos},
                "nota": "no se decidió cuál valor es correcto; el resto de las reglas usa el de la fuente con mayor prioridad"},
            contratos_ids=[cid], afectada_por_contradiccion=True))
    return senales


# ------------------------------------------------------------------ COINCIDENCIAS 69-B (HU-04)
def cruzar_con_listado(contratos: list[dict], listado: list[dict]) -> list[dict]:
    """Modo CSV/demo: calcula coincidencias con el mismo formato que clean.v_coincidencias_69b_agente.

    listado: filas con rfc, nombre_del_contribuyente, situacion_del_contribuyente, [fecha_publicacion].
    En modo base de datos NO se usa: el ETL ya precalcula las coincidencias.
    """
    por_rfc = {normalizar_rfc(r.get("rfc"))[0]: r for r in listado if r.get("rfc")}
    por_nombre = {normalizar_proveedor(r.get("nombre_del_contribuyente")): r for r in listado}
    out = []
    for c in contratos:
        if c["rfc_valido"] and c["rfc"] in por_rfc:
            r, exacto = por_rfc[c["rfc"]], True
        elif c["proveedor_norm"] and c["proveedor_norm"] in por_nombre:
            r, exacto = por_nombre[c["proveedor_norm"]], False
        else:
            continue
        out.append({"codigo_contrato": c["id"], "rfc_exacto": exacto,
                    "nombre_normalizado_exacto": normalizar_proveedor(r.get("nombre_del_contribuyente")) == c["proveedor_norm"],
                    "rfc": r.get("rfc"), "nombre_del_contribuyente": r.get("nombre_del_contribuyente"),
                    "situacion": r.get("situacion_del_contribuyente"), "fecha_publicacion": r.get("fecha_publicacion")})
    return out


def _nivel_69b(situacion, exacto: bool) -> str:
    if not exacto:
        return "bajo"
    s = _sin_acentos(situacion)
    if "definitivo" in s:
        return "alto"
    if "desvirtuado" in s or "sentencia" in s:
        return "bajo"                       # situación favorable: informativa
    return "medio"                          # presunto o situación desconocida


def _nota_69b(sit, fpub):
    faltan = [n for n, v in (("situación vigente", sit), ("fecha de publicación", fpub)) if not v]
    return None if not faltan else \
        "la fuente cargada no trae: " + " ni ".join(faltan) + "; verificar en el listado oficial del SAT antes de interpretarla"


def detectar_69b(contratos: list[dict], coincidencias: list[dict] | None) -> list[Senal]:
    if not contratos:
        return []
    criterio = "Coincidencia con el listado 69-B del SAT; por RFC exacto (confianza alta) o solo por nombre (baja)"
    umbral = "coincidencia exacta de RFC"
    if coincidencias is None:
        return [Senal(senal_id="PROVEEDOR_LISTA_69B-000", codigo="PROVEEDOR_LISTA_69B",
                      nombre="Proveedor en listado 69-B del SAT", criterio=criterio, umbral=umbral,
                      estado="no_evaluable", motivo="no se recibieron coincidencias ni el listado 69-B",
                      campos_faltantes=["coincidencias_69b"], contratos_ids=[c["id"] for c in contratos])]
    por_id = {c["id"]: c for c in contratos}
    grupos = defaultdict(list)
    for m in coincidencias:
        if m["codigo_contrato"] in por_id:
            grupos[(m.get("rfc") or m.get("nombre_del_contribuyente"), bool(m.get("rfc_exacto")))].append(m)
    senales, con_coincidencia = [], set()
    for (_, exacto), ms in sorted(grupos.items(), key=lambda kv: str(kv[0])):
        cs = [por_id[m["codigo_contrato"]] for m in ms]
        con_coincidencia.update(c["id"] for c in cs)
        sit = next((m.get("situacion") for m in ms if m.get("situacion")), None)
        fpub = next((m.get("fecha_publicacion") for m in ms if m.get("fecha_publicacion")), None)
        senales.append(Senal(
            senal_id=f"PROVEEDOR_LISTA_69B-{len(senales) + 1:03d}", codigo="PROVEEDOR_LISTA_69B",
            nombre="Proveedor en listado 69-B del SAT", criterio=criterio, umbral=umbral,
            nivel=_nivel_69b(sit, exacto), confianza="alta" if exacto else "baja", periodo=_periodo(cs),
            valores_calculados={
                "criterio_cruce": "rfc_exacto" if exacto else "nombre_normalizado",
                "rfc": ms[0].get("rfc"), "nombre_en_listado": ms[0].get("nombre_del_contribuyente"),
                "situacion_vigente": sit, "fecha_publicacion": fpub,
                "nota": _nota_69b(sit, fpub)},
            contratos_ids=[c["id"] for c in cs], afectada_por_contradiccion=any(c["en_contradiccion"] for c in cs)))
    sin_rfc = [c["id"] for c in contratos if not c["rfc_valido"] and c["id"] not in con_coincidencia]
    if sin_rfc:
        senales.append(Senal(
            senal_id="PROVEEDOR_LISTA_69B-NE", codigo="PROVEEDOR_LISTA_69B", nombre="Proveedor en listado 69-B del SAT",
            criterio=criterio, umbral=umbral, estado="no_evaluable",
            motivo="el contrato no tiene un RFC válido y su nombre no coincide con el listado",
            campos_faltantes=["rfc"], contratos_ids=sin_rfc))
    return senales


# ------------------------------------------------------------------ CONCENTRACIÓN Y PATRONES (HU-02, HU-09)
def calcular_concentracion(contratos: list[dict]) -> list[dict]:
    validos = [c for c in contratos if c["monto"] is not None and c["monto"] > 0 and c["moneda"] == "MXN"]
    total = sum(c["monto"] for c in validos)
    validos_ids = {id(c) for c in validos}
    por_prov = defaultdict(list)
    for c in contratos:
        if c["proveedor_key"]:
            por_prov[c["proveedor_key"]].append(c)
    filas = []
    for key, cs in por_prov.items():
        monto = sum(c["monto"] for c in cs if id(c) in validos_ids)
        filas.append({
            "proveedor_key": key, "rfc": cs[0]["rfc"] if cs[0]["rfc_valido"] else None,
            "proveedor": Counter(c["proveedor"] for c in cs).most_common(1)[0][0],
            "persona_fisica": cs[0]["persona_fisica"], "num_contratos": len(cs),
            "monto_total": round(monto, 2),
            "porcentaje_monto": round(100 * monto / total, 1) if total else None,
            "porcentaje_adjudicaciones_directas":
                round(100 * sum(c["tipo_proc_norm"] == "adjudicacion_directa" for c in cs) / len(cs), 1)})
    return sorted(filas, key=lambda f: f["monto_total"], reverse=True)


def calcular_patrones(contratos: list[dict]) -> dict:
    por_dep = defaultdict(list)
    for c in contratos:
        if c["dependencia"]:
            por_dep[c["dependencia"]].append(c)
    return {"por_dependencia": sorted(
        [{"dependencia": d, "num_contratos": len(cs),
          "porcentaje_adjudicacion_directa": round(100 * sum(c["tipo_proc_norm"] == "adjudicacion_directa" for c in cs) / len(cs), 1)}
         for d, cs in por_dep.items()], key=lambda f: f["num_contratos"], reverse=True)}


# ------------------------------------------------------------------ EXCLUIDOS (Escenario 5)
def construir_excluidos(contratos: list[dict]) -> list[dict]:
    out = []

    def add(c, motivo, alcance):
        out.append({"contrato_id": c["id"], "motivo": motivo, "alcance": alcance})
    for c in contratos:
        monto_alc = ["MONTO_ATIPICO", "concentracion"]
        if c["monto"] is None:
            add(c, "sin monto", monto_alc)
        elif c["monto"] <= 0:
            add(c, "monto en cero o negativo", monto_alc)
        if c["moneda"] is None:
            add(c, "moneda no especificada", monto_alc)
        elif c["moneda"] != "MXN":
            add(c, f"moneda distinta de pesos ({c['moneda']})", monto_alc)
        if c["fecha"] is None:
            motivo = (f"fecha fuera del rango válido del ETL ({c['fecha_estado']})" if c.get("fecha_estado")
                      else "fecha inválida" if c["fecha_texto_invalido"] else "sin fecha")
            add(c, motivo, ["ADJ_DIRECTA_RECURRENTE"])
        if c["proveedor_key"] is None:
            add(c, "proveedor no identificable", ["ADJ_DIRECTA_RECURRENTE", "concentracion"])
        if not c["rfc_valido"]:
            motivo = {"faltante": "sin RFC", "generico": "RFC genérico", "formato": "RFC con formato inválido",
                      "fecha_en_rfc": "RFC con fecha inválida"}.get(c["rfc_motivo"], "RFC no válido")
            add(c, motivo, ["PROVEEDOR_LISTA_69B"])
    return out