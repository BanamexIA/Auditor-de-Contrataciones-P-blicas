"""Piezas que unen a los agentes reales con el backend en el guion de demo.

- ClienteConBitacora: cualquier llamada al modelo pasa por ``llamar_llm`` (bitácora + telemetría).
- llm_fn_redactor: la función (mensajes, schema) -> texto que espera el Redactor de Reportes.
- entrada_reporte: convierte el JSON de Detección (Agente 2) en la EntradaReporte (Agente 3).

El contrato n.º 1 ("Señal de riesgo") aún no está cerrado; las diferencias que corrige
``entrada_reporte`` están listadas ahí para acordarlas con Mario y Michelle.
"""

from __future__ import annotations

import json
import re
from typing import Any

from backend.casos.bitacora import llamar_llm

COLUMNAS_ID = ("codigo_contrato", "contrato_id", "id")


class ClienteConBitacora:
    """Envuelve un LLMClient: cada ``generate`` queda registrado en el caso."""

    def __init__(self, cliente, registrar, caso_id: str, agente: str):
        self._cliente, self._registrar = cliente, registrar
        self.caso_id, self.agente = caso_id, agente
        self.model = cliente.model
        self.base_url = getattr(cliente, "base_url", None)
        self.llamadas: list[Any] = []

    def generate(self, system: str, prompt: str, temperature: float = 0.0):
        r = llamar_llm(self._registrar, self.caso_id, self.agente, self._cliente,
                       system, prompt, temperature)
        self.llamadas.append(r)
        return r


def _json_de(texto: str) -> str:
    """Quita cercas ```json y texto alrededor: deja el primer objeto JSON."""
    inicio, fin = texto.find("{"), texto.rfind("}")
    return texto[inicio:fin + 1] if 0 <= inicio < fin else texto


def llm_fn_redactor(cliente: ClienteConBitacora, temperatura: float = 0.1):
    """Adapta el cliente al Redactor. El esquema va en el prompt (OllamaClient no envía ``format``);
    si la respuesta no cumple, el Redactor reintenta una vez y luego usa su texto de respaldo."""

    def _fn(mensajes: list[dict], schema: dict) -> str:
        system = "\n\n".join(m["content"] for m in mensajes if m["role"] == "system")
        conversacion = "\n\n".join(
            f"{'RESPUESTA ANTERIOR' if m['role'] == 'assistant' else 'USUARIO'}:\n{m['content']}"
            for m in mensajes if m["role"] != "system")
        prompt = (f"{conversacion}\n\nResponde SOLO con un objeto JSON que cumpla este JSON Schema:\n"
                  f"{json.dumps(schema, ensure_ascii=False)}")
        return _json_de(cliente.generate(system, prompt, temperatura).text)

    _fn.modelo = cliente.model  # type: ignore[attr-defined]
    return _fn


def ids_de_contratos(filas: list[dict]) -> list[str]:
    """Ids de contrato que devolvió el Agente Consulta (si su SQL los incluye)."""
    for columna in COLUMNAS_ID:
        ids = [str(f[columna]) for f in filas if f.get(columna)]
        if ids:
            return list(dict.fromkeys(ids))
    return []


def _texto(valor: Any) -> str:
    if valor is None:
        return "sin umbral"
    return valor if isinstance(valor, str) else json.dumps(valor, ensure_ascii=False, default=str)


def entrada_reporte(deteccion: dict) -> dict:
    """JSON de Detección -> EntradaReporte. Diferencias que corrige:

    - señal ``estado``: "evaluada" -> "activa"; ``umbral`` objeto -> texto; ``confianza`` nula -> "baja".
    - contrato ``moneda`` nula -> "MXN" (se declara en las limitaciones del caso, no se inventa monto).
    - normas sin ley, artículo, versión o texto se descartan (el verificador no podría citarlas).
    - concentración sin porcentaje (sin montos válidos) se omite.
    """
    contratos = [{
        "id": str(c["id"]), "proveedor": c.get("proveedor"), "rfc": c.get("rfc"),
        "monto": float(c["monto"]) if c.get("monto") is not None else None,
        "moneda": c.get("moneda") or "MXN", "dependencia": c.get("dependencia"),
        "tipo_procedimiento": c.get("tipo_procedimiento"), "fecha": c.get("fecha"),
        "fuente": c.get("fuente"),
    } for c in deteccion["contratos"]]
    senales = [{
        "codigo": s["codigo"], "nombre": s["nombre"], "criterio": s["criterio"],
        "umbral": _texto(s.get("umbral")),
        "valores_calculados": s.get("valores_calculados") or {},
        "contratos_ids": [str(i) for i in s.get("contratos_ids", [])],
        "confianza": s.get("confianza") or "baja",
        "estado": "activa" if s["estado"] == "evaluada" else "no_evaluable",
        "campos_faltantes": s.get("campos_faltantes") or [],
    } for s in deteccion["senales"]]
    normas = [{
        "fragmento_id": n["fragmento_id"], "senal_codigo": n.get("senal_codigo"),
        "norma": n["norma"], "articulo": str(n["articulo"]), "version": str(n["version"]),
        "vigencia": n.get("vigencia"), "texto": n["texto"],
    } for n in deteccion["normas_recuperadas"]
        if all(n.get(k) for k in ("norma", "articulo", "version", "texto"))]
    concentracion = [{
        "rfc": c.get("rfc"), "proveedor": c["proveedor"], "num_contratos": c["num_contratos"],
        "monto_total": c["monto_total"], "porcentaje_monto": c["porcentaje_monto"],
        "porcentaje_adjudicaciones_directas": c.get("porcentaje_adjudicaciones_directas"),
    } for c in deteccion["concentracion"] if c.get("porcentaje_monto") is not None][:10]
    return {
        "consulta_id": deteccion["consulta_id"],
        "version_reglas": deteccion["version_reglas"],
        "contratos": contratos,
        "senales": senales,
        "normas_recuperadas": normas,
        "excluidos": [{"contrato_id": str(e["contrato_id"]), "motivo": e["motivo"]}
                      for e in deteccion["excluidos"]],
        "contradicciones": deteccion["contradicciones"],
        "concentracion": concentracion,
        "patrones_adjudicacion": deteccion["patrones_adjudicacion"],
    }


def senales_para_backend(deteccion: dict) -> list[dict]:
    """Señales de Detección en el formato de ``audit.senales`` (tipo + datos)."""
    return [{"tipo": re.sub(r"\W+", "_", s["codigo"].lower()),
             "datos": json.loads(json.dumps(s, default=str))} for s in deteccion["senales"]]
