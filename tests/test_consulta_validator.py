import re
import unittest
from pathlib import Path

import yaml

from agents.consulta.validator import (
    MAX_SQL_ROWS,
    VIEW_COLUMNS,
    SQLValidationError,
    add_missing_limit,
    extract_sql,
    is_single_select,
    validate_sql,
)


ROOT = Path(__file__).resolve().parents[1]
CONTRATOS = "clean.v_contratos_agente"
COINCIDENCIAS = "clean.v_coincidencias_69b_agente"


class AcceptedQueriesTests(unittest.TestCase):
    def assert_accepted(self, query):
        self.assertTrue(validate_sql(query))

    def test_accepts_aggregation_over_an_approved_view(self):
        self.assert_accepted(
            f"SELECT fuente, COUNT(*) AS contratos FROM {CONTRATOS} GROUP BY fuente LIMIT 20"
        )

    def test_accepts_join_between_approved_views(self):
        self.assert_accepted(
            f"SELECT c.fuente, COUNT(DISTINCT c.codigo_contrato) AS contratos "
            f"FROM {COINCIDENCIAS} AS m JOIN {CONTRATOS} AS c "
            f"ON c.codigo_contrato = m.codigo_contrato GROUP BY c.fuente LIMIT 20"
        )

    def test_accepts_subquery_over_an_approved_view(self):
        self.assert_accepted(
            f"SELECT fuente, total FROM (SELECT fuente, COUNT(*) AS total "
            f"FROM {CONTRATOS} GROUP BY fuente) AS t LIMIT 5"
        )

    def test_accepts_filtered_aggregates_and_offset(self):
        self.assert_accepted(
            f"SELECT COUNT(*) FILTER (WHERE tipo_procedimiento_norm = 'adjudicacion_directa') "
            f"AS adjudicaciones FROM {CONTRATOS} LIMIT 10 OFFSET 5"
        )

    def test_accepts_unquoted_uppercase_names(self):
        self.assert_accepted("SELECT * FROM CLEAN.V_CONTRATOS_AGENTE LIMIT 1")

    def test_accepts_limit_at_the_maximum(self):
        self.assert_accepted(f"SELECT * FROM {CONTRATOS} LIMIT {MAX_SQL_ROWS}")


