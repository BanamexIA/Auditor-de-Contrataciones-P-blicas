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
# Values of the categorical columns, from the comments in etl/sql/07 and the data
# (2026-11-20). A text outside the list returns nothing, so the validator rejects it.
CATEGORY_VALUES = {
    "fuente": ("comprasmx", "historico"),
    "tipo_procedimiento_norm": (
        "adjudicacion_directa", "invitacion_tres_personas", "licitacion_publica", "otro", "sin_dato",
    ),
    "fecha_inicio_estado": ("valida", "nula", "fuera_de_rango", "no_parseable"),
    "nivel_confianza": ("alta", "media"),
}
_NAME_HINT = (
    " Si es el nombre de un proveedor, búscalo en proveedor_normalizado; si es una institución, "
    "en institucion."
)
CATEGORY_HINTS = {"fuente": _NAME_HINT, "tipo_procedimiento_norm": _NAME_HINT}
# COUNT(*) over the views counts contracts. A column alias that names another unit
# says the model meant that unit (A5, mejora 21: on 2026-11-23, n02 of casos_nuevos
# labeled 2,356,609 contracts as "expedientes"; there are 1,768,189).
COUNT_UNITS = (
    ("expedientes", re.compile(r"expedientes?"), "codigo_expediente"),
    ("proveedores", re.compile(r"proveedor(es)?"), "proveedor_normalizado"),
    ("instituciones", re.compile(r"instituci[oó]n(es)?"), "institucion"),
)
# Aliases that still count contracts: contratos_por_expediente, sin_proveedor, con_expediente.
_CONTRACT_WORDS = re.compile(r"contratos?|registros?|filas?|sin|con")

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


TIEBREAK_COLUMN = "codigo_contrato"


def add_order_tiebreaker(query: str) -> tuple[str, bool]:
    """Ends ORDER BY with codigo_contrato in a SELECT that also has LIMIT.

    Rows that tie on the ORDER BY come back in any order, so the LIMIT can keep
    different contracts each time the same SQL runs (q08 in A5). Only applies
    when codigo_contrato is a selected column, is not already in the ORDER BY,
    and the query has no aggregate unless it groups by codigo_contrato. Returns
    the query and whether it changed; anything else comes back unchanged.
    """
    try:
        statements = sqlglot.parse(query, read="postgres")
    except sqlglot.errors.ParseError:
        return query, False
    if len(statements) != 1 or not isinstance(statements[0], exp.Select):
        return query, False
    tree = statements[0]
    order = tree.args.get("order")
    distinct = tree.args.get("distinct")
    if order is None or tree.args.get("limit") is None:
        return query, False
    if distinct is not None and distinct.args.get("on") is not None:
        return query, False
    key = _tiebreak_key(tree)
    if key is None or _orders_by(order, *key):
        return query, False
    group = tree.args.get("group")
    if group is not None:
        if not any(_is_tiebreak_column(item) for item in group.expressions):
            return query, False
    elif any(item.find(exp.AggFunc) for item in tree.expressions):
        return query, False
    tree.order_by(key[1], append=True, copy=False)
    return tree.sql(dialect="postgres"), True


def _is_tiebreak_column(node: exp.Expression) -> bool:
    return isinstance(node, exp.Column) and node.name == TIEBREAK_COLUMN


def _tiebreak_key(tree: exp.Select) -> tuple[int, exp.Expression] | None:
    """Position and ORDER BY expression of the first selected codigo_contrato."""
    for position, item in enumerate(tree.expressions, start=1):
        if _is_tiebreak_column(item):
            return position, item.copy()
        if isinstance(item, exp.Alias) and _is_tiebreak_column(item.this):
            return position, exp.column(item.alias)
    return None


def _orders_by(order: exp.Order, position: int, expression: exp.Expression) -> bool:
    """Whether the ORDER BY already uses codigo_contrato, its alias or its position."""
    names = {TIEBREAK_COLUMN, expression.name}
    for ordered in order.expressions:
        target = ordered.this
        if isinstance(target, exp.Literal) and not target.is_string and target.name == str(position):
            return True
        if any(column.name in names for column in target.find_all(exp.Column)):
            return True
    return False


MAX_ALIAS_FIXES = 5


def fix_alias_typos(query: str) -> tuple[str, list[str]]:
    """Rewrites alias_columna as alias.columna when only that reading resolves (A5, mejora 15).

    On 2026-11-20 q08 wrote c_fuente in its first attempt and, told to write
    c.fuente, made a different mistake in the retry, so it ran out of attempts.
    Only a column that sqlglot cannot resolve is touched, and only when its
    prefix is the alias of an approved view that has the rest of the name, so a
    name defined in the query (such as COUNT(*) AS c_total) stays as it is.
    Returns the query and the fixes made ("c_fuente -> c.fuente").
    """
    try:
        statements = sqlglot.parse(query, read="postgres")
    except sqlglot.errors.ParseError:
        return query, []
    if len(statements) != 1 or not isinstance(statements[0], exp.Select):
        return query, []
    tree = statements[0]
    fixes: list[str] = []
    for _ in range(MAX_ALIAS_FIXES):
        typo = _unresolved_alias_typo(tree)
        if typo is None:
            break
        column, alias, rest = typo
        for node in list(tree.find_all(exp.Column)):
            if not node.table and node.name.lower() == column:
                node.replace(exp.column(rest, table=alias))
        fixes.append(f"{column} -> {alias}.{rest}")
    if not fixes:
        return query, []
    return tree.sql(dialect="postgres"), fixes


