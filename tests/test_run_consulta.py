import tempfile
import unittest
from decimal import Decimal
from pathlib import Path

from agents.consulta.coverage import Coverage, check_coverage
from agents.consulta.validator import validate_sql
from eval.run_consulta import (
    canonical_rows,
    compare_results,
    evaluate,
    load_cases,
    summarize,
    write_report,
)
from tests.test_consulta_coverage import M9_ROWS


CASE_SQL = {"id": "q01", "dificultad": "facil", "tipo_esperado": "sql"}
CASE_NO_DATA = {"id": "q11", "dificultad": "media", "tipo_esperado": "sin_datos"}


class GoldenSetTests(unittest.TestCase):
    def setUp(self):
        self.cases = load_cases()

    def test_every_case_has_an_expected_type(self):
        types = {case["id"]: case["tipo_esperado"] for case in self.cases}
        self.assertEqual(len(types), 20)
        self.assertEqual(
            sorted(case_id for case_id, kind in types.items() if kind == "sin_datos"),
            ["q11", "q12", "q14", "q20"],
        )

    def test_expected_type_matches_the_coverage_check(self):
        coverage = Coverage.from_rows(M9_ROWS)
        for case in self.cases:
            with self.subTest(caso=case["id"]):
                check = check_coverage(validate_sql(case["sql_esperado"]), coverage)
                self.assertEqual(check.sin_datos is not None, case["tipo_esperado"] == "sin_datos")

    def test_no_case_asks_for_an_impossible_combination(self):
        for case in self.cases:
            sql = case["sql_esperado"]
            where = sql.split("WHERE", 1)[1] if "WHERE" in sql else ""
            with self.subTest(caso=case["id"]):
                self.assertFalse("rfc_exacto" in where and "requiere_revision_humana" in where)


class CompareResultsTests(unittest.TestCase):
    def test_ignores_aliases_and_column_order(self):
        expected = [{"fuente": "historico", "contratos": 5}]
        actual = [{"total": 5, "origen": "historico"}]
        self.assertIsNone(compare_results(expected, actual))

    def test_ignores_row_order(self):
        expected = [{"a": 1}, {"a": 2}]
        self.assertIsNone(compare_results(expected, list(reversed(expected))))

    def test_numbers_compare_by_value(self):
        self.assertEqual(canonical_rows([{"anio": Decimal("2019")}]), canonical_rows([{"anio": 2019}]))
        self.assertEqual(canonical_rows([{"pct": Decimal("72.10")}]), canonical_rows([{"pct": Decimal("72.1")}]))
        self.assertNotEqual(canonical_rows([{"x": 1}]), canonical_rows([{"x": "1"}]))

    def test_classifies_differences(self):
        expected = [{"fuente": "a", "contratos": 5}]
        self.assertEqual(compare_results(expected, [{"fuente": "a", "contratos": 5, "extra": 1}]), "columnas_distintas")
        self.assertEqual(compare_results(expected, expected * 2), "filas_distintas")
        self.assertEqual(compare_results(expected, [{"fuente": "a", "contratos": 6}]), "valores_distintos")


class EvaluateTests(unittest.TestCase):
    def test_correct_sql(self):
        row = evaluate(CASE_SQL, {"tipo": "sql", "sql": "SELECT 1", "intentos": 1}, [{"n": 1}], [{"total": 1}])
        self.assertTrue(row["correcto"])
        self.assertIsNone(row["error"])

    def test_wrong_type(self):
        row = evaluate(CASE_NO_DATA, {"tipo": "sql", "sql": "SELECT 1", "intentos": 1})
        self.assertEqual(row["error"], "tipo_incorrecto")

    def test_no_data_is_correct_without_running_sql(self):
        row = evaluate(CASE_NO_DATA, {"tipo": "sin_datos", "motivo": "No hay 2025.", "intentos": 1})
        self.assertTrue(row["correcto"])

    def test_model_and_execution_errors(self):
        self.assertEqual(evaluate(CASE_SQL, {"tipo": "error", "motivo": "x", "intentos": 2})["error"], "error_modelo")
        row = evaluate(CASE_SQL, {"tipo": "sql", "sql": "SELECT 1", "intentos": 1}, [{"n": 1}], None, "QueryCanceled: timeout")
        self.assertEqual(row["error"], "error_ejecucion")


class SummaryTests(unittest.TestCase):
    def setUp(self):
        self.results = [
            evaluate(CASE_SQL, {"tipo": "sql", "sql": "s", "intentos": 1}, [{"n": 1}], [{"n": 1}]),
            evaluate({**CASE_SQL, "dificultad": "dificil"}, {"tipo": "sql", "sql": "s", "intentos": 1}, [{"n": 1}], [{"n": 2}]),
            evaluate(CASE_NO_DATA, {"tipo": "sin_datos", "motivo": "m", "intentos": 1}),
        ]

    def test_computes_accuracy_and_error_types(self):
        summary = summarize(self.results)
        self.assertEqual(summary["exactitud_sql_pct"], 50.0)
        self.assertEqual(summary["acierto_global_pct"], 66.7)
        self.assertEqual(summary["por_dificultad"], {"dificil": 0.0, "facil": 100.0})
        self.assertEqual(summary["errores"], {"valores_distintos": 1})

    def test_writes_the_report_files(self):
        with tempfile.TemporaryDirectory() as folder:
            output = Path(folder) / "consulta"
            metadata = {"modelo": "qwen2.5:7b", "casos": 3, "repeticiones": 1, "fecha": "2026-11-16"}
            write_report(output, self.results, summarize(self.results), metadata)
            self.assertEqual(sorted(p.name for p in output.iterdir()), ["detalle.csv", "resumen.json", "resumen.md"])
            report = (output / "resumen.md").read_text(encoding="utf-8")
            self.assertIn("Exactitud del SQL (casos que esperan SQL) | 50.0 %", report)
            self.assertIn("| q01 | sql | sql | valores_distintos |", report)


if __name__ == "__main__":
    unittest.main()