class RejectedQueriesTests(unittest.TestCase):
    def assert_rejected(self, query, message):
        with self.assertRaisesRegex(SQLValidationError, message):
            validate_sql(query)

    def test_rejects_statements_that_are_not_select(self):
        self.assert_rejected(f"DELETE FROM {CONTRATOS}", "Solo se permiten")
        self.assert_rejected(f"EXPLAIN ANALYZE SELECT * FROM {CONTRATOS} LIMIT 1", "Solo se permiten")
        self.assert_rejected(f"COPY (SELECT * FROM {CONTRATOS}) TO '/tmp/x'", "Solo se permiten")
        self.assert_rejected(
            f"SELECT fuente FROM {CONTRATOS} UNION SELECT fuente FROM {CONTRATOS} LIMIT 5",
            "Solo se permiten",
        )

    def test_rejects_multiple_statements(self):
        self.assert_rejected(
            f"SELECT * FROM {CONTRATOS} LIMIT 1; DROP TABLE clean.contratos", "exactamente una"
        )

    def test_rejects_unparseable_sql(self):
        self.assert_rejected("SELECT FROM WHERE", "SQL no válido")

    def test_rejects_write_hidden_in_a_cte(self):
        self.assert_rejected(
            f"WITH x AS (DELETE FROM {CONTRATOS} RETURNING *) SELECT * FROM x LIMIT 1",
            "modifiquen datos",
        )

    def test_rejects_read_only_cte_with_a_clear_message(self):
        self.assert_rejected(
            f"WITH x AS (SELECT fuente FROM {CONTRATOS}) SELECT * FROM x LIMIT 1", "CTE"
        )

    def test_rejects_select_into_and_row_locks(self):
        self.assert_rejected(f"SELECT * INTO clean.copia FROM {CONTRATOS} LIMIT 1", "INTO")
        self.assert_rejected(f"SELECT * FROM {CONTRATOS} FOR UPDATE LIMIT 1", "bloqueos")

    def test_rejects_tables_outside_the_approved_views(self):
        for query in (
            "SELECT * FROM clean.contratos LIMIT 1",
            "SELECT * FROM v_contratos_agente LIMIT 1",
            "SELECT * FROM raw.contratos_comprasmx LIMIT 1",
            "SELECT * FROM clean.v_cobertura_fuentes LIMIT 1",
            "SELECT * FROM pg_catalog.pg_tables LIMIT 1",
            "SELECT * FROM information_schema.tables LIMIT 1",
        ):
            with self.subTest(query=query):
                self.assert_rejected(query, "Tabla no permitida")

    def test_rejects_unapproved_tables_inside_subqueries_and_laterals(self):
        self.assert_rejected(
            f"SELECT * FROM {CONTRATOS} WHERE codigo_contrato IN "
            f"(SELECT codigo_contrato FROM clean.contratos) LIMIT 1",
            "Tabla no permitida",
        )
        self.assert_rejected(
            f"SELECT * FROM {CONTRATOS} AS a, LATERAL "
            f"(SELECT * FROM raw.contratos_comprasmx) AS b LIMIT 1",
            "Tabla no permitida",
        )

    def test_rejects_queries_that_read_no_approved_view(self):
        self.assert_rejected("SELECT 1 LIMIT 1", "al menos una vista")
        self.assert_rejected("SELECT * FROM (VALUES (1)) AS t(x) LIMIT 1", "al menos una vista")

    def test_rejects_unrecognized_and_system_functions(self):
        for function in (
            "pg_sleep(1)",
            "pg_read_file('/etc/passwd')",
            "current_setting('is_superuser')",
            "set_config('statement_timeout', '0', false)",
            "dblink('x', 'y')",
            "unaccent(institucion)",
            "RANK() OVER (ORDER BY fuente)",
        ):
            with self.subTest(function=function):
                self.assert_rejected(
                    f"SELECT {function} FROM {CONTRATOS} LIMIT 1", "funciones SQL no reconocidas"
                )

    def test_rejects_generate_series(self):
        self.assert_rejected(
            f"SELECT generate_series(1, 1000000000) FROM {CONTRATOS} LIMIT 1", "generate_series"
        )

    def test_rejects_missing_or_non_literal_limit(self):
        for query in (
            f"SELECT * FROM {CONTRATOS}",
            f"SELECT * FROM {CONTRATOS} LIMIT ALL",
            f"SELECT * FROM {CONTRATOS} LIMIT 10 + 5",
            f"SELECT * FROM {CONTRATOS} LIMIT '5'",
            f"SELECT * FROM {CONTRATOS} FETCH FIRST 5 ROWS ONLY",
        ):
            with self.subTest(query=query):
                self.assert_rejected(query, "LIMIT entero")

    def test_rejects_limit_out_of_range(self):
        self.assert_rejected(f"SELECT * FROM {CONTRATOS} LIMIT 0", "entre 1 y 200")
        self.assert_rejected(f"SELECT * FROM {CONTRATOS} LIMIT {MAX_SQL_ROWS + 1}", "entre 1 y 200")
        self.assert_rejected(f"SELECT * FROM {CONTRATOS} LIMIT 5.5", "entero literal")


