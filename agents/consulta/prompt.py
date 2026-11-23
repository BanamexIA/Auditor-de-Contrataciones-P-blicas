from __future__ import annotations

import json
import re
from typing import Any, Sequence

from agents.consulta.agencies import uppercase_agency_literals
from agents.consulta.concepts import MISSING_CONCEPTS
from agents.consulta.providers import add_suffix_variants, normalize_provider_literals
from agents.consulta.validator import (
    MAX_SQL_ROWS,
    add_missing_limit,
    adds_amounts,
    add_order_tiebreaker,
    fix_alias_typos,
    validate_sql,
)


RESPONSE_TYPES = ("sql", "aclaracion", "sin_datos")
LIMIT_ADDED_NOTE = (
    f"La consulta no traía LIMIT; el sistema agregó LIMIT {MAX_SQL_ROWS}, el máximo permitido."
)


PROVIDER_NOTE_PREFIX = "El proveedor se buscó como "


def provider_note(name: str) -> str:
    """A5, mejora 12: says how the provider name was searched."""
    return f"{PROVIDER_NOTE_PREFIX}'{name}' en proveedor_normalizado, la forma normalizada del ETL."


SUFFIX_NOTE = (
    "El proveedor también se buscó con su tipo de sociedad al final (como S A DE C V), "
    "porque el ETL lo conserva en parte de los contratos."
)


CURRENCY_NOTE = (
    "El importe es el registrado en la moneda de cada contrato y no se convierte a pesos; "
    "por eso se suma por moneda."
)
AGENCY_NOTE_PREFIX = "La dependencia se buscó en mayúsculas, como está en la base: "


def agency_note(name: str) -> str:
    """A5, mejora 26: says that an agency name was searched in upper case."""
    return f"{AGENCY_NOTE_PREFIX}'{name}'."


def is_system_note(text: str) -> bool:
    """Notes written by code, which the coverage filter must keep even if a name contains "completo"."""
    return text in (LIMIT_ADDED_NOTE, SUFFIX_NOTE, CURRENCY_NOTE) or text.startswith(
        (PROVIDER_NOTE_PREFIX, AGENCY_NOTE_PREFIX)
    )

# Rules distilled from docs/capa_semantica.md; keep both in sync.
DATA_RULES = """Reglas de los datos:
- fuente = 'comprasmx' es ComprasMX 2026. fuente = 'historico' es CompraNet histórico, con inicios válidos de 2010 a 2024; 2010, 2023 y 2024 están incompletos. No hay contratos con inicio en 2025.
- institucion, nombre_de_la_uc, descripcion_ramo y articulo_de_excepcion solo existen en ComprasMX. En el histórico son nulos: eso no significa cero actividad.
- Un periodo se filtra con un rango semiabierto de fecha_inicio, por ejemplo fecha_inicio >= DATE '2024-01-01' AND fecha_inicio < DATE '2025-01-01'. Para agrupar por año usa EXTRACT(YEAR FROM fecha_inicio)::integer y filtra fecha_inicio_valida.
- Cada fila de clean.v_contratos_agente es un contrato: COUNT(*) cuenta contratos. Un expediente puede tener varios contratos: para contar expedientes usa COUNT(DISTINCT codigo_expediente).
- importe se suma por fuente y por moneda. Es importe registrado, no gasto pagado.
- «Nulo», «sin dato» o «sin registrar» es IS NULL, no cero: importe IS NULL es un contrato sin importe registrado e importe = 0 es un importe en cero. Si eliges una lectura que la pregunta no deja clara, dila en supuestos.
- tipo_procedimiento_norm es una clasificación preliminar con los valores adjudicacion_directa, invitacion_tres_personas, licitacion_publica, otro y sin_dato.
- Los porcentajes se calculan desde conteos, con NULLIF en el denominador. Nunca sumes ni promedies porcentajes.
- clean.v_coincidencias_69b_agente tiene una fila por contrato, no por empresa. Al unirla con clean.v_contratos_agente por codigo_contrato, cuenta COUNT(DISTINCT codigo_contrato). nivel_confianza 'alta' es RFC exacto y 'media' es solo nombre. La vista no tiene la situación del contribuyente: no la afirmes.
- Ordena los rankings por la métrica y después por el nombre."""

# Boolean columns of the approved views (etl/sql/04_clean.sql and 06_fase4b_schema.sql).
BOOLEAN_COLUMNS = (
    "fecha_inicio_valida", "fecha_inicio_futura", "fecha_fin_antes_inicio",
    "rfc_exacto", "nombre_normalizado_exacto", "requiere_revision_humana",
)

