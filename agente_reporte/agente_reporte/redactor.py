"""Redacción con el modelo local (Ollama).

El LLM SOLO redacta narrativa a partir de resultados ya calculados. No calcula, no define umbrales
y no inventa normas. Cada salida se valida (esquema + citas + lenguaje + cifras); si falla, se
regenera UNA vez; si vuelve a fallar, se usa un texto determinista de respaldo.
"""
from __future__ import annotations

import json
import logging
import os
from typing import Any, Callable, Optional, Type, TypeVar

from pydantic import BaseModel, ValidationError

from .schemas import (
    Contrato, FragmentoNorma, NarrativaSenal, ResumenEjecutivoLLM, Senal,
)
from .verificador import (
    articulos_mencionados, normalizar_articulo, numeros_no_respaldados, terminos_prohibidos,
)

log = logging.getLogger(__name__)

MAX_REGENERACIONES = 1
LLMFn = Callable[[list[dict], dict], str]  # (mensajes, json_schema) -> texto JSON
T = TypeVar("T", bound=BaseModel)

SYSTEM_PROMPT = """Eres un redactor técnico para auditores de contrataciones públicas en México.
Escribes en español neutro, claro y breve.

Reglas obligatorias:
1. Usa EXCLUSIVAMENTE los datos del bloque DATOS. No agregues cifras, nombres, fechas ni normas que no estén ahí.
   No hagas cálculos ni redondees: si mencionas una cifra, cópiala tal cual aparece.
2. Describe señales de riesgo que requieren revisión humana. Nunca afirmes ni insinúes fraude, corrupción,
   culpa, ilegalidad ni responsabilidad. Usa expresiones como "se detectó una señal" o "podría requerir revisión".
3. Cita normas únicamente con los fragmento_id del bloque NORMAS. Si NORMAS está vacío, no menciones ningún
   artículo y deja fragmento_ids vacío. Si mencionas un artículo, su fragmento_id debe estar en fragmento_ids.
4. Si hay datos faltantes o confianza baja, dilo explícitamente.
5. Responde únicamente con JSON que cumpla el esquema solicitado."""


# --------------------------------------------------------------------------- backend Ollama
def llm_ollama(modelo: Optional[str] = None, host: Optional[str] = None, temperature: float = 0.1) -> LLMFn:
    """Devuelve una función que llama a Ollama forzando salida estructurada con JSON Schema."""
    import ollama  # import diferido: las pruebas no lo necesitan

    modelo = modelo or os.getenv("OLLAMA_MODEL", "qwen2.5:7b-instruct")
    client = ollama.Client(host=host or os.getenv("OLLAMA_HOST", "http://localhost:11434"))

    def _fn(messages: list[dict], schema: dict) -> str:
        r = client.chat(model=modelo, messages=messages, format=schema, options={"temperature": temperature})
        return r["message"]["content"]

    _fn.modelo = modelo  # type: ignore[attr-defined]
    return _fn


def _resumen_errores(exc: ValidationError) -> str:
    return "; ".join(f"{'.'.join(map(str, e['loc']))}: {e['msg']}" for e in exc.errors())


