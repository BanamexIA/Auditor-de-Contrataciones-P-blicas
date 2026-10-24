#!/usr/bin/env python3
from __future__ import annotations

import argparse
import codecs
import csv
import io
import os
import re
import sys
import time
import unicodedata
from pathlib import Path
from typing import Iterable

try:
    import psycopg
except ImportError:  # pragma: no cover - handled at runtime
    psycopg = None

from db_config import load_database_environment

load_database_environment()


EXPECTED_HEADERS = {
    "contratos_comprasmx": {
        "codigo_contrato",
        "codigo_expediente",
        "proveedor",
        "titulo_contrato",
        "descripcion_contrato",
        "contract_type",
        "tipo_contratacion",
        "tipo_expediente",
        "importe",
        "moneda",
        "fecha_inicio",
        "fecha_fin",
    },
    "listado_69b": {
        "rfc",
        "nombre_o_razon_social",
        "situacion_del_contribuyente",
        "fecha_de_baja",
        "provincia",
    },
}


def normalize_identifier(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value or "")
    normalized = "".join(ch for ch in normalized if unicodedata.category(ch) != "Mn")
    clean = re.sub(r"[^a-zA-Z0-9]+", "_", normalized.strip())
    clean = clean.strip("_")
    return clean.lower() or "col"


def sanitize_sql_identifier(value: str) -> str:
    return '"' + value.replace('"', '""') + '"'


def detect_best_encoding(path: Path) -> str:
    encodings = ["utf-8-sig", "utf-8", "cp1252", "latin-1", "iso-8859-1"]
    for encoding in encodings:
        decoder = codecs.getincrementaldecoder(encoding)(errors="strict")
        try:
            with path.open("rb") as handle:
                while True:
                    chunk = handle.read(1024 * 1024)
                    if not chunk:
                        break
                    decoder.decode(chunk)
                decoder.decode(b"", final=True)
            return encoding
        except (UnicodeDecodeError, ValueError):
            continue
    return "latin-1"


def detect_delimiter(path: Path, encoding: str) -> str:
    delimiters = [",", ";", "\t", "|"]
    best_delimiter = ","
    best_score = 0
    header_tokens = {
        "codigo_contrato",
        "codigo_expediente",
        "proveedor",
        "rfc",
        "situacion_del_contribuyente",
        "no",
        "nombre_del_contribuyente",
        "fecha_de_inicio",
        "fecha_de_fin",
        "importe",
        "moneda",
    }

    with path.open("rb") as handle:
        sample = handle.read(256 * 1024).decode(encoding)
    for delimiter in delimiters:
        score = 0
        for row in csv.reader(io.StringIO(sample), delimiter=delimiter):
            if not row or all(not cell.strip() for cell in row):
                continue
            normalized = [normalize_identifier(cell) for cell in row]
            matches = sum(1 for token in header_tokens if token in normalized)
            if matches:
                score += matches * 10
                if "rfc" in normalized or "codigo_contrato" in normalized:
                    score += 20
                break
        if score > best_score:
            best_score = score
            best_delimiter = delimiter
    return best_delimiter


def iter_csv_rows(path: Path, encoding: str, delimiter: str) -> Iterable[list[str]]:
    with path.open("r", encoding=encoding, newline="") as handle:
        reader = csv.reader(handle, delimiter=delimiter)
        for row in reader:
            if not row or all(not cell.strip() for cell in row):
                continue
            yield row


def find_header_row(rows: Iterable[list[str]], table_key: str) -> tuple[int, list[str]]:
    known = EXPECTED_HEADERS.get(table_key, set())
    for index, row in enumerate(rows):
        norm_row = [normalize_identifier(cell) for cell in row]
        if any(candidate in norm_row for candidate in ["codigo_contrato", "codigo_expediente", "proveedor", "rfc", "situacion_del_contribuyente"]):
            return index, row
        if known and any(normalize_identifier(cell) in known for cell in row):
            return index, row
    return 0, next(iter(rows)) if False else []


