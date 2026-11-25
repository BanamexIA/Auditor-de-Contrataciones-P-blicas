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
from collections import Counter
from dataclasses import asdict
from datetime import datetime, timezone

from .detectores import (Parametros, calcular_concentracion, calcular_patrones, construir_excluidos, cruzar_con_listado,
                         detectar_69b, detectar_adj_directa, detectar_inconsistencias, detectar_monto_atipico)
from .esquema import AVISO, VERSION_REGLAS, validar_resultado
from .normalizacion import normalizar_contratos
from .normativo import recuperar_normas
from .ranking import rankear_proveedores


def ejecutar(filas, coincidencias=None, listado_69b=None, recuperador=None, parametros=None, consulta_id=None,
             moneda_por_defecto=None, alias=None, prioridad_fuentes=(), top_k=3, umbral_distancia=None,
             comparables=None, empresa=None) -> dict:
    """comparables: filas de OTROS proveedores, solo como base de comparación de montos atípicos (ficha de empresa).
    empresa: {'clave', 'tipo', 'ids_por_nombre'} para que todos los contratos de la ficha compartan una sola llave."""
    p = parametros or Parametros()
    contratos, contradicciones, calidad = normalizar_contratos(filas, moneda_por_defecto, alias, prioridad_fuentes)
    ids_foco = {c["id"] for c in contratos}
    contexto = []
    if comparables:
        contexto = [c for c in normalizar_contratos(comparables, moneda_por_defecto, alias, prioridad_fuentes)[0]
                    if c["id"] not in ids_foco]
    if empresa:
        por_nombre = set(empresa.get("ids_por_nombre", ()))
        for c in contratos:
            c["proveedor_key"] = empresa["clave"]
            c["proveedor_key_tipo"] = "nombre" if (empresa["tipo"] == "nombre" or c["id"] in por_nombre) else "rfc"
    if coincidencias is None and listado_69b is not None:
        coincidencias = cruzar_con_listado(contratos, listado_69b)
    monto = detectar_monto_atipico(contratos + contexto, p)
    if contexto:
        monto = _solo_foco(monto, ids_foco)
    senales = (detectar_adj_directa(contratos, p) + monto + detectar_69b(contratos, coincidencias)
               + detectar_inconsistencias(contratos, contradicciones))
    senales_d = [asdict(s) for s in senales]
    normas, sin_norma = ([], [])
    if recuperador is not None:
        normas, sin_norma = recuperar_normas(senales_d, contratos, recuperador, top_k, umbral_distancia)
    fechas = Counter(c["fecha"].isoformat() for c in contratos if c["fecha"])
    calidad["fechas_mas_frecuentes"] = [{"fecha": d, "contratos": n, "porcentaje": round(100 * n / len(contratos), 1)}
                                        for d, n in fechas.most_common(3)]      # una fecha dominante delata fechas de relleno
    exclusiones = construir_excluidos(contratos)
    calidad["exclusiones_por_motivo"] = dict(Counter(e["motivo"] for e in exclusiones))
    if comparables is not None:
        calidad["comparables_para_montos"] = len(contexto)
    calidad["normativa_consultada"] = recuperador is not None
    calidad["senales_evaluadas"] = sum(s["estado"] == "evaluada" for s in senales_d)
    calidad["senales_no_evaluables"] = sum(s["estado"] == "no_evaluable" for s in senales_d)
    resultado = {
        "consulta_id": consulta_id or "CONSULTA-" + datetime.now().strftime("%Y%m%d-%H%M%S"),
        "version_reglas": VERSION_REGLAS,
        "generado_en": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "parametros": p.a_dict(),
        "umbrales": p.resumen_umbrales(),
        "contratos": [{
            "id": c["id"], "proveedor": c["proveedor"], "rfc": c["rfc"], "persona_fisica": c["persona_fisica"],
            "monto": c["monto"], "moneda": c["moneda"], "dependencia": c["dependencia"],
            "tipo_procedimiento": c["tipo_procedimiento"], "tipo_procedimiento_normalizado": c["tipo_proc_norm"],
            "ley": c["ley"],
            "fecha": c["fecha"].isoformat() if c["fecha"] else None, "fuente": c["fuente"],
            "en_contradiccion": c["en_contradiccion"]} for c in contratos],
        "senales": senales_d,
        "normas_recuperadas": normas,
        "sin_norma_aplicable": sin_norma,
        "excluidos": exclusiones,
        "contradicciones": contradicciones,
        "concentracion": calcular_concentracion(contratos),
        "patrones_adjudicacion": calcular_patrones(contratos),
        "calidad": calidad,
        "aviso": AVISO,
    }
    resultado["ranking_proveedores"] = rankear_proveedores(resultado)
    return resultado


def _solo_foco(senales, ids_foco):
    """Deja solo las señales que tocan contratos de la empresa y renumera las evaluadas."""
    out = []
    for s in senales:
        ids = [i for i in s.contratos_ids if i in ids_foco]
        if ids:
            s.contratos_ids = ids
            out.append(s)
    n = 0
    for s in out:
        if s.estado == "evaluada":
            n += 1
            s.senal_id = f"{s.codigo}-{n:03d}"
    return out


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


