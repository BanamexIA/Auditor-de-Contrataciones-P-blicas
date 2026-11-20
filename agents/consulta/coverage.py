from __future__ import annotations

import re
import statistics
import unicodedata
from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Any, Iterable

import sqlglot
from sqlglot import exp


# M9 of docs/capa_semantica.md. The backend runs it with agent_ro and caches the rows;
# it is not generated SQL, so it does not go through the validator.
COVERAGE_QUERY = """
SELECT EXTRACT(YEAR FROM fecha_inicio)::integer AS anio, fuente, COUNT(*) AS filas
FROM clean.v_contratos_agente
WHERE fecha_inicio_valida
GROUP BY EXTRACT(YEAR FROM fecha_inicio), fuente
"""

# Provisional: a year with fewer rows than this share of its source's median is incomplete.
PARTIAL_YEAR_RATIO = 0.25

SOURCE_NAMES = {"comprasmx": "ComprasMX", "historico": "CompraNet histórico"}
SOURCE_ONLY_COLUMNS = {
    "comprasmx": frozenset({
        "institucion",
        "clave_institucion",
        "siglas_de_la_institucion",
        "tipo_de_institucion",
        "clave_ramo",
        "descripcion_ramo",
        "clave_de_la_uc",
        "nombre_de_la_uc",
        "numero_de_procedimiento",
        "caracter_del_procedimiento",
        "articulo_de_excepcion",
        "descripcion_excepcion",
        "tipo_procedimiento",
    }),
    "historico": frozenset({"tipo_expediente"}),
}

_FLIPPED = {exp.GTE: exp.LTE, exp.GT: exp.LT, exp.LTE: exp.GTE, exp.LT: exp.GT, exp.EQ: exp.EQ}


@dataclass(frozen=True)
class Coverage:
    years: dict[str, frozenset[int]]
    partial_years: dict[str, frozenset[int]]

    @classmethod
    def from_rows(cls, rows: Iterable[Any]) -> Coverage:
        counts: dict[str, dict[int, int]] = {}
        for row in rows:
            year, source, total = (
                (row["anio"], row["fuente"], row["filas"]) if isinstance(row, dict) else row
            )
            if year is None or not total:
                continue
            counts.setdefault(source, {})[int(year)] = int(total)
        partial = {}
        for source, by_year in counts.items():
            median = statistics.median(by_year.values())
            partial[source] = frozenset(
                year for year, total in by_year.items() if total < PARTIAL_YEAR_RATIO * median
            )
        return cls(
            years={source: frozenset(by_year) for source, by_year in counts.items()},
            partial_years=partial,
        )

    def describe(self) -> str:
        return "; ".join(
            f"{SOURCE_NAMES.get(source, source)}: {format_years(years)}"
            for source, years in sorted(self.years.items())
        )


_YEAR_IN_TEXT = re.compile(r"\b((?:19|20)\d{2})\b")
# A "no data" claim, over the text without accents and in lowercase.
_NO_DATA_TALK = re.compile(
    r"\b(no (hay|tiene|tienen|registra|registran|existen?|cuenta con)|sin|ningun\w*)\b"
    r".{0,40}\b(contratos?|datos|registros|informacion)\b"
)
SOURCE_WORDS = {"comprasmx": ("comprasmx",), "historico": ("historico", "compranet")}


def contradicted_no_data(motivo: str, coverage: Coverage) -> str | None:
    """Which years of a "no data" reason do have contracts, or None (A5, mejora 17).

    On 2026-11-20 the model answered q17 with "El histórico de CompraNet no
    registra contratos con inicio en 2024", which has 1,836. The claim is
    contradicted only when every year it names has contracts in the sources it
    names (in any source if it names none), so "no hay contratos en 2025" stands.
    """
    plain = _plain(motivo)
    years = {int(year) for year in _YEAR_IN_TEXT.findall(plain)}
    if not years or not _NO_DATA_TALK.search(plain):
        return None
    sources = {
        source for source, words in SOURCE_WORDS.items() if any(word in plain for word in words)
    } or set(coverage.years)
    found: dict[str, set[int]] = {}
    for year in years:
        holders = [source for source in sorted(sources) if year in coverage.years.get(source, ())]
        if not holders:
            return None
        for source in holders:
            found.setdefault(source, set()).add(year)
    parts = []
    for source, source_years in sorted(found.items()):
        partial = source_years & coverage.partial_years.get(source, frozenset())
        note = f" ({format_years(partial)} incompleto)" if partial else ""
        parts.append(
            f"{SOURCE_NAMES.get(source, source)} sí tiene contratos con inicio en "
            f"{format_years(source_years)}{note}"
        )
    return "; ".join(parts)


def _plain(text: str) -> str:
    decomposed = unicodedata.normalize("NFKD", text.casefold())
    return "".join(char for char in decomposed if not unicodedata.combining(char))


