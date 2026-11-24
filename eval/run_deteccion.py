"""Mide el Agente de Detección contra los casos de referencia (D7 / D10: escenarios 3, 4, 5 y 6).

Corre cada caso de eval/casos_deteccion.yaml (sin base de datos ni LLM), compara contra el resultado esperado calculado a mano
y deja la evidencia en eval/results/deteccion_<fecha>/:  resumen.md, resultados.json y salidas/<caso>.json (el JSON que recibe Mich).

    python -m eval.run_deteccion
    python -m eval.run_deteccion --casos eval/casos_deteccion.yaml --escenario 4
"""
from __future__ import annotations

import argparse
import json
import math
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Any

import yaml

from agente_deteccion.agente import ejecutar
from agente_deteccion.detectores import Parametros
from agente_deteccion.esquema import validar_resultado
from agente_deteccion.ficha import ficha_empresa

ROOT = Path(__file__).resolve().parents[1]
CASOS = ROOT / "eval" / "casos_deteccion.yaml"
RESULTADOS = ROOT / "eval" / "results"
NOMBRES = {3: "Coincidencia con el 69-B", 4: "Monto atípico", 5: "Información insuficiente", 6: "Información contradictoria"}
QUE_COMPRUEBA = {3: "Situación vigente, fecha y cruce por RFC",
                 4: "Marcar solo los atípicos, con grupo de comparación, mediana y umbral",
                 5: "Excluir registros sin monto, informar cuántos y no estimar",
                 6: "Mostrar ambos valores, marcar la inconsistencia y dejar en revisión humana"}


def cargar_casos(ruta: Path = CASOS) -> list[dict]:
    casos = yaml.safe_load(ruta.read_text(encoding="utf-8"))
    ids = [c["id"] for c in casos]
    if len(ids) != len(set(ids)):
        raise ValueError("hay ids de caso repetidos")
    for c in casos:
        for llave in ("id", "escenario", "titulo", "calculo", "entrada", "esperado"):
            if llave not in c:
                raise ValueError(f"{c.get('id')}: falta la llave '{llave}'")
    return casos


def correr_caso(caso: dict) -> dict:
    e, base = caso["entrada"], caso.get("base", {})
    filas = [{**base, **f} for f in e["filas"]]
    params = None
    if e.get("parametros"):
        d = dict(e["parametros"])
        if "monto_columnas_grupo" in d:
            d["monto_columnas_grupo"] = tuple(d["monto_columnas_grupo"])
        params = Parametros(**d)
    comunes = dict(coincidencias=e.get("coincidencias"), listado_69b=e.get("listado_69b"), parametros=params,
                   consulta_id=caso["id"], moneda_por_defecto=e.get("moneda_por_defecto"),
                   prioridad_fuentes=tuple(e.get("prioridad_fuentes", ())))
    if caso.get("modo", "ejecutar") == "ficha":
        emp = e["empresa"]
        return ficha_empresa(filas, rfc=emp.get("rfc"), nombre=emp.get("nombre"), desde=emp.get("desde"),
                             hasta=emp.get("hasta"), **comunes)
    return ejecutar(filas, **comunes)


# ------------------------------------------------------------------ comparación
def igual(esp: Any, obt: Any, tol: float) -> bool:
    if isinstance(esp, bool) or isinstance(obt, bool) or esp is None or obt is None:
        return esp is obt or esp == obt
    if isinstance(esp, (int, float)) and isinstance(obt, (int, float)):
        return math.isclose(esp, obt, rel_tol=tol, abs_tol=tol)
    if isinstance(esp, dict) and isinstance(obt, dict):
        return all(k in obt and igual(v, obt[k], tol) for k, v in esp.items())
    return esp == obt


def _clave(codigo, ids):
    return (codigo, tuple(sorted(map(str, ids))))


