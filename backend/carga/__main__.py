"""Prueba de carga con 2 o 3 usuarios concurrentes (B10).

Escenarios:
  api       Cada usuario repite el flujo HTTP del front (crear, ver, avanzar,
            bloquear, desbloquear, rastro, listar). Mide latencia por endpoint.
  carrera   Todos intentan la misma transición del mismo caso a la vez.
            Debe ganar exactamente uno; los demás reciben 409.
  reportes  Todos guardan un reporte del mismo caso a la vez. Cada uno debe
            quedar con su propia versión y su archivo intacto. (Dentro del backend.)
  llm       Cada usuario hace una llamada al modelo en su propio caso, a la vez,
            con el agente que elija el registro. (Dentro del backend.)

Uso:
  python -m backend.carga api --url http://localhost:5000 --usuarios 3 --repeticiones 10
  docker compose exec backend python -m backend.carga todo --url http://localhost:5000
"""

from __future__ import annotations

import argparse
import hashlib
import json
import statistics
import sys
import threading
import time
import urllib.error
import urllib.request
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from typing import Any, Callable


# ---------------------------------------------------------------- HTTP

class Api:
    def __init__(self, url: str) -> None:
        self.url = url.rstrip("/")
        self.tiempos: dict[str, list[float]] = defaultdict(list)
        self.fallas: list[str] = []
        self._lock = threading.Lock()

    def llamar(self, metodo: str, ruta: str, nombre: str, cuerpo: dict | None = None,
               esperado: int | tuple[int, ...] = 200) -> tuple[int, Any]:
        datos = json.dumps(cuerpo).encode() if cuerpo is not None else None
        req = urllib.request.Request(self.url + ruta, data=datos, method=metodo,
                                     headers={"Content-Type": "application/json"})
        inicio = time.perf_counter()
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                codigo, texto = r.status, r.read()
        except urllib.error.HTTPError as e:
            codigo, texto = e.code, e.read()
        except OSError as e:
            codigo, texto = 0, str(e).encode()
        ms = (time.perf_counter() - inicio) * 1000
        esperados = esperado if isinstance(esperado, tuple) else (esperado,)
        with self._lock:
            self.tiempos[nombre].append(ms)
            if codigo not in esperados:
                self.fallas.append(f"{nombre}: HTTP {codigo} {texto[:120]!r}")
        try:
            return codigo, json.loads(texto)
        except ValueError:
            return codigo, None


def flujo_usuario(api: Api, usuario: int, repeticiones: int) -> None:
    for i in range(repeticiones):
        _, caso = api.llamar("POST", "/casos", "POST /casos",
                             {"solicitud": f"Carga u{usuario} #{i}", "creado_por": f"u{usuario}"}, 201)
        if not caso or "id" not in caso:
            continue
        cid = caso["id"]
        api.llamar("GET", f"/casos/{cid}", "GET /casos/<id>")
        api.llamar("POST", f"/casos/{cid}/transiciones", "POST transiciones", {"estado": "consultado"})
        api.llamar("POST", f"/casos/{cid}/transiciones", "POST transiciones",
                   {"estado": "bloqueado", "motivo": "Prueba de carga"})
        api.llamar("POST", f"/casos/{cid}/transiciones", "POST transiciones", {"estado": "consultado"})
        api.llamar("GET", f"/casos/{cid}/bitacora", "GET bitacora")
        api.llamar("GET", f"/casos/{cid}/senales", "GET senales")
        api.llamar("GET", f"/casos/{cid}/telemetria", "GET telemetria")
        api.llamar("GET", "/casos?limite=20", "GET /casos")
        api.llamar("GET", "/agentes", "GET /agentes", esperado=(200, 503))


def escenario_api(url: str, usuarios: int, repeticiones: int) -> dict[str, Any]:
    api = Api(url)
    inicio = time.perf_counter()
    with ThreadPoolExecutor(usuarios) as pool:
        list(pool.map(lambda u: flujo_usuario(api, u, repeticiones), range(1, usuarios + 1)))
    total_s = time.perf_counter() - inicio
    peticiones = sum(len(t) for t in api.tiempos.values())
    return {
        "escenario": "api", "usuarios": usuarios, "repeticiones": repeticiones,
        "peticiones": peticiones, "duracion_s": round(total_s, 2),
        "peticiones_por_s": round(peticiones / total_s, 1),
        "errores": len(api.fallas), "detalle_errores": api.fallas[:10],
        "latencia_ms": {k: _stats(v) for k, v in sorted(api.tiempos.items())},
        "ok": not api.fallas,
    }


