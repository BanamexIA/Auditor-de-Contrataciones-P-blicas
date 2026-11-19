from __future__ import annotations

import json
import re
from typing import Any, Sequence

from agents.consulta.validator import MAX_SQL_ROWS, add_missing_limit, validate_sql


RESPONSE_TYPES = ("sql", "aclaracion", "sin_datos")
LIMIT_ADDED_NOTE = (
    f"La consulta no traía LIMIT; el sistema agregó LIMIT {MAX_SQL_ROWS}, el máximo permitido."
)

# Rules distilled from docs/capa_semantica.md; keep both in sync.
DATA_RULES = """Reglas de los datos:
- fuente = 'comprasmx' es ComprasMX 2026. fuente = 'historico' es CompraNet histórico, con inicios válidos de 2010 a 2024; 2010, 2023 y 2024 están incompletos. No hay contratos con inicio en 2025.
- institucion, nombre_de_la_uc, descripcion_ramo y articulo_de_excepcion solo existen en ComprasMX. En el histórico son nulos: eso no significa cero actividad.
- Un periodo se filtra con un rango semiabierto de fecha_inicio, por ejemplo fecha_inicio >= DATE '2024-01-01' AND fecha_inicio < DATE '2025-01-01'. Para agrupar por año usa EXTRACT(YEAR FROM fecha_inicio)::integer y filtra fecha_inicio_valida.
- Cada fila de clean.v_contratos_agente es un registro de contrato: cuenta con COUNT(*).
- importe se suma por fuente y por moneda. Es importe registrado, no gasto pagado.
- tipo_procedimiento_norm es una clasificación preliminar.
- Los porcentajes se calculan desde conteos, con NULLIF en el denominador. Nunca sumes ni promedies porcentajes.
- clean.v_coincidencias_69b_agente tiene una fila por contrato, no por empresa. Al unirla con clean.v_contratos_agente por codigo_contrato, cuenta COUNT(DISTINCT codigo_contrato). nivel_confianza 'alta' es RFC exacto y 'media' es solo nombre. La vista no tiene la situación del contribuyente: no la afirmes.
- Ordena los rankings por la métrica y después por el nombre."""

BUILT_IN_EXAMPLES = (
    {
        "pregunta": "¿Cuál es el proveedor más grande?",
        "respuesta": {
            "tipo": "aclaracion",
            "pregunta": "¿Cómo quieres medir el tamaño del proveedor y en qué fuente?",
            "opciones": [
                "Por número de contratos en ComprasMX 2026",
                "Por importe registrado en ComprasMX 2026, por moneda",
                "Por número de contratos en el histórico, en un año que indiques",
            ],
        },
    },
    {
        "pregunta": "¿Qué contratos se pagaron con retraso?",
        "respuesta": {
            "tipo": "sin_datos",
            "motivo": "Las fuentes no registran fechas de pago, y el importe no es gasto pagado.",
        },
    },
)


class ResponseFormatError(ValueError):
    pass


def _compact(sql: str) -> str:
    return " ".join(sql.split())


def _format_examples(examples: list[dict[str, Any]]) -> str:
    rendered = [
        {
            "pregunta": item["pregunta"],
            "respuesta": {"tipo": "sql", "sql": _compact(item["sql"]), "filtros": [], "supuestos": []},
        }
        for item in examples
    ]
    rendered.extend(BUILT_IN_EXAMPLES)
    return "\n\n".join(
        f"Pregunta: {item['pregunta']}\nRespuesta: {json.dumps(item['respuesta'], ensure_ascii=False)}"
        for item in rendered
    )