def verificar(caso: dict, res: dict) -> list[dict]:
    esp, tol = caso["esperado"], caso["esperado"].get("tolerancia", 1e-6)
    checks = []

    def chk(que, esperado, obtenido, ok=None):
        checks.append({"que": que, "esperado": esperado, "obtenido": obtenido,
                       "ok": igual(esperado, obtenido, tol) if ok is None else ok})

    # --- invariantes de TODO resultado (reglas del plan)
    chk("el JSON cumple el contrato con el Agente 3", [], validar_resultado(res))
    chk("toda señal pide revisión humana", True, all(s["requiere_revision_humana"] for s in res["senales"]))
    chk("el resultado trae el aviso de que son señales y no determinaciones", True, bool(res.get("aviso")))
    chk("toda señal evaluada muestra criterio, umbral, valores y contratos", True, all(
        s["criterio"] and s["umbral"] is not None and s["valores_calculados"] and s["contratos_ids"]
        for s in res["senales"] if s["estado"] == "evaluada"))

    # --- señales
    obtenidas = {}
    for s in res["senales"]:
        obtenidas.setdefault(_clave(s["codigo"], s["contratos_ids"]), []).append(s)
    esperadas = esp.get("senales", [])
    for x in esperadas:
        k = _clave(x["codigo"], x["contratos_ids"])
        et = f"señal {x['codigo']} sobre {sorted(x['contratos_ids'])}"
        s = (obtenidas.get(k) or [None])[0]
        if s is None:
            chk(f"{et} existe", True, False)
            continue
        for campo in ("estado", "nivel", "confianza", "periodo", "afectada_por_contradiccion",
                      "requiere_revision_humana", "campos_faltantes"):
            if campo in x:
                chk(f"{et}: {campo}", x[campo], s.get(campo))
        for campo, v in x.get("valores", {}).items():
            chk(f"{et}: valores.{campo}", v, s["valores_calculados"].get(campo))
        for campo, sub in x.get("valores_contiene", {}).items():
            chk(f"{et}: valores.{campo} contiene «{sub}»", sub, s["valores_calculados"].get(campo),
                ok=sub in str(s["valores_calculados"].get(campo)))
        if "motivo_contiene" in x:
            chk(f"{et}: motivo contiene «{x['motivo_contiene']}»", x["motivo_contiene"], s.get("motivo"),
                ok=x["motivo_contiene"] in (s.get("motivo") or ""))
    for codigo in esp.get("alcance", []):          # para estos códigos no puede haber señales de más ni de menos
        exp = sorted(_clave(x["codigo"], x["contratos_ids"]) for x in esperadas if x["codigo"] == codigo)
        obt = sorted(k for k in obtenidas if k[0] == codigo)
        chk(f"{codigo}: solo las señales esperadas", [f"{c} {list(i)}" for c, i in exp], [f"{c} {list(i)}" for c, i in obt],
            ok=exp == obt)

    # --- exclusiones, contradicciones, contratos, calidad, concentración
    for x in esp.get("excluidos", []):
        chk(f"exclusión {x['contrato_id']}: {x['motivo']}", True,
            any(e["contrato_id"] == x["contrato_id"] and e["motivo"] == x["motivo"] for e in res["excluidos"]))
    if "excluidos_total" in esp:
        chk("total de exclusiones", esp["excluidos_total"], len(res["excluidos"]))
    for x in esp.get("contradicciones", []):
        chk(f"contradicción {x['contrato_id']}.{x['campo']} muestra ambos valores", True,
            any(all(c.get(k) == v for k, v in x.items()) for c in res["contradicciones"]))
    if "contradicciones_total" in esp:
        chk("total de contradicciones", esp["contradicciones_total"], len(res["contradicciones"]))
    por_id = {c["id"]: c for c in res["contratos"]}
    for cid, campos in esp.get("contratos", {}).items():
        for campo, v in campos.items():
            chk(f"contrato {cid}: {campo}", v, por_id.get(cid, {}).get(campo))
    for campo, v in esp.get("calidad", {}).items():
        chk(f"calidad.{campo}", v, res["calidad"].get(campo))
    for x in esp.get("concentracion", []):
        fila = next((c for c in res["concentracion"] if c["proveedor"] == x["proveedor"]), {})
        for campo, v in x.items():
            if campo != "proveedor":
                chk(f"concentración {x['proveedor']}: {campo}", v, fila.get(campo))

    # --- ficha de empresa
    if "empresa" in esp:
        chk("bloque empresa", esp["empresa"], res.get("empresa"))
    if "empresa_motivo_contiene" in esp:
        m = (res.get("empresa") or {}).get("motivo_sin_datos") or ""
        chk("motivo de sin datos", esp["empresa_motivo_contiene"], m, ok=esp["empresa_motivo_contiene"] in m)
    for sub in esp.get("advertencias_contienen", []):
        adv = (res.get("empresa") or {}).get("advertencias", [])
        chk(f"advertencia que contiene «{sub}»", True, any(sub in a for a in adv))
    return checks


