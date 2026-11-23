"""Names of government agencies in the SQL, in upper case as the views store them (A5, mejora 26).

In ComprasMX, institucion, descripcion_ramo and tipo_de_institucion are always in
upper case, and nombre_de_la_uc in 1,180 of its 1,182 values (2026-11-23). The
model writes the name as the question says it, so on 2026-11-23 Escenario 1 s3
filtered institucion = 'Secretaría de Salud' and answered 0 contracts instead of
239, without an error. The code rewrites those literals in upper case before the
SQL is validated, the way providers.py does with provider names.
"""
from __future__ import annotations

import sqlglot
from sqlglot import exp

AGENCY_COLUMNS = frozenset({
    "institucion",
    "nombre_de_la_uc",
    "descripcion_ramo",
    "tipo_de_institucion",
    "siglas_de_la_institucion",
})


def _agency_column(node: exp.Expression) -> bool:
    # LOWER(institucion) = 'x' already compares in lower case; upper-casing 'x' would break it.
    while isinstance(node, (exp.Upper, exp.Paren, exp.Cast)):
        node = node.this
    return isinstance(node, exp.Column) and node.name.lower() in AGENCY_COLUMNS


def uppercase_agency_literals(query: str) -> tuple[str, list[str]]:
    """Writes in upper case the texts compared with an agency column.

    Covers =, <>, IN and LIKE (ILIKE already ignores case). Returns the query and
    the names that changed; anything that does not parse comes back unchanged so
    the validator can reject it with its usual message.
    """
    try:
        statements = sqlglot.parse(query, read="postgres")
    except sqlglot.errors.ParseError:
        return query, []
    if len(statements) != 1 or statements[0] is None:
        return query, []
    tree = statements[0]
    changed: list[str] = []

    def rewrite(literal: exp.Expression) -> None:
        if isinstance(literal, exp.Literal) and literal.is_string and literal.this.upper() != literal.this:
            upper = literal.this.upper()
            literal.replace(exp.Literal.string(upper))
            changed.append(upper)

    for node in list(tree.find_all(exp.EQ, exp.NEQ, exp.Like, exp.In)):
        if isinstance(node, exp.In):
            if _agency_column(node.this):
                for item in list(node.expressions):
                    rewrite(item)
            continue
        if _agency_column(node.this):
            rewrite(node.expression)
        elif _agency_column(node.expression):
            rewrite(node.this)
    if not changed:
        return query, []
    return tree.sql(dialect="postgres"), list(dict.fromkeys(changed))
