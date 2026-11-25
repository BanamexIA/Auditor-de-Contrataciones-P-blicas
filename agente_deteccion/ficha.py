"""Ficha de empresa (D6): el auditor pide una empresa (por RFC, por nombre o por ambos) y el sistema devuelve
el MISMO JSON del contrato para el Agente 3, limitado a esa empresa, más un bloque extra 'empresa'.

Reglas de identificación (nada se decide en silencio; todo lo dudoso sale en empresa.advertencias):
- Contrato de la empresa por RFC: RFC válido igual al capturado.
- Contrato de la empresa por nombre: mismo nombre normalizado y sin RFC válido (p. ej. el histórico no trae RFC).
  Confianza menor: las señales que lo usan bajan de confianza.
- Mismo nombre pero OTRO RFC válido: se deja fuera (posible homónimo) y se avisa.
- Si solo se capturó RFC, los nombres se infieren de los contratos con ese RFC (y se avisa).
- Los contratos de otras empresas solo sirven como base de comparación para montos atípicos.
"""
from collections import Counter
from datetime import date

from .agente import ejecutar
from .normalizacion import aplicar_alias, normalizar_fecha, normalizar_fila, normalizar_proveedor, normalizar_rfc

MAX_IDS_EN_AVISO = 10


def _ids(cs):
    return ", ".join(str(c["id"]) for c in cs[:MAX_IDS_EN_AVISO]) + ("…" if len(cs) > MAX_IDS_EN_AVISO else "")


def identificar(filas, rfc=None, nombre=None, moneda_por_defecto=None, alias=None):
    """Separa 'filas' en (contratos de la empresa, comparables, info de identificación)."""
    rfc_n, rfc_ok, rfc_motivo = normalizar_rfc(rfc)
    nombre_n = aplicar_alias(normalizar_proveedor(nombre), alias) or None
    adv = []
    if rfc_n and not rfc_ok:
        adv.append(f"El RFC capturado no es válido ({rfc_motivo}); no se usó para buscar contratos.")
    if not rfc_ok and not nombre_n:
        raise ValueError("Indica un RFC válido o el nombre de la empresa.")
    norm = [(f, normalizar_fila(f, moneda_por_defecto, alias)) for f in filas]
    por_rfc = [c for _, c in norm if rfc_ok and c["rfc_valido"] and c["rfc"] == rfc_n]
    nombres = {nombre_n} if nombre_n else {c["proveedor_norm"] for c in por_rfc if c["proveedor_norm"]}
    foco, comparables, homonimos, por_nombre = [], [], [], []
    for f, c in norm:
        if rfc_ok and c["rfc_valido"] and c["rfc"] == rfc_n:
            foco.append(f)
        elif c["proveedor_norm"] in nombres:
            if rfc_ok and c["rfc_valido"]:
                homonimos.append(c)                      # mismo nombre, otro RFC válido: no se mezcla
            else:
                foco.append(f)
                por_nombre.append(c)
        else:
            comparables.append(f)
    if rfc_ok and nombre_n and por_rfc and not any(c["proveedor_norm"] == nombre_n for c in por_rfc):
        vistos = sorted({c["proveedor"] for c in por_rfc if c["proveedor"]})[:3]
        adv.append(f"El RFC y el nombre capturados no coinciden en ningún contrato: el RFC aparece con {vistos}.")
    if rfc_ok and not por_rfc and por_nombre:
        adv.append("Ningún contrato trae ese RFC; la empresa se identificó solo por nombre (confianza menor).")
    if rfc_ok and por_rfc and not nombre_n and nombres:
        adv.append(f"Solo se capturó RFC: los nombres se infirieron de sus contratos ({sorted(nombres)[:3]}).")
    if rfc_ok and por_nombre and por_rfc:
        adv.append(f"{len(por_nombre)} contrato(s) sin RFC válido se incluyeron por coincidir el nombre normalizado "
                   f"(confianza menor): {_ids(por_nombre)}.")
    if homonimos:
        rfcs = sorted({c['rfc'] for c in homonimos})[:5]
        adv.append(f"{len(homonimos)} contrato(s) con el mismo nombre pero otro RFC válido {rfcs} NO se incluyeron; "
                   f"podrían ser otra empresa: {_ids(homonimos)}.")
    if not rfc_ok:
        rfcs = sorted({c["rfc"] for c in por_nombre if c["rfc_valido"]})
        if len(rfcs) > 1:
            adv.append(f"El nombre corresponde a {len(rfcs)} RFC distintos {rfcs[:5]}; se agruparon por nombre. "
                       "Captura el RFC para separarlos.")
        elif len(rfcs) == 1:
            adv.append(f"Los contratos con RFC válido bajo ese nombre usan {rfcs[0]}; captúralo para mayor confianza.")
    return foco, comparables, {
        "clave": rfc_n if rfc_ok else (nombre_n or sorted(nombres)[0]), "tipo": "rfc" if rfc_ok else "nombre",
        "rfc": rfc_n if rfc_ok else None, "nombres_considerados": sorted(n for n in nombres if n),
        "contratos_por_rfc": len(por_rfc), "contratos_por_nombre": len(por_nombre),
        "ids_por_nombre": [c["id"] for c in por_nombre], "advertencias": adv}