def _conectar(host=None, puerto=None, password_env="AGENT_RO_PASSWORD"):
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
    conn = psycopg.connect(**cfg, connect_timeout=10, options="-c statement_timeout=30000")
    conn.read_only = True
    return conn


_COLS_CONTRATO = """codigo_contrato AS id, proveedor, rfc, importe AS monto, moneda, institucion AS dependencia,
                   tipo_procedimiento, tipo_procedimiento_norm, fecha_inicio AS fecha, fecha_fin, fuente,
                   fecha_inicio_estado, fecha_inicio_valida, ley"""


def cargar_empresa_desde_db(rfc=None, nombre=None, limite=5000, limite_comparables=5000, host=None, puerto=None,
                            password_env="AGENT_RO_PASSWORD"):
    """Para la ficha de empresa. Devuelve (filas, coincidencias_69b, cobertura_por_anio).

    filas = contratos candidatos de la empresa (por RFC o por nombre normalizado) + contratos de OTROS proveedores
    del mismo tipo de procedimiento (los más recientes, hasta limite_comparables) que solo sirven para comparar montos.
    La cobertura sale de la vista aprobada clean.v_cobertura_fuentes.
    """
    from .normalizacion import normalizar_proveedor, normalizar_rfc
    r, ok, _ = normalizar_rfc(rfc)
    nom = normalizar_proveedor(nombre) or None
    with _conectar(host, puerto, password_env) as conn:
        with conn.cursor() as cur:
            def contratos(where, params, tope):
                cur.execute(f"SELECT {_COLS_CONTRATO} FROM clean.contratos WHERE {where} "
                            "ORDER BY fecha_inicio DESC NULLS LAST, codigo_contrato LIMIT %(tope)s", {**params, "tope": tope})
                cols = [c.name for c in cur.description]
                return [dict(zip(cols, x)) for x in cur.fetchall()]
            candidatos = contratos("(%(r)s::text IS NOT NULL AND rfc = %(r)s) OR proveedor_normalizado = ANY(%(n)s::text[])",
                                   {"r": r if ok else None, "n": [nom] if nom else []}, limite)
            if not nom:                                  # solo RFC: traer también los contratos sin RFC con sus nombres
                nombres = sorted({normalizar_proveedor(f["proveedor"]) for f in candidatos if f["proveedor"]} - {""})
                if nombres:
                    vistos = {f["id"] for f in candidatos}
                    candidatos += [f for f in contratos("proveedor_normalizado = ANY(%(n)s::text[])", {"n": nombres}, limite)
                                   if f["id"] not in vistos]
            ids = [f["id"] for f in candidatos if f["id"]]
            tipos = sorted({f["tipo_procedimiento_norm"] for f in candidatos if f.get("tipo_procedimiento_norm")})
            comparables = []
            if tipos:
                comparables = contratos("tipo_procedimiento_norm = ANY(%(t)s::text[]) AND fecha_inicio_valida "
                                        "AND codigo_contrato <> ALL(%(i)s::text[])", {"t": tipos, "i": ids}, limite_comparables)
            cur.execute("SELECT anio, SUM(filas) FROM clean.v_cobertura_fuentes WHERE anio IS NOT NULL GROUP BY anio")
            cobertura = {int(a): int(n) for a, n in cur.fetchall()}
        coincidencias = _coincidencias_69b(conn, ids)
    return candidatos + comparables, coincidencias, cobertura


def leer_umbrales_db(host=None, puerto=None, password_env="AGENT_RO_PASSWORD"):
    """Lee config.umbrales con el rol de solo lectura. Si la tabla no existe o no se puede leer, NO se adivina en silencio:
    se devuelve (Parametros de respaldo, mensaje) y el JSON dirá que los umbrales vienen del código."""
    try:
        with _conectar(host, puerto, password_env) as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT clave, valor, unidad, motivo, estado FROM config.umbrales ORDER BY clave")
                cols = [c.name for c in cur.description]
                filas = [dict(zip(cols, r)) for r in cur.fetchall()]
        if not filas:
            raise RuntimeError("config.umbrales está vacía")
        return Parametros.desde_filas(filas), None
    except Exception as e:                      # sin tabla, sin permiso o sin conexión: usar el respaldo y decirlo
        p = Parametros()
        p.origen = "codigo (respaldo)"
        return p, f"No se pudo leer config.umbrales ({type(e).__name__}: {e}); se usaron los valores de respaldo del código."