# ------------------------------------------------------------------ ejecución y reporte
def ejecutar_casos(casos: list[dict], salidas: Path | None = None) -> list[dict]:
    out = []
    for caso in casos:
        try:
            res = correr_caso(caso)
            checks = verificar(caso, res)
            error = None
        except Exception as exc:           # un caso que truena cuenta como fallido, no detiene el resto
            res, checks, error = None, [], f"{type(exc).__name__}: {exc}"
        if salidas is not None and res is not None:
            (salidas / f"{caso['id']}.json").write_text(json.dumps(res, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
        out.append({"id": caso["id"], "escenario": caso["escenario"], "titulo": caso["titulo"], "calculo": caso["calculo"],
                    "ok": error is None and all(c["ok"] for c in checks), "error": error, "checks": checks})
    return out


def resumen_md(resultados: list[dict], archivo: str, ahora: str) -> str:
    total = len(resultados)
    ok = sum(r["ok"] for r in resultados)
    checks = [c for r in resultados for c in r["checks"]]
    inv = [c for c in checks if c["que"].startswith(("el JSON", "toda señal", "el resultado trae"))]
    L = ["# Medición del Agente de Detección (casos de referencia)", "",
         f"Archivo: `{archivo}` · Casos: {total} · Fecha: {ahora}", "",
         "Los resultados esperados se calcularon a mano antes de ejecutar el agente (ver `calculo` de cada caso en el YAML). "
         "Los umbrales y niveles son **provisionales** hasta que el socio formador los confirme.", "",
         "| Indicador | Valor |", "|---|---:|",
         f"| Casos que coinciden con lo esperado | {ok} de {total} ({100 * ok / total:.1f} %) |",
         f"| Verificaciones individuales correctas | {sum(c['ok'] for c in checks)} de {len(checks)} |",
         f"| Invariantes del plan (contrato, revisión humana, aviso, criterio y umbral visibles) | {sum(c['ok'] for c in inv)} de {len(inv)} |",
         "", "## Por escenario", "", "| Escenario | Qué comprueba | Casos | Correctos |", "|---|---|---:|---:|"]
    for n, nombre in NOMBRES.items():
        rs = [r for r in resultados if r["escenario"] == n]
        if rs:
            L.append(f"| {n}. {nombre} | {QUE_COMPRUEBA[n]} | {len(rs)} | {sum(r['ok'] for r in rs)} |")
    L += ["", "## Detalle por caso", ""]
    for n, nombre in NOMBRES.items():
        rs = [r for r in resultados if r["escenario"] == n]
        if not rs:
            continue
        L += [f"### Escenario {n} · {nombre}", "", "| Caso | Resultado | Qué se comprobó | Verificaciones |", "|---|---|---|---:|"]
        for r in rs:
            L.append(f"| {r['id']} | {'✔ coincide' if r['ok'] else '✘ NO coincide'} | {r['titulo']} | "
                     f"{sum(c['ok'] for c in r['checks'])}/{len(r['checks'])} |")
        L.append("")
    fallos = [r for r in resultados if not r["ok"]]
    L += ["## Diferencias contra lo esperado", ""]
    if not fallos:
        L.append("Ninguna: todos los casos coinciden con lo calculado a mano.")
    for r in fallos:
        L += [f"### {r['id']} · {r['titulo']}", ""]
        if r["error"]:
            L += [f"- El caso falló al ejecutarse: `{r['error']}`", ""]
        L += [f"- {c['que']}: esperado `{json.dumps(c['esperado'], ensure_ascii=False, default=str)}`, "
              f"obtenido `{json.dumps(c['obtenido'], ensure_ascii=False, default=str)}`" for c in r["checks"] if not c["ok"]]
        L.append("")
    return "\n".join(L) + "\n"


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--casos", default=str(CASOS))
    ap.add_argument("--escenario", type=int, action="append", help="solo este escenario (se puede repetir)")
    a = ap.parse_args(argv)
    casos = cargar_casos(Path(a.casos))
    if a.escenario:
        casos = [c for c in casos if c["escenario"] in a.escenario]
    ahora = datetime.now()
    carpeta = RESULTADOS / f"deteccion_{ahora.strftime('%Y%m%d_%H%M%S')}"
    (carpeta / "salidas").mkdir(parents=True, exist_ok=True)
    resultados = ejecutar_casos(casos, carpeta / "salidas")
    (carpeta / "resultados.json").write_text(json.dumps(resultados, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    (carpeta / "resumen.md").write_text(resumen_md(resultados, Path(a.casos).name, ahora.isoformat(timespec="seconds")), encoding="utf-8")
    ok = sum(r["ok"] for r in resultados)
    print(f"{ok}/{len(resultados)} casos coinciden con lo esperado -> {carpeta}")
    for r in resultados:
        if not r["ok"]:
            print(f"  ✘ {r['id']}: {r['titulo']}")
    return 0 if ok == len(resultados) else 1


if __name__ == "__main__":
    raise SystemExit(main())