def _unresolved_alias_typo(tree: exp.Select) -> tuple[str, str, str] | None:
    try:
        qualify(tree.copy(), schema=_SCHEMA, dialect="postgres", validate_qualify_columns=True,
                quote_identifiers=False, identify=False)
    except OptimizeError as exc:
        match = _COLUMN_IN_ERROR.search(str(exc))
        if not match:
            return None
        name = (match.group(1) or match.group(2)).replace('"', "").lower()
        if "." in name:
            return None
        return _alias_typo(name, tree)
    except sqlglot.errors.SqlglotError:
        return None
    return None


def _alias_typo(column: str, tree: exp.Expression) -> tuple[str, str, str] | None:
    """(column, alias, rest) when column is alias_rest and rest is a column of that alias's view."""
    if "_" not in column:
        return None
    aliases = {node.alias_or_name.lower(): node.name.lower() for node in tree.find_all(exp.Table)}
    prefix, _, rest = column.partition("_")
    view = aliases.get(prefix)
    if view and rest in VIEW_COLUMNS.get(view, ()):
        return column, prefix, rest
    return None


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
    _check_values(tree)
    _check_count_units(tree)
    return tree.sql(dialect="postgres")


def _check_count_units(tree: exp.Select) -> None:
    """Rejects COUNT(*) named as expedientes, proveedores or instituciones (A5, mejora 21).

    COUNT(*) over a subquery is left alone: it may count rows that are already
    distinct, as in SELECT COUNT(*) AS proveedores FROM (SELECT DISTINCT ...) AS t.
    """
    for alias in tree.find_all(exp.Alias):
        count = alias.this
        if not (isinstance(count, exp.Count) and isinstance(count.this, exp.Star)):
            continue
        select = alias.find_ancestor(exp.Select)
        source = select.args.get("from") if select is not None else None
        if source is None or not isinstance(source.this, exp.Table):
            continue
        words = alias.alias.lower().split("_")
        if any(_CONTRACT_WORDS.fullmatch(word) for word in words):
            continue
        for unit, pattern, column in COUNT_UNITS:
            if any(pattern.fullmatch(word) for word in words):
                raise SQLValidationError(
                    f"COUNT(*) cuenta contratos, pero la columna {alias.alias} dice {unit}. "
                    f"Para contar {unit} usa COUNT(DISTINCT {column}); si cuentas contratos, "
                    "llama a la columna contratos."
                )


def _check_values(tree: exp.Select) -> None:
    """Rejects a text compared with a categorical column that never holds it (A5, mejora 16).

    On 2026-11-20 e03 filtered tipo_procedimiento_norm = 'brand_and_push': the
    company name taken for a procedure type, which returns nothing.
    """
    for node in tree.find_all(exp.EQ, exp.NEQ, exp.In):
        if isinstance(node, exp.In):
            pairs = [(node.this, item) for item in node.expressions]
        else:
            pairs = [(node.this, node.expression), (node.expression, node.this)]
        for column, value in pairs:
            if not (isinstance(column, exp.Column) and isinstance(value, exp.Literal) and value.is_string):
                continue
            allowed = CATEGORY_VALUES.get(column.name.lower())
            if allowed and value.this not in allowed:
                hint = CATEGORY_HINTS.get(column.name.lower(), "")
                raise SQLValidationError(
                    f"'{value.this}' no es un valor de {column.name}; sus valores son: "
                    f"{', '.join(allowed)}.{hint}"
                )


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
        name = (match.group(1) or match.group(2)).replace('"', "").lower()
        qualifier, _, column = name.rpartition(".")
        raise SQLValidationError(_column_message(column, views_in_query, qualifier, tree)) from exc
    except sqlglot.errors.SqlglotError as exc:
        raise SQLValidationError(f"No se pudieron revisar las columnas de la consulta: {exc}") from exc


def _column_message(column: str, views_in_query: set[str], qualifier: str = "",
                    tree: exp.Expression | None = None) -> str:
    homes = [view for view, columns in VIEW_COLUMNS.items() if column in columns]
    typo = _alias_typo(column, tree) if not qualifier and tree is not None else None
    if typo:
        # A5, mejora 10: on 2026-11-19 the model wrote c_fuente for c.fuente in q07 and
        # q08 and, told only that c_fuente does not exist, repeated it in the retry.
        # parse_response now fixes it first (mejora 15); this message is for other callers.
        _, prefix, rest = typo
        view = {node.alias_or_name.lower(): node.name.lower() for node in tree.find_all(exp.Table)}[prefix]
        return (
            f"La columna {column} no existe: para la columna {rest} de clean.{view} "
            f"escribe {prefix}.{rest}, con punto y no con guion bajo."
        )
    if qualifier and tree is not None:
        # sqlglot names the qualifier only when it matches no table or subquery.
        known = {node.alias_or_name.lower() for node in tree.find_all(exp.Table)}
        known |= {node.alias.lower() for node in tree.find_all(exp.Subquery) if node.alias}
        if qualifier not in known:
            where = f" La columna {column} está en clean.{homes[0]}." if len(homes) == 1 else ""
            return (
                f"El alias {qualifier} no corresponde a ninguna vista ni subconsulta de la consulta."
                f"{where} Usa el alias que le diste a esa vista en FROM o JOIN."
            )
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
