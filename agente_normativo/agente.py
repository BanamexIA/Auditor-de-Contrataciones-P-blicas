"""Agente 2 · Normalización y detección: une las dos partes y escribe el JSON para el Agente 3 (Reporte).

Flujo (todo determinista salvo la recuperación normativa, que solo busca fragmentos):
    filas -> normalizar -> detectar señales -> (opcional) normas vigentes -> validar contrato -> .json

Uso desde la raíz del repo:
    python -m agente_deteccion.agente --entrada contratos.json --salida resultado.json --moneda-por-defecto MXN
    python -m agente_deteccion.agente --entrada contratos.csv --listado69b listado.csv --salida resultado.json
    python -m agente_deteccion.agente --desde-db --institucion "Salud" --desde 2026-01-01 --con-normas --salida resultado.json
"""
import argparse
import csv
import json
import sys
from dataclasses import asdict
from datetime import datetime, timezone

from .detectores import (Parametros, calcular_concentracion, calcular_patrones, construir_excluidos, cruzar_con_listado,
                         detectar_69b, detectar_adj_directa, detectar_monto_atipico)
from .esquema import AVISO, VERSION_REGLAS, validar_resultado
from .normalizacion import normalizar_contratos
from .normativo import recuperar_normas


def ejecutar(filas, coincidencias=None, listado_69b=None, recuperador=None, parametros=None, consulta_id=None,
             moneda_por_defecto=None, alias=None, prioridad_fuentes=(), top_k=3, umbral_distancia=None) -> dict:
    p = parametros or Parametros()
    contratos, contradicciones, calidad = normalizar_contratos(filas, moneda_por_defecto, alias, prioridad_fuentes)
    if coincidencias is None and listado_69b is not None:
        coincidencias = cruzar_con_listado(contratos, listado_69b)
    senales = (detectar_adj_directa(contratos, p) + detectar_monto_atipico(contratos, p)
               + detectar_69b(contratos, coincidencias))
    senales_d = [asdict(s) for s in senales]
    normas, sin_norma = ([], [])
    if recuperador is not None:
        normas, sin_norma = recuperar_normas(senales_d, contratos, recuperador, top_k, umbral_distancia)
    calidad["normativa_consultada"] = recuperador is not None
    calidad["senales_evaluadas"] = sum(s["estado"] == "evaluada" for s in senales_d)
    calidad["senales_no_evaluables"] = sum(s["estado"] == "no_evaluable" for s in senales_d)
    resultado = {
        "consulta_id": consulta_id or "CONSULTA-" + datetime.now().strftime("%Y%m%d-%H%M%S"),
        "version_reglas": VERSION_REGLAS,
        "generado_en": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "parametros": p.a_dict(),
        "contratos": [{
            "id": c["id"], "proveedor": c["proveedor"], "rfc": c["rfc"], "persona_fisica": c["persona_fisica"],
            "monto": c["monto"], "moneda": c["moneda"], "dependencia": c["dependencia"],
            "tipo_procedimiento": c["tipo_procedimiento"], "tipo_procedimiento_normalizado": c["tipo_proc_norm"],
            "fecha": c["fecha"].isoformat() if c["fecha"] else None, "fuente": c["fuente"],
            "en_contradiccion": c["en_contradiccion"]} for c in contratos],
        "senales": senales_d,
        "normas_recuperadas": normas,
        "sin_norma_aplicable": sin_norma,
        "excluidos": construir_excluidos(contratos),
        "contradicciones": contradicciones,
        "concentracion": calcular_concentracion(contratos),
        "patrones_adjudicacion": calcular_patrones(contratos),
        "calidad": calidad,
        "aviso": AVISO,
    }
    return resultado


# ------------------------------------------------------------------ entradas
def leer_filas(ruta: str) -> list[dict]:
    if ruta.lower().endswith(".csv"):
        with open(ruta, encoding="utf-8-sig", newline="") as f:
            return list(csv.DictReader(f))
    with open(ruta, encoding="utf-8") as f:
        datos = json.load(f)
    return datos["contratos"] if isinstance(datos, dict) else datos     # acepta el JSON de ejemplo como entrada