def build_system_prompt(schema: str, examples: list[dict[str, Any]]) -> str:
    return f"""Eres el Agente Consulta de un sistema de auditoría de contrataciones públicas.
Traduces la pregunta del auditor a una consulta SQL de PostgreSQL de solo lectura.
Tus resultados son datos para revisión humana: nunca afirmes fraude, corrupción ni responsabilidad legal.

Responde solo con un objeto JSON, sin texto adicional, con una de estas formas:
{{"tipo": "sql", "sql": "<una consulta SELECT>", "filtros": ["<filtro en palabras>"], "supuestos": ["<supuesto>"]}}
{{"tipo": "aclaracion", "pregunta": "<qué falta saber>", "opciones": ["<opción>", "<opción>"]}}
{{"tipo": "sin_datos", "motivo": "<por qué las fuentes no tienen ese dato>"}}

Cuándo usar cada tipo:
- sql: la pregunta se puede responder con las vistas sin adivinar. Si el periodo es 2010, 2023 o 2024, anota en supuestos que el año está incompleto.
- aclaracion: falta elegir la métrica, el periodo o la fuente, y elegir mal cambiaría la respuesta. No escribas SQL.
- sin_datos: el periodo o el campo no existe en las fuentes. No escribas SQL ni estimes.

Reglas del SQL:
- Una sola sentencia SELECT. Solo puedes leer clean.v_contratos_agente y clean.v_coincidencias_69b_agente, siempre con el esquema clean.
- Incluye LIMIT con un entero entre 1 y {MAX_SQL_ROWS}.
- No uses WITH, UNION, RANK, DENSE_RANK, NTILE ni unaccent. Si necesitas pasos intermedios, usa subconsultas.
- Usa solo las columnas de la lista de abajo.

{DATA_RULES}

Vistas y comentarios de PostgreSQL:
{schema}

Ejemplos:
{_format_examples(examples)}
"""


def build_user_prompt(question: str, clarifications: Sequence[tuple[str, str]] = ()) -> str:
    parts = [f"Pregunta del auditor: {question.strip()}"]
    for asked, answer in clarifications:
        parts.append(f"Aclaración pedida: {asked.strip()}\nRespuesta del auditor: {answer.strip()}")
    if clarifications:
        parts.append("Usa estas aclaraciones y no vuelvas a preguntar lo mismo.")
    return "\n\n".join(parts)


def _load_json_object(text: str) -> dict[str, Any]:
    fences = re.findall(r"```(?:json)?\s*(.*?)```", text, flags=re.IGNORECASE | re.DOTALL)
    if len(fences) > 1:
        raise ResponseFormatError("La respuesta contiene más de un bloque de código.")
    candidate = fences[0] if fences else text
    start, end = candidate.find("{"), candidate.rfind("}")
    if start == -1 or end < start:
        raise ResponseFormatError("La respuesta no contiene un objeto JSON.")
    try:
        payload = json.loads(candidate[start : end + 1])
    except json.JSONDecodeError as exc:
        raise ResponseFormatError(f"La respuesta no es un JSON válido: {exc.msg}.") from exc
    if not isinstance(payload, dict):
        raise ResponseFormatError("La respuesta debe ser un objeto JSON.")
    return payload


def _required_text(payload: dict[str, Any], key: str) -> str:
    value = payload.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ResponseFormatError(f"Falta el campo de texto '{key}'.")
    return value.strip()


def _text_list(payload: dict[str, Any], key: str, minimum: int = 0) -> list[str]:
    value = payload.get(key, [])
    if not isinstance(value, list) or not all(isinstance(item, str) and item.strip() for item in value):
        raise ResponseFormatError(f"'{key}' debe ser una lista de textos.")
    if len(value) < minimum:
        raise ResponseFormatError(f"'{key}' debe tener al menos {minimum} elementos.")
    return [item.strip() for item in value]


def parse_response(text: str) -> dict[str, Any]:
    """Validates the model output; raises ResponseFormatError or SQLValidationError."""
    payload = _load_json_object(text)
    response_type = payload.get("tipo")
    if response_type not in RESPONSE_TYPES:
        raise ResponseFormatError(
            f"'tipo' debe ser uno de {', '.join(RESPONSE_TYPES)}; se recibió {response_type!r}."
        )
    if response_type == "sql":
        sql, limit_added = add_missing_limit(_required_text(payload, "sql"))
        supuestos = _text_list(payload, "supuestos")
        if limit_added:
            supuestos.append(LIMIT_ADDED_NOTE)
        return {
            "tipo": "sql",
            "sql": validate_sql(sql),
            "filtros": _text_list(payload, "filtros"),
            "supuestos": supuestos,
        }
    if response_type == "aclaracion":
        return {
            "tipo": "aclaracion",
            "pregunta": _required_text(payload, "pregunta"),
            "opciones": _text_list(payload, "opciones", minimum=2),
        }
    return {"tipo": "sin_datos", "motivo": _required_text(payload, "motivo")}