def _anios(d, h):
    if d and h:
        return list(range(d.year, h.year + 1))
    return [(d or h).year] if (d or h) else None


def ficha_empresa(filas, rfc=None, nombre=None, desde=None, hasta=None, coincidencias=None, listado_69b=None,
                  recuperador=None, parametros=None, consulta_id=None, moneda_por_defecto=None, alias=None,
                  prioridad_fuentes=(), cobertura_anios=None, top_k=3, umbral_distancia=None) -> dict:
    """'filas' es el universo: contratos de la empresa y de otros (estos últimos solo para comparar montos).

    cobertura_anios: {año: número de contratos en las fuentes}; si no se da, se calcula de 'filas'.
    """
    foco, comparables, info = identificar(filas, rfc, nombre, moneda_por_defecto, alias)
    adv = list(info["advertencias"])
    d, h = normalizar_fecha(desde), normalizar_fecha(hasta)
    total_empresa = len(foco)
    fuera = sin_fecha = 0
    if d or h:
        dentro = []
        for f in foco:
            fecha = normalizar_fila(f, moneda_por_defecto, alias)["fecha"]
            if fecha is None:
                sin_fecha += 1
            elif (not d or fecha >= d) and (not h or fecha <= h):
                dentro.append(f)
            else:
                fuera += 1
        foco = dentro
        if sin_fecha:
            adv.append(f"{sin_fecha} contrato(s) de la empresa sin fecha válida quedaron fuera porque se pidió un periodo.")
    if cobertura_anios is None:
        cobertura_anios = dict(Counter(
            c["fecha"].year for c in (normalizar_fila(f, moneda_por_defecto, alias) for f in filas) if c["fecha"]))
    pedidos = _anios(d, h)
    sin_cobertura = [a for a in (pedidos or []) if not cobertura_anios.get(a)]
    sin_datos, motivo_sin_datos = False, None
    if not foco:
        sin_datos = True
        if pedidos and len(sin_cobertura) == len(pedidos):
            motivo_sin_datos = (f"Las fuentes cargadas no tienen contratos de ningún proveedor en {sin_cobertura}; "
                                "no es que la empresa no tenga contratos, es que no hay datos de ese periodo.")
        elif total_empresa:
            motivo_sin_datos = (f"La empresa tiene {total_empresa} contrato(s) en las fuentes, pero ninguno en el periodo pedido.")
        else:
            motivo_sin_datos = "No se encontraron contratos de esta empresa en las fuentes cargadas."
    elif sin_cobertura:
        adv.append(f"Las fuentes cargadas no tienen datos de {sin_cobertura}; la ficha no cubre esos años.")

    res = ejecutar(foco, coincidencias, listado_69b, recuperador, parametros, consulta_id, moneda_por_defecto, alias,
                   prioridad_fuentes, top_k, umbral_distancia, comparables=comparables,
                   empresa={"clave": info["clave"], "tipo": info["tipo"], "ids_por_nombre": info["ids_por_nombre"]})
    cs = res["contratos"]
    if info["rfc"]:
        for fila in res["concentracion"]:
            fila["rfc"] = info["rfc"]
    if any(c["persona_fisica"] for c in cs):
        adv.append("El RFC corresponde a una persona física: manejar los datos con cuidado de privacidad.")
    n = len(cs)
    fechas = sorted(c["fecha"] for c in cs if c["fecha"])
    res["empresa"] = {
        "consulta": {"rfc": rfc, "nombre": nombre, "desde": d.isoformat() if d else None, "hasta": h.isoformat() if h else None},
        "identificacion": {k: info[k] for k in ("tipo", "rfc", "nombres_considerados", "contratos_por_rfc",
                                                 "contratos_por_nombre", "ids_por_nombre")},
        "resumen": {
            "num_contratos": n,
            "periodo": {"desde": fechas[0], "hasta": fechas[-1]} if fechas else None,
            "monto_total_mxn": round(sum(c["monto"] for c in cs if c["monto"] and c["monto"] > 0 and c["moneda"] == "MXN"), 2),
            "contratos_sin_monto_en_pesos": sum(not (c["monto"] and c["monto"] > 0 and c["moneda"] == "MXN") for c in cs),
            "contratos_por_anio": dict(sorted(Counter(c["fecha"][:4] for c in cs if c["fecha"]).items())),
            "porcentaje_adjudicaciones_directas": round(100 * sum(c["tipo_procedimiento_normalizado"] == "adjudicacion_directa" for c in cs) / n, 1) if n else None,
            "por_tipo_procedimiento": dict(Counter(c["tipo_procedimiento_normalizado"] for c in cs)),
            "num_dependencias": len({c["dependencia"] for c in cs if c["dependencia"]}),
            "fuentes": sorted({c["fuente"] for c in cs if c["fuente"]}),
            "contratos_fuera_del_periodo": fuera},
        "sin_datos": sin_datos, "motivo_sin_datos": motivo_sin_datos,
        "cobertura_fuentes_por_anio": {str(a): v for a, v in sorted(cobertura_anios.items())},
        "advertencias": adv}
    return res