def escenario_carrera(url: str, usuarios: int) -> dict[str, Any]:
    api = Api(url)
    _, caso = api.llamar("POST", "/casos", "crear", {"solicitud": "Carrera de transiciones"}, 201)
    cid = caso["id"]
    barrera = threading.Barrier(usuarios)

    def intentar(_):
        barrera.wait()
        return api.llamar("POST", f"/casos/{cid}/transiciones", "transicion",
                          {"estado": "consultado"}, esperado=(200, 409))[0]

    with ThreadPoolExecutor(usuarios) as pool:
        codigos = sorted(pool.map(intentar, range(usuarios)))
    _, rastro = api.llamar("GET", f"/casos/{cid}/bitacora", "bitacora")
    transiciones = [e for e in (rastro or {}).get("eventos", [])
                    if e["evento"] == "transicion" and e["detalle"].get("a") == "consultado"]
    ok = codigos.count(200) == 1 and codigos.count(409) == usuarios - 1 and len(transiciones) == 1
    return {"escenario": "carrera", "usuarios": usuarios, "caso_id": cid, "codigos": codigos,
            "eventos_transicion": len(transiciones), "errores": len(api.fallas), "ok": ok}


# ------------------------------------------------- dentro del backend

def escenario_reportes(usuarios: int) -> dict[str, Any]:
    from backend.app import engine_desde_entorno
    from backend.casos.repositorio import RepositorioCasosSQL
    from backend.reportes.almacen import almacen_desde_entorno
    from backend.reportes.servicio import guardar_reporte, leer_reporte

    repo, almacen = RepositorioCasosSQL(engine_desde_entorno()), almacen_desde_entorno()
    cid = repo.crear("Carrera de reportes", "carga")["id"]
    barrera = threading.Barrier(usuarios)

    def guardar(u):
        barrera.wait()
        contenido = f"# Reporte del usuario {u}\n".encode()
        try:
            return guardar_reporte(repo, almacen, cid, contenido, "md", modelo="carga")
        except Exception as exc:
            return f"{type(exc).__name__}: {str(exc)[:100]}"

    with ThreadPoolExecutor(usuarios) as pool:
        resultados = list(pool.map(guardar, range(1, usuarios + 1)))
    errores = [r for r in resultados if isinstance(r, str)]
    reportes = repo.listar_reportes(cid)
    corruptos = []
    for r in reportes:
        try:
            leer_reporte(almacen, r)
        except Exception as exc:
            corruptos.append(f"v{r['version']}: {type(exc).__name__}")
    versiones = sorted(r["version"] for r in reportes)
    ok = not errores and not corruptos and versiones == list(range(1, usuarios + 1))
    return {"escenario": "reportes", "usuarios": usuarios, "caso_id": cid,
            "versiones": versiones, "errores": len(errores), "detalle_errores": errores,
            "corruptos": corruptos, "ok": ok}


def escenario_llm(usuarios: int, modelo: str | None) -> dict[str, Any]:
    from backend.agentes.repositorio import RepositorioAgentesSQL
    from backend.agentes.servicio import seleccionar_agente
    from backend.app import engine_desde_entorno
    from backend.casos.bitacora import llamar_llm
    from backend.casos.repositorio import RepositorioCasosSQL
    from llm.ollama_client import OllamaClient

    engine = engine_desde_entorno()
    repo, repo_agentes = RepositorioCasosSQL(engine), RepositorioAgentesSQL(engine)
    prompt = "Resume en una frase qué es una licitación pública."

    def llamada(u: int) -> dict[str, Any]:
        cid = repo.crear(f"Carga LLM u{u}", f"u{u}")["id"]
        inicio = time.perf_counter()
        try:
            agente = seleccionar_agente(repo_agentes)
            cliente = OllamaClient(base_url=agente["url"], model=modelo or agente["modelo"])
            r = llamar_llm(repo.registrar_evento, cid, "consultas", cliente,
                           "Responde en español, breve.", prompt)
            return {"usuario": u, "caso_id": cid, "equipo": agente["nombre_tailnet"],
                    "ms": round((time.perf_counter() - inicio) * 1000),
                    "tokens_salida": r.output_tokens, "error": None}
        except Exception as exc:
            return {"usuario": u, "caso_id": cid, "equipo": None,
                    "ms": round((time.perf_counter() - inicio) * 1000),
                    "tokens_salida": None, "error": type(exc).__name__}

    solo = llamada(0)  # referencia: una sola llamada, sin concurrencia
    with ThreadPoolExecutor(usuarios) as pool:
        concurrentes = list(pool.map(llamada, range(1, usuarios + 1)))
    errores = [c for c in [solo, *concurrentes] if c["error"]]
    ms = [c["ms"] for c in concurrentes if not c["error"]]
    return {"escenario": "llm", "usuarios": usuarios, "referencia_ms": solo["ms"],
            "concurrentes": concurrentes,
            "latencia_ms": _stats(ms) if ms else None,
            "factor_vs_referencia": round(max(ms) / solo["ms"], 2) if ms and solo["ms"] else None,
            "errores": len(errores), "ok": not errores}


