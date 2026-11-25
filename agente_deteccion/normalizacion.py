"""Parte 1 (Mario) · Normalización y calidad.

Convierte filas crudas en 'contratos' homogéneos, une duplicados, detecta contradicciones entre
fuentes y marca problemas de calidad SIN imputar valores faltantes.

Fila cruda (llaves esperadas; las que falten quedan en None):
    id, proveedor, rfc, monto, moneda, dependencia, tipo_procedimiento, fecha, fuente,
    [fecha_fin], [tipo_procedimiento_norm]  <- si el ETL ya la calculó se respeta, [ley]
"""
import re
import unicodedata
from collections import defaultdict
from datetime import date, datetime

PROCEDIMIENTOS = ("adjudicacion_directa", "invitacion_tres_personas", "licitacion_publica", "otro", "sin_dato")
RFC_GENERICOS = {"XAXX010101000", "XEXX010101000"}
_RFC = re.compile(r"^[A-ZÑ&]{3,4}\d{6}[A-Z0-9]{3}$")
_VACIOS = {"", "SIN DATO", "N/A", "NA", "NULL", "NONE", "NAN"}


def _vacio(v) -> bool:
    return v is None or str(v).strip().upper() in _VACIOS


def normalizar_texto(v) -> str:
    if v is None:
        return ""
    return re.sub(r"\s+", " ", unicodedata.normalize("NFKC", str(v)).strip())


def normalizar_proveedor(v) -> str:
    """Misma regla que etl/build_clean.py::normalize_provider (mantener sincronizadas)."""
    t = normalizar_texto(v).upper()
    t = unicodedata.normalize("NFKD", t)
    t = "".join(ch for ch in t if unicodedata.category(ch) != "Mn")
    t = t.replace("&", " Y ")
    t = re.sub(r"[^A-Z0-9 ]+", " ", t)
    t = re.sub(r"\b(S\.?A\.?|SOCIEDAD ANONIMA|S\.? DE R\.?L\.?|S\.? DE C\.?V\.?|DE C\.?V\.?|SA DE CV|S\.?R\.?L\.?|S\.?C\.?|SC|SRL)\b", "", t)
    return re.sub(r"\s+", " ", t).strip()


def normalizar_rfc(v) -> tuple[str | None, bool, str | None]:
    """(rfc en mayúsculas | None, es_valido, motivo_si_no). No intenta corregir ni adivinar."""
    if _vacio(v):
        return None, False, "faltante"
    r = re.sub(r"[\s-]", "", str(v)).upper()
    if r in RFC_GENERICOS:
        return r, False, "generico"
    if not _RFC.match(r):
        return r, False, "formato"
    aa_mm_dd = r[-9:-3]
    if not (1 <= int(aa_mm_dd[2:4]) <= 12 and 1 <= int(aa_mm_dd[4:6]) <= 31):
        return r, False, "fecha_en_rfc"
    return r, True, None


def normalizar_fecha(v) -> date | None:
    if isinstance(v, datetime):
        return v.date()
    if isinstance(v, date):
        return v
    if _vacio(v):
        return None
    s = str(v).strip()
    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%Y/%m/%d", "%d-%m-%Y"):
        try:
            return datetime.strptime(s[:10], fmt).date()
        except ValueError:
            continue
    return None


def normalizar_monto(v) -> float | None:
    if v is None or isinstance(v, bool):
        return None
    if isinstance(v, (int, float)):
        return round(float(v), 2) if v == v else None   # descarta NaN
    s = re.sub(r"[$\s]", "", str(v))
    if _vacio(s):
        return None
    if re.fullmatch(r"-?\d{1,3}(,\d{3})+(\.\d+)?", s):
        s = s.replace(",", "")
    elif "," in s and "." not in s:
        s = s.replace(",", ".")
    try:
        return round(float(s), 2)
    except ValueError:
        return None