class ColumnTests(unittest.TestCase):
    """A5, mejora 3: a column is checked against the view where the query looks for it."""

    def assert_rejected(self, query, *fragments):
        with self.assertRaises(SQLValidationError) as caught:
            validate_sql(query)
        for fragment in fragments:
            self.assertIn(fragment, str(caught.exception))

    def test_q07_column_in_the_wrong_view_points_to_the_join(self):
        # The SQL the model wrote for q07 on 2026-11-17; PostgreSQL rejected it.
        self.assert_rejected(
            f"SELECT fuente, COUNT(*) AS coincidencias FROM {CONTRATOS} "
            f"WHERE fuente IN ('comprasmx', 'historico') AND rfc_exacto = 'S' "
            f"GROUP BY fuente ORDER BY coincidencias DESC, fuente LIMIT 50",
            "rfc_exacto", f"está en {COINCIDENCIAS}", "JOIN por codigo_contrato",
        )

    def test_alias_of_the_wrong_view(self):
        self.assert_rejected(f"SELECT c.rfc_exacto FROM {CONTRATOS} AS c LIMIT 5", "rfc_exacto", COINCIDENCIAS)
        self.assert_rejected(
            f"SELECT c.rfc_exacto FROM {CONTRATOS} AS c JOIN {COINCIDENCIAS} AS m "
            f"ON m.codigo_contrato = c.codigo_contrato LIMIT 5",
            f"solo está en {COINCIDENCIAS}", "alias",
        )

    def test_an_alias_that_does_not_exist_is_named_as_the_problem(self):
        # q06 on 2026-11-19: alias t was never defined; the column itself exists.
        self.assert_rejected(
            f"SELECT c.fuente, t.tipo_procedimiento_norm, COUNT(*) FROM {CONTRATOS} AS c "
            f"GROUP BY c.fuente, t.tipo_procedimiento_norm LIMIT 100",
            "El alias t no corresponde", f"está en {CONTRATOS}",
        )

    def test_column_that_exists_in_no_view(self):
        self.assert_rejected(f"SELECT monto FROM {CONTRATOS} LIMIT 5", "monto", "no existe")

    def test_unqualified_column_present_in_both_joined_views(self):
        self.assert_rejected(
            f"SELECT proveedor FROM {CONTRATOS} AS c JOIN {COINCIDENCIAS} AS m "
            f"ON m.codigo_contrato = c.codigo_contrato LIMIT 5",
            "proveedor", "las dos vistas",
        )

    def test_accepts_valid_ways_to_name_columns(self):
        for query in (
            # Unqualified column that exists in only one of the joined views.
            f"SELECT fuente, COUNT(*) FROM {CONTRATOS} AS c JOIN {COINCIDENCIAS} AS m "
            f"ON m.codigo_contrato = c.codigo_contrato WHERE rfc_exacto GROUP BY fuente LIMIT 20",
            # Output aliases in GROUP BY and ORDER BY, and the view name as qualifier.
            f"SELECT EXTRACT(YEAR FROM fecha_inicio)::integer AS anio, COUNT(*) AS n FROM {CONTRATOS} "
            f"GROUP BY anio ORDER BY n DESC LIMIT 20",
            f"SELECT v_contratos_agente.fuente FROM {CONTRATOS} LIMIT 1",
            # Columns of a subquery and a correlated subquery.
            f"SELECT fuente, total FROM (SELECT fuente, COUNT(*) AS total FROM {CONTRATOS} "
            f"GROUP BY fuente) AS t LIMIT 5",
            f"SELECT c.codigo_contrato FROM {CONTRATOS} AS c WHERE EXISTS (SELECT 1 FROM {COINCIDENCIAS} AS m "
            f"WHERE m.codigo_contrato = c.codigo_contrato AND m.rfc_exacto) LIMIT 5",
            f"SELECT fuente, ROW_NUMBER() OVER (PARTITION BY fuente ORDER BY importe DESC) AS rn "
            f"FROM {CONTRATOS} LIMIT 5",
        ):
            with self.subTest(query=query[:70]):
                validate_sql(query)

    def test_column_list_matches_the_view_definitions(self):
        definitions = {}
        for path in sorted((ROOT / "etl" / "sql").glob("*.sql")):
            text = path.read_text(encoding="utf-8")
            for view, body in re.findall(
                r"CREATE OR REPLACE VIEW clean\.(\w+) AS\s*SELECT(.*?)\bFROM\b", text, flags=re.DOTALL | re.IGNORECASE
            ):
                definitions[view.lower()] = tuple(column.strip() for column in body.split(","))
        for view, columns in VIEW_COLUMNS.items():
            with self.subTest(vista=view):
                self.assertEqual(definitions[view], columns)