def parse_header(header: list[str]) -> list[str]:
    columns: list[str] = []
    seen: set[str] = set()
    for index, cell in enumerate(header):
        base = normalize_identifier(cell) or f"col_{index + 1}"
        candidate = base[:63]
        suffix_index = 1
        while candidate in seen:
            suffix = f"_{suffix_index}"
            candidate = f"{base[:63 - len(suffix)]}{suffix}"
            suffix_index += 1
        columns.append(candidate)
        seen.add(candidate)
    return columns


def get_table_name(file_name: str) -> str:
    stem = Path(file_name).stem.lower()
    stem = re.sub(r"[^a-z0-9]+", "_", stem)
    stem = stem.strip("_")
    if stem.startswith("listado_completo_69_b"):
        return "listado_69b"
    if stem.startswith("contratos_comprasmx"):
        return "contratos_comprasmx"
    return stem


def get_db_connection() -> object:
    if psycopg is None:
        raise RuntimeError("psycopg is required for database actions. Install dependencies from the project requirements.")

    password = os.getenv("DB_PASSWORD") or os.getenv("POSTGRES_PASSWORD")
    user = os.getenv("DB_USER") or os.getenv("POSTGRES_USER") or "postgres"
    host = os.getenv("DB_HOST") or "localhost"
    port = os.getenv("DB_PORT") or os.getenv("DB_PORT_HOST") or "5432"
    dbname = os.getenv("DB_NAME") or os.getenv("POSTGRES_DB") or "postgres"
    conninfo = f"dbname={dbname} user={user} password={password} host={host} port={port}"
    conninfo = psycopg.conninfo.make_conninfo(dbname=dbname, user=user, host=host, port=port)
    return psycopg.connect(conninfo, password=password)


def build_create_table_sql(table_name: str, columns: list[str]) -> str:
    column_sql = ",\n  ".join(f"{sanitize_sql_identifier(col)} TEXT" for col in columns)
    sql = (
        f"CREATE TABLE IF NOT EXISTS raw.{sanitize_sql_identifier(table_name)} (\n"
        f"  {column_sql},\n"
        "  _source_file TEXT,\n"
        "  _loaded_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),\n"
        "  _row_number BIGINT\n"
        ");"
    )
    return sql


def ensure_raw_table(cursor, table_name: str, columns: list[str]) -> None:
    table = f"raw.{sanitize_sql_identifier(table_name)}"
    cursor.execute(build_create_table_sql(table_name, columns))
    required_columns = [*columns, "_source_file", "_loaded_at", "_row_number"]
    for column in required_columns:
        column_type = {
            "_loaded_at": "TIMESTAMPTZ NOT NULL DEFAULT NOW()",
            "_row_number": "BIGINT",
        }.get(column, "TEXT")
        cursor.execute(
            f"ALTER TABLE {table} ADD COLUMN IF NOT EXISTS "
            f"{sanitize_sql_identifier(column)} {column_type}"
        )


def detect_csv_structure(path: Path, table_key: str) -> tuple[str, str, int, list[str]]:
    encoding = detect_best_encoding(path)
    delimiter = detect_delimiter(path, encoding)
    with path.open("r", encoding=encoding, newline="") as handle:
        for index, row in enumerate(csv.reader(handle, delimiter=delimiter)):
            if not row or all(not cell.strip() for cell in row):
                continue
            normalized = [normalize_identifier(cell) for cell in row]
            known = EXPECTED_HEADERS.get(table_key, set())
            if any(token in normalized for token in known):
                return encoding, delimiter, index, parse_header(row)
            if any(token in normalized for token in ("codigo_contrato", "codigo_del_contrato", "rfc", "situacion_del_contribuyente")):
                return encoding, delimiter, index, parse_header(row)
    raise ValueError(f"Could not identify a supported header row in {path.name}")


