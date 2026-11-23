import unittest
from pathlib import Path

import yaml

from agents.consulta.coverage import COVERAGE_QUERY, Coverage, check_coverage, contradicted_no_data, format_years
from agents.consulta.prompt import BUILT_IN_EXAMPLES
from agents.consulta.validator import validate_sql


ROOT = Path(__file__).resolve().parents[1]
V = "clean.v_contratos_agente"

# M9 verified against the EC2 database on 2026-11-12 (docs/capa_semantica.md).
M9_ROWS = [
    (2010, "historico", 4913), (2011, "historico", 128912), (2012, "historico", 170815),
    (2013, "historico", 181932), (2014, "historico", 197411), (2015, "historico", 223053),
    (2016, "historico", 233890), (2017, "historico", 234360), (2018, "historico", 198330),
    (2019, "historico", 193997), (2020, "historico", 162405), (2021, "historico", 204035),
    (2022, "historico", 198510), (2023, "historico", 16896), (2024, "historico", 1836),
    (2026, "comprasmx", 84676),
]
COVERAGE = Coverage.from_rows(M9_ROWS)


def count_sql(where):
    return f"SELECT COUNT(*) AS contratos FROM {V} WHERE {where} LIMIT 1"


class CoverageFromRowsTests(unittest.TestCase):
    def test_reads_years_per_source(self):
        self.assertEqual(COVERAGE.years["comprasmx"], frozenset({2026}))
        self.assertEqual(COVERAGE.years["historico"], frozenset(range(2010, 2025)))

    def test_marks_years_far_below_the_median_as_partial(self):
        self.assertEqual(COVERAGE.partial_years["historico"], frozenset({2010, 2023, 2024}))
        self.assertEqual(COVERAGE.partial_years["comprasmx"], frozenset())

    def test_accepts_dict_rows_and_ignores_null_years(self):
        coverage = Coverage.from_rows([
            {"anio": None, "fuente": "historico", "filas": 5307},
            {"anio": 2026, "fuente": "comprasmx", "filas": 10},
        ])
        self.assertEqual(coverage.years, {"comprasmx": frozenset({2026})})

    def test_coverage_query_reads_only_valid_start_dates(self):
        self.assertIn("fecha_inicio_valida", COVERAGE_QUERY)

    def test_formats_year_spans(self):
        self.assertEqual(format_years([2025]), "2025")
        self.assertEqual(format_years([2010, 2023, 2024]), "2010 y 2023–2024")
        self.assertEqual(format_years(range(2010, 2025)), "2010–2024")


class NoDataTests(unittest.TestCase):
    def assert_no_data(self, sql, *fragments):
        check = check_coverage(sql, COVERAGE)
        self.assertIsNotNone(check.sin_datos)
        for fragment in fragments:
            self.assertIn(fragment, check.sin_datos)

    def test_year_without_contracts_in_any_source(self):
        self.assert_no_data(
            count_sql("fecha_inicio >= DATE '2025-01-01' AND fecha_inicio < DATE '2026-01-01'"),
            "2025",
            "Cobertura disponible",
        )

    def test_year_filter_written_with_extract(self):
        self.assert_no_data(count_sql("EXTRACT(YEAR FROM fecha_inicio)::integer = 2025"), "2025")

    def test_date_literal_on_the_left_side(self):
        self.assert_no_data(
            count_sql("DATE '2025-01-01' <= fecha_inicio AND fecha_inicio < DATE '2026-01-01'"),
            "2025",
        )

    def test_between_dates(self):
        self.assert_no_data(count_sql("fecha_inicio BETWEEN '2025-01-01' AND '2025-12-31'"), "2025")

    def test_year_filter_written_with_date_trunc(self):
        # A5, mejora 6: the model wrote c12 this way on 2026-11-19.
        self.assert_no_data(count_sql("DATE_TRUNC('YEAR', fecha_inicio) = CAST('2025-01-01' AS DATE)"), "2025")
        self.assert_no_data(count_sql("date_trunc('month', fecha_inicio) = DATE '2025-03-01'"), "2025")

    def test_year_outside_the_requested_source(self):
        self.assert_no_data(
            count_sql("fuente = 'historico' AND EXTRACT(YEAR FROM fecha_inicio) = 2026"),
            "CompraNet histórico",
        )
        self.assert_no_data(
            count_sql("fuente IN ('comprasmx') AND EXTRACT(YEAR FROM fecha_inicio) BETWEEN 2019 AND 2020"),
            "ComprasMX",
        )

    def test_unknown_source(self):
        self.assert_no_data(count_sql("fuente = 'compranet'"), "No existe la fuente")

    def test_comprasmx_field_in_a_historico_only_period(self):
        self.assert_no_data(
            f"SELECT institucion, COUNT(*) AS contratos FROM {V} "
            f"WHERE EXTRACT(YEAR FROM fecha_inicio) = 2018 GROUP BY institucion LIMIT 10",
            "institucion",
            "ComprasMX",
        )

    def test_comprasmx_field_with_historico_source(self):
        self.assert_no_data(
            f"SELECT nombre_de_la_uc FROM {V} WHERE fuente = 'historico' LIMIT 10",
            "nombre_de_la_uc",
        )

    def test_historico_field_with_comprasmx_source(self):
        self.assert_no_data(
            f"SELECT tipo_expediente, COUNT(*) AS contratos FROM {V} "
            f"WHERE fuente = 'comprasmx' GROUP BY tipo_expediente LIMIT 10",
            "tipo_expediente",
        )


