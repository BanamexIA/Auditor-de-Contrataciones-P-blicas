#!/usr/bin/env python3
from __future__ import annotations

import argparse
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
    data = path.read_bytes()
    encodings = ["utf-8-sig", "utf-8", "cp1252", "latin-1", "iso-8859-1"]
    for encoding in encodings:
        try:
            data.decode(encoding)
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

    for delimiter in delimiters:
        score = 0
        with path.open("r", encoding=encoding, newline="") as handle:
            for row in csv.reader(handle, delimiter=delimiter):
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


def parse_header(header: list[str], table_key: str) -> list[str]:
    columns: list[str] = []
    seen: set[str] = set()
    for index, cell in enumerate(header):
        candidate = normalize_identifier(cell)
        if not candidate:
            candidate = f"col_{index + 1}"
        if candidate in seen:
            candidate = f"{candidate}_{index + 1}"
        columns.append(candidate)
        seen.add(candidate)
    if table_key == "contratos_comprasmx":
        for known in EXPECTED_HEADERS[table_key]:
            if known not in columns:
                columns.append(known)
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
    return psycopg.connect(conninfo)


def build_create_table_sql(table_name: str, columns: list[str]) -> str:
    column_sql = ",\n  ".join(f"{sanitize_sql_identifier(col)} TEXT" for col in columns)
    sql = (
        f"CREATE TABLE IF NOT EXISTS raw.{table_name} (\n"
        f"  {column_sql},\n"
        "  _source_file TEXT,\n"
        "  _loaded_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),\n"
        "  _row_number BIGINT\n"
        ");"
    )
    return sql


def detect_csv_structure(path: Path, table_key: str) -> tuple[str, str, list[str], list[list[str]], int]:
    encoding = detect_best_encoding(path)
    delimiter = detect_delimiter(path, encoding)
    rows = list(iter_csv_rows(path, encoding, delimiter))
    if not rows:
        raise ValueError(f"No rows found in {path}")
    header_index, header = find_header_row(rows, table_key)
    data_rows = rows[max(0, header_index + 1):]
    return encoding, delimiter, parse_header(header, table_key), data_rows, len(data_rows)


def copy_rows_to_db(table_name: str, columns: list[str], rows: list[list[str]], source_file: str) -> int:
    conn = get_db_connection()
    columns_sql = ", ".join(sanitize_sql_identifier(col) for col in columns)
    copy_target = f"raw.{table_name} ({columns_sql}, _source_file, _row_number)"
    buffer = io.StringIO()
    writer = csv.writer(buffer, lineterminator="\n")
    for row_number, row in enumerate(rows, start=1):
        values = [cell.strip() if isinstance(cell, str) else cell for cell in row]
        if len(values) < len(columns):
            values = values + [""] * (len(columns) - len(values))
        if len(values) > len(columns):
            values = values[:len(columns)]
        writer.writerow(values + [source_file, row_number])
    buffer.seek(0)
    with conn.cursor() as cursor:
        cursor.execute(f"TRUNCATE TABLE raw.{table_name};")
        cursor.copy_expert(
            f"COPY {copy_target} FROM STDIN WITH CSV",
            buffer,
        )
    conn.commit()
    conn.close()
    return len(rows)


def detect_and_prepare_file(path: Path) -> dict:
    table_key = "contratos_comprasmx" if "contratos" in path.name.lower() else "listado_69b"
    encoding = detect_best_encoding(path)
    delimiter = detect_delimiter(path, encoding)
    rows = list(iter_csv_rows(path, encoding, delimiter))
    if not rows:
        raise ValueError(f"No readable rows found in {path}")

    header_index = -1
    header = []
    for index, row in enumerate(rows):
        norm_row = [normalize_identifier(cell) for cell in row]
        known_values = [
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
            "rfc",
            "razon_social",
            "nombre",
            "nombre_del_contribuyente",
            "situacion_del_contribuyente",
            "no",
        ]
        if any(value in norm_row for value in known_values):
            header = row
            header_index = index
            break
    if header_index < 0:
        header = rows[0]
        header_index = 0
    columns = parse_header(header, table_key)
    data_rows = rows[header_index + 1:]
    return {
        "table_key": table_key,
        "encoding": encoding,
        "delimiter": delimiter,
        "columns": columns,
        "rows": data_rows,
        "header_index": header_index,
        "total_rows": len(data_rows),
    }


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
        table_key = "contratos_comprasmx" if "contratos" in path.name.lower() else "listado_69b"
        preview = detect_and_prepare_file(path)
        print(f"FILE: {path.name}")
        print(f"  table: raw.{get_table_name(path.name)}")
        print(f"  encoding: {preview['encoding']}")
        print(f"  delimiter: {preview['delimiter']!r}")
        print(f"  columns: {len(preview['columns'])}")
        print(f"  data rows: {preview['total_rows']}")
        if args.dry_run:
            print("  DRY RUN: no database write performed")
            continue

        table_name = get_table_name(path.name)
        if psycopg is None:
            raise SystemExit("psycopg is required to load data. Install project dependencies first.")

        try:
            start = time.perf_counter()
            conn = get_db_connection()
            with conn.cursor() as cursor:
                cursor.execute(build_create_table_sql(table_name, preview["columns"]))
                cursor.execute(f"TRUNCATE TABLE raw.{table_name};")
                buffer = io.StringIO()
                writer = csv.writer(buffer, lineterminator="\n")
                for row_number, row in enumerate(preview["rows"], start=1):
                    values = [cell.strip() if isinstance(cell, str) else cell for cell in row]
                    if len(values) < len(preview["columns"]):
                        values = values + [""] * (len(preview["columns"]) - len(values))
                    if len(values) > len(preview["columns"]):
                        values = values[:len(preview["columns"])]
                    writer.writerow(values + [path.name, row_number])
                buffer.seek(0)
                cursor.copy_expert(
                    f"COPY raw.{table_name} ({', '.join(sanitize_sql_identifier(col) for col in preview['columns'])}, _source_file, _row_number) FROM STDIN WITH CSV",
                    buffer,
                )
            conn.commit()
            conn.close()
            elapsed = time.perf_counter() - start
            print(f"  loaded rows: {preview['total_rows']}")
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
