"""Verificación determinista (sin IA): citas, artículos, lenguaje y cifras.

Meta del equipo: tasa de citas correctas >= 90 % y CERO normas inventadas.
"""
from __future__ import annotations

import re
from typing import Any

from .schemas import EntradaReporte, Reporte, Verificacion

# --------------------------------------------------------------------------- lenguaje
_RE_PROHIBIDOS = re.compile(
    r"\b(fraud\w*|corrup\w*|culpab\w*|culpa|ileg\w*|il[ií]cit\w*|delit\w*|delict\w*|"
    r"soborn\w*|colusi[oó]n|malversaci[oó]n|desv[ií]o de recursos)\b",
    re.IGNORECASE,
)


def terminos_prohibidos(texto: str) -> list[str]:
    """Términos de culpa/delito que no deben aparecer en texto redactado por el modelo."""
    return sorted({m.group(0).lower() for m in _RE_PROHIBIDOS.finditer(texto)})


# --------------------------------------------------------------------------- artículos
_RE_ART = re.compile(
    r"\bart(?:[ií]culos?|s?\.)\s*((?:\d+(?:-?[A-Za-z]{1,3}\b)?(?:\s*(?:,|y|e|o)\s*)?)+)",
    re.IGNORECASE,
)
_RE_NUM_ART = re.compile(r"\d+(?:-?[A-Za-z]{1,3}\b)?")


def normalizar_articulo(a: str) -> str:
    """'69-B' -> '69B', ' 41 ' -> '41'."""
    return re.sub(r"[\s\-]", "", a).upper()


def articulos_mencionados(texto: str) -> list[str]:
    """Artículos que el texto menciona ('artículo 41', 'arts. 41 y 42', 'art. 69-B')."""
    encontrados: list[str] = []
    for m in _RE_ART.finditer(texto):
        for n in _RE_NUM_ART.findall(m.group(1)):
            encontrados.append(normalizar_articulo(n))
    return encontrados


# --------------------------------------------------------------------------- cifras
_RE_NUM = re.compile(r"\d+(?:[.,]\d+)*")


def _a_float(token: str) -> float | None:
    try:
        return float(token.replace(",", ""))
    except ValueError:
        return None


def _recolectar(obj: Any, acc: set[float]) -> None:
    if isinstance(obj, bool) or obj is None:
        return
    if isinstance(obj, (int, float)):
        acc.add(float(obj))
    elif isinstance(obj, str):
        for t in _RE_NUM.findall(obj):
            v = _a_float(t)
            if v is not None:
                acc.add(v)
    elif isinstance(obj, dict):
        for v in obj.values():
            _recolectar(v, acc)
    elif isinstance(obj, (list, tuple, set)):
        for v in obj:
            _recolectar(v, acc)


def numeros_no_respaldados(texto: str, *fuentes: Any, ignorar_hasta: float = 10) -> list[str]:
    """Cifras del texto que no aparecen en los datos de origen (el agente no calcula)."""
    permitidos: set[float] = set()
    for f in fuentes:
        _recolectar(f, permitidos)
    sospechosos = []
    for t in _RE_NUM.findall(texto):
        v = _a_float(t)
        if v is None or v <= ignorar_hasta:
            continue
        if not any(abs(v - p) < 0.011 for p in permitidos):
            sospechosos.append(t)
    return sospechosos


# --------------------------------------------------------------------------- verificación final
def verificar_reporte(reporte: Reporte, entrada: EntradaReporte) -> Verificacion:
    """Comprueba que cada norma citada exista en los fragmentos recuperados en ESTA consulta."""
    fragmentos = {f.fragmento_id: f for f in entrada.normas_recuperadas}
    contratos = {c.id: c for c in reporte.contratos}
    total = correctas = 0
    invalidas: list[str] = []
    no_respaldados: list[str] = []
    prohibidos: set[str] = set()
    numeros: list[str] = []

    for s in reporte.senales:
        for c in s.citas:
            total += 1
            f = fragmentos.get(c.fragmento_id)
            if f is None:
                invalidas.append(f"{s.codigo}: el fragmento '{c.fragmento_id}' no existe en esta consulta")
            elif (c.norma, normalizar_articulo(c.articulo), c.version) != (
                f.norma, normalizar_articulo(f.articulo), f.version
            ):
                invalidas.append(f"{s.codigo}: la cita '{c.fragmento_id}' no coincide con el fragmento recuperado")
            elif f.senal_codigo and f.senal_codigo != s.codigo:
                invalidas.append(f"{s.codigo}: el fragmento '{c.fragmento_id}' pertenece a la señal {f.senal_codigo}")
            else:
                correctas += 1

        citados = {normalizar_articulo(c.articulo) for c in s.citas}
        for a in articulos_mencionados(s.narrativa):
            if a not in citados:
                no_respaldados.append(f"{s.codigo}: artículo {a} mencionado sin fragmento que lo respalde")
        prohibidos.update(terminos_prohibidos(s.narrativa))
        if s.narrativa_generada_por_llm:
            fuentes = [
                s.valores_calculados, s.umbral, s.criterio,
                [contratos[i].model_dump() for i in s.contratos_ids if i in contratos],
                [fragmentos[c.fragmento_id].model_dump() for c in s.citas if c.fragmento_id in fragmentos],
            ]
            numeros += [f"{s.codigo}: {n}" for n in numeros_no_respaldados(s.narrativa, *fuentes)]

    r = reporte.resumen_ejecutivo
    if r and r.texto:
        for a in articulos_mencionados(r.texto):
            no_respaldados.append(f"resumen: artículo {a} sin fragmento que lo respalde")
        prohibidos.update(terminos_prohibidos(r.texto))
        if r.generado_por_llm:
            numeros += [f"resumen: {n}" for n in numeros_no_respaldados(r.texto, r.model_dump(exclude={"texto"}))]

    tasa = correctas / total if total else 1.0  # sin citas no hay nada inventado (ver limitación sin_norma)
    return Verificacion(
        total_citas=total,
        citas_correctas=correctas,
        tasa_citas_correctas=round(tasa, 4),
        citas_invalidas=invalidas,
        articulos_no_respaldados=no_respaldados,
        terminos_prohibidos=sorted(prohibidos),
        numeros_no_respaldados=numeros,
        aprobado=not invalidas and not no_respaldados and not prohibidos,
    )
