import json
import unittest

from psycopg import errors as pg_errors

from agents.consulta.agent import MAX_ATTEMPTS, answer_question
from agents.consulta.coverage import Coverage
from agents.consulta.prompt import LIMIT_ADDED_NOTE
from llm.base import LLMClient, LLMResponse


COVERAGE = Coverage.from_rows([
    (2023, "historico", 16896), (2024, "historico", 1836), (2022, "historico", 198510),
    (2021, "historico", 204035), (2026, "comprasmx", 84676),
])
VALID_SQL = "SELECT fuente, COUNT(*) AS contratos FROM clean.v_contratos_agente GROUP BY fuente LIMIT 20"


class FakeClient(LLMClient):
    provider = "fake"
    model = "fake"

    def __init__(self, *answers):
        self.answers = list(answers)
        self.prompts = []

    def generate(self, system, prompt, temperature=0.0):
        self.prompts.append(prompt)
        return LLMResponse(text=self.answers.pop(0), input_tokens=0, output_tokens=0, latency_ms=0.0)


class FakeExecutor:
    """Stands in for execute_read_only: returns rows or raises, in order."""

    def __init__(self, *outcomes):
        self.outcomes = list(outcomes)
        self.queries = []

    def __call__(self, sql):
        self.queries.append(sql)
        outcome = self.outcomes.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        return outcome


def sql_answer(sql, supuestos=()):
    return json.dumps({"tipo": "sql", "sql": sql, "filtros": [], "supuestos": list(supuestos)})


def ask(client, question="¿Cuántos contratos hay?", clarifications=(), execute=None):
    return answer_question(question, client, "sistema", COVERAGE, clarifications, execute=execute)


ROWS = [{"fuente": "comprasmx", "contratos": 84676}]
BAD_COLUMN_SQL = "SELECT COUNT(*) FROM clean.v_contratos_agente WHERE rfc_exacto LIMIT 1"


class AnswerQuestionTests(unittest.TestCase):
    def test_valid_sql_on_the_first_try(self):
        result = ask(FakeClient(sql_answer(VALID_SQL)))
        self.assertEqual(result["tipo"], "sql")
        self.assertEqual(result["intentos"], 1)

    def test_retries_once_with_the_error(self):
        client = FakeClient(
            sql_answer("SELECT * FROM clean.contratos LIMIT 1"),
            sql_answer(VALID_SQL),
        )
        result = ask(client)
        self.assertEqual(result["tipo"], "sql")
        self.assertEqual(result["intentos"], 2)
        self.assertIn("Tabla no permitida", client.prompts[1])

    def test_missing_limit_is_added_without_a_retry(self):
        client = FakeClient(
            sql_answer("SELECT fuente, COUNT(*) AS contratos FROM clean.v_contratos_agente GROUP BY fuente")
        )
        result = ask(client)
        self.assertEqual(result["tipo"], "sql")
        self.assertEqual(result["intentos"], 1)
        self.assertEqual(len(client.prompts), 1)
        self.assertTrue(result["sql"].endswith("LIMIT 200"))
        self.assertIn(LIMIT_ADDED_NOTE, result["supuestos"])

    def test_returns_error_after_the_retry_fails(self):
        client = FakeClient("no es JSON", "tampoco")
        result = ask(client)
        self.assertEqual(result["tipo"], "error")
        self.assertEqual(result["intentos"], MAX_ATTEMPTS)
        self.assertIn("no contiene un objeto JSON", result["motivo"])
        self.assertEqual(len(client.prompts), MAX_ATTEMPTS)

    def test_clarification_is_returned_without_sql(self):
        answer = {"tipo": "aclaracion", "pregunta": "¿Por número o por importe?", "opciones": ["Número", "Importe"]}
        result = ask(FakeClient(json.dumps(answer)))
        self.assertEqual(result["tipo"], "aclaracion")
        self.assertNotIn("sql", result)

    def test_sql_for_a_period_without_data_becomes_no_data(self):
        sql = (
            "SELECT COUNT(*) AS contratos FROM clean.v_contratos_agente "
            "WHERE fecha_inicio >= DATE '2025-01-01' AND fecha_inicio < DATE '2026-01-01' LIMIT 1"
        )
        result = ask(FakeClient(sql_answer(sql)))
        self.assertEqual(result["tipo"], "sin_datos")
        self.assertIn("2025", result["motivo"])
        self.assertIn("2025-01-01", result["sql_descartado"])

    def test_partial_year_note_is_added_once(self):
        sql = (
            "SELECT COUNT(*) AS contratos FROM clean.v_contratos_agente "
            "WHERE fuente = 'historico' AND EXTRACT(YEAR FROM fecha_inicio) = 2024 LIMIT 1"
        )
        note = "Cobertura incompleta en CompraNet histórico para 2024."
        result = ask(FakeClient(sql_answer(sql, supuestos=[note])))
        self.assertEqual(result["tipo"], "sql")
        self.assertEqual(result["supuestos"], [note])

    def test_without_an_executor_nothing_runs(self):
        result = ask(FakeClient(sql_answer(VALID_SQL)))
        self.assertNotIn("filas", result)

    def test_clarifications_reach_the_model(self):
        client = FakeClient(sql_answer(VALID_SQL))
        ask(client, clarifications=[("¿Por número o por importe?", "Por número de contratos")])
        self.assertIn("Respuesta del auditor: Por número de contratos", client.prompts[0])
        self.assertIn("no vuelvas a preguntar", client.prompts[0])


