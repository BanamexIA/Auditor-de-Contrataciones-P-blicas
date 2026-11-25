"""Parte 2 (Aarón) · Tool normativa: fragmentos de norma vigentes para cada señal evaluada.

Reglas del plan que cumple esta capa:
- Solo busca normas para señales 'evaluada'; una señal 'no_evaluable' no cita nada.
- Filtra por la vigencia a la fecha del contrato (lo hace rag.core.retrieve).
- Si no hay fragmento aplicable (o la señal es puramente estadística), lo DECLARA en 'sin_norma_aplicable'.
- No inventa texto: todo 'texto' sale de un fragmento recuperado.

Un 'recuperador' es cualquier función  f(consulta: str, fecha: date | None, top_k: int, [palabras_clave=...]) -> list[dict]
(palabras_clave solo se pasa si la función lo acepta) con las llaves: id, ley, version, fecha_entrada_vigor, fecha_abrogacion, contenido, articulo, distancia, fuente.
Eso permite probar sin base de datos y cambiar el backend (búsqueda híbrida, etc.) sin tocar el resto.
"""
import inspect
from datetime import date

# Qué buscar para cada tipo de señal. 'consulta' = texto que se vectoriza; None = no hay norma aplicable.
# 'referencias_preferidas': [(ley, articulo)] que Aarón puede fijar tras revisar el corpus (se priorizan).
# No se escriben números de artículo aquí: dependen de la versión de cada ley y deben salir del corpus.
# Qué ley puede citar cada señal: 'leyes' fija la lista; 'ley_del_contrato' usa la ley de sus contratos (LAASSP para
# adquisiciones, LOPSRM para obra pública…). Sin esto, una obra pública citaba la LAASSP (2026-11-24).
MAPA_SENAL_NORMA = {
    "ADJ_DIRECTA_RECURRENTE": {
        "consulta": "supuestos de excepción a la licitación pública y procedencia de la adjudicación directa",
        "palabras_clave": ["adjudicación directa", "excepción a la licitación pública", "casos de excepción"],
        "ley_del_contrato": True,
        "referencias_preferidas": []},
    "PROVEEDOR_LISTA_69B": {
        "consulta": "presunción de operaciones inexistentes y listado de contribuyentes del artículo 69-B del Código Fiscal de la Federación",
        "palabras_clave": ["69-B", "operaciones inexistentes", "comprobantes fiscales"],
        "leyes": ["CFF"],
        "referencias_preferidas": []},
    "INCONSISTENCIA_FUENTES": {"consulta": None, "referencias_preferidas": [],
                               "motivo": "es una discrepancia entre fuentes de datos; no hay norma que la defina"},
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
        leyes = _leyes(regla, s, por_id)
        filas = recuperador(regla["consulta"], fecha, top_k, **_extra(recuperador, regla, leyes))
        if leyes:   # también aquí, por si el recuperador no filtra por ley
            filas = [f for f in filas if f.get("ley") in leyes]
        recuperados = len(filas)
        if umbral_distancia is not None:
            filas = [f for f in filas if f.get("distancia") is None or f["distancia"] <= umbral_distancia]
        pref = set(map(tuple, regla.get("referencias_preferidas", [])))
        filas.sort(key=lambda f: 0 if (f.get("ley"), f.get("articulo")) in pref else 1)   # estable: respeta el orden del recuperador (RRF)
        if not filas:
            cual = f" de {', '.join(leyes)}" if leyes else ""
            motivo = (f"ningún fragmento vigente al {fecha.isoformat()} supera el umbral de similitud" if recuperados
                      else f"el corpus no tiene fragmentos vigentes al {fecha.isoformat()}{cual} para esta señal")
            sin_norma.append({"senal_id": s["senal_id"], "motivo": motivo})
            continue
        for f in filas:
            normas.append({
                "fragmento_id": f"chunk-{f['id']}", "senal_id": s["senal_id"], "senal_codigo": s["codigo"],
                "norma": f.get("ley"), "articulo": f.get("articulo"), "version": f.get("version"),
                "vigencia": _iso(f.get("fecha_entrada_vigor")), "abrogacion": _iso(f.get("fecha_abrogacion")),
                "fecha_referencia": fecha.isoformat(), "distancia_coseno": f.get("distancia"),
                "fuente": f.get("fuente"), "texto": f.get("contenido"),
                **{k: f[k] for k in ("metodo_busqueda", "puntaje_rrf", "coincide_texto", "rank_vector", "rank_texto") if k in f}})
    return normas, sin_norma


def llamar(recuperador, consulta, fecha, top_k, **extra):
    """Llama al recuperador pasándole solo los argumentos opcionales que acepta (para envoltorios)."""
    try:
        ps = inspect.signature(recuperador).parameters
    except (TypeError, ValueError):
        return recuperador(consulta, fecha, top_k)
    if not any(p.kind is inspect.Parameter.VAR_KEYWORD for p in ps.values()):
        extra = {k: v for k, v in extra.items() if k in ps}
    return recuperador(consulta, fecha, top_k, **extra)


# Cada ley con su reglamento (las siglas son las de rag.documentos.ley; ver rag/corpus/README.md).
REGLAMENTOS = {"LAASSP": "RLAASSP", "LOPSRM": "RLOPSRM"}


def _leyes(regla, senal, por_id) -> list[str]:
    """Leyes que la señal puede citar; [] = cualquiera (p. ej. contratos sin ley registrada)."""
    if regla.get("leyes"):
        return list(regla["leyes"])
    if regla.get("ley_del_contrato"):
        leyes = {por_id[i]["ley"] for i in senal["contratos_ids"] if i in por_id and por_id[i].get("ley")}
        return sorted(leyes | {REGLAMENTOS[l] for l in leyes if l in REGLAMENTOS})
    return []


def _extra(recuperador, regla, leyes=()) -> dict:
    """Argumentos opcionales que el recuperador acepta (palabras_clave, leyes)."""
    try:
        ps = inspect.signature(recuperador).parameters
    except (TypeError, ValueError):
        return {}
    todos = any(p.kind is inspect.Parameter.VAR_KEYWORD for p in ps.values())
    extra = {"palabras_clave": regla.get("palabras_clave"), "leyes": list(leyes) or None}
    return {k: v for k, v in extra.items() if v and (todos or k in ps)}


def _iso(v):
    return v.isoformat() if isinstance(v, date) else v


class RecuperadorPgvector:
    """Backend real: embeddings con Ollama + búsqueda por vectores en rag.chunks (rag.core.retrieve).

    Búsqueda híbrida (D5): vectores + palabras clave (texto completo en español), fusionadas con RRF y con el filtro de
    vigencia a la fecha del contrato. El umbral de similitud sigue siendo sobre la distancia coseno: una coincidencia por
    palabras clave no basta por sí sola para citar una norma. Con hibrida=False vuelve a la búsqueda solo vectorial.
    Pendiente: calibrar el umbral con rag/results/embedding_retrieval.csv.
    """
    def __init__(self, conn=None, hibrida: bool = True):
        self.hibrida = hibrida
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

    def __call__(self, consulta, fecha, top_k, palabras_clave=None, leyes=None):
        from rag.core import retrieve, retrieve_hybrid
        vectores, _ = self.cliente.embed([consulta])
        if self.hibrida:
            filas, _ = retrieve_hybrid(self.conn, vectores[0], top_k, fecha, consulta, palabras_clave,
                                       tipos=("normas",), leyes=leyes)
        else:
            filas, _ = retrieve(self.conn, vectores[0], top_k, fecha, tipos=("normas",), leyes=leyes)
        return [{"id": r["id"], "ley": r.get("ley"), "version": r.get("version"),
                 "fecha_entrada_vigor": r.get("fecha_entrada_vigor"), "fecha_abrogacion": r.get("fecha_abrogacion"),
                 "contenido": r["contenido"], "articulo": (r.get("metadata") or {}).get("articulo"),
                 "distancia": float(r["distancia_coseno"]), "fuente": r.get("url_o_ruta"),
                 "metodo_busqueda": "hibrida" if self.hibrida else "vectorial",
                 **({k: r[k] for k in ("puntaje_rrf", "coincide_texto", "rank_vector", "rank_texto") if k in r})}
                for r in filas if r.get("tipo") == "normas"]