class AnswerableQueryTests(unittest.TestCase):
    def test_query_without_filters_has_no_notes(self):
        check = check_coverage(f"SELECT fuente, COUNT(*) AS contratos FROM {V} GROUP BY fuente LIMIT 5", COVERAGE)
        self.assertIsNone(check.sin_datos)
        self.assertEqual(check.supuestos, [])

    def test_partial_year_adds_a_note(self):
        check = check_coverage(
            count_sql("fuente = 'historico' AND fecha_inicio >= DATE '2024-01-01' AND fecha_inicio < DATE '2025-01-01'"),
            COVERAGE,
        )
        self.assertIsNone(check.sin_datos)
        self.assertEqual(check.supuestos, ["Cobertura incompleta en CompraNet histórico para 2024."])

    def test_range_that_includes_a_year_without_data(self):
        check = check_coverage(
            count_sql("fecha_inicio >= DATE '2020-01-01' AND fecha_inicio < DATE '2026-01-01'"),
            COVERAGE,
        )
        self.assertIsNone(check.sin_datos)
        self.assertIn("Sin datos para 2025; el resultado solo incluye 2020–2024.", check.supuestos)
        self.assertIn("Cobertura incompleta en CompraNet histórico para 2023–2024.", check.supuestos)

    def test_year_list_with_and_without_data(self):
        check = check_coverage(count_sql("EXTRACT(YEAR FROM fecha_inicio) IN (2024, 2025)"), COVERAGE)
        self.assertIsNone(check.sin_datos)
        self.assertIn("Sin datos para 2025; el resultado solo incluye 2024.", check.supuestos)

    def test_comprasmx_field_across_both_sources_adds_a_note(self):
        check = check_coverage(f"SELECT institucion, COUNT(*) AS c FROM {V} GROUP BY institucion LIMIT 5", COVERAGE)
        self.assertIsNone(check.sin_datos)
        self.assertEqual(len(check.supuestos), 1)
        self.assertIn("institucion solo existe en ComprasMX", check.supuestos[0])

    def test_comprasmx_field_in_2026_is_fine(self):
        check = check_coverage(
            f"SELECT nombre_de_la_uc, COUNT(*) AS c FROM {V} WHERE fuente = 'comprasmx' "
            f"AND fecha_inicio >= DATE '2026-01-01' GROUP BY nombre_de_la_uc LIMIT 5",
            COVERAGE,
        )
        self.assertIsNone(check.sin_datos)
        self.assertEqual(check.supuestos, [])

    def test_or_conditions_are_not_treated_as_restrictions(self):
        check = check_coverage(
            count_sql("(fuente = 'historico' OR EXTRACT(YEAR FROM fecha_inicio) = 2025)"),
            COVERAGE,
        )
        self.assertIsNone(check.sin_datos)


