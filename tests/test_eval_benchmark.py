import unittest
from unittest.mock import patch

from eval.run_benchmark import (
    SQLValidationError,
    benchmark_ollama_base_url,
    choose_ollama_models,
    load_golden_set,
    load_examples,
    result_digest,
    validate_sql,
)


class BenchmarkSqlValidationTests(unittest.TestCase):
    def test_accepts_a_limited_query_to_an_approved_view(self):
        query = validate_sql(
            "SELECT fuente, COUNT(*) AS contratos "
            "FROM clean.v_contratos_agente GROUP BY fuente LIMIT 20"
        )
        self.assertIn("clean.v_contratos_agente", query)

    def test_rejects_non_select_statement(self):
        with self.assertRaisesRegex(SQLValidationError, "Solo se permiten"):
            validate_sql("DELETE FROM clean.v_contratos_agente")

    def test_rejects_multiple_statements(self):
        with self.assertRaisesRegex(SQLValidationError, "exactamente una"):
            validate_sql("SELECT 1 LIMIT 1; SELECT 2 LIMIT 1")

    def test_rejects_unapproved_table(self):
        with self.assertRaisesRegex(SQLValidationError, "Tabla no permitida"):
            validate_sql("SELECT * FROM clean.contratos LIMIT 1")

    def test_rejects_unqualified_table(self):
        with self.assertRaisesRegex(SQLValidationError, "Tabla no permitida"):
            validate_sql("SELECT * FROM v_contratos_agente LIMIT 1")

    def test_rejects_missing_or_excessive_limit(self):
        with self.assertRaisesRegex(SQLValidationError, "LIMIT entero"):
            validate_sql("SELECT * FROM clean.v_contratos_agente")
        with self.assertRaisesRegex(SQLValidationError, "entre 1 y 200"):
            validate_sql("SELECT * FROM clean.v_contratos_agente LIMIT 201")

    def test_rejects_unrecognized_function(self):
        with self.assertRaisesRegex(SQLValidationError, "funciones SQL no reconocidas"):
            validate_sql("SELECT pg_sleep(1) FROM clean.v_contratos_agente LIMIT 1")

    def test_rejects_write_via_select_into(self):
        with self.assertRaisesRegex(SQLValidationError, "INTO"):
            validate_sql(
                "SELECT * INTO clean.copy FROM clean.v_contratos_agente LIMIT 1"
            )

    def test_loads_twenty_or_more_cases_and_validates_references(self):
        cases = load_golden_set()
        self.assertGreaterEqual(len(cases), 20)
        self.assertEqual(len({case["id"] for case in cases}), len(cases))
        examples = load_examples(cases)
        self.assertEqual(len(examples), 2)


class BenchmarkResultComparisonTests(unittest.TestCase):
    def test_digest_ignores_row_order_but_compares_column_names(self):
        rows = [{"fuente": "a", "contratos": 3}, {"fuente": "b", "contratos": 1}]
        self.assertEqual(result_digest(rows), result_digest(list(reversed(rows))))
        self.assertNotEqual(
            result_digest(rows),
            result_digest([{"fuente": "a", "conteo": 3}, {"fuente": "b", "conteo": 1}]),
        )

    @patch("eval.run_benchmark.setting", return_value="")
    def test_embedding_model_does_not_count_as_local_text_model(self, _setting):
        models = [
            {"name": "qwen2.5:0.5b", "size": 500_000_000, "capabilities": ["completion"]},
            {"name": "nomic-embed-text:latest", "size": 300_000_000, "capabilities": ["embedding"]},
        ]
        with self.assertRaisesRegex(RuntimeError, "dos modelos locales"):
            choose_ollama_models(models)

    @patch(
        "eval.run_benchmark.setting",
        return_value="http://host.docker.internal:11434",
    )
    def test_host_benchmark_resolves_docker_host_alias(self, _setting):
        self.assertEqual(benchmark_ollama_base_url(), "http://localhost:11434")


if __name__ == "__main__":
    unittest.main()
