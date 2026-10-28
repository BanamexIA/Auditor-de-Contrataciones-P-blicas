#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import re
import unicodedata
from datetime import datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path

try:
    import psycopg
except ImportError:  # pragma: no cover - runtime dependency
    psycopg = None

from db_config import load_database_environment

load_database_environment()


def normalize_text(value: object) -> str:
    if value is None:
        return ""
    text = unicodedata.normalize("NFKC", str(value)).strip()
    return re.sub(r"\s+", " ", text)


def optional_text(value: object) -> str | None:
    text = normalize_text(value)
    return text or None


def normalize_provider(value: object) -> str:
    text = normalize_text(value).upper()
    text = unicodedata.normalize("NFKD", text)
    text = "".join(ch for ch in text if unicodedata.category(ch) != "Mn")
    text = text.replace("&", " Y ")
    text = re.sub(r"[^A-Z0-9 ]+", " ", text)
    text = re.sub(r"\b(S\.?A\.?|SOCIEDAD ANONIMA|S\.? DE R\.?L\.?|S\.? DE C\.?V\.?|DE C\.?V\.?|SA DE CV|S\.?R\.?L\.?|S\.?C\.?|SC|SRL)\b", "", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def clean_decimal(value: object) -> Decimal | None:
    raw = normalize_text(value)
    if raw == "":
        return None
    normalized = raw.replace("$", "").replace(",", "")
    normalized = normalized.replace("(", "-").replace(")", "")
    normalized = normalized.replace(" ", "")
    try:
        return Decimal(normalized)
    except InvalidOperation:
        return None


def clean_date(value: object) -> datetime.date | None:
    raw = normalize_text(value)
    if raw == "":
        return None
    patterns = [
        "%Y-%m-%d",
        "%d/%m/%Y",
        "%d-%m-%Y",
        "%Y/%m/%d",
        "%m/%d/%Y",
        "%d.%m.%Y",
        "%Y-%m-%d %H:%M:%S",
        "%d/%m/%Y %H:%M:%S",
    ]
    for pattern in patterns:
        try:
            return datetime.strptime(raw, pattern).date()
        except ValueError:
            continue
    try:
        return datetime.fromisoformat(raw.replace("Z", "+00:00")).date()
    except ValueError:
        pass
    return None


def fecha_inicio_estado(raw_value: object, parsed_value: datetime.date | None) -> str:
    if not normalize_text(raw_value) or normalize_text(raw_value).casefold() == "sin dato":
        return "nula"
    if parsed_value is None:
        return "no_parseable"
    return "valida"


def get_db_connection():
    if psycopg is None:
        raise RuntimeError("psycopg is required. Install dependencies from requirements.txt.")
    password = os.getenv("DB_PASSWORD") or os.getenv("POSTGRES_PASSWORD") or "postgres"
    user = os.getenv("DB_USER") or os.getenv("POSTGRES_USER") or "postgres"
    host = os.getenv("DB_HOST") or "localhost"
    port = os.getenv("DB_PORT") or os.getenv("DB_PORT_HOST") or "5432"
    db_name = os.getenv("DB_NAME") or os.getenv("POSTGRES_DB") or "auditor_contrataciones"
    conninfo = f"dbname={db_name} user={user} password={password} host={host} port={port}"
    return psycopg.connect(conninfo)


def ensure_stage_tables(conn) -> None:
    with conn.cursor() as cursor:
        sql_path = Path(__file__).resolve().parent / "sql" / "03_staging.sql"
        cursor.execute(sql_path.read_text(encoding="utf-8"))
    conn.commit()


def identifier_sql(value: str) -> str:
    return '"' + value.replace('"', '""') + '"'


def mapped_value(record: dict, *names: str) -> object:
    for name in names:
        value = record.get(name)
        if value is not None:
            return value
    return None


def build_staging_contracts(conn, limit: int | None = None) -> dict:
    with conn.cursor() as cursor:
        cursor.execute(
            "SELECT tablename FROM pg_tables WHERE schemaname = 'raw' AND tablename <> 'listado_69b' ORDER BY tablename"
        )
        table_names = [row[0] for row in cursor.fetchall()]

    staged_total = 0
    rejected_total = 0
    for table_index, table_name in enumerate(table_names):
        table_staged = 0
        table_rejected = 0
        limit_sql = f" LIMIT {int(limit)}" if limit is not None else ""
        with conn.cursor(name=f"raw_contracts_{table_index}") as source_cursor:
            source_cursor.execute(
                f"SELECT * FROM raw.{identifier_sql(table_name)} ORDER BY _row_number{limit_sql}"
            )
            columns = [desc[0] for desc in source_cursor.description]
            staged_batch = []
            rejected_batch = []
            while True:
                rows = source_cursor.fetchmany(5000)
                if not rows:
                    break
                for row in rows:
                    record = dict(zip(columns, row))
                    raw_amount = mapped_value(record, "importe", "importe_drc", "monto_sin_imp_maximo")
                    raw_start = mapped_value(
                        record,
                        "fecha_inicio",
                        "fecha_de_inicio_del_contrato",
                        "fecha_de_inicio",
                    )
                    raw_end = mapped_value(
                        record,
                        "fecha_fin",
                        "fecha_de_fin_del_contrato",
                        "fecha_de_fin",
                    )
                    importe = clean_decimal(raw_amount)
                    fecha_inicio = clean_date(raw_start)
                    fecha_fin = clean_date(raw_end)
                    errors = []
                    if normalize_text(raw_amount) and importe is None:
                        errors.append("importe_invalido")
                    if errors:
                        rejected_batch.append(
                            (table_name, ",".join(errors), json.dumps(record, default=str))
                        )
                        continue

                    proveedor = normalize_text(mapped_value(record, "proveedor", "proveedor_o_contratista"))
                    staged_batch.append(
                        (
                            normalize_text(mapped_value(record, "codigo_contrato", "codigo_del_contrato")),
                            normalize_text(mapped_value(record, "codigo_expediente", "codigo_del_expediente")),
                            normalize_text(mapped_value(record, "rfc")),
                            proveedor,
                            normalize_text(mapped_value(record, "titulo_contrato", "titulo_del_contrato")),
                            normalize_text(mapped_value(record, "descripcion_contrato", "descripcion_del_contrato")),
                            normalize_text(mapped_value(record, "contract_type", "tipo_de_contrato")),
                            normalize_text(mapped_value(record, "tipo_contratacion", "tipo_de_contratacion")),
                            normalize_text(mapped_value(record, "tipo_expediente", "tipo_de_expediente")),
                            importe,
                            normalize_text(mapped_value(record, "moneda")),
                            fecha_inicio,
                            fecha_fin,
                            fecha_inicio_estado(raw_start, fecha_inicio),
                            optional_text(mapped_value(record, "tipo_procedimiento")),
                            optional_text(mapped_value(record, "ley")),
                            optional_text(mapped_value(record, "institucion")),
                            optional_text(mapped_value(record, "clave_institucion")),
                            optional_text(mapped_value(record, "siglas_de_la_institucion")),
                            optional_text(mapped_value(record, "tipo_de_institucion")),
                            optional_text(mapped_value(record, "clave_ramo")),
                            optional_text(mapped_value(record, "descripcion_ramo")),
                            optional_text(mapped_value(record, "clave_de_la_uc")),
                            optional_text(mapped_value(record, "nombre_de_la_uc")),
                            optional_text(mapped_value(record, "numero_de_procedimiento")),
                            optional_text(mapped_value(record, "caracter_del_procedimiento")),
                            optional_text(mapped_value(record, "articulo_de_excepcion")),
                            optional_text(mapped_value(record, "descripcion_excepcion")),
                            "comprasmx" if table_name == "contratos_comprasmx" else "historico",
                            normalize_provider(proveedor),
                            record.get("_source_file"),
                        )
                    )

                with conn.cursor() as cursor:
                    if staged_batch:
                        cursor.executemany(
                            """
                            INSERT INTO staging.contratos (
                                codigo_contrato, codigo_expediente, rfc, proveedor,
                                titulo_contrato, descripcion_contrato, contract_type,
                                tipo_contratacion, tipo_expediente, importe, moneda,
                                fecha_inicio, fecha_fin, fecha_inicio_estado,
                                tipo_procedimiento, ley, institucion, clave_institucion,
                                siglas_de_la_institucion, tipo_de_institucion, clave_ramo,
                                descripcion_ramo, clave_de_la_uc, nombre_de_la_uc,
                                numero_de_procedimiento, caracter_del_procedimiento,
                                articulo_de_excepcion, descripcion_excepcion, fuente,
                                proveedor_normalizado, _source_file
                            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                            """,
                            staged_batch,
                        )
                    if rejected_batch:
                        cursor.executemany(
                            """
                            INSERT INTO staging.rechazados (source_table, motivo, raw_payload)
                            VALUES (%s, %s, %s::jsonb)
                            """,
                            rejected_batch,
                        )
                staged_total += len(staged_batch)
                rejected_total += len(rejected_batch)
                table_staged += len(staged_batch)
                table_rejected += len(rejected_batch)
                staged_batch.clear()
                rejected_batch.clear()
        print(
            f"  {table_name}: {table_staged:,} staged; {table_rejected:,} rejected "
            f"(total: {staged_total:,} staged; {rejected_total:,} rejected)"
        )

    conn.commit()
    return {"staged_contracts": staged_total, "rejections": rejected_total}


def build_staging_69b(conn, limit: int | None = None) -> dict:
    with conn.cursor() as cursor:
        limit_sql = f" LIMIT {int(limit)}" if limit is not None else ""
        cursor.execute(f"SELECT * FROM raw.listado_69b ORDER BY _row_number{limit_sql}")
        rows = cursor.fetchall()
        columns = [desc[0] for desc in cursor.description]

    stage_rows = []
    for row in rows:
        record = dict(zip(columns, row))
        stage_rows.append(
            (
                normalize_text(mapped_value(record, "rfc")),
                normalize_text(mapped_value(record, "nombre_del_contribuyente", "nombre_o_razon_social")),
                normalize_text(mapped_value(record, "situacion_del_contribuyente")),
                record.get("_source_file"),
            )
        )

    with conn.cursor() as cursor:
        if stage_rows:
            cursor.executemany(
                "INSERT INTO staging.listado_69b (rfc, nombre_del_contribuyente, situacion_del_contribuyente, _source_file) VALUES (%s, %s, %s, %s)",
                stage_rows,
            )
    conn.commit()
    return {"staged_69b": len(stage_rows)}


def main() -> int:
    parser = argparse.ArgumentParser(description="Normalize raw CSV loads into staging tables with basic validation.")
    parser.add_argument("--limit", type=int, default=None, help="Optional row cap for preview runs.")
    parser.add_argument("--dry-run", action="store_true", help="Validate database connectivity only; does not write staging data.")
    args = parser.parse_args()

    try:
        conn = get_db_connection()
    except Exception as exc:  # pragma: no cover - runtime only
        raise SystemExit(f"Unable to connect to PostgreSQL: {exc}")

    with conn:
        ensure_stage_tables(conn)
        if args.dry_run:
            print("Staging schema ready; dry-run enabled, no data copied into staging tables.")
            return 0

        with conn.cursor() as cursor:
            cursor.execute("TRUNCATE staging.contratos, staging.listado_69b, staging.rechazados")
        contract_metrics = build_staging_contracts(conn, limit=args.limit)
        sixnine_metrics = build_staging_69b(conn, limit=args.limit)

    print(json.dumps({"contratos": contract_metrics, "listado_69b": sixnine_metrics}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
