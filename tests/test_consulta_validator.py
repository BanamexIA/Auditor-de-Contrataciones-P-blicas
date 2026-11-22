import re
import unittest
from pathlib import Path

import yaml

from agents.consulta.validator import (
    MAX_SQL_ROWS,
    VIEW_COLUMNS,
    SQLValidationError,
    add_missing_limit,
    add_order_tiebreaker,
    extract_sql,
    fix_alias_typos,
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

    def test_alias_written_with_an_underscore_gets_the_fix(self):
        # A5, mejora 10: q07 and q08 on 2026-11-19 wrote c_fuente for c.fuente.
        self.assert_rejected(
            f"SELECT c_fuente, COUNT(DISTINCT c.codigo_contrato) AS contratos FROM {CONTRATOS} AS c "
            f"JOIN {COINCIDENCIAS} AS m ON m.codigo_contrato = c.codigo_contrato "
            f"WHERE m.rfc_exacto GROUP BY c_fuente LIMIT 20",
            "escribe c.fuente", "con punto",
        )

    def test_underscore_without_a_matching_alias_keeps_the_usual_message(self):
        self.assert_rejected(f"SELECT x_fuente FROM {CONTRATOS} AS c LIMIT 5", "no existe en las vistas aprobadas")
        self.assert_rejected(f"SELECT c_monto FROM {CONTRATOS} AS c LIMIT 5", "no existe en las vistas aprobadas")

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


class AddOrderTiebreakerTests(unittest.TestCase):
    """A5, mejora 14: ties on the ORDER BY are broken by codigo_contrato."""

    def test_q08_as_the_model_writes_it(self):
        query, added = add_order_tiebreaker(
            f"SELECT c.codigo_contrato, c.fuente, c.fecha_inicio, c.proveedor, m.nivel_confianza "
            f"FROM {CONTRATOS} AS c JOIN {COINCIDENCIAS} AS m ON c.codigo_contrato = m.codigo_contrato "
            f"WHERE m.requiere_revision_humana AND c.fecha_inicio BETWEEN '2011-01-01' AND '2022-12-31' "
            f"ORDER BY c.fecha_inicio DESC LIMIT 20"
        )
        self.assertTrue(added)
        self.assertIn("ORDER BY c.fecha_inicio DESC, c.codigo_contrato LIMIT 20", query)
        validate_sql(query)

    def test_uses_the_alias_when_codigo_contrato_is_renamed(self):
        query, added = add_order_tiebreaker(
            f"SELECT codigo_contrato AS codigo, importe FROM {CONTRATOS} ORDER BY importe DESC LIMIT 10"
        )
        self.assertTrue(added)
        self.assertIn("ORDER BY importe DESC, codigo LIMIT 10", query)

    def test_works_with_distinct_and_with_a_group_by_codigo_contrato(self):
        for query, expected in (
            (f"SELECT DISTINCT c.codigo_contrato, c.fecha_inicio FROM {CONTRATOS} AS c "
             f"ORDER BY c.fecha_inicio DESC LIMIT 5",
             "ORDER BY c.fecha_inicio DESC, c.codigo_contrato LIMIT 5"),
            (f"SELECT codigo_contrato, COUNT(*) AS coincidencias FROM {COINCIDENCIAS} "
             f"GROUP BY codigo_contrato ORDER BY coincidencias DESC LIMIT 5",
             "ORDER BY coincidencias DESC, codigo_contrato LIMIT 5"),
        ):
            with self.subTest(query=query):
                result, added = add_order_tiebreaker(query)
                self.assertTrue(added)
                self.assertIn(expected, result)

    def test_leaves_an_order_that_already_uses_codigo_contrato_alone(self):
        for query in (
            f"SELECT codigo_contrato, fecha_inicio FROM {CONTRATOS} ORDER BY fecha_inicio DESC, codigo_contrato LIMIT 5",
            f"SELECT codigo_contrato, fecha_inicio FROM {CONTRATOS} ORDER BY codigo_contrato DESC LIMIT 5",
            f"SELECT codigo_contrato, fecha_inicio FROM {CONTRATOS} ORDER BY 2 DESC, 1 LIMIT 5",
            f"SELECT codigo_contrato AS codigo, fecha_inicio FROM {CONTRATOS} ORDER BY fecha_inicio, codigo LIMIT 5",
        ):
            with self.subTest(query=query):
                self.assertEqual(add_order_tiebreaker(query), (query, False))

    def test_leaves_queries_where_the_tiebreaker_does_not_apply_alone(self):
        for query in (
            f"SELECT codigo_contrato, fecha_inicio FROM {CONTRATOS} LIMIT 5",
            f"SELECT codigo_contrato, fecha_inicio FROM {CONTRATOS} ORDER BY fecha_inicio",
            f"SELECT fuente, COUNT(*) AS contratos FROM {CONTRATOS} GROUP BY fuente ORDER BY contratos DESC LIMIT 5",
            f"SELECT COUNT(DISTINCT codigo_contrato) AS contratos FROM {CONTRATOS} ORDER BY 1 LIMIT 1",
            f"SELECT codigo_contrato, COUNT(*) AS filas FROM {CONTRATOS} ORDER BY filas LIMIT 5",
            f"SELECT DISTINCT ON (fuente) codigo_contrato, fuente FROM {CONTRATOS} ORDER BY fuente LIMIT 5",
            f"SELECT codigo_contrato FROM {CONTRATOS} UNION SELECT codigo_contrato FROM {COINCIDENCIAS} LIMIT 5",
            "SELECT FROM WHERE",
        ):
            with self.subTest(query=query):
                self.assertEqual(add_order_tiebreaker(query), (query, False))

    def test_no_expected_sql_needs_it(self):
        """The expected answers already break their ties; the tiebreaker leaves them as they are."""
        for name in ("golden_set.yaml", "casos_consulta.yaml", "casos_empresa.yaml", "casos_empresa_69b.yaml",
                     "casos_nuevos.yaml"):
            for case in yaml.safe_load((ROOT / "eval" / name).read_text(encoding="utf-8")):
                if case.get("sql_esperado"):
                    with self.subTest(caso=case["id"]):
                        self.assertFalse(add_order_tiebreaker(case["sql_esperado"])[1])


class FixAliasTyposTests(unittest.TestCase):
    """A5, mejora 15: alias_columna becomes alias.columna before validating."""

    def test_q08_first_attempt(self):
        query, fixes = fix_alias_typos(
            f"SELECT c.codigo_contrato, c_fuente, c.fecha_inicio, m.nivel_confianza FROM {CONTRATOS} AS c "
            f"JOIN {COINCIDENCIAS} AS m ON m.codigo_contrato = c.codigo_contrato "
            f"WHERE m.requiere_revision_humana ORDER BY c.fecha_inicio DESC LIMIT 20"
        )
        self.assertEqual(fixes, ["c_fuente -> c.fuente"])
        self.assertIn("SELECT c.codigo_contrato, c.fuente, c.fecha_inicio", query)
        validate_sql(query)

    def test_fixes_every_typo_and_every_place_it_appears(self):
        query, fixes = fix_alias_typos(
            f"SELECT c_fuente, m_nivel_confianza, COUNT(*) AS contratos FROM {CONTRATOS} AS c "
            f"JOIN {COINCIDENCIAS} AS m ON m.codigo_contrato = c.codigo_contrato "
            f"GROUP BY c_fuente, m_nivel_confianza LIMIT 20"
        )
        self.assertEqual(fixes, ["c_fuente -> c.fuente", "m_nivel_confianza -> m.nivel_confianza"])
        self.assertIn("GROUP BY c.fuente, m.nivel_confianza", query)
        validate_sql(query)

    def test_leaves_names_defined_in_the_query_and_real_errors_alone(self):
        for query in (
            f"SELECT SUM(c.importe) AS c_importe FROM {CONTRATOS} AS c GROUP BY c.fuente ORDER BY c_importe LIMIT 5",
            f"SELECT c.fuente FROM {CONTRATOS} AS c LIMIT 5",
            f"SELECT c_inventada FROM {CONTRATOS} AS c LIMIT 5",
            f"SELECT m_fuente FROM {CONTRATOS} AS c LIMIT 5",
            f"SELECT c_rfc_exacto FROM {CONTRATOS} AS c LIMIT 5",
            "SELECT FROM WHERE",
        ):
            with self.subTest(query=query):
                self.assertEqual(fix_alias_typos(query), (query, []))


class CategoryValuesTests(unittest.TestCase):
    """A5, mejora 16: a text that a categorical column never holds."""

    def test_e03_company_taken_for_a_procedure_type(self):
        with self.assertRaisesRegex(SQLValidationError, "'brand_and_push' no es un valor de tipo_procedimiento_norm.*proveedor_normalizado"):
            validate_sql(
                f"SELECT tipo_procedimiento_norm, COUNT(*) FROM {CONTRATOS} WHERE fuente = 'comprasmx' "
                f"AND tipo_procedimiento_norm = 'brand_and_push' GROUP BY tipo_procedimiento_norm LIMIT 200"
            )

    def test_checks_both_sides_in_lists_and_inequalities(self):
        for query, value in (
            (f"SELECT COUNT(*) FROM {CONTRATOS} WHERE 'ComprasMX' = fuente LIMIT 1", "ComprasMX"),
            (f"SELECT COUNT(*) FROM {CONTRATOS} AS c WHERE c.fuente IN ('historico', 'compranet') LIMIT 1", "compranet"),
            (f"SELECT COUNT(*) FROM {CONTRATOS} WHERE fecha_inicio_estado <> 'invalida' LIMIT 1", "invalida"),
            (f"SELECT COUNT(*) FROM {COINCIDENCIAS} WHERE nivel_confianza = 'baja' LIMIT 1", "baja"),
        ):
            with self.subTest(query=query):
                with self.assertRaisesRegex(SQLValidationError, f"'{value}' no es un valor de"):
                    validate_sql(query)

    def test_known_values_and_other_columns_pass(self):
        for query in (
            f"SELECT COUNT(*) FROM {CONTRATOS} WHERE fuente = 'comprasmx' AND tipo_procedimiento_norm IN ('otro', 'sin_dato') LIMIT 1",
            f"SELECT COUNT(*) FROM {CONTRATOS} WHERE fecha_inicio_estado = 'no_parseable' LIMIT 1",
            f"SELECT COUNT(*) FROM {CONTRATOS} WHERE moneda = 'MXN' AND proveedor_normalizado = 'brand_and_push' LIMIT 1",
            f"SELECT COUNT(*) FROM {CONTRATOS} WHERE UPPER(fuente) = 'COMPRASMX' LIMIT 1",
        ):
            with self.subTest(query=query):
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
