"""D9 (Aarón) · Ranking por nivel de señal (HU-08): la lista ordenada que ve el auditor.

Sin puntajes inventados: es un orden por CONTEO, y el criterio sale escrito en la propia salida.
  1. más señales de nivel alto; 2. más de nivel medio; 3. más de nivel bajo;
  4. más señales con confianza alta; 5. (solo para que el orden sea siempre el mismo) la clave.
Empatan, y comparten posición, los que coinciden en los cuatro primeros criterios.

Solo cuentan las señales evaluadas. Las 'no_evaluable' no suman (se cuentan aparte para que se vea qué no se pudo revisar)
y las que el auditor descartó (decisión 'descartada', HU-07) tampoco. Quien no tiene ninguna señal queda al final.
El criterio es provisional hasta que el socio formador lo confirme.
"""
from collections import defaultdict

from .normalizacion import normalizar_proveedor

VERSION_RANKING = "ranking-v0.1-provisional"
CRITERIO = ("Se ordena por número de señales de nivel alto, luego de nivel medio, luego de nivel bajo; el empate se resuelve por número "
            "de señales con confianza alta. Solo cuentan señales evaluadas y no descartadas por el auditor. No hay puntaje ni "
            "ponderaciones: es un orden por conteo. Una posición alta indica dónde revisar primero, no que haya irregularidad.")


def _clave_orden(u):
    c = u["conteo"]
    return (-c["alto"], -c["medio"], -c["bajo"], -u["con_confianza_alta"])


def rankear(unidades: list[dict], decisiones: dict | None = None) -> dict:
    """unidades: [{'clave', 'nombre', 'senales': [dict de señal]}]. decisiones: {senal_id: 'relevante'|'descartada'|'pendiente'}."""
    decisiones = decisiones or {}
    filas = []
    for u in unidades:
        cuenta = {"alto": 0, "medio": 0, "bajo": 0}
        conf_alta = no_eval = descartadas = 0
        ids, codigos = [], set()
        for s in u["senales"]:
            if s.get("estado") != "evaluada":
                no_eval += 1
                continue
            if decisiones.get(s["senal_id"]) == "descartada":
                descartadas += 1
                continue
            cuenta[s["nivel"]] += 1
            conf_alta += s.get("confianza") == "alta"
            ids.append(s["senal_id"])
            codigos.add(s["codigo"])
        filas.append({"clave": u["clave"], "nombre": u.get("nombre"), "conteo": cuenta, "con_confianza_alta": conf_alta,
                      "senales_no_evaluables": no_eval, "senales_descartadas": descartadas,
                      "senales_ids": ids, "codigos": sorted(codigos), "total_senales": sum(cuenta.values())})
    con = sorted([f for f in filas if f["total_senales"]], key=lambda f: (_clave_orden(f), str(f["clave"])))
    sin = sorted([f for f in filas if not f["total_senales"]], key=lambda f: str(f["clave"]))
    lista, previo, pos = [], None, 0
    for i, f in enumerate(con, start=1):
        k = _clave_orden(f)
        if k != previo:
            pos, previo = i, k                       # empate: misma posición (1, 1, 3…)
        lista.append({"posicion": pos, **f, "empate": False})
    for f in lista:
        f["empate"] = sum(g["posicion"] == f["posicion"] for g in lista) > 1
    for f in sin:
        lista.append({"posicion": None, **f, "empate": False})
    return {"version": VERSION_RANKING, "criterio": CRITERIO, "estado_criterio": "provisional",
            "total": len(lista), "con_senales": len(con), "lista": lista}


def rankear_casos(casos: list[dict], decisiones: dict | None = None) -> dict:
    """casos: [{'caso_id', 'titulo', 'senales': [...]}] (las señales que guarda audit.senales para cada caso)."""
    return rankear([{"clave": c["caso_id"], "nombre": c.get("titulo"), "senales": c["senales"]} for c in casos], decisiones)


def rankear_proveedores(resultado: dict, decisiones: dict | None = None) -> dict:
    """Ordena los proveedores de UN resultado de detección. Una señal cuenta para cada proveedor cuyos contratos toca."""
    prov_de = {}
    for c in resultado["contratos"]:
        nombre = c.get("proveedor")
        clave = c.get("rfc") or normalizar_proveedor(nombre) or None
        prov_de[c["id"]] = (clave, nombre)
    grupos = defaultdict(lambda: {"nombre": None, "senales": []})
    for s in resultado["senales"]:
        for clave in {prov_de[i][0] for i in s["contratos_ids"] if i in prov_de and prov_de[i][0]}:
            grupos[clave]["senales"].append(s)
    for cid, (clave, nombre) in prov_de.items():
        if clave:
            grupos[clave]["nombre"] = grupos[clave]["nombre"] or nombre
    return rankear([{"clave": k, "nombre": g["nombre"], "senales": g["senales"]} for k, g in grupos.items()], decisiones)
