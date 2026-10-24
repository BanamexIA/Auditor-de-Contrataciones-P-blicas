#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import re
import unicodedata

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


def normalize_provider(value: object) -> str:
    text = normalize_text(value).upper()
    text = unicodedata.normalize("NFKD", text)
    text = "".join(ch for ch in text if unicodedata.category(ch) != "Mn")
    text = text.replace("&", " Y ")
    text = re.sub(r"[^A-Z0-9 ]+", " ", text)
    text = re.sub(r"\b(S\.?A\.?|SOCIEDAD ANONIMA|S\.? DE R\.?L\.?|S\.? DE C\.?V\.?|DE C\.?V\.?|SA DE CV|S\.?R\.?L\.?|S\.?C\.?|SC|SRL)\b", "", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


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


def ensure_clean_tables(conn) -> None:
    with conn.cursor() as cursor:
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS clean.proveedores (
                proveedor TEXT,
                proveedor_normalizado TEXT,
                fuente TEXT,
                created_at TIMESTAMPTZ DEFAULT NOW(),
                PRIMARY KEY (proveedor_normalizado)
            );
            """
        )
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS clean.contratos (
                codigo_contrato TEXT,
                codigo_expediente TEXT,
                rfc TEXT,
                proveedor TEXT,
                proveedor_normalizado TEXT,
                titulo_contrato TEXT,
                descripcion_contrato TEXT,
                contract_type TEXT,
                tipo_contratacion TEXT,
                tipo_expediente TEXT,
                importe NUMERIC,
                moneda TEXT,
                fecha_inicio DATE,
                fecha_fin DATE,
                _source_file TEXT,
                _loaded_at TIMESTAMPTZ
            );
            """
        )
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS clean.listado_69b (
                rfc TEXT,
                nombre_del_contribuyente TEXT,
                situacion_del_contribuyente TEXT,
                _source_file TEXT,
                _loaded_at TIMESTAMPTZ
            );
            """
        )
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS clean.coincidencias_69b (
                codigo_contrato TEXT,
                rfc_exacto BOOLEAN,
                nombre_normalizado_exacto BOOLEAN,
                nivel_confianza TEXT,
                requiere_revision_humana BOOLEAN,
                proveedor TEXT,
                rfc TEXT,
                nombre_del_contribuyente TEXT,
                created_at TIMESTAMPTZ DEFAULT NOW()
            );
            """
        )
    conn.commit()


def build_clean_contratos(conn) -> int:
    with conn.cursor() as cursor:
        cursor.execute(
            """
            INSERT INTO clean.contratos (
                codigo_contrato,
                codigo_expediente,
                rfc,
                proveedor,
                proveedor_normalizado,
                titulo_contrato,
                descripcion_contrato,
                contract_type,
                tipo_contratacion,
                tipo_expediente,
                importe,
                moneda,
                fecha_inicio,
                fecha_fin,
                _source_file,
                _loaded_at
            )
            SELECT
                codigo_contrato,
                codigo_expediente,
                rfc,
                proveedor,
                proveedor_normalizado,
                titulo_contrato,
                descripcion_contrato,
                contract_type,
                tipo_contratacion,
                tipo_expediente,
                importe,
                moneda,
                fecha_inicio,
                fecha_fin,
                _source_file,
                _loaded_at
            FROM staging.contratos
            ON CONFLICT DO NOTHING
            """
        )
        inserted = cursor.rowcount
    conn.commit()
    return inserted


def build_clean_proveedores(conn) -> int:
    with conn.cursor() as cursor:
        cursor.execute(
            """
            INSERT INTO clean.proveedores (proveedor, proveedor_normalizado, fuente)
            SELECT DISTINCT proveedor, proveedor_normalizado, 'contratos_comprasmx' AS fuente
            FROM staging.contratos
            WHERE proveedor IS NOT NULL AND proveedor <> ''
            ON CONFLICT (proveedor_normalizado) DO NOTHING
            """
        )
        inserted = cursor.rowcount
    conn.commit()
    return inserted


