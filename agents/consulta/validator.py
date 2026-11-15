from __future__ import annotations

import re

import sqlglot
from sqlglot import exp


ALLOWED_TABLES = {
    "v_contratos_agente",
    "v_coincidencias_69b_agente",
}
MAX_SQL_ROWS = 200
QUERY_TIMEOUT_MS = 60_000

# Statements that write data or change the schema, even when nested inside a SELECT.
WRITE_EXPRESSIONS = (
    exp.Insert,
    exp.Update,
    exp.Delete,
    exp.Merge,
    exp.Create,
    exp.Drop,
    exp.Alter,
    exp.TruncateTable,
    exp.Copy,
    exp.Grant,
    exp.Command,
    exp.Set,
    exp.Transaction,
    exp.Commit,
    exp.Rollback,
)


class SQLValidationError(ValueError):
    pass


def extract_sql(response: str) -> str:
    fences = re.findall(r"```(?:sql)?\s*(.*?)```", response, flags=re.IGNORECASE | re.DOTALL)
    if len(fences) > 1:
        raise SQLValidationError("La respuesta contiene más de un bloque de código.")
    candidate = fences[0] if fences else response
    candidate = candidate.strip()
    if candidate[:4].upper() == "SQL ":
        candidate = candidate[4:].lstrip()
    return candidate


def validate_sql(query: str, max_rows: int = MAX_SQL_ROWS) -> str:
    try:
        statements = sqlglot.parse(query, read="postgres")
    except sqlglot.errors.ParseError as exc:
        raise SQLValidationError(f"SQL no válido: {exc}") from exc
    if len(statements) != 1 or statements[0] is None:
        raise SQLValidationError("Se permite exactamente una sentencia SQL.")
    tree = statements[0]
    if not isinstance(tree, exp.Select):
        raise SQLValidationError("Solo se permiten consultas SELECT.")
    if tree.find(*WRITE_EXPRESSIONS):
        raise SQLValidationError("No se permiten operaciones que modifiquen datos o el esquema.")
    if tree.find(exp.With):
        raise SQLValidationError("No se permiten CTE (WITH); usa subconsultas.")
    if tree.find(exp.Into) or tree.find(exp.Lock):
        raise SQLValidationError("No se permiten INTO ni bloqueos de filas.")
    tables = list(tree.find_all(exp.Table))
    for table in tables:
        if table.db.lower() != "clean" or table.name.lower() not in ALLOWED_TABLES:
            raise SQLValidationError(
                f"Tabla no permitida: {table.sql(dialect='postgres')}."
            )
    if not tables:
        raise SQLValidationError("La consulta debe leer al menos una vista aprobada.")
    for function in tree.find_all(exp.Anonymous):
        raise SQLValidationError(f"No se permiten funciones SQL no reconocidas: {function.name}.")
    if tree.find(exp.GenerateSeries):
        raise SQLValidationError("No se permite generate_series.")
    limit = tree.args.get("limit")
    if (
        limit is None
        or not isinstance(limit.expression, exp.Literal)
        or limit.expression.is_string
    ):
        raise SQLValidationError("La consulta debe incluir un LIMIT entero explícito.")
    try:
        row_limit = int(limit.expression.this)
    except (TypeError, ValueError) as exc:
        raise SQLValidationError("El LIMIT debe ser un entero literal.") from exc
    if not 1 <= row_limit <= max_rows:
        raise SQLValidationError(f"El LIMIT debe estar entre 1 y {max_rows}.")
    return tree.sql(dialect="postgres")


def is_single_select(query: str) -> bool:
    try:
        statements = sqlglot.parse(query, read="postgres")
    except sqlglot.errors.ParseError:
        return False
    return len(statements) == 1 and isinstance(statements[0], exp.Select)
