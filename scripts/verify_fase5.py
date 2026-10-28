#!/usr/bin/env python3
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

import psycopg

REPO_ROOT = Path(__file__).resolve().parents[1]
ETL_DIR = REPO_ROOT / "etl"
sys.path.insert(0, str(ETL_DIR))

from db_config import connect_database


DEFAULT_DICTIONARY = REPO_ROOT / "docs" / "diccionario_datos.md"
TABLE_HEADING = re.compile(r"^#{2,3}\s+`clean\.([a-z_][a-z0-9_]*)`\s*$")
MARKDOWN_ROW = re.compile(r"^\s*\|.*\|\s*$")
REQUIRED_METADATA_HEADERS = {
    "columna",
    "tipo",
    "significado",
    "origen raw",
    "limpieza / transformación",
    "riesgos de calidad y privacidad",
}
TYPE_ALIASES = {
    "TIMESTAMPTZ": "timestamp with time zone",
    "TIMESTAMP WITH TIME ZONE": "timestamp with time zone",
    "BOOL": "boolean",
    "INT2": "smallint",
    "INT4": "integer",
    "INT8": "bigint",
}


def _cells(line: str) -> list[str]:
    return [cell.strip().strip("`") for cell in line.strip().strip("|").split("|")]


def _canonical_type(value: str) -> str:
    normalized = value.strip().upper()
    return TYPE_ALIASES.get(normalized, normalized.lower())


def parse_dictionary(path: Path) -> dict[str, dict[str, str]]:
    tables: dict[str, dict[str, str]] = {}
    current_table: str | None = None
    header: list[str] | None = None

    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        heading = TABLE_HEADING.match(line)
        if heading:
            current_table = heading.group(1)
            tables[current_table] = {}
            header = None
            continue
        if line.startswith("#"):
            current_table = None
            header = None
            continue
        if current_table is None or not MARKDOWN_ROW.match(line):
            continue

        cells = _cells(line)
        if all(set(cell) <= {"-", ":"} for cell in cells):
            continue
        if header is None:
            header = [cell.casefold() for cell in cells]
            missing_headers = REQUIRED_METADATA_HEADERS - set(header)
            if missing_headers:
                raise ValueError(
                    f"Tabla clean.{current_table} en línea {line_number}: "
                    f"faltan columnas de metadatos: {', '.join(sorted(missing_headers))}"
                )
            continue
        if len(cells) != len(header):
            raise ValueError(
                f"Tabla clean.{current_table}, línea {line_number}: "
                f"se esperaban {len(header)} celdas, se encontraron {len(cells)}."
            )
        values = dict(zip(header, cells))
        column = values["columna"].strip("`")
        if not column or column in tables[current_table]:
            raise ValueError(
                f"Tabla clean.{current_table}, línea {line_number}: "
                f"columna vacía o duplicada: {column!r}."
            )
        for field in REQUIRED_METADATA_HEADERS:
            if not values[field].strip():
                raise ValueError(
                    f"Tabla clean.{current_table}, línea {line_number}: "
                    f"`{field}` está vacío para `{column}`."
                )
        tables[current_table][column] = _canonical_type(values["tipo"])

    return {name: columns for name, columns in tables.items() if columns}


def fetch_clean_schema() -> dict[str, dict[str, str]]:
    query = """
        SELECT c.table_name, c.column_name, c.data_type
        FROM information_schema.columns AS c
        JOIN information_schema.tables AS t
          ON t.table_schema = c.table_schema
         AND t.table_name = c.table_name
        WHERE c.table_schema = 'clean'
          AND t.table_type = 'BASE TABLE'
        ORDER BY c.table_name, c.ordinal_position
    """
    schema: dict[str, dict[str, str]] = {}
    with connect_database() as conn:
        with conn.cursor() as cursor:
            cursor.execute(query)
            for table, column, data_type in cursor.fetchall():
                schema.setdefault(table, {})[column] = _canonical_type(data_type)
    return schema


def compare_schema(
    documented: dict[str, dict[str, str]],
    actual: dict[str, dict[str, str]],
) -> list[str]:
    discrepancies: list[str] = []
    for table in sorted(set(documented) - set(actual)):
        discrepancies.append(f"Tabla documentada inexistente en clean: clean.{table}")
    for table in sorted(set(actual) - set(documented)):
        discrepancies.append(f"Tabla clean.{table} ausente del diccionario")

    for table in sorted(set(documented) & set(actual)):
        documented_columns = documented[table]
        actual_columns = actual[table]
        for column in sorted(set(documented_columns) - set(actual_columns)):
            discrepancies.append(f"Columna documentada inexistente: clean.{table}.{column}")
        for column in sorted(set(actual_columns) - set(documented_columns)):
            discrepancies.append(f"Columna sin documentar: clean.{table}.{column}")
        for column in sorted(set(documented_columns) & set(actual_columns)):
            if documented_columns[column] != actual_columns[column]:
                discrepancies.append(
                    f"Tipo distinto en clean.{table}.{column}: "
                    f"diccionario={documented_columns[column]}, BD={actual_columns[column]}"
                )
    return discrepancies


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Compara las tablas y columnas de clean con el diccionario de datos."
    )
    parser.add_argument("--dictionary", type=Path, default=DEFAULT_DICTIONARY)
    args = parser.parse_args()

    try:
        documented = parse_dictionary(args.dictionary)
        actual = fetch_clean_schema()
    except (OSError, ValueError, RuntimeError, psycopg.Error) as exc:
        print(f"Error al verificar Fase 5: {exc}", file=sys.stderr)
        return 2

    discrepancies = compare_schema(documented, actual)
    if discrepancies:
        print("Discrepancias entre clean y el diccionario:")
        for discrepancy in discrepancies:
            print(f"- {discrepancy}")
        return 1

    columns = sum(len(table_columns) for table_columns in actual.values())
    print(
        f"Fase 5: OK. {len(actual)} tablas y {columns} columnas de clean "
        "coinciden con el diccionario, incluidos sus tipos."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
