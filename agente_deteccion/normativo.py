"""Parte 2 (Aarón) · Tool normativa: fragmentos de norma vigentes para cada señal evaluada.

Reglas del plan que cumple esta capa:
- Solo busca normas para señales 'evaluada'; una señal 'no_evaluable' no cita nada.
- Filtra por la vigencia a la fecha del contrato (lo hace rag.core.retrieve).
- Si no hay fragmento aplicable (o la señal es puramente estadística), lo DECLARA en 'sin_norma_aplicable'.
- No inventa texto: todo 'texto' sale de un fragmento recuperado.

Un 'recuperador' es cualquier función  f(consulta: str, fecha: date | None, top_k: int) -> list[dict]
con las llaves: id, ley, version, fecha_entrada_vigor, fecha_abrogacion, contenido, articulo, distancia, fuente.
Eso permite probar sin base de datos y cambiar el backend (búsqueda híbrida, etc.) sin tocar el resto.
"""
from datetime import date

# Qué buscar para cada tipo de señal. 'consulta' = texto que se vectoriza; None = no hay norma aplicable.
# 'referencias_preferidas': [(ley, articulo)] que Aarón puede fijar tras revisar el corpus (se priorizan).
# No se escriben números de artículo aquí: dependen de la versión de cada ley y deben salir del corpus.
MAPA_SENAL_NORMA = {
    "ADJ_DIRECTA_RECURRENTE": {
        "consulta": "supuestos de excepción a la licitación pública y procedencia de la adjudicación directa",
        "referencias_preferidas": []},
    "PROVEEDOR_LISTA_69B": {
        "consulta": "presunción de operaciones inexistentes y listado de contribuyentes del artículo 69-B del Código Fiscal de la Federación",
        "referencias_preferidas": []},
    "MONTO_ATIPICO": {"consulta": None, "referencias_preferidas": [],
                      "motivo": "es una comparación estadística interna; no hay norma que la defina"},
}


def recuperar_normas(senales: list[dict], contratos: list[dict], recuperador, top_k: int = 3,
                     umbral_distancia: float | None = None) -> tuple[list[dict], list[dict]]:
    """Devuelve (normas_recuperadas, sin_norma_aplicable). 'senales' son dicts del JSON (no objetos Senal)."""
    por_id = {c["id"]: c for c in contratos}
    normas, sin_norma = [], []
    for s in senales:
        if s["estado"] != "evaluada":
            continue
        regla = MAPA_SENAL_NORMA.get(s["codigo"])
        if not regla or not regla.get("consulta"):
            sin_norma.append({"senal_id": s["senal_id"], "motivo": (regla or {}).get("motivo", "sin norma asociada a este tipo de señal")})
            continue
        fechas = [por_id[i]["fecha"] for i in s["contratos_ids"] if i in por_id and por_id[i]["fecha"]]
        fecha = min(fechas) if fechas else None          # norma vigente a la fecha del contrato más antiguo
        if fecha is None:
            sin_norma.append({"senal_id": s["senal_id"], "motivo": "sin fecha de contrato; no se puede determinar la versión vigente"})
            continue
        filas = recuperador(regla["consulta"], fecha, top_k)
        if umbral_distancia is not None:
            filas = [f for f in filas if f.get("distancia") is None or f["distancia"] <= umbral_distancia]
        pref = set(map(tuple, regla.get("referencias_preferidas", [])))
        filas.sort(key=lambda f: (0 if (f.get("ley"), f.get("articulo")) in pref else 1, f.get("distancia") or 0))
        if not filas:
            sin_norma.append({"senal_id": s["senal_id"], "motivo": f"ningún fragmento vigente al {fecha.isoformat()} supera el umbral de similitud"})
            continue
        for f in filas:
            normas.append({
                "fragmento_id": f"chunk-{f['id']}", "senal_id": s["senal_id"], "senal_codigo": s["codigo"],
                "norma": f.get("ley"), "articulo": f.get("articulo"), "version": f.get("version"),
                "vigencia": _iso(f.get("fecha_entrada_vigor")), "abrogacion": _iso(f.get("fecha_abrogacion")),
                "fecha_referencia": fecha.isoformat(), "distancia_coseno": f.get("distancia"),
                "fuente": f.get("fuente"), "texto": f.get("contenido")})
    return normas, sin_norma


def _iso(v):
    return v.isoformat() if isinstance(v, date) else v


class RecuperadorPgvector:
    """Backend real: embeddings con Ollama + búsqueda por vectores en rag.chunks (rag.core.retrieve).

    Pendiente (Aarón, según el plan): búsqueda híbrida (vectorial + palabras clave) y calibrar el umbral
    de similitud con rag/results/embedding_retrieval.csv.
    """
    def __init__(self, conn=None):
        from rag.core import OllamaEmbeddingClient, ollama_settings
        url, modelo = ollama_settings()
        self.cliente = OllamaEmbeddingClient(url, modelo)
        if conn is None:
            try:
                from etl.db_config import connect_database
            except ImportError:                                  # ejecución desde la carpeta etl/
                from db_config import connect_database
            conn = connect_database()
        self.conn = conn

    def __call__(self, consulta, fecha, top_k):
        from rag.core import retrieve
        vectores, _ = self.cliente.embed([consulta])
        filas, _ = retrieve(self.conn, vectores[0], top_k, fecha)
        return [{"id": r["id"], "ley": r.get("ley"), "version": r.get("version"),
                 "fecha_entrada_vigor": r.get("fecha_entrada_vigor"), "fecha_abrogacion": r.get("fecha_abrogacion"),
                 "contenido": r["contenido"], "articulo": (r.get("metadata") or {}).get("articulo"),
                 "distancia": float(r["distancia_coseno"]), "fuente": r.get("url_o_ruta")}
                for r in filas if r.get("tipo") == "normas"]