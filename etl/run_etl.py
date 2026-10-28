#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import json
import subprocess
import sys
from datetime import date
from pathlib import Path

from build_clean import (
    build_clean_69b,
    build_clean_contratos,
    build_clean_proveedores,
    build_coincidencias_69b,
    ensure_clean_tables,
)
from build_staging import (
    build_staging_69b,
    build_staging_contracts,
    ensure_stage_tables,
)
from db_config import connect_database, connect_database_admin


ETL_DIR = Path(__file__).resolve().parent
REPO_ROOT = ETL_DIR.parent
SEED_PATH = ETL_DIR / "seeds" / "map_tipo_procedimiento.csv"
SCHEMA_SQL = ETL_DIR / "sql" / "06_fase4b_schema.sql"
TRANSFORM_SQL = ETL_DIR / "sql" / "07_fase4b_transform.sql"
EXTENSION_SQL = ETL_DIR / "sql" / "00_extensions.sql"

COMPRASMX_EXPECTED = {
    "adjudicacion_directa": 58868,
    "invitacion_tres_personas": 5402,
    "licitacion_publica": 17307,
    "otro": 49,
    "sin_dato": 3050,
}


def parse_date(value: str) -> date:
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("Use el formato YYYY-MM-DD.") from exc


def load_seed() -> list[tuple[str, str, str, int, str]]:
    with SEED_PATH.open(encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        expected_columns = [
            "fuente",
            "prefijo",
            "tipo_normalizado",
            "prioridad",
            "estado",
        ]
        if reader.fieldnames != expected_columns:
            raise ValueError(f"El seed debe tener estas columnas: {expected_columns}")
        rows = [
            (
                row["fuente"],
                row["prefijo"],
                row["tipo_normalizado"],
                int(row["prioridad"]),
                row["estado"],
            )
            for row in reader
        ]
    if not rows or len({(row[0], row[1]) for row in rows}) != len(rows):
        raise ValueError("El seed debe tener reglas y no repetir fuente/prefijo.")
    if any(row[4] != "pendiente" for row in rows):
        raise ValueError("Las reglas iniciales deben permanecer en estado pendiente.")
    return rows


def ensure_unaccent() -> None:
    with connect_database() as conn:
        with conn.cursor() as cursor:
            cursor.execute(
                "SELECT EXISTS (SELECT 1 FROM pg_extension WHERE extname = 'unaccent')"
            )
            installed = cursor.fetchone()[0]
    if installed:
        return

    with connect_database_admin() as conn:
        with conn.cursor() as cursor:
            cursor.execute(EXTENSION_SQL.read_text(encoding="utf-8"))
    print("Instalada la extensión unaccent usando las credenciales de administrador.")


def load_raw_if_requested(input_dir: Path) -> None:
    subprocess.run(
        [
            sys.executable,
            str(ETL_DIR / "load_raw.py"),
            "--input-dir",
            str(input_dir),
        ],
        cwd=REPO_ROOT,
        check=True,
    )


def verify_source_reconciliation(cursor) -> None:
    cursor.execute(
        """
        WITH raw_counts AS (
            SELECT 'comprasmx'::text AS fuente, COUNT(*)::bigint AS filas
            FROM raw.contratos_comprasmx
            UNION ALL
            SELECT 'historico', COUNT(*)::bigint
            FROM raw.compranet_historico
        ),
        output_counts AS (
            SELECT fuente, COUNT(*)::bigint AS filas
            FROM clean.contratos
            GROUP BY fuente
            UNION ALL
            SELECT fuente, COUNT(*)::bigint
            FROM clean.contratos_excluidos
            GROUP BY fuente
        ),
        summarized AS (
            SELECT fuente, SUM(filas)::bigint AS filas
            FROM output_counts
            GROUP BY fuente
        )
        SELECT r.fuente, r.filas AS raw_filas, COALESCE(o.filas, 0) AS clean_mas_excluidos
        FROM raw_counts AS r
        LEFT JOIN summarized AS o USING (fuente)
        WHERE r.filas <> COALESCE(o.filas, 0)
        ORDER BY r.fuente
        """
    )
    mismatches = cursor.fetchall()
    if mismatches:
        raise RuntimeError(f"No se cumple raw = clean + excluidos: {mismatches}")

    cursor.execute(
        """
        WITH raw_labels AS (
            SELECT 'historico'::text AS fuente, tipo_expediente AS etiqueta
            FROM raw.compranet_historico
            UNION ALL
            SELECT 'comprasmx', tipo_procedimiento
            FROM raw.contratos_comprasmx
        ),
        raw_normalized AS (
            SELECT
                fuente,
                UPPER(UNACCENT(REGEXP_REPLACE(
                    COALESCE(BTRIM(etiqueta), ''),
                    '^(V[0-9]{8}\\s+)?([0-9]+\\.\\s*)?',
                    ''
                ))) AS etiqueta
            FROM raw_labels
        ),
        raw_classified AS (
            SELECT
                r.fuente,
                CASE
                    WHEN r.etiqueta IN ('', 'SIN DATO') THEN 'sin_dato'
                    ELSE COALESCE(m.tipo_normalizado, 'otro')
                END AS tipo_procedimiento_norm,
                COUNT(*)::bigint AS filas
            FROM raw_normalized AS r
            LEFT JOIN LATERAL (
                SELECT tipo_normalizado
                FROM clean.map_tipo_procedimiento AS m
                WHERE m.fuente = r.fuente
                  AND LEFT(r.etiqueta, LENGTH(m.prefijo)) = m.prefijo
                ORDER BY m.prioridad, LENGTH(m.prefijo) DESC, m.prefijo
                LIMIT 1
            ) AS m ON TRUE
            GROUP BY r.fuente, 2
        ),
        clean_classified AS (
            SELECT fuente, tipo_procedimiento_norm, COUNT(*)::bigint AS filas
            FROM (
                SELECT fuente, tipo_procedimiento_norm FROM clean.contratos
                UNION ALL
                SELECT fuente, tipo_procedimiento_norm FROM clean.contratos_excluidos
            ) AS output_rows
            GROUP BY fuente, tipo_procedimiento_norm
        )
        SELECT
            COALESCE(r.fuente, c.fuente) AS fuente,
            COALESCE(r.tipo_procedimiento_norm, c.tipo_procedimiento_norm) AS tipo_procedimiento_norm,
            COALESCE(r.filas, 0) AS raw_filas,
            COALESCE(c.filas, 0) AS clean_mas_excluidos
        FROM raw_classified AS r
        FULL OUTER JOIN clean_classified AS c
            USING (fuente, tipo_procedimiento_norm)
        WHERE COALESCE(r.filas, 0) <> COALESCE(c.filas, 0)
        ORDER BY 1, 2
        """
    )
    type_mismatches = cursor.fetchall()
    if type_mismatches:
        raise RuntimeError(
            "No se cumple raw = clean + excluidos por tipo de procedimiento: "
            f"{type_mismatches}"
        )


def verify_clean_metadata(cursor) -> None:
    cursor.execute(
        """
        SELECT COUNT(*)
        FROM pg_class AS c
        JOIN pg_namespace AS n ON n.oid = c.relnamespace
        LEFT JOIN pg_description AS d ON d.objoid = c.oid AND d.objsubid = 0
        WHERE n.nspname = 'clean'
          AND c.relkind IN ('r', 'v', 'm', 'p')
          AND d.description IS NULL
        """
    )
    missing_object_comments = cursor.fetchone()[0]
    cursor.execute(
        """
        SELECT COUNT(*)
        FROM pg_attribute AS a
        JOIN pg_class AS c ON c.oid = a.attrelid
        JOIN pg_namespace AS n ON n.oid = c.relnamespace
        LEFT JOIN pg_description AS d ON d.objoid = a.attrelid AND d.objsubid = a.attnum
        WHERE n.nspname = 'clean'
          AND c.relkind IN ('r', 'v', 'm', 'p')
          AND a.attnum > 0
          AND NOT a.attisdropped
          AND d.description IS NULL
        """
    )
    missing_column_comments = cursor.fetchone()[0]
    if missing_object_comments or missing_column_comments:
        raise RuntimeError(
            "Faltan comentarios de clean: "
            f"{missing_object_comments} objetos y {missing_column_comments} columnas."
        )

    cursor.execute(
        """
        SELECT
            has_schema_privilege('agent_ro', 'clean', 'USAGE'),
            has_table_privilege('agent_ro', 'clean.contratos', 'SELECT'),
            has_table_privilege('agent_ro', 'clean.contratos_excluidos', 'SELECT'),
            has_table_privilege('agent_ro', 'clean.v_contratos_agente', 'SELECT'),
            has_table_privilege('agent_ro', 'clean.v_cobertura_fuentes', 'SELECT')
        """
    )
    if not all(cursor.fetchone()):
        raise RuntimeError("agent_ro no tiene los permisos SELECT/USAGE previstos en clean.")


def print_verification(cursor, stage_metrics: dict, clean_metrics: dict) -> None:
    cursor.execute(
        """
        SELECT fuente, tipo_procedimiento_norm, COUNT(*)::bigint AS filas
        FROM (
            SELECT fuente, tipo_procedimiento_norm FROM clean.contratos
            UNION ALL
            SELECT fuente, tipo_procedimiento_norm FROM clean.contratos_excluidos
        ) AS all_rows
        GROUP BY fuente, tipo_procedimiento_norm
        ORDER BY fuente, tipo_procedimiento_norm
        """
    )
    categories = [
        {"fuente": row[0], "tipo_procedimiento_norm": row[1], "filas": row[2]}
        for row in cursor.fetchall()
    ]
    cursor.execute(
        """
        SELECT fuente, etiqueta, filas
        FROM clean.v_tipos_procedimiento_sin_regla
        ORDER BY fuente, filas DESC, etiqueta
        """
    )
    unmatched = [
        {"fuente": row[0], "etiqueta": row[1], "filas": row[2]}
        for row in cursor.fetchall()
    ]
    cursor.execute(
        """
        SELECT fecha_inicio_estado, COUNT(*)::bigint
        FROM clean.contratos
        GROUP BY fecha_inicio_estado
        ORDER BY fecha_inicio_estado
        """
    )
    date_states = [
        {"estado": row[0], "filas": row[1]} for row in cursor.fetchall()
    ]
    cursor.execute(
        """
        SELECT fecha_inicio_maxima, fecha_descarga
        FROM clean.config_calidad
        WHERE id = 1
        """
    )
    date_config = cursor.fetchone()
    print(json.dumps({
        "staging": stage_metrics,
        "clean": clean_metrics,
        "configuracion_fechas": {
            "fecha_inicio_maxima": date_config[0].isoformat(),
            "fecha_descarga": date_config[1].isoformat(),
        },
        "clasificacion_por_fuente_y_tipo": categories,
        "etiquetas_sin_regla": unmatched,
        "fechas_inicio_por_estado": date_states,
    }, ensure_ascii=False, indent=2, default=str))


def run(args: argparse.Namespace) -> int:
    seed_rows = load_seed()
    if args.fecha_inicio_maxima and args.fecha_inicio_maxima < date(2010, 1, 1):
        raise ValueError("fecha-inicio-maxima no puede ser anterior a 2010-01-01.")
    if args.load_raw:
        load_raw_if_requested(args.input_dir)

    ensure_unaccent()

    with connect_database() as conn:
        ensure_stage_tables(conn)
        with conn.cursor() as cursor:
            cursor.execute(
                "TRUNCATE staging.contratos, staging.listado_69b, staging.rechazados"
            )
        stage_metrics = build_staging_contracts(conn)
        stage_69b_metrics = build_staging_69b(conn)
        stage_metrics["listado_69b"] = stage_69b_metrics["staged_69b"]

        with conn.transaction():
            ensure_clean_tables(conn)
            with conn.cursor() as cursor:
                cursor.execute("DELETE FROM clean.map_tipo_procedimiento")
                cursor.executemany(
                    """
                    INSERT INTO clean.map_tipo_procedimiento
                        (fuente, prefijo, tipo_normalizado, prioridad, estado)
                    VALUES (%s, %s, %s, %s, %s)
                    """,
                    seed_rows,
                )
                if args.fecha_inicio_maxima:
                    cursor.execute(
                        """
                        UPDATE clean.config_calidad
                        SET fecha_inicio_maxima = %s,
                            fecha_descarga = %s,
                            updated_at = NOW()
                        WHERE id = 1
                        """,
                        (args.fecha_inicio_maxima, args.fecha_descarga),
                    )
                else:
                    cursor.execute(
                        """
                        UPDATE clean.config_calidad
                        SET fecha_descarga = %s, updated_at = NOW()
                        WHERE id = 1
                        """,
                        (args.fecha_descarga,),
                    )
                cursor.execute(
                    """
                    TRUNCATE clean.coincidencias_69b, clean.listado_69b,
                        clean.contratos, clean.proveedores
                    """
                )

            providers = build_clean_proveedores(conn)
            contracts = build_clean_contratos(conn)
            sixty_nine = build_clean_69b(conn)
            matches = build_coincidencias_69b(conn)
            clean_metrics = {
                "proveedores_insertados": providers,
                "contratos_insertados": contracts,
                "listado_69b_insertados": sixty_nine,
                "coincidencias_69b": matches,
            }

            with conn.cursor() as cursor:
                cursor.execute(TRANSFORM_SQL.read_text(encoding="utf-8"))
                verify_source_reconciliation(cursor)
                verify_clean_metadata(cursor)

                cursor.execute(
                    """
                    SELECT tipo_procedimiento_norm, COUNT(*)::bigint
                    FROM (
                        SELECT tipo_procedimiento_norm
                        FROM clean.contratos
                        WHERE fuente = 'comprasmx'
                        UNION ALL
                        SELECT tipo_procedimiento_norm
                        FROM clean.contratos_excluidos
                        WHERE fuente = 'comprasmx'
                    ) AS comprasmx_rows
                    GROUP BY tipo_procedimiento_norm
                    """
                )
                comprasmx_categories = dict(cursor.fetchall())
                if comprasmx_categories != COMPRASMX_EXPECTED:
                    raise RuntimeError(
                        "Los conteos de ComprasMX no coinciden con los valores confirmados: "
                        f"esperado={COMPRASMX_EXPECTED}, actual={comprasmx_categories}"
                    )

                print_verification(cursor, stage_metrics, clean_metrics)
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Ejecuta staging, reconstruye clean y aplica la Fase 4B."
    )
    parser.add_argument(
        "--fecha-descarga",
        type=parse_date,
        required=True,
        help="Fecha real de descarga de los CSV (YYYY-MM-DD), no la fecha de carga a la BD.",
    )
    parser.add_argument(
        "--fecha-inicio-maxima",
        type=parse_date,
        default=None,
        help="Actualiza el límite superior inclusivo; por defecto conserva el valor de clean.config_calidad.",
    )
    parser.add_argument(
        "--input-dir",
        type=Path,
        default=REPO_ROOT / "data" / "raw",
        help="Directorio de fuentes CSV, usado con --load-raw.",
    )
    parser.add_argument(
        "--load-raw",
        action="store_true",
        help="Recarga raw desde --input-dir antes de ejecutar el resto del ETL.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Valida argumentos, seed y archivos SQL sin modificar la base de datos.",
    )
    args = parser.parse_args()

    if args.fecha_inicio_maxima and args.fecha_inicio_maxima < date(2010, 1, 1):
        parser.error("--fecha-inicio-maxima no puede ser anterior a 2010-01-01.")
    if args.dry_run:
        seed_rows = load_seed()
        missing = [
            path for path in (SCHEMA_SQL, TRANSFORM_SQL, EXTENSION_SQL) if not path.is_file()
        ]
        if missing:
            raise FileNotFoundError(f"Faltan archivos SQL: {missing}")
        print(
            f"dry-run correcto: seed con {len(seed_rows)} reglas; "
            f"descarga={args.fecha_descarga}; sin escrituras a la BD"
        )
        return 0

    return run(args)


if __name__ == "__main__":
    raise SystemExit(main())