def _coincidencias_69b(conn, ids):
    with conn.cursor() as cur:
        cur.execute("""SELECT codigo_contrato, rfc_exacto, nombre_normalizado_exacto, nivel_confianza, rfc,
                              nombre_del_contribuyente FROM clean.v_coincidencias_69b_agente
                       WHERE codigo_contrato = ANY(%s)""", (ids,))
        cols = [c.name for c in cur.description]
        coincidencias = [dict(zip(cols, r)) for r in cur.fetchall()]
    _agregar_situacion_69b(conn, coincidencias)
    return coincidencias


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
                   tipo_procedimiento, tipo_procedimiento_norm, fecha_inicio AS fecha, fecha_fin, fuente,
                   fecha_inicio_estado, fecha_inicio_valida, ley
            FROM clean.contratos
            WHERE (%(i)s::text IS NULL OR institucion ILIKE '%%' || %(i)s || '%%')
              AND (%(d)s::date IS NULL OR fecha_inicio >= %(d)s::date)
              AND (%(h)s::date IS NULL OR fecha_inicio <= %(h)s::date)
            ORDER BY fecha_inicio DESC NULLS LAST, codigo_contrato LIMIT %(n)s""", {"i": institucion, "d": desde, "h": hasta, "n": limite})
        cols = [c.name for c in cur.description]
        filas = [dict(zip(cols, r)) for r in cur.fetchall()]
        ids = [f["id"] for f in filas if f["id"]]
        cur.execute("""SELECT codigo_contrato, rfc_exacto, nombre_normalizado_exacto, nivel_confianza, rfc,
                              nombre_del_contribuyente FROM clean.v_coincidencias_69b_agente
                       WHERE codigo_contrato = ANY(%s)""", (ids,))
        cols = [c.name for c in cur.description]
        coincidencias = [dict(zip(cols, r)) for r in cur.fetchall()]
    _agregar_situacion_69b(conn, coincidencias)
    return filas, coincidencias


def _agregar_situacion_69b(conn, coincidencias):
    """La vista v_coincidencias_69b_agente no trae la situación; se toma de clean.listado_69b por RFC.

    - Si el RFC aparece con varias situaciones distintas se conservan todas (no se decide cuál vale).
    - 'fecha_publicacion' queda en None: el ETL no la conserva (el CSV solo trae fecha_de_baja, que es otra cosa).
    - Si agent_ro no puede leer la tabla, se sigue sin situación; la señal lo declara en su nota.
    """
    rfcs = sorted({m["rfc"] for m in coincidencias if m.get("rfc")})
    situaciones = {}
    if rfcs:
        try:
            with conn.cursor() as cur:
                cur.execute("SELECT rfc, situacion_del_contribuyente FROM clean.listado_69b WHERE rfc = ANY(%s)", (rfcs,))
                for rfc, sit in cur.fetchall():
                    if sit and sit.strip():
                        situaciones.setdefault(rfc, [])
                        if sit.strip() not in situaciones[rfc]:
                            situaciones[rfc].append(sit.strip())
        except Exception:                      # p. ej. sin permiso sobre la tabla: degradar sin romper el resto
            conn.rollback()
    for m in coincidencias:
        m["situacion"] = "; ".join(situaciones.get(m.get("rfc"), [])) or None
        m.setdefault("fecha_publicacion", None)


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
    ap.add_argument("--rfc", help="ficha de empresa: RFC de la empresa (con --nombre, usa ambos)")
    ap.add_argument("--nombre", help="ficha de empresa: nombre de la empresa; --desde/--hasta acotan el periodo")
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
    ficha = bool(a.rfc or a.nombre)
    coincidencias, cobertura = None, None
    if ficha and a.desde_db:
        filas, coincidencias, cobertura = cargar_empresa_desde_db(a.rfc, a.nombre, a.limite, 5000, a.db_host,
                                                                  a.db_puerto, a.db_password_env)
    elif a.desde_db:
        filas, coincidencias = cargar_desde_db(a.institucion, a.desde, a.hasta, a.limite, a.db_host, a.db_puerto,
                                          a.db_password_env)
    else:
        filas = leer_filas(a.entrada)
    recuperador = None
    if a.con_normas:
        from .normativo import RecuperadorPgvector
        recuperador = RecuperadorPgvector()
    listado = leer_listado(a.listado69b) if a.listado69b else None
    parametros = Parametros.desde_json(a.parametros) if a.parametros else None
    if parametros is None and a.desde_db:
        parametros, aviso_umbrales = leer_umbrales_db(a.db_host, a.db_puerto, a.db_password_env)
        if aviso_umbrales:
            print("  ! " + aviso_umbrales)
    if ficha:
        from .ficha import ficha_empresa
        try:
            res = ficha_empresa(filas, a.rfc, a.nombre, a.desde, a.hasta, coincidencias, listado, recuperador, parametros,
                                a.consulta_id, a.moneda_por_defecto, None, tuple(a.prioridad_fuentes), cobertura,
                                umbral_distancia=a.umbral_distancia)
        except ValueError as e:
            ap.error(str(e))
        e = res["empresa"]
        print(f"FICHA: {e['resumen']['num_contratos']} contratos de la empresa"
              + (f" | SIN DATOS: {e['motivo_sin_datos']}" if e["sin_datos"] else "")
              + "".join(f"\n  ! {x}" for x in e["advertencias"]))
    else:
        res = ejecutar(filas, coincidencias, listado, recuperador, parametros, a.consulta_id,
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