def detect_and_prepare_file(path: Path) -> dict:
    table_key = "listado_69b" if "69" in path.name.lower() or "listado" in path.name.lower() else "contratos_comprasmx"
    encoding, delimiter, header_index, columns = detect_csv_structure(path, table_key)
    return {
        "table_key": table_key,
        "encoding": encoding,
        "delimiter": delimiter,
        "columns": columns,
        "header_index": header_index,
    }


def iter_data_rows(path: Path, encoding: str, delimiter: str, header_index: int) -> Iterable[list[str]]:
    with path.open("r", encoding=encoding, newline="") as handle:
        for index, row in enumerate(csv.reader(handle, delimiter=delimiter)):
            if index <= header_index or not row or all(not cell.strip() for cell in row):
                continue
            yield row


def main() -> int:
    parser = argparse.ArgumentParser(description="Load public-source CSV files into Postgres raw schemas.")
    parser.add_argument("--input-dir", default="data/raw", help="Directory containing source CSVs.")
    parser.add_argument("--dry-run", action="store_true", help="Detect encoding/delimiter and print counts without writing to the database.")
    args = parser.parse_args()

    input_dir = Path(args.input_dir)
    if not input_dir.exists():
        raise SystemExit(f"Input directory does not exist: {input_dir}")

    files = [
        path for path in sorted(input_dir.iterdir())
        if path.is_file() and path.suffix.lower() in {".csv", ".txt"}
    ]
    if not files:
        raise SystemExit(f"No CSV/TXT files found in {input_dir}")

    for path in files:
        preview = detect_and_prepare_file(path)
        table_name = get_table_name(path.name)
        print(f"FILE: {path.name}")
        print(f"  table: raw.{table_name}")
        print(f"  encoding: {preview['encoding']}")
        print(f"  delimiter: {preview['delimiter']!r}")
        print(f"  columns: {len(preview['columns'])}")
        if args.dry_run:
            count = sum(
                1
                for _ in iter_data_rows(
                    path,
                    preview["encoding"],
                    preview["delimiter"],
                    preview["header_index"],
                )
            )
            print(f"  data rows: {count}")
            print("  DRY RUN: no database write performed")
            continue

        if psycopg is None:
            raise SystemExit("psycopg is required to load data. Install project dependencies first.")

        try:
            start = time.perf_counter()
            loaded_rows = 0
            with get_db_connection() as conn:
                with conn.cursor() as cursor:
                    ensure_raw_table(cursor, table_name, preview["columns"])
                    cursor.execute(f"TRUNCATE TABLE raw.{sanitize_sql_identifier(table_name)};")
                    columns_sql = ", ".join(sanitize_sql_identifier(col) for col in preview["columns"])
                    copy_target = (
                        f"COPY raw.{sanitize_sql_identifier(table_name)} "
                        f"({columns_sql}, _source_file, _row_number) FROM STDIN"
                    )
                    with cursor.copy(copy_target) as copy:
                        for row_number, row in enumerate(
                            iter_data_rows(
                                path,
                                preview["encoding"],
                                preview["delimiter"],
                                preview["header_index"],
                            ),
                            start=1,
                        ):
                            values = [cell.strip() for cell in row]
                            if len(values) < len(preview["columns"]):
                                values.extend([""] * (len(preview["columns"]) - len(values)))
                            if len(values) > len(preview["columns"]):
                                values = values[: len(preview["columns"])]
                            copy.write_row((*values, path.name, row_number))
                            loaded_rows = row_number
                            if row_number % 100000 == 0:
                                print(f"  loaded rows: {row_number:,}")
            elapsed = time.perf_counter() - start
            print(f"  loaded rows: {loaded_rows:,}")
            print(f"  elapsed: {elapsed:.2f}s")
        except Exception as exc:  # pragma: no cover - runtime only
            raise SystemExit(f"Database load failed for {path.name}: {exc}")

    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        raise SystemExit(1)