class ExecutionRetryTests(unittest.TestCase):
    """A5, mejora 2: when PostgreSQL rejects the SQL, the model gets the error."""

    def test_rows_come_back_when_the_sql_runs(self):
        execute = FakeExecutor(ROWS)
        result = ask(FakeClient(sql_answer(VALID_SQL)), execute=execute)
        self.assertEqual(result["tipo"], "sql")
        self.assertEqual(result["intentos"], 1)
        self.assertEqual(result["filas"], ROWS)
        self.assertEqual(execute.queries, [result["sql"]])

    def test_a_database_rejection_is_retried_with_the_sql_and_the_error(self):
        client = FakeClient(sql_answer(BAD_COLUMN_SQL), sql_answer(VALID_SQL))
        execute = FakeExecutor(pg_errors.UndefinedColumn('column "rfc_exacto" does not exist'), ROWS)
        result = ask(client, execute=execute)
        self.assertEqual(result["tipo"], "sql")
        self.assertEqual(result["intentos"], 2)
        self.assertEqual(result["filas"], ROWS)
        self.assertIn('PostgreSQL rechazó la consulta: column "rfc_exacto" does not exist', client.prompts[1])
        self.assertIn("rfc_exacto LIMIT 1", client.prompts[1])
        self.assertEqual(len(execute.queries), 2)

    def test_a_second_rejection_returns_error_with_the_rejected_sql(self):
        client = FakeClient(sql_answer(BAD_COLUMN_SQL), sql_answer(BAD_COLUMN_SQL))
        execute = FakeExecutor(
            pg_errors.GroupingError("must appear in the GROUP BY clause"),
            pg_errors.GroupingError("must appear in the GROUP BY clause"),
        )
        result = ask(client, execute=execute)
        self.assertEqual(result["tipo"], "error")
        self.assertEqual(result["intentos"], MAX_ATTEMPTS)
        self.assertIn("PostgreSQL rechazó la consulta", result["motivo"])
        self.assertIn("rfc_exacto", result["sql_rechazado"])

    def test_a_format_error_after_a_rejection_does_not_keep_the_rejected_sql(self):
        client = FakeClient(sql_answer(BAD_COLUMN_SQL), "no es JSON")
        execute = FakeExecutor(pg_errors.UndefinedColumn('column "rfc_exacto" does not exist'))
        result = ask(client, execute=execute)
        self.assertEqual(result["tipo"], "error")
        self.assertNotIn("sql_rechazado", result)

    def test_timeouts_and_connection_errors_are_not_retried(self):
        client = FakeClient(sql_answer(VALID_SQL), sql_answer(VALID_SQL))
        execute = FakeExecutor(pg_errors.QueryCanceled("canceling statement due to statement timeout"))
        with self.assertRaises(pg_errors.QueryCanceled):
            ask(client, execute=execute)
        self.assertEqual(len(client.prompts), 1)

    def test_sql_without_data_is_not_executed(self):
        sql = (
            "SELECT COUNT(*) AS contratos FROM clean.v_contratos_agente "
            "WHERE fecha_inicio >= DATE '2025-01-01' AND fecha_inicio < DATE '2026-01-01' LIMIT 1"
        )
        execute = FakeExecutor()
        result = ask(FakeClient(sql_answer(sql)), execute=execute)
        self.assertEqual(result["tipo"], "sin_datos")
        self.assertEqual(execute.queries, [])


if __name__ == "__main__":
    unittest.main()