def leer_listado(ruta: str) -> list[dict]:
    with open(ruta, encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def cargar_desde_db(institucion=None, desde=None, hasta=None, limite=5000, host=None, puerto=None,
                    password_env="AGENT_RO_PASSWORD"):
    """Lee con el rol de solo lectura (usuario AGENT_RO_USER; contraseña en la variable de entorno indicada).

    host/puerto permiten apuntar a la base remota (p. ej. un túnel SSH a 127.0.0.1:15432) sin tocar el .env,
    que sigue apuntando a tu base local (la del RAG). La sesión es de solo lectura y con tiempo límite.

    Nota: clean.v_contratos_agente NO trae RFC, así que se lee clean.contratos (agent_ro tiene SELECT).
    Las coincidencias 69-B vienen precalculadas por el ETL en clean.v_coincidencias_69b_agente.
    """
    import psycopg
    from rag.core import setting
    try:
        from etl.db_config import database_settings
    except ImportError:
        from db_config import database_settings
    cfg = database_settings()
    if host:
        cfg["host"] = host
    if puerto:
        cfg["port"] = str(puerto)
    cfg["user"] = setting("AGENT_RO_USER", "agent_ro")
    cfg["password"] = setting(password_env)
    if not cfg["password"]:
        raise RuntimeError(f"Falta la contraseña del rol de solo lectura: define la variable de entorno {password_env}.")
    with psycopg.connect(**cfg, connect_timeout=10, options="-c statement_timeout=30000") as conn:
        conn.read_only = True
        return _leer(conn, institucion, desde, hasta, limite)


def _leer(conn, institucion, desde, hasta, limite):
    with conn.cursor() as cur:
        cur.execute("""
            SELECT codigo_contrato AS id, proveedor, rfc, importe AS monto, moneda, institucion AS dependencia,
                   tipo_procedimiento, tipo_procedimiento_norm, fecha_inicio AS fecha, fecha_fin, fuente
            FROM clean.contratos
            WHERE (%(i)s::text IS NULL OR institucion ILIKE '%%' || %(i)s || '%%')
              AND (%(d)s::date IS NULL OR fecha_inicio >= %(d)s::date)
              AND (%(h)s::date IS NULL OR fecha_inicio <= %(h)s::date)
            ORDER BY fecha_inicio, codigo_contrato LIMIT %(n)s""", {"i": institucion, "d": desde, "h": hasta, "n": limite})
        cols = [c.name for c in cur.description]
        filas = [dict(zip(cols, r)) for r in cur.fetchall()]
        ids = [f["id"] for f in filas if f["id"]]
        cur.execute("""SELECT codigo_contrato, rfc_exacto, nombre_normalizado_exacto, nivel_confianza, rfc,
                              nombre_del_contribuyente FROM clean.v_coincidencias_69b_agente
                       WHERE codigo_contrato = ANY(%s)""", (ids,))
        cols = [c.name for c in cur.description]
        coincidencias = [dict(zip(cols, r)) for r in cur.fetchall()]
    return filas, coincidencias


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--entrada", help="contratos .json (acepta el JSON de ejemplo) o .csv")
    ap.add_argument("--desde-db", action="store_true", help="leer de PostgreSQL con el rol agent_ro")
    ap.add_argument("--institucion"); ap.add_argument("--desde"); ap.add_argument("--hasta")
    ap.add_argument("--limite", type=int, default=5000)
    ap.add_argument("--db-host", help="host de la base de contratos (por defecto el del .env)")
    ap.add_argument("--db-puerto", type=int, help="puerto de la base de contratos (túnel SSH: 15432)")
    ap.add_argument("--db-password-env", default="AGENT_RO_PASSWORD",
                    help="nombre de la variable de entorno con la contraseña de agent_ro de ESA base")
    ap.add_argument("--listado69b", help="CSV con rfc, nombre_del_contribuyente, situacion_del_contribuyente")
    ap.add_argument("--parametros", help="JSON con umbrales (ver Parametros)")
    ap.add_argument("--moneda-por-defecto", default=None, help="p. ej. MXN, si la fuente no trae moneda (es un supuesto)")
    ap.add_argument("--prioridad-fuentes", nargs="*", default=[])
    ap.add_argument("--con-normas", action="store_true", help="consulta rag.chunks (requiere Ollama y la base)")
    ap.add_argument("--umbral-distancia", type=float, default=None)
    ap.add_argument("--consulta-id"); ap.add_argument("--salida", default="resultado_deteccion.json")
    a = ap.parse_args(argv)
    if not a.entrada and not a.desde_db:
        ap.error("indica --entrada o --desde-db")
    coincidencias = None
    if a.desde_db:
        filas, coincidencias = cargar_desde_db(a.institucion, a.desde, a.hasta, a.limite, a.db_host, a.db_puerto,
                                          a.db_password_env)
    else:
        filas = leer_filas(a.entrada)
    recuperador = None
    if a.con_normas:
        from .normativo import RecuperadorPgvector
        recuperador = RecuperadorPgvector()
    res = ejecutar(filas, coincidencias, leer_listado(a.listado69b) if a.listado69b else None, recuperador,
                   Parametros.desde_json(a.parametros) if a.parametros else None, a.consulta_id,
                   a.moneda_por_defecto, None, tuple(a.prioridad_fuentes), umbral_distancia=a.umbral_distancia)
    problemas = validar_resultado(res)
    with open(a.salida, "w", encoding="utf-8") as f:
        json.dump(res, f, ensure_ascii=False, indent=2, default=str)
    c = res["calidad"]
    print(f"{c['contratos_unicos']} contratos | {c['senales_evaluadas']} señales evaluadas, "
          f"{c['senales_no_evaluables']} no evaluables | {len(res['contradicciones'])} contradicciones | "
          f"{len(res['excluidos'])} exclusiones -> {a.salida}")
    if problemas:
        print("EL JSON NO CUMPLE EL CONTRATO:", *problemas, sep="\n  - ")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())