# A5, mejora 4: rules for the mistakes seen in the A4 measurement (2026-11-17) and in
# the quick check with the model on 2026-11-19 (booleans compared with 'S' or 'si').
SQL_RULES = f"""- Nunca uses SELECT * ni alias.*: escribe cada columna que devuelves.
- Si piden una lista de contratos («lista contratos…», «muestra contratos…», «¿qué contratos…?»), devuelve una fila por contrato con codigo_contrato, fuente y las columnas de cada dato que la pregunta menciona: si habla de fechas o importes, devuelve esas columnas. En una lista no uses GROUP BY ni funciones de agregación.
- {", ".join(BOOLEAN_COLUMNS)} son verdadero o falso: úsalas solas en WHERE (por ejemplo WHERE m.rfc_exacto) o con NOT, nunca comparadas con texto como 'S' o 'si'. fecha_inicio_estado es otra cosa: el estado de la fecha (valida, nula, fuera_de_rango o no_parseable); si preguntan por el estado de la fecha de inicio, usa esa columna.
- Para buscar un proveedor (la empresa o persona que vende), filtra clean.v_contratos_agente con proveedor_normalizado = '<nombre como lo dice la pregunta>'; el sistema lo pasa a la forma normalizada. nombre_de_la_uc es la unidad compradora, quien compra, no el proveedor. No unas la vista del 69-B ni agregues filtros que la pregunta no pide.
- Pon en WHERE todas las condiciones de la pregunta: fuente, periodo, tipo de procedimiento, institución, coincidencia con el 69-B. Si nombra un tipo de procedimiento, filtra tipo_procedimiento_norm con su valor. No agregues condiciones que la pregunta no pide, como un tope de fechas; la excepción es fecha_inicio_valida cuando usas fecha_inicio.
- "Preliminar" describe toda la clasificación de tipo_procedimiento_norm, no es un filtro: no filtres por tipo_procedimiento_estado salvo que la pregunta pida un estado de validación.
- rfc_exacto, nivel_confianza, requiere_revision_humana, rfc y nombre_del_contribuyente solo están en clean.v_coincidencias_69b_agente. Si la pregunta habla del 69-B y necesitas esas columnas junto con datos del contrato, une las vistas: FROM clean.v_contratos_agente AS c JOIN clean.v_coincidencias_69b_agente AS m ON m.codigo_contrato = c.codigo_contrato. Si no habla del 69-B, no las unas."""

# A5, mejora 5: the same list the agent checks in code (agents/consulta/concepts.py).
MISSING_CONCEPTS_TEXT = "; ".join(concept for _, concept in MISSING_CONCEPTS)

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
    {
        # A5, mejora 12: a fictitious company; on 2026-11-19 the model searched companies in nombre_de_la_uc.
        "pregunta": "¿Cuántos contratos de licitación pública ganó la empresa Constructora Ejemplo del Valle en ComprasMX?",
        "respuesta": {
            "tipo": "sql",
            "sql": (
                "SELECT COUNT(*) AS contratos FROM clean.v_contratos_agente WHERE fuente = 'comprasmx' "
                "AND tipo_procedimiento_norm = 'licitacion_publica' "
                "AND proveedor_normalizado = 'CONSTRUCTORA EJEMPLO DEL VALLE' LIMIT 1"
            ),
            "filtros": ["fuente: ComprasMX", "procedimiento: licitación pública", "proveedor: Constructora Ejemplo del Valle"],
            "supuestos": [],
        },
    },
    {
        "pregunta": "¿Qué proveedores fueron sancionados?",
        "respuesta": {
            "tipo": "sin_datos",
            "motivo": "Las fuentes no registran sanciones ni inhabilitaciones. El listado 69-B es una presunción fiscal, no una sanción.",
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
- sql: la pregunta se puede responder con las vistas sin adivinar.
- aclaracion: falta elegir la métrica, el periodo o la fuente, y elegir mal cambiaría la respuesta. No escribas SQL.
- sin_datos: el periodo, el campo o el concepto no existe en las fuentes. No escribas SQL ni estimes.
- Las fuentes no registran: {MISSING_CONCEPTS_TEXT}. Si la pregunta trata de uno de ellos, responde sin_datos y no lo sustituyas con otra columna parecida, como una fecha o una bandera de calidad.

En supuestos anota solo cómo interpretaste la pregunta, por ejemplo qué métrica usaste. No escribas nada sobre años o periodos completos o incompletos ni sobre la cobertura de las fuentes: eso lo agrega el sistema.

Reglas del SQL:
- Una sola sentencia SELECT. Solo puedes leer clean.v_contratos_agente y clean.v_coincidencias_69b_agente, siempre con el esquema clean.
- Incluye LIMIT con un entero entre 1 y {MAX_SQL_ROWS}. Usa LIMIT {MAX_SQL_ROWS} salvo que la pregunta pida un número de filas (por ejemplo «los 10 más…» o «hasta 20»): el LIMIT es un tope de seguridad, no un recorte del resultado.
- No uses WITH, UNION, RANK, DENSE_RANK, NTILE ni unaccent. Si necesitas pasos intermedios, usa subconsultas.
- Usa solo las columnas de la lista de abajo.
{SQL_RULES}

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


def proposed_sql(text: str) -> str | None:
    """The "sql" field of a model answer, if it can be read; used to record failed attempts."""
    try:
        value = _load_json_object(text).get("sql")
    except ResponseFormatError:
        return None
    return value.strip() if isinstance(value, str) and value.strip() else None


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
        sql, _ = fix_alias_typos(sql)
        sql, _ = add_order_tiebreaker(sql)
        sql, providers = normalize_provider_literals(sql)
        sql, searched = add_suffix_variants(sql)
        sql, agencies = uppercase_agency_literals(sql)
        supuestos = _text_list(payload, "supuestos")
        if limit_added:
            supuestos.append(LIMIT_ADDED_NOTE)
        supuestos.extend(provider_note(name) for name in dict.fromkeys(providers))
        supuestos.extend(agency_note(name) for name in agencies)
        if searched:
            supuestos.append(SUFFIX_NOTE)
        safe_sql = validate_sql(sql)
        if adds_amounts(safe_sql):
            # A5, mejora 25: HU-01 asks to say that currencies are kept apart.
            supuestos.append(CURRENCY_NOTE)
        return {
            "tipo": "sql",
            "sql": safe_sql,
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