class ReferenceCasesTests(unittest.TestCase):
    """eval/casos_consulta.yaml holds the A2 cases used later with the real model."""

    def setUp(self):
        self.cases = yaml.safe_load((ROOT / "eval" / "casos_consulta.yaml").read_text(encoding="utf-8"))

    def test_cases_are_well_formed_and_new(self):
        golden = yaml.safe_load((ROOT / "eval" / "golden_set.yaml").read_text(encoding="utf-8"))
        examples = yaml.safe_load((ROOT / "eval" / "examples.yaml").read_text(encoding="utf-8"))
        seen = {item["pregunta"].casefold() for item in [*golden, *examples, *BUILT_IN_EXAMPLES]}
        ids = [case["id"] for case in self.cases]
        self.assertEqual(len(ids), len(set(ids)))
        for case in self.cases:
            with self.subTest(caso=case["id"]):
                self.assertIn(case["tipo_esperado"], {"sql", "aclaracion", "sin_datos"})
                self.assertTrue(case["notas"].strip())
                self.assertNotIn(case["pregunta"].casefold(), seen)

    def test_covers_ambiguity_and_missing_data(self):
        kinds = [case["tipo_esperado"] for case in self.cases]
        self.assertGreaterEqual(kinds.count("aclaracion"), 5)
        self.assertGreaterEqual(kinds.count("sin_datos"), 5)

    def test_naive_sql_is_caught_by_the_coverage_check(self):
        for case in self.cases:
            sql = case.get("sql_ingenuo") or case.get("sql_esperado")
            if not sql:
                continue
            with self.subTest(caso=case["id"]):
                check = check_coverage(validate_sql(sql), COVERAGE)
                expected_no_data = case["tipo_esperado"] == "sin_datos"
                self.assertEqual(check.sin_datos is not None, expected_no_data, check.sin_datos)

    def test_cases_that_expect_sql_have_the_expected_sql(self):
        for case in self.cases:
            with self.subTest(caso=case["id"]):
                self.assertEqual("sql_esperado" in case, case["tipo_esperado"] == "sql")


class DateTruncNotesTests(unittest.TestCase):
    """A5, mejora 6: the partial-year note no longer depends on the model writing it."""

    def test_partial_year_note_for_date_trunc_by_year(self):
        # c12 as the model wrote it on 2026-11-19; the note was missing.
        sql = count_sql(
            "fuente = 'historico' AND fecha_inicio_valida "
            "AND DATE_TRUNC('YEAR', fecha_inicio) = CAST('2024-01-01' AS DATE)"
        )
        check = check_coverage(sql, COVERAGE)
        self.assertIsNone(check.sin_datos)
        self.assertEqual(check.supuestos, ["Cobertura incompleta en CompraNet histórico para 2024."])

    def test_a_december_month_ends_at_the_next_year(self):
        sql = count_sql("fuente = 'historico' AND DATE_TRUNC('month', fecha_inicio) = DATE '2023-12-01'")
        self.assertEqual(check_coverage(sql, COVERAGE).supuestos, ["Cobertura incompleta en CompraNet histórico para 2023."])

    def test_other_units_are_not_read_as_a_period(self):
        sql = count_sql("DATE_TRUNC('day', fecha_inicio) = DATE '2025-03-01'")
        self.assertIsNone(check_coverage(sql, COVERAGE).sin_datos)


if __name__ == "__main__":
    unittest.main()