def normalizar_moneda(v, por_defecto: str | None = None) -> str | None:
    if _vacio(v):
        return por_defecto
    m = normalizar_texto(v).upper()
    return "MXN" if m in {"MXN", "MN", "PESO", "PESOS", "PESO MEXICANO", "PESOS MEXICANOS", "M.N."} else m


def normalizar_procedimiento(v) -> str:
    """Clasificación preliminar (las reglas oficiales están pendientes de aprobación del socio)."""
    if _vacio(v):
        return "sin_dato"
    t = unicodedata.normalize("NFKD", normalizar_texto(v).upper())
    t = "".join(ch for ch in t if unicodedata.category(ch) != "Mn")
    if t.startswith("ADJUDICACION DIRECTA"):
        return "adjudicacion_directa"
    if t.startswith("INVITACION A CUANDO MENOS") or t.startswith("INVITACION A 3") or "TRES PERSONAS" in t:
        return "invitacion_tres_personas"
    if t.startswith("LICITACION PUBLICA"):
        return "licitacion_publica"
    return "otro"


def aplicar_alias(nombre_norm: str, catalogo: dict[str, str] | None) -> str:
    """Catálogo de alias: {nombre_normalizado_variante: nombre_oficial_normalizado}. Conserva el original aparte."""
    return (catalogo or {}).get(nombre_norm, nombre_norm)


def normalizar_fila(f: dict, moneda_por_defecto: str | None = None, alias: dict[str, str] | None = None) -> dict:
    rfc, rfc_ok, rfc_motivo = normalizar_rfc(f.get("rfc"))
    prov_orig = normalizar_texto(f.get("proveedor"))
    prov_norm = aplicar_alias(normalizar_proveedor(prov_orig), alias)
    fecha, fecha_fin = normalizar_fecha(f.get("fecha")), normalizar_fecha(f.get("fecha_fin"))
    fecha_estado = None
    if f.get("fecha_inicio_valida") is False:       # el ETL ya la marcó fuera de rango o inválida: no se usa
        fecha_estado = normalizar_texto(f.get("fecha_inicio_estado")) or "fuera_de_rango"
        fecha = None
    proc_norm = f.get("tipo_procedimiento_norm")
    proc_norm = proc_norm if proc_norm in PROCEDIMIENTOS else normalizar_procedimiento(f.get("tipo_procedimiento"))
    return {
        "id": None if _vacio(f.get("id")) else str(f["id"]).strip(),
        "proveedor": prov_orig or None,
        "proveedor_norm": prov_norm or None,
        "rfc": rfc, "rfc_valido": rfc_ok, "rfc_motivo": rfc_motivo,
        "persona_fisica": (len(rfc) == 13) if rfc_ok else None,
        "monto": normalizar_monto(f.get("monto")),
        "moneda": normalizar_moneda(f.get("moneda"), moneda_por_defecto),
        "dependencia": normalizar_texto(f.get("dependencia")) or None,
        "tipo_procedimiento": normalizar_texto(f.get("tipo_procedimiento")) or None,
        "tipo_proc_norm": proc_norm,
        "ley": normalizar_texto(f.get("ley")).upper() or None,      # LAASSP, LOPSRM, LAPP, ESTATAL… (None si la fuente no la trae)
        "anio": fecha.year if fecha else None,                      # año de inicio; criterio de 'comparable' de los montos
        "fecha": fecha, "fecha_estado": fecha_estado,
        "fecha_texto_invalido": fecha_estado is not None or (fecha is None and not _vacio(f.get("fecha"))),
        "fecha_fin": fecha_fin,
        "fuente": normalizar_texto(f.get("fuente")) or None,
        "en_contradiccion": False,
        # Llave del proveedor: RFC válido si existe; si no, nombre normalizado (confianza menor).
        "proveedor_key": rfc if rfc_ok else (prov_norm or None),
        "proveedor_key_tipo": "rfc" if rfc_ok else ("nombre" if prov_norm else None),
    }