def build_clean_69b(conn) -> int:
    with conn.cursor() as cursor:
        cursor.execute(
            """
            INSERT INTO clean.listado_69b (rfc, nombre_del_contribuyente, situacion_del_contribuyente, _source_file, _loaded_at)
            SELECT rfc, nombre_del_contribuyente, situacion_del_contribuyente, _source_file, _loaded_at
            FROM staging.listado_69b
            ON CONFLICT DO NOTHING
            """
        )
        inserted = cursor.rowcount
    conn.commit()
    return inserted


def build_coincidencias_69b(conn) -> int:
    with conn.cursor() as cursor:
        cursor.execute("SELECT rfc, nombre_del_contribuyente FROM clean.listado_69b")
        proveedores_69b = cursor.fetchall()
        cursor.execute("DELETE FROM clean.coincidencias_69b")

    by_rfc = {}
    by_name = {}
    for rfc, nombre in proveedores_69b:
        if rfc:
            by_rfc[rfc.upper()] = {"rfc": rfc, "nombre": nombre}
        if nombre:
            by_name[normalize_provider(nombre)] = {"rfc": rfc, "nombre": nombre}

    insert_sql = """
        INSERT INTO clean.coincidencias_69b (
            codigo_contrato,
            rfc_exacto,
            nombre_normalizado_exacto,
            nivel_confianza,
            requiere_revision_humana,
            proveedor,
            rfc,
            nombre_del_contribuyente
        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
    """
    inserted = 0
    rows = []
    with conn.cursor(name="clean_contracts_match") as source_cursor:
        source_cursor.execute(
            "SELECT codigo_contrato, rfc, proveedor, proveedor_normalizado FROM clean.contratos"
        )
        while True:
            contracts = source_cursor.fetchmany(5000)
            if not contracts:
                break
            for codigo_contrato, rfc, proveedor, proveedor_normalizado in contracts:
                nombre_norm = normalize_provider(proveedor_normalizado or proveedor or "")
                if rfc and rfc.upper() in by_rfc:
                    match = by_rfc[rfc.upper()]
                    rows.append((
                        codigo_contrato,
                        True,
                        False,
                        "alta",
                        False,
                        proveedor,
                        match["rfc"],
                        match["nombre"],
                    ))
                elif nombre_norm and nombre_norm in by_name:
                    match = by_name[nombre_norm]
                    rows.append((
                        codigo_contrato,
                        False,
                        True,
                        "media",
                        True,
                        proveedor,
                        match["rfc"],
                        match["nombre"],
                    ))
            if rows:
                with conn.cursor() as cursor:
                    cursor.executemany(insert_sql, rows)
                inserted += len(rows)
                rows.clear()
    if rows:
        with conn.cursor() as cursor:
            cursor.executemany(insert_sql, rows)
        inserted += len(rows)
    conn.commit()
    return inserted


def main() -> int:
    parser = argparse.ArgumentParser(description="Create clean tables from validated staging data.")
    parser.add_argument("--dry-run", action="store_true", help="Create the schema only; do not populate it.")
    args = parser.parse_args()

    try:
        conn = get_db_connection()
    except Exception as exc:  # pragma: no cover - runtime only
        raise SystemExit(f"Unable to connect to PostgreSQL: {exc}")

    with conn:
        ensure_clean_tables(conn)
        if args.dry_run:
            print("Clean schema ready; dry-run enabled, no data loaded into clean tables.")
            return 0

        with conn.cursor() as cursor:
            cursor.execute(
                "TRUNCATE clean.coincidencias_69b, clean.listado_69b, clean.contratos, clean.proveedores"
            )
        providers = build_clean_proveedores(conn)
        contracts = build_clean_contratos(conn)
        sixty_nine = build_clean_69b(conn)
        matches = build_coincidencias_69b(conn)

    print(json.dumps({
        "proveedores_insertados": providers,
        "contratos_insertados": contracts,
        "listado_69b_insertados": sixty_nine,
        "coincidencias_69b": matches,
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