# ---------------------------------------------------------- salida

def _stats(valores: list[float]) -> dict[str, float]:
    v = sorted(valores)
    p95 = v[min(len(v) - 1, round(0.95 * (len(v) - 1)))]
    return {"n": len(v), "p50": round(statistics.median(v), 1), "p95": round(p95, 1),
            "max": round(v[-1], 1)}


def a_markdown(resultados: list[dict[str, Any]]) -> str:
    l = [f"# Prueba de carga (B10) — {datetime.now(timezone.utc):%Y-%m-%d %H:%M} UTC", ""]
    for r in resultados:
        l.append(f"## {r['escenario']} — {'OK' if r['ok'] else 'FALLA'}")
        l.append("")
        if r["escenario"] == "api":
            l += [f"{r['usuarios']} usuarios × {r['repeticiones']} flujos: {r['peticiones']} peticiones "
                  f"en {r['duracion_s']} s ({r['peticiones_por_s']} pet/s), {r['errores']} errores.", "",
                  "| Endpoint | n | p50 ms | p95 ms | máx ms |", "|---|---|---|---|---|"]
            l += [f"| {k} | {s['n']} | {s['p50']} | {s['p95']} | {s['max']} |"
                  for k, s in r["latencia_ms"].items()]
        elif r["escenario"] == "carrera":
            l.append(f"Códigos: {r['codigos']} · eventos de transición en la bitácora: "
                     f"{r['eventos_transicion']} (esperado: un 200, el resto 409, un evento).")
        elif r["escenario"] == "reportes":
            l.append(f"Versiones: {r['versiones']} · errores: {r['errores']} · "
                     f"archivos corruptos: {r['corruptos'] or 'ninguno'}.")
        elif r["escenario"] == "llm":
            l += [f"Referencia (1 llamada sola): {r['referencia_ms']} ms · "
                  f"concurrentes: {r['latencia_ms']} · la más lenta tardó "
                  f"{r['factor_vs_referencia']}× la referencia.", "",
                  "| Usuario | Equipo | ms | Tokens salida | Error |", "|---|---|---|---|---|"]
            l += [f"| u{c['usuario']} | {c['equipo']} | {c['ms']} | {c['tokens_salida']} | {c['error'] or ''} |"
                  for c in r["concurrentes"]]
        for e in r.get("detalle_errores") or []:
            l.append(f"- {e}")
        l.append("")
    return "\n".join(l)


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="python -m backend.carga")
    p.add_argument("escenario", choices=["api", "carrera", "reportes", "llm", "todo"])
    p.add_argument("--url", default="http://localhost:5000")
    p.add_argument("--usuarios", type=int, default=3)
    p.add_argument("--repeticiones", type=int, default=10)
    p.add_argument("--modelo", help="Modelo para el escenario llm (por defecto el del agente)")
    p.add_argument("--salida", help="Guardar el resultado en Markdown")
    a = p.parse_args(argv)

    pasos: list[Callable[[], dict[str, Any]]] = []
    if a.escenario in ("api", "todo"):
        pasos.append(lambda: escenario_api(a.url, a.usuarios, a.repeticiones))
    if a.escenario in ("carrera", "todo"):
        pasos.append(lambda: escenario_carrera(a.url, a.usuarios))
    if a.escenario in ("reportes", "todo"):
        pasos.append(lambda: escenario_reportes(a.usuarios))
    if a.escenario in ("llm", "todo"):
        pasos.append(lambda: escenario_llm(a.usuarios, a.modelo))

    resultados = []
    for paso in pasos:
        r = paso()
        resultados.append(r)
        print(f"{r['escenario']:<9} {'OK' if r['ok'] else 'FALLA'}", file=sys.stderr)
    texto = a_markdown(resultados)
    print(texto)
    if a.salida:
        with open(a.salida, "w", encoding="utf-8") as f:
            f.write(texto)
    return 0 if all(r["ok"] for r in resultados) else 1


if __name__ == "__main__":
    sys.exit(main())
