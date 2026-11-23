"""Cuántos registros respaldan una respuesta (HU-01, para A6).

HU-01 pide que el agente "siempre informe cuántos registros respaldan la
respuesta". Después de ejecutar el SQL, el agente agrega ``conteo``:

- ``filas``: las que devolvió la consulta.
- ``filas_totales``: las que habría sin el LIMIT. Solo se consulta a la base si
  las filas llegaron al LIMIT; si no, son las mismas.
- ``truncado``: si el LIMIT cortó el resultado.
- ``registros``: cuántos registros de las vistas resume la respuesta. En una
  consulta con agregados (COUNT, SUM, GROUP BY) son los que entran a los grupos,
  antes del LIMIT; en una lista, cada fila es un registro.

Las consultas de conteo salen del mismo SQL con sqlglot y pasan por el mismo
validador antes de ejecutarse. Si algo no se puede contar, el campo queda en None.
"""
from __future__ import annotations

from decimal import Decimal
from typing import Any, Callable

import sqlglot
from sqlglot import exp

from agents.consulta.validator import VIEW_COLUMNS

Executor = Callable[[str], list[Any]]
_INPUT_COLUMNS = {column for columns in VIEW_COLUMNS.values() for column in columns}
TRUNCATION_NOTE_PREFIX = "El resultado se cortó: "


def _single_select(sql: str) -> exp.Select | None:
    try:
        statements = sqlglot.parse(sql, read="postgres")
    except sqlglot.errors.ParseError:
        return None
    if len(statements) != 1 or not isinstance(statements[0], exp.Select):
        return None
    return statements[0]


def _limit(tree: exp.Select) -> int | None:
    limit = tree.args.get("limit")
    if limit is None or not isinstance(limit.expression, exp.Literal) or limit.expression.is_string:
        return None
    try:
        return int(limit.expression.this)
    except ValueError:
        return None


def _is_aggregate(tree: exp.Select) -> bool:
    return tree.args.get("group") is not None or any(item.find(exp.AggFunc) for item in tree.expressions)


def _reads_a_subquery(tree: exp.Select) -> bool:
    sources = [tree.args["from"].this] if tree.args.get("from") else []
    sources += [join.this for join in tree.args.get("joins") or []]
    return any(isinstance(source, exp.Subquery) for source in sources)


def total_rows_query(sql: str) -> str | None:
    """SELECT COUNT(*) of the same query without LIMIT, OFFSET or ORDER BY."""
    tree = _single_select(sql)
    if tree is None:
        return None
    inner = tree.copy()
    inner.set("limit", None)
    inner.set("offset", None)
    distinct = inner.args.get("distinct")
    if distinct is None or distinct.args.get("on") is None:  # DISTINCT ON needs its ORDER BY
        inner.set("order", None)
    return f"SELECT COUNT(*) AS filas_totales FROM ({inner.sql(dialect='postgres')}) AS t LIMIT 1"


def _resolve_group_item(item: exp.Expression, projections: list[exp.Expression]) -> exp.Expression:
    """GROUP BY 1 or GROUP BY an output alias, written as the expression itself.

    PostgreSQL reads a GROUP BY name as an input column first, so an alias is
    only replaced when no view has a column with that name.
    """
    if isinstance(item, exp.Literal) and not item.is_string:
        position = int(item.this) - 1
        if 0 <= position < len(projections):
            return projections[position].unalias().copy()
        return item
    if isinstance(item, exp.Column) and not item.table and item.name.lower() not in _INPUT_COLUMNS:
        for projection in projections:
            if isinstance(projection, exp.Alias) and projection.alias.lower() == item.name.lower():
                return projection.this.copy()
    return item


def records_query(sql: str) -> str | None:
    """How many view records feed an aggregated answer, before its LIMIT.

    Keeps FROM, JOIN, WHERE, GROUP BY and HAVING, counts each group and adds the
    counts up. Returns None for a query without aggregates (each row is a record)
    or one that reads from a subquery.
    """
    tree = _single_select(sql)
    if tree is None or not _is_aggregate(tree) or _reads_a_subquery(tree):
        return None
    inner = tree.copy()
    group = inner.args.get("group")
    if group is not None:
        group.set("expressions", [_resolve_group_item(item, tree.expressions) for item in group.expressions])
    inner.set("expressions", [exp.alias_(exp.Count(this=exp.Star()), "n")])
    for key in ("order", "limit", "offset", "distinct"):
        inner.set(key, None)
    return f"SELECT COALESCE(SUM(t.n), 0) AS registros FROM ({inner.sql(dialect='postgres')}) AS t LIMIT 1"


def _first_value(rows: list[Any], key: str) -> int | None:
    if not rows:
        return None
    row = rows[0]
    value = row[key] if isinstance(row, dict) else row[0]
    if value is None:
        return None
    return int(value) if isinstance(value, (int, Decimal, float)) else None


def count_support(sql: str, rows: list[Any], execute: Executor) -> dict[str, Any]:
    """The ``conteo`` of an executed answer. Database errors propagate to the caller."""
    shown = len(rows)
    tree = _single_select(sql)
    if tree is None:
        return {"filas": shown, "filas_totales": None, "truncado": None, "registros": None}
    limit = _limit(tree)
    total: int | None = shown
    if limit is None or shown >= limit or tree.args.get("offset") is not None:
        query = total_rows_query(sql)
        total = _first_value(execute(query), "filas_totales") if query else None
    if _is_aggregate(tree):
        query = records_query(sql)
        records = _first_value(execute(query), "registros") if query else None
    else:
        records = total
    return {
        "filas": shown,
        "filas_totales": total,
        "truncado": None if total is None else total > shown,
        "registros": records,
    }


def empty_count(rows: list[Any]) -> dict[str, Any]:
    """The ``conteo`` when the counting queries could not run."""
    return {"filas": len(rows), "filas_totales": None, "truncado": None, "registros": None}


def truncation_note(count: dict[str, Any]) -> str | None:
    if not count.get("truncado"):
        return None
    return (
        f"{TRUNCATION_NOTE_PREFIX}se muestran {count['filas']:,} de {count['filas_totales']:,} "
        "filas por el LIMIT."
    )