class AddMissingLimitTests(unittest.TestCase):
    """A5, mejora 1: a SELECT without LIMIT gets one instead of a retry."""

    def test_adds_the_maximum_limit_and_the_result_passes_the_validator(self):
        query, added = add_missing_limit(f"SELECT fuente, COUNT(*) FROM {CONTRATOS} GROUP BY fuente")
        self.assertTrue(added)
        self.assertTrue(query.endswith(f"LIMIT {MAX_SQL_ROWS}"))
        validate_sql(query)

    def test_keeps_order_by_and_places_the_limit_before_offset(self):
        query, added = add_missing_limit(f"SELECT * FROM {CONTRATOS} ORDER BY fecha_inicio DESC OFFSET 5")
        self.assertTrue(added)
        self.assertIn(f"ORDER BY fecha_inicio DESC LIMIT {MAX_SQL_ROWS} OFFSET 5", query)
        validate_sql(query)

    def test_a_limit_inside_a_subquery_does_not_count(self):
        query, added = add_missing_limit(
            f"SELECT * FROM (SELECT * FROM {CONTRATOS} LIMIT 5) AS t"
        )
        self.assertTrue(added)
        self.assertTrue(query.endswith(f"LIMIT {MAX_SQL_ROWS}"))

    def test_leaves_an_existing_limit_alone_even_if_it_is_invalid(self):
        for query in (
            f"SELECT * FROM {CONTRATOS} LIMIT 20",
            f"SELECT * FROM {CONTRATOS} LIMIT {MAX_SQL_ROWS + 1}",
            f"SELECT * FROM {CONTRATOS} LIMIT ALL",
            f"SELECT * FROM {CONTRATOS} LIMIT '5'",
            f"SELECT * FROM {CONTRATOS} FETCH FIRST 5 ROWS ONLY",
        ):
            with self.subTest(query=query):
                self.assertEqual(add_missing_limit(query), (query, False))

    def test_leaves_anything_that_is_not_a_single_select_alone(self):
        for query in (
            f"DELETE FROM {CONTRATOS}",
            f"SELECT * FROM {CONTRATOS}; DROP TABLE clean.contratos",
            f"SELECT fuente FROM {CONTRATOS} UNION SELECT fuente FROM {CONTRATOS}",
            "SELECT FROM WHERE",
        ):
            with self.subTest(query=query):
                self.assertEqual(add_missing_limit(query), (query, False))

    def test_the_other_rules_still_apply_after_adding_the_limit(self):
        query, added = add_missing_limit("SELECT * FROM clean.contratos")
        self.assertTrue(added)
        with self.assertRaisesRegex(SQLValidationError, "Tabla no permitida"):
            validate_sql(query)


class ExtractSqlTests(unittest.TestCase):
    def test_extracts_from_a_sql_fence(self):
        self.assertEqual(
            extract_sql("Aquí está:\n```sql\nSELECT 1 LIMIT 1\n```"), "SELECT 1 LIMIT 1"
        )

    def test_strips_a_sql_prefix(self):
        self.assertEqual(extract_sql("SQL SELECT 1 LIMIT 1"), "SELECT 1 LIMIT 1")

    def test_rejects_more_than_one_code_block(self):
        with self.assertRaisesRegex(SQLValidationError, "más de un bloque"):
            extract_sql("```sql\nSELECT 1\n```\n```sql\nSELECT 2\n```")

    def test_detects_a_single_select(self):
        self.assertTrue(is_single_select(f"SELECT * FROM {CONTRATOS} LIMIT 1"))
        self.assertFalse(is_single_select("SELECT 1; SELECT 2"))
        self.assertFalse(is_single_select(f"DELETE FROM {CONTRATOS}"))


class ProjectQueriesTests(unittest.TestCase):
    """The reference SQL used by the team must keep passing the validator."""

    def test_golden_set_and_examples_pass(self):
        for name, key in (("golden_set.yaml", "sql_esperado"), ("examples.yaml", "sql")):
            cases = yaml.safe_load((ROOT / "eval" / name).read_text(encoding="utf-8"))
            for case in cases:
                with self.subTest(archivo=name, pregunta=case["pregunta"]):
                    validate_sql(case[key])

    def test_semantic_layer_queries_pass(self):
        document = (ROOT / "docs" / "capa_semantica.md").read_text(encoding="utf-8")
        blocks = re.findall(r"```sql\n(.*?)```", document, flags=re.DOTALL)
        self.assertGreaterEqual(len(blocks), 10)
        for block in blocks:
            with self.subTest(sql=block.splitlines()[0]):
                validate_sql(block)


if __name__ == "__main__":
    unittest.main()
