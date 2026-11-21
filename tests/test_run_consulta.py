import tempfile
import unittest
from decimal import Decimal
from pathlib import Path

import yaml
from psycopg import errors as pg_errors

from agents.consulta.coverage import Coverage, check_coverage
from agents.consulta.validator import validate_sql
from agents.consulta.concepts import missing_concept
from agents.consulta.prompt import BUILT_IN_EXAMPLES
from eval.run_consulta import (
    ask_and_execute,
    canonical_rows,
    compare_results,
    consistency,
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

    def test_loads_the_a2_cases_too(self):
        cases = load_cases(Path(__file__).resolve().parents[1] / "eval" / "casos_consulta.yaml")
        self.assertEqual(len(cases), 13)
        self.assertTrue(all(case["dificultad"] == "sin_clasificar" for case in cases))
        self.assertEqual(sum(case["tipo_esperado"] == "aclaracion" for case in cases), 5)

    def test_rejects_a_sql_case_without_expected_sql(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "casos.yaml"
            path.write_text("- id: x1\n  pregunta: ¿Algo?\n  tipo_esperado: sql\n", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "sql_esperado"):
                load_cases(path)

    def test_q08_covers_complete_years_only(self):
        # A5, mejora 8: 2024 had no coincidence needing review, so q08 expected no rows.
        q08 = next(case for case in self.cases if case["id"] == "q08")
        check = check_coverage(validate_sql(q08["sql_esperado"]), Coverage.from_rows(M9_ROWS))
        self.assertIsNone(check.sin_datos)
        self.assertEqual(check.supuestos, [])
        self.assertNotIn("2024", q08["sql_esperado"])

    def test_no_case_asks_for_an_impossible_combination(self):
        for case in self.cases:
            sql = case["sql_esperado"]
            where = sql.split("WHERE", 1)[1] if "WHERE" in sql else ""
            with self.subTest(caso=case["id"]):
                self.assertFalse("rfc_exacto" in where and "requiere_revision_humana" in where)


class CompanyCasesTests(unittest.TestCase):
    """A5: the company questions of the demo (mejora 8) and the new 69-B ones."""

    FILES = ("casos_empresa.yaml", "casos_empresa_69b.yaml")

    def setUp(self):
        self.folder = Path(__file__).resolve().parents[1] / "eval"
        self.files = {name: load_cases(self.folder / name) for name in self.FILES}

    def test_cases_are_new_and_cover_sql_and_no_data(self):
        seen = {item["pregunta"].casefold() for item in BUILT_IN_EXAMPLES}
        for name in ("golden_set.yaml", "casos_consulta.yaml", "examples.yaml"):
            others = yaml.safe_load((self.folder / name).read_text(encoding="utf-8"))
            seen |= {case["pregunta"].casefold() for case in others}
        ids = [case["id"] for cases in self.files.values() for case in cases]
        self.assertEqual(len(ids), len(set(ids)))
        for name, cases in self.files.items():
            with self.subTest(archivo=name):
                self.assertGreaterEqual(sum(case["tipo_esperado"] == "sql" for case in cases), 5)
                self.assertGreaterEqual(sum(case["tipo_esperado"] == "sin_datos" for case in cases), 1)
            for case in cases:
                with self.subTest(caso=case["id"]):
                    self.assertNotIn(case["pregunta"].casefold(), seen)
                    self.assertTrue(case["notas"].strip())
                seen.add(case["pregunta"].casefold())

    def test_reference_sql_passes_the_validator_and_the_coverage_check(self):
        coverage = Coverage.from_rows(M9_ROWS)
        for cases in self.files.values():
            for case in cases:
                sql = case.get("sql_esperado") or case.get("sql_ingenuo")
                if not sql:  # f04: the model must say "sin datos" by itself; there is no naive SQL
                    continue
                with self.subTest(caso=case["id"]):
                    check = check_coverage(validate_sql(sql), coverage)
                    self.assertEqual(check.sin_datos is not None, case["tipo_esperado"] == "sin_datos")

    def test_only_f04_is_caught_as_a_missing_concept(self):
        """f04 asks for the 69-B situation, which the views lack (A5, mejora 18)."""
        for cases in self.files.values():
            for case in cases:
                with self.subTest(caso=case["id"]):
                    if case["id"] == "f04":
                        self.assertIsNotNone(missing_concept(case["pregunta"]))
                    else:
                        self.assertIsNone(missing_concept(case["pregunta"]))


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

    def test_sql_rejected_twice_by_the_database_is_an_execution_error(self):
        answer = {"tipo": "error", "motivo": "PostgreSQL rechazó…", "intentos": 2, "sql_rechazado": "SELECT c.*"}
        row = evaluate(CASE_SQL, answer, [{"n": 1}])
        self.assertEqual(row["error"], "error_ejecucion")
        self.assertEqual(row["sql"], "SELECT c.*")


class AttemptsAndConsistencyTests(unittest.TestCase):
    """A5, mejora 9: what the measurement keeps about retries and repetitions."""

    def test_detail_keeps_the_error_of_each_failed_attempt(self):
        answer = {"tipo": "sql", "sql": "s", "intentos": 2, "intentos_fallidos": [
            {"intento": 1, "etapa": "validador", "error": "Tabla no permitida", "sql": "x"},
        ]}
        row = evaluate(CASE_SQL, answer, [{"n": 1}], [{"n": 1}])
        self.assertEqual(row["errores_intentos"], "1 validador: Tabla no permitida")
        self.assertEqual(evaluate(CASE_NO_DATA, {"tipo": "sin_datos", "motivo": "m"})["errores_intentos"], "")

    def test_consistency_counts_cases_with_the_same_sql_and_verdict(self):
        same = {"id": "q01", "sql": "s", "correcto": True, "error": None}
        results = [same, same, same, {**same, "id": "q07"}, {**same, "id": "q07", "sql": "t", "correcto": False}]
        self.assertEqual(
            consistency(results),
            {"casos": 2, "consistentes": 1, "pct": 50.0, "casos_que_variaron": ["q07"]},
        )

    def test_consistency_needs_more_than_one_repetition(self):
        self.assertIsNone(consistency([{"id": "q01", "sql": "s", "correcto": True, "error": None}]))

    def test_report_warns_about_empty_expected_results_and_shows_consistency(self):
        results = [
            evaluate(CASE_SQL, {"tipo": "sql", "sql": "s", "intentos": 1}, [], []),
            evaluate(CASE_SQL, {"tipo": "sql", "sql": "s", "intentos": 1}, [], []),
        ]
        summary = summarize(results)
        self.assertEqual(summary["esperados_vacios"], ["q01"])
        with tempfile.TemporaryDirectory() as folder:
            output = Path(folder) / "consulta"
            metadata = {"modelo": "m", "casos": 1, "repeticiones": 2, "fecha": "2026-11-19"}
            write_report(output, results, summary, metadata)
            report = (output / "resumen.md").read_text(encoding="utf-8")
        self.assertIn("q01 tienen un resultado esperado vacío", report)
        self.assertIn("1 de 1 casos (100.0 %)", report)


class AskAndExecuteTests(unittest.TestCase):
    def test_returns_the_rows_of_a_sql_answer(self):
        answer = {"tipo": "sql", "sql": "s", "intentos": 1, "filas": [{"n": 1}]}
        self.assertEqual(ask_and_execute("¿?", lambda question: answer), (answer, [{"n": 1}], None))

    def test_other_answers_have_no_rows(self):
        answer = {"tipo": "sin_datos", "motivo": "m", "intentos": 1}
        self.assertEqual(ask_and_execute("¿?", lambda question: answer), (answer, None, None))

    def test_a_database_error_the_agent_does_not_retry_is_recorded(self):
        def timeout(question):
            raise pg_errors.QueryCanceled("canceling statement due to statement timeout")

        answer, rows, detail = ask_and_execute("¿?", timeout)
        self.assertEqual(answer["tipo"], "error")
        self.assertIsNone(rows)
        self.assertIn("QueryCanceled", detail)
        self.assertEqual(evaluate(CASE_SQL, answer, [{"n": 1}], rows, detail)["error"], "error_ejecucion")


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