@dataclass
class CoverageCheck:
    sin_datos: str | None = None
    supuestos: list[str] = field(default_factory=list)


@dataclass
class _Filters:
    start: date | None = None
    end: date | None = None
    years: set[int] | None = None
    sources: set[str] | None = None

    def from_date(self, value: date) -> None:
        self.start = value if self.start is None else max(self.start, value)

    def before_date(self, value: date) -> None:
        self.end = value if self.end is None else min(self.end, value)

    def only_years(self, values: set[int]) -> None:
        self.years = values if self.years is None else self.years & values

    def only_sources(self, values: set[str]) -> None:
        self.sources = values if self.sources is None else self.sources & values

    @property
    def period_restricted(self) -> bool:
        return self.start is not None or self.end is not None or self.years is not None


def format_years(years: Iterable[int]) -> str:
    ordered = sorted(set(years))
    if not ordered:
        return "ningún año"
    spans: list[str] = []
    first = previous = ordered[0]
    for year in ordered[1:] + [None]:
        if year is not None and year == previous + 1:
            previous = year
            continue
        spans.append(str(first) if first == previous else f"{first}–{previous}")
        if year is not None:
            first = previous = year
    return spans[0] if len(spans) == 1 else f"{', '.join(spans[:-1])} y {spans[-1]}"


def _unwrap(node: exp.Expression) -> exp.Expression:
    while isinstance(node, (exp.Cast, exp.Paren)):
        node = node.this
    return node


def _is_column(node: exp.Expression, name: str) -> bool:
    node = _unwrap(node)
    return isinstance(node, exp.Column) and node.name.lower() == name


def _is_start_year(node: exp.Expression) -> bool:
    node = _unwrap(node)
    return (
        isinstance(node, exp.Extract)
        and node.this.name.upper() == "YEAR"
        and _is_column(node.expression, "fecha_inicio")
    )


def _start_trunc_unit(node: exp.Expression) -> str | None:
    """'YEAR' or 'MONTH' for DATE_TRUNC(unit, fecha_inicio); None otherwise."""
    node = _unwrap(node)
    if not isinstance(node, (exp.TimestampTrunc, exp.DateTrunc)) or not _is_column(node.this, "fecha_inicio"):
        return None
    unit = node.args.get("unit")
    name = unit.name.upper() if unit is not None else ""
    return name if name in ("YEAR", "MONTH") else None


def _next_period(day: date, unit: str) -> date:
    if unit == "YEAR":
        return date(day.year + 1, 1, 1)
    return date(day.year + 1, 1, 1) if day.month == 12 else date(day.year, day.month + 1, 1)


def _date_value(node: exp.Expression) -> date | None:
    node = _unwrap(node)
    if isinstance(node, exp.Literal) and node.is_string:
        try:
            return date.fromisoformat(node.this[:10])
        except ValueError:
            return None
    return None


def _int_value(node: exp.Expression) -> int | None:
    node = _unwrap(node)
    if isinstance(node, exp.Literal) and not node.is_string:
        try:
            return int(node.this)
        except ValueError:
            return None
    return None


def _conjuncts(condition: exp.Expression):
    if isinstance(condition, exp.Paren):
        yield from _conjuncts(condition.this)
    elif isinstance(condition, exp.And):
        yield from _conjuncts(condition.this)
        yield from _conjuncts(condition.expression)
    else:
        yield condition


def _apply_comparison(filters: _Filters, kind: type, target: exp.Expression, value: exp.Expression) -> None:
    if _is_column(target, "fecha_inicio"):
        day = _date_value(value)
        if day is None:
            return
        bounds = {
            exp.GTE: (day, None),
            exp.GT: (day + timedelta(days=1), None),
            exp.LT: (None, day),
            exp.LTE: (None, day + timedelta(days=1)),
            exp.EQ: (day, day + timedelta(days=1)),
        }[kind]
    elif _start_trunc_unit(target):
        # DATE_TRUNC('year', fecha_inicio) = DATE '2024-01-01' covers the whole period
        # (A5, mejora 6: the coverage notes must not depend on how the model wrote it).
        day = _date_value(value)
        if day is None:
            return
        following = _next_period(day, _start_trunc_unit(target))
        bounds = {
            exp.GTE: (day, None),
            exp.GT: (following, None),
            exp.LT: (None, day),
            exp.LTE: (None, following),
            exp.EQ: (day, following),
        }[kind]
    elif _is_start_year(target):
        year = _int_value(value)
        if year is None:
            return
        bounds = {
            exp.GTE: (date(year, 1, 1), None),
            exp.GT: (date(year + 1, 1, 1), None),
            exp.LT: (None, date(year, 1, 1)),
            exp.LTE: (None, date(year + 1, 1, 1)),
            exp.EQ: (date(year, 1, 1), date(year + 1, 1, 1)),
        }[kind]
    elif kind is exp.EQ and _is_column(target, "fuente"):
        literal = _unwrap(value)
        if isinstance(literal, exp.Literal) and literal.is_string:
            filters.only_sources({literal.this})
        return
    else:
        return
    if bounds[0] is not None:
        filters.from_date(bounds[0])
    if bounds[1] is not None:
        filters.before_date(bounds[1])


