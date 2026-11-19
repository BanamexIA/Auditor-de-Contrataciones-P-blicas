from __future__ import annotations

import re

import sqlglot
from sqlglot import exp
from sqlglot.errors import OptimizeError
from sqlglot.optimizer.qualify import qualify


# Columns of the approved views, as defined in etl/sql/07_fase4b_transform.sql.
# tests/test_consulta_validator.py fails if the SQL and this list drift apart.
VIEW_COLUMNS = {
    "v_contratos_agente": (
        "codigo_contrato", "codigo_expediente", "fuente", "proveedor", "proveedor_normalizado",
        "titulo_contrato", "descripcion_contrato", "tipo_contratacion", "tipo_expediente",
        "tipo_procedimiento", "tipo_procedimiento_norm", "tipo_procedimiento_estado", "ley",
        "contract_type", "importe", "moneda", "fecha_inicio", "fecha_fin", "fecha_inicio_estado",
        "fecha_inicio_valida", "fecha_inicio_futura", "fecha_fin_antes_inicio", "institucion",
        "clave_institucion", "siglas_de_la_institucion", "tipo_de_institucion", "clave_ramo",
        "descripcion_ramo", "clave_de_la_uc", "nombre_de_la_uc", "numero_de_procedimiento",
        "caracter_del_procedimiento", "articulo_de_excepcion", "descripcion_excepcion",
        "_source_file",
    ),
    "v_coincidencias_69b_agente": (
        "codigo_contrato", "rfc_exacto", "nombre_normalizado_exacto", "nivel_confianza",
        "requiere_revision_humana", "proveedor", "rfc", "nombre_del_contribuyente", "created_at",
    ),
}
ALLOWED_TABLES = set(VIEW_COLUMNS)
# Only the names matter for checking columns; the types are not used.
_SCHEMA = {"clean": {view: {column: "TEXT" for column in columns} for view, columns in VIEW_COLUMNS.items()}}
_COLUMN_IN_ERROR = re.compile(r"Column '([^']+)' could not be resolved|Unknown column: (\S+)")
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


def add_missing_limit(query: str, max_rows: int = MAX_SQL_ROWS) -> tuple[str, bool]:
    """Adds LIMIT max_rows to a single SELECT that has none.

    Returns the query and whether a LIMIT was added. Anything else (invalid SQL,
    several statements, a statement that is not SELECT, or a LIMIT or FETCH that
    is already there, valid or not) comes back unchanged so validate_sql can
    reject it with its usual message.
    """
    try:
        statements = sqlglot.parse(query, read="postgres")
    except sqlglot.errors.ParseError:
        return query, False
    if len(statements) != 1 or not isinstance(statements[0], exp.Select):
        return query, False
    tree = statements[0]
    if tree.args.get("limit") is not None:
        return query, False
    return tree.limit(max_rows).sql(dialect="postgres"), True


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
    # Last, so every earlier rule keeps its own message (LIMIT ALL is not a column).
    _check_columns(tree, {table.name.lower() for table in tables})
    return tree.sql(dialect="postgres")


def _check_columns(tree: exp.Select, views_in_query: set[str]) -> None:
    """Rejects a column that does not exist in the view where the query looks for it.

    sqlglot resolves every column against VIEW_COLUMNS, following aliases and
    subqueries, so the model learns about a misplaced column before PostgreSQL
    runs the query.
    """
    try:
        qualify(tree.copy(), schema=_SCHEMA, dialect="postgres", validate_qualify_columns=True,
                quote_identifiers=False, identify=False)
    except OptimizeError as exc:
        match = _COLUMN_IN_ERROR.search(str(exc))
        if not match:
            raise SQLValidationError(f"La consulta usa columnas que no se pudieron resolver: {exc}") from exc
        column = (match.group(1) or match.group(2)).strip('"').lower()
        raise SQLValidationError(_column_message(column, views_in_query)) from exc
    except sqlglot.errors.SqlglotError as exc:
        raise SQLValidationError(f"No se pudieron revisar las columnas de la consulta: {exc}") from exc


def _column_message(column: str, views_in_query: set[str]) -> str:
    homes = [view for view, columns in VIEW_COLUMNS.items() if column in columns]
    if not homes:
        return f"La columna {column} no existe en las vistas aprobadas. Usa solo las columnas de la lista."
    if len(homes) > 1:
        return (
            f"La columna {column} está en las dos vistas; antepón el alias de la vista que quieres "
            f"(por ejemplo c.{column} o m.{column})."
        )
    home = homes[0]
    if home not in views_in_query:
        others = ", ".join(f"clean.{view}" for view in sorted(views_in_query))
        return (
            f"La columna {column} no está en {others}: está en clean.{home}. "
            f"Une las dos vistas con JOIN por codigo_contrato y usa la columna con el alias de clean.{home}."
        )
    return f"La columna {column} solo está en clean.{home}; úsala con el alias de esa vista."


def is_single_select(query: str) -> bool:
    try:
        statements = sqlglot.parse(query, read="postgres")
    except sqlglot.errors.ParseError:
        return False
    return len(statements) == 1 and isinstance(statements[0], exp.Select)