class ContradictedNoDataTests(unittest.TestCase):
    """A5, mejora 17: a "no data" reason that names years with contracts."""

    def test_q17_reason_is_contradicted_with_the_partial_year(self):
        self.assertEqual(
            contradicted_no_data("El histórico de CompraNet no registra contratos con inicio en 2024.", COVERAGE),
            "CompraNet histórico sí tiene contratos con inicio en 2024 (2024 incompleto)",
        )

    def test_a_year_without_data_is_not_contradicted(self):
        for reason in (
            "No hay contratos con inicio en 2025.",
            "No hay datos de 2024 ni de 2025.",
            "ComprasMX no tiene contratos de 2024.",
        ):
            with self.subTest(motivo=reason):
                self.assertIsNone(contradicted_no_data(reason, COVERAGE))

    def test_a_year_with_data_in_any_source_when_none_is_named(self):
        message = contradicted_no_data("No hay registros de 2026.", COVERAGE)
        self.assertEqual(message, "ComprasMX sí tiene contratos con inicio en 2026")

    def test_reasons_that_are_not_about_missing_years_are_left_alone(self):
        for reason in (
            "Las fuentes no registran pagos ni fechas de pago.",
            "El importe de 2024 no es gasto pagado.",
        ):
            with self.subTest(motivo=reason):
                self.assertIsNone(contradicted_no_data(reason, COVERAGE))


class GroupByYearNotesTests(unittest.TestCase):
    """A5, mejora 20: a result split by year also warns about the incomplete years."""

    HISTORICO_NOTE = "Cobertura incompleta en CompraNet histórico para 2010 y 2023–2024."

    def test_n06_as_the_model_wrote_it(self):
        # casos_nuevos n06 on 2026-11-23: 2010 was a row of the result and had no note.
        sql = (
            "SELECT CAST(EXTRACT(YEAR FROM fecha_inicio) AS INT) AS año_inicio, COUNT(*) AS contratos "
            f"FROM {V} AS c JOIN clean.v_coincidencias_69b_agente AS m ON m.codigo_contrato = c.codigo_contrato "
            "WHERE m.requiere_revision_humana AND c.fecha_inicio_valida "
            "GROUP BY año_inicio ORDER BY año_inicio LIMIT 200"
        )
        check = check_coverage(sql, COVERAGE)
        self.assertIsNone(check.sin_datos)
        self.assertEqual(check.supuestos, [self.HISTORICO_NOTE])

    def test_group_by_the_expression_or_its_position(self):
        for group in ("EXTRACT(YEAR FROM fecha_inicio)", "1"):
            with self.subTest(group=group):
                sql = (
                    f"SELECT EXTRACT(YEAR FROM fecha_inicio) AS anio, COUNT(*) AS contratos FROM {V} "
                    f"WHERE fuente = 'historico' GROUP BY {group} ORDER BY 1 LIMIT 50"
                )
                self.assertEqual(check_coverage(sql, COVERAGE).supuestos, [self.HISTORICO_NOTE])

    def test_group_by_month(self):
        sql = (
            f"SELECT DATE_TRUNC('month', fecha_inicio) AS mes, COUNT(*) AS contratos FROM {V} "
            "WHERE fuente = 'historico' GROUP BY mes ORDER BY mes LIMIT 500"
        )
        self.assertEqual(check_coverage(sql, COVERAGE).supuestos, [self.HISTORICO_NOTE])

    def test_comprasmx_by_year_has_no_incomplete_year(self):
        sql = (
            f"SELECT EXTRACT(YEAR FROM fecha_inicio) AS anio, COUNT(*) AS contratos FROM {V} "
            "WHERE fuente = 'comprasmx' GROUP BY anio ORDER BY anio LIMIT 50"
        )
        self.assertEqual(check_coverage(sql, COVERAGE).supuestos, [])

    def test_other_groupings_still_have_no_notes(self):
        for group in ("fuente", "moneda"):
            with self.subTest(group=group):
                sql = f"SELECT {group}, COUNT(*) AS contratos FROM {V} GROUP BY {group} LIMIT 50"
                self.assertEqual(check_coverage(sql, COVERAGE).supuestos, [])

    def test_a_year_filter_keeps_a_single_note(self):
        sql = (
            f"SELECT EXTRACT(YEAR FROM fecha_inicio) AS anio, COUNT(*) AS contratos FROM {V} "
            "WHERE fuente = 'historico' AND fecha_inicio >= DATE '2023-01-01' "
            "AND fecha_inicio < DATE '2025-01-01' GROUP BY anio LIMIT 50"
        )
        self.assertEqual(
            check_coverage(sql, COVERAGE).supuestos,
            ["Cobertura incompleta en CompraNet histórico para 2023–2024."],
        )