# --------------------------------------------------------------------------- redactor
class Redactor:
    def __init__(self, llm_fn: Optional[LLMFn] = None, modelo: Optional[str] = None):
        """llm_fn=None => modo sin LLM (todo se resuelve con texto determinista)."""
        self.llm_fn = llm_fn
        self.modelo = modelo or getattr(llm_fn, "modelo", None) or ("sin-llm" if llm_fn is None else "desconocido")
        self.eventos: list[dict[str, Any]] = []

    @classmethod
    def desde_ollama(cls, modelo: Optional[str] = None) -> "Redactor":
        fn = llm_ollama(modelo)
        return cls(fn, getattr(fn, "modelo", modelo))

    # ------------------------------------------------------------------ núcleo: generar + validar + 1 reintento
    def _generar(
        self, etiqueta: str, mensajes: list[dict], modelo_salida: Type[T], validar: Callable[[T], list[str]]
    ) -> Optional[T]:
        if self.llm_fn is None:
            return None
        mensajes = list(mensajes)
        schema = modelo_salida.model_json_schema()
        for intento in range(1 + MAX_REGENERACIONES):
            try:
                crudo = self.llm_fn(mensajes, schema)
            except Exception as exc:  # Ollama caído, timeout, etc.
                log.error("Fallo del LLM en %s: %s", etiqueta, exc)
                self.eventos.append({"evento": "error_llm", "objetivo": etiqueta, "detalle": str(exc)})
                return None
            try:
                obj = modelo_salida.model_validate_json(crudo)
                errores = validar(obj)
            except ValidationError as exc:
                obj, errores = None, [f"JSON inválido o fuera de esquema: {_resumen_errores(exc)}"]
            if not errores:
                self.eventos.append({"evento": "narrativa_ok", "objetivo": etiqueta, "intento": intento + 1})
                return obj
            self.eventos.append({"evento": "validacion_fallida", "objetivo": etiqueta,
                                 "intento": intento + 1, "errores": errores})
            mensajes += [
                {"role": "assistant", "content": crudo},
                {"role": "user", "content": "Tu respuesta no es válida por: " + " | ".join(errores)
                 + ". Corrígela y responde solo con el JSON."},
            ]
        self.eventos.append({"evento": "usa_respaldo", "objetivo": etiqueta})
        return None

    # ------------------------------------------------------------------ señales
    def redactar_senal(
        self, senal: Senal, contratos: list[Contrato], fragmentos: list[FragmentoNorma]
    ) -> Optional[NarrativaSenal]:
        permitidos = {f.fragmento_id: f for f in fragmentos}
        fuentes = [senal.model_dump(), [c.model_dump() for c in contratos], [f.model_dump() for f in fragmentos]]

        def validar(n: NarrativaSenal) -> list[str]:
            errs: list[str] = []
            desconocidos = [i for i in n.fragmento_ids if i not in permitidos]
            if desconocidos:
                errs.append(f"fragmento_ids no permitidos para esta señal: {desconocidos}")
            citados = {normalizar_articulo(permitidos[i].articulo) for i in n.fragmento_ids if i in permitidos}
            ajenos = [a for a in articulos_mencionados(n.narrativa) if a not in citados]
            if ajenos:
                errs.append(f"menciona artículos sin fragmento citado: {ajenos}")
            if (p := terminos_prohibidos(n.narrativa)):
                errs.append(f"usa lenguaje de culpa: {p}")
            if (x := numeros_no_respaldados(n.narrativa, *fuentes)):
                errs.append(f"cifras que no están en los datos: {x}")
            return errs

        datos = {
            "senal": senal.model_dump(exclude={"estado"}),
            "contratos": [c.model_dump() for c in contratos],
        }
        normas = [f.model_dump(include={"fragmento_id", "norma", "articulo", "version", "texto"}) for f in fragmentos]
        usuario = (
            f"DATOS:\n{json.dumps(datos, ensure_ascii=False, indent=2)}\n\n"
            f"NORMAS:\n{json.dumps(normas, ensure_ascii=False, indent=2)}\n\n"
            "Redacta la narrativa de esta señal (máximo 120 palabras) y lista en fragmento_ids "
            "las normas que cites."
        )
        n = self._generar(
            f"senal:{senal.codigo}",
            [{"role": "system", "content": SYSTEM_PROMPT}, {"role": "user", "content": usuario}],
            NarrativaSenal, validar,
        )
        if n:
            n.fragmento_ids = list(dict.fromkeys(n.fragmento_ids))  # sin duplicados, conserva orden
        return n

    @staticmethod
    def narrativa_respaldo(senal: Senal) -> str:
        return (
            f"Se detectó la señal «{senal.nombre}»: {senal.criterio} (umbral: {senal.umbral}). "
            "La redacción automática no estuvo disponible; consulte los valores calculados y las normas "
            "listadas. Esta señal requiere revisión humana."
        )

    # ------------------------------------------------------------------ resumen ejecutivo (HU-09)
    def redactar_resumen(self, datos: dict[str, Any]) -> Optional[str]:
        def validar(r: ResumenEjecutivoLLM) -> list[str]:
            errs: list[str] = []
            if (a := articulos_mencionados(r.texto)):
                errs.append(f"no debe citar artículos en el resumen: {a}")
            if (p := terminos_prohibidos(r.texto)):
                errs.append(f"usa lenguaje de culpa: {p}")
            if (x := numeros_no_respaldados(r.texto, datos)):
                errs.append(f"cifras que no están en los datos: {x}")
            return errs

        usuario = (
            f"DATOS:\n{json.dumps(datos, ensure_ascii=False, indent=2)}\n\nNORMAS:\n[]\n\n"
            "Redacta un resumen ejecutivo de dos párrafos breves para directivos sobre concentración de "
            "proveedores y patrones de adjudicación. Presenta todo como señales que requieren revisión. "
            "Menciona las limitaciones (registros excluidos, señales de baja confianza) si los datos las indican."
        )
        r = self._generar(
            "resumen_ejecutivo",
            [{"role": "system", "content": SYSTEM_PROMPT}, {"role": "user", "content": usuario}],
            ResumenEjecutivoLLM, validar,
        )
        return r.texto if r else None

    @staticmethod
    def resumen_respaldo(datos: dict[str, Any]) -> str:
        partes = []
        top = sorted(datos.get("concentracion", []), key=lambda c: c["monto_total"], reverse=True)[:3]
        for c in top:
            partes.append(
                f"{c['proveedor']} concentra {c['num_contratos']} contrato(s) y "
                f"{c['porcentaje_monto']:.1f}% del monto analizado."
            )
        cuerpo = " ".join(partes) if partes else "No hay datos de concentración para esta consulta."
        return (
            f"{cuerpo} Estos datos son señales que requieren revisión humana, no determinaciones. "
            f"Registros excluidos: {datos.get('num_excluidos', 0)}; "
            f"señales de baja confianza: {datos.get('num_senales_confianza_baja', 0)}."
        )
