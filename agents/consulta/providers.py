"""Provider names in the SQL, written the way the ETL stores them (A5, mejora 12).

proveedor_normalizado holds names in upper case, without accents, punctuation or
company suffixes. The model writes the name as the question says it ("Molinera
de México"), so on 2026-11-19 every company question found nothing. The code
rewrites those literals with the ETL rule before the SQL is validated.
"""
from __future__ import annotations

import re
import unicodedata

import sqlglot
from sqlglot import exp

COLUMN = "proveedor_normalizado"


def normalize_text(value: object) -> str:
    """Same rule as etl/build_clean.py::normalize_text; keep them in sync (a test compares them)."""
    if value is None:
        return ""
    text = unicodedata.normalize("NFKC", str(value)).strip()
    return re.sub(r"\s+", " ", text)


def normalize_provider(value: object) -> str:
    """Same rule as etl/build_clean.py::normalize_provider; keep them in sync (a test compares them)."""
    text = normalize_text(value).upper()
    text = unicodedata.normalize("NFKD", text)
    text = "".join(ch for ch in text if unicodedata.category(ch) != "Mn")
    text = text.replace("&", " Y ")
    text = re.sub(r"[^A-Z0-9 ]+", " ", text)
    text = re.sub(r"\b(S\.?A\.?|SOCIEDAD ANONIMA|S\.? DE R\.?L\.?|S\.? DE C\.?V\.?|DE C\.?V\.?|SA DE CV|S\.?R\.?L\.?|S\.?C\.?|SC|SRL)\b", "", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def _normalize_pattern(pattern: str) -> str:
    """LIKE pattern: normalize the text between the % wildcards and keep them."""
    return "%".join(normalize_provider(part) if part else "" for part in pattern.split("%"))


def _is_provider_column(node: exp.Expression) -> bool:
    while isinstance(node, (exp.Upper, exp.Lower, exp.Paren, exp.Cast)):
        node = node.this
    return isinstance(node, exp.Column) and node.name.lower() == COLUMN


def normalize_provider_literals(query: str) -> tuple[str, list[str]]:
    """Rewrites string literals compared with proveedor_normalizado.

    Covers =, <>, IN, LIKE and ILIKE. Returns the query and the normalized names
    that changed; anything that does not parse comes back unchanged so the
    validator can reject it with its usual message.
    """
    try:
        statements = sqlglot.parse(query, read="postgres")
    except sqlglot.errors.ParseError:
        return query, []
    if len(statements) != 1 or statements[0] is None:
        return query, []
    tree = statements[0]
    changed: list[str] = []

    def rewrite(literal: exp.Expression, like: bool) -> None:
        if not (isinstance(literal, exp.Literal) and literal.is_string):
            return
        normalized = _normalize_pattern(literal.this) if like else normalize_provider(literal.this)
        if normalized != literal.this:
            literal.replace(exp.Literal.string(normalized))
            changed.append(normalized)

    for node in list(tree.find_all(exp.EQ, exp.NEQ, exp.Like, exp.ILike, exp.In)):
        like = isinstance(node, (exp.Like, exp.ILike))
        if isinstance(node, exp.In):
            if _is_provider_column(node.this):
                for item in list(node.expressions):
                    rewrite(item, like=False)
            continue
        left, right = node.this, node.expression
        if _is_provider_column(left):
            rewrite(right, like)
        elif _is_provider_column(right):
            rewrite(left, like)
    if not changed:
        return query, []
    return tree.sql(dialect="postgres"), changed