def _read_filters(tree: exp.Expression) -> _Filters:
    """Reads the period and source restrictions joined by AND in the outer WHERE."""
    filters = _Filters()
    where = tree.args.get("where")
    if where is None:
        return filters
    for predicate in _conjuncts(where.this):
        kind = type(predicate)
        if kind in _FLIPPED:
            left, right = predicate.this, predicate.expression
            if _date_value(left) is not None or _int_value(left) is not None:
                left, right, kind = right, left, _FLIPPED[kind]
            _apply_comparison(filters, kind, left, right)
        elif isinstance(predicate, exp.Between):
            low, high = predicate.args["low"], predicate.args["high"]
            if _is_column(predicate.this, "fecha_inicio") and _date_value(low) and _date_value(high):
                filters.from_date(_date_value(low))
                filters.before_date(_date_value(high) + timedelta(days=1))
            elif _is_start_year(predicate.this) and _int_value(low) is not None and _int_value(high) is not None:
                filters.from_date(date(_int_value(low), 1, 1))
                filters.before_date(date(_int_value(high) + 1, 1, 1))
        elif isinstance(predicate, exp.In):
            values = [_unwrap(item) for item in predicate.expressions]
            if _is_start_year(predicate.this) and all(_int_value(v) is not None for v in values):
                filters.only_years({_int_value(v) for v in values})
            elif _is_column(predicate.this, "fuente") and all(
                isinstance(v, exp.Literal) and v.is_string for v in values
            ):
                filters.only_sources({v.this for v in values})
    return filters


def _requested_years(filters: _Filters, coverage: Coverage) -> set[int]:
    known = set().union(*coverage.years.values()) if coverage.years else set()
    if not known:
        return set()
    first = filters.start.year if filters.start else min(known)
    last = (filters.end - timedelta(days=1)).year if filters.end else max(known)
    years = set(range(first, last + 1))
    return years & filters.years if filters.years is not None else years


def _names(sources: Iterable[str]) -> str:
    names = [SOURCE_NAMES.get(source, f"'{source}'") for source in sorted(sources)]
    return names[0] if len(names) == 1 else f"{', '.join(names[:-1])} y {names[-1]}"


def check_coverage(sql: str, coverage: Coverage) -> CoverageCheck:
    """Decides, without the model, whether a validated query asks for data the sources lack."""
    tree = sqlglot.parse_one(sql, read="postgres")
    filters = _read_filters(tree)
    requested_sources = filters.sources if filters.sources is not None else set(coverage.years)
    check = CoverageCheck()

    unknown = requested_sources - set(coverage.years)
    if unknown and unknown == requested_sources:
        check.sin_datos = (
            f"No existe la fuente {_names(unknown)}. Fuentes disponibles: {coverage.describe()}."
        )
        return check

    requested = _requested_years(filters, coverage)
    covered = {
        source: requested & coverage.years.get(source, frozenset())
        for source in requested_sources
    }
    effective = {source for source, years in covered.items() if years}
    if not effective:
        place = f" en {_names(requested_sources)}" if filters.sources is not None else ""
        period = format_years(requested) if requested else "el periodo pedido"
        check.sin_datos = (
            f"No hay contratos con inicio en {period}{place}. "
            f"Cobertura disponible: {coverage.describe()}."
        )
        return check

    referenced = {column.name.lower() for column in tree.find_all(exp.Column)}
    for source, columns in SOURCE_ONLY_COLUMNS.items():
        used = sorted(referenced & columns)
        if not used:
            continue
        if source not in effective:
            scope = "ese periodo" if filters.period_restricted else "la consulta"
            check.sin_datos = (
                f"El campo {used[0]} solo existe en {SOURCE_NAMES[source]}, y {scope} "
                f"solo tiene datos de {_names(effective)}."
            )
            return check
        if len(effective) > 1:
            others = _names(effective - {source})
            check.supuestos.append(
                f"{', '.join(used)} solo existe en {SOURCE_NAMES[source]}; "
                f"los contratos de {others} aparecen sin ese dato."
            )

    if filters.period_restricted:
        covered_years = set().union(*(covered[source] for source in effective))
        missing = requested - covered_years
        if missing:
            check.supuestos.append(
                f"Sin datos para {format_years(missing)}; el resultado solo incluye "
                f"{format_years(covered_years)}."
            )
        for source in sorted(effective):
            partial = covered[source] & coverage.partial_years.get(source, frozenset())
            if partial:
                check.supuestos.append(
                    f"Cobertura incompleta en {SOURCE_NAMES.get(source, source)} "
                    f"para {format_years(partial)}."
                )
    return check
