"""Deja los modelos cargados en la GPU de cada laptop antes de usarlas (p. ej. antes de una demo).

La primera pregunta después de un rato sin uso paga la carga del modelo (~4.7 GB de qwen2.5:7b), y
eso hizo lenta la primera consulta de la sesión del 2026-11-26. Calentar:

1. Pide a Ollama cargar el LLM (``/api/generate`` sin prompt) y el modelo de embeddings (``/api/embed``),
   con ``keep_alive`` para que no los descargue.
2. Lee ``/api/ps``: cuánta memoria ocupa cada modelo y qué parte está en la GPU. Si no es 100%, una parte
   corre en CPU y las respuestas serán mucho más lentas (el modelo no cabe en la VRAM de esa laptop).
"""
from __future__ import annotations

import json
import os
import time
import urllib.request
from typing import Any, Callable

PostJson = Callable[[str, dict, float], dict]
GetJson = Callable[[str, float], dict]


def _post(url: str, cuerpo: dict, timeout: float) -> dict:
    req = urllib.request.Request(url, data=json.dumps(cuerpo).encode(), method="POST",
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read() or b"{}")


def _get(url: str, timeout: float) -> dict:
    with urllib.request.urlopen(url, timeout=timeout) as r:
        return json.loads(r.read() or b"{}")


def calentar(url: str, modelo: str, modelo_embed: str | None = None, keep_alive: str | None = None,
             post: PostJson = _post, get: GetJson = _get, timeout: float = 600.0,
             reloj: Callable[[], float] = time.perf_counter) -> dict[str, Any]:
    """Carga los modelos en ``url`` y devuelve segundos de carga y el % en GPU de cada modelo."""
    keep_alive = keep_alive or os.environ.get("OLLAMA_KEEP_ALIVE") or "60m"
    modelo_embed = modelo_embed or os.environ.get("OLLAMA_EMBEDDING_MODEL") or "nomic-embed-text"
    url = url.rstrip("/")
    inicio = reloj()
    post(f"{url}/api/generate", {"model": modelo, "keep_alive": keep_alive}, timeout)
    llm_s = reloj() - inicio
    inicio = reloj()
    post(f"{url}/api/embed", {"model": modelo_embed, "input": "calentar", "keep_alive": keep_alive}, timeout)
    embed_s = reloj() - inicio
    cargados = {}
    for m in get(f"{url}/api/ps", 10).get("models", []):
        total, vram = m.get("size") or 0, m.get("size_vram") or 0
        cargados[m.get("name") or m.get("model")] = {
            "memoria_gb": round(total / 1e9, 1),
            "gpu_pct": round(100 * vram / total) if total else None,
        }
    return {"llm_s": round(llm_s, 1), "embed_s": round(embed_s, 1), "modelos": cargados}


def resumen(nombre: str, r: dict[str, Any]) -> str:
    partes = [f"{m} {d['memoria_gb']} GB, {d['gpu_pct']}% GPU" for m, d in r["modelos"].items()]
    pcts = [d["gpu_pct"] or 0 for d in r["modelos"].values()]
    if all(p == 100 for p in pcts):
        aviso = ""
    elif all(p == 0 for p in pcts):
        aviso = "  << AVISO: corre completo en CPU (sin GPU); las respuestas serán lentas"
    else:
        aviso = "  << AVISO: parte del modelo corre en CPU; será lento"
    return f"{nombre}: listo (LLM {r['llm_s']} s, embeddings {r['embed_s']} s) · " + "; ".join(partes) + aviso