def normalizar_contratos(filas: list[dict], moneda_por_defecto: str | None = None, alias: dict[str, str] | None = None,
                         prioridad_fuentes: tuple[str, ...] = ()):
    """Devuelve (contratos_canonicos, contradicciones, resumen_calidad).

    - Filas con el mismo id se unen en una fila canónica (la de fuente con mayor prioridad).
    - Si difieren monto, fecha o RFC entre fuentes, se conservan ambos valores en 'contradicciones'
      y la fila canónica queda con en_contradiccion=True (no se decide cuál es el correcto).
    """
    norm = [normalizar_fila(f, moneda_por_defecto, alias) for f in filas]
    sin_id = [c for c in norm if c["id"] is None]
    por_id = defaultdict(list)
    for c in norm:
        if c["id"] is not None:
            por_id[c["id"]].append(c)
    rank = lambda c: prioridad_fuentes.index(c["fuente"]) if c["fuente"] in prioridad_fuentes else len(prioridad_fuentes)
    canonicos, contradicciones, duplicados = [], [], 0
    for cid, grupo in por_id.items():
        grupo.sort(key=rank)
        base = grupo[0]
        for otro in grupo[1:]:
            difiere = False
            for campo in ("monto", "fecha", "rfc"):
                a, b = base[campo], otro[campo]
                if a is not None and b is not None and a != b:
                    difiere = True
                    contradicciones.append({
                        "contrato_id": cid, "campo": campo,
                        "valor_a": f"{a:.2f}" if campo == "monto" else str(a), "fuente_a": base["fuente"],
                        "valor_b": f"{b:.2f}" if campo == "monto" else str(b), "fuente_b": otro["fuente"]})
            if difiere:
                base["en_contradiccion"] = True
            else:
                duplicados += 1
        canonicos.append(base)
    resumen = {
        "filas_recibidas": len(filas), "contratos_unicos": len(canonicos), "duplicados_exactos_unidos": duplicados,
        "filas_sin_id_descartadas": len(sin_id),
        "contratos_en_contradiccion": sum(c["en_contradiccion"] for c in canonicos),
        "sin_monto": sum(c["monto"] is None for c in canonicos),
        "monto_no_positivo": sum(c["monto"] is not None and c["monto"] <= 0 for c in canonicos),
        "sin_moneda": sum(c["moneda"] is None for c in canonicos),
        "moneda_distinta_de_pesos": sum(c["moneda"] not in (None, "MXN") for c in canonicos),
        "fecha_invalida": sum(c["fecha_texto_invalido"] for c in canonicos),
        "sin_fecha": sum(c["fecha"] is None and not c["fecha_texto_invalido"] for c in canonicos),
        "sin_rfc": sum(c["rfc_motivo"] == "faltante" for c in canonicos),
        "rfc_invalido": sum(c["rfc_motivo"] in ("formato", "generico", "fecha_en_rfc") for c in canonicos),
        "fecha_fin_antes_de_inicio": sum(bool(c["fecha"] and c["fecha_fin"] and c["fecha_fin"] < c["fecha"]) for c in canonicos),
    }
    return canonicos, contradicciones, resumen


def tabla_calidad(contratos: list[dict]) -> list[dict]:
    """Una fila por contrato con sus banderas de calidad (alimenta HU-03)."""
    out = []
    for c in contratos:
        out.append({
            "id": c["id"], "fuente": c["fuente"],
            "sin_monto": c["monto"] is None,
            "monto_no_positivo": c["monto"] is not None and c["monto"] <= 0,
            "moneda_faltante": c["moneda"] is None,
            "moneda_no_mxn": c["moneda"] not in (None, "MXN"),
            "fecha_invalida": c["fecha_texto_invalido"], "sin_fecha": c["fecha"] is None,
            "sin_rfc": c["rfc_motivo"] == "faltante",
            "rfc_invalido": c["rfc_motivo"] in ("formato", "generico", "fecha_en_rfc"),
            "en_contradiccion": c["en_contradiccion"],
        })
    return out