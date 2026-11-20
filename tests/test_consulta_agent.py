import json
import unittest

from psycopg import errors as pg_errors

from agents.consulta.agent import MAX_ATTEMPTS, answer_question, talks_about_coverage
from agents.consulta.coverage import Coverage
from agents.consulta.prompt import LIMIT_ADDED_NOTE, provider_note
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
# Passes the validator but PostgreSQL rejects it, like q08 on 2026-11-17.
GROUPING_SQL = (
    "SELECT c.*, COUNT(*) AS contratos FROM clean.v_contratos_agente AS c "
    "GROUP BY c.codigo_contrato LIMIT 20"
)
GROUPING_ERROR = 'column "c.codigo_expediente" must appear in the GROUP BY clause'


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


class FailedAttemptsTests(unittest.TestCase):
    """A5, mejora 9: each failed attempt says which stage rejected it and why."""

    def test_first_try_success_has_no_failed_attempts(self):
        self.assertEqual(ask(FakeClient(sql_answer(VALID_SQL)))["intentos_fallidos"], [])

    def test_validator_rejection_keeps_the_proposed_sql(self):
        bad = "SELECT * FROM clean.contratos LIMIT 1"
        result = ask(FakeClient(sql_answer(bad), sql_answer(VALID_SQL)))
        self.assertEqual(len(result["intentos_fallidos"]), 1)
        failed = result["intentos_fallidos"][0]
        self.assertEqual((failed["intento"], failed["etapa"], failed["sql"]), (1, "validador", bad))
        self.assertIn("Tabla no permitida", failed["error"])

    def test_format_and_database_failures_are_told_apart(self):
        client = FakeClient("no es JSON", sql_answer(GROUPING_SQL))
        execute = FakeExecutor(pg_errors.GroupingError(GROUPING_ERROR))
        result = ask(client, execute=execute)
        self.assertEqual(result["tipo"], "error")
        self.assertEqual([item["etapa"] for item in result["intentos_fallidos"]], ["formato", "base"])
        self.assertIsNone(result["intentos_fallidos"][0]["sql"])
        self.assertIn("SELECT c.*", result["intentos_fallidos"][1]["sql"])


class MissingConceptTests(unittest.TestCase):
    """A5, mejora 5: c10 must answer "sin datos" instead of a substitute column."""

    C10 = "¿Qué contratos se cancelaron antes de terminar?"

    def test_c10_sql_with_a_substitute_column_becomes_no_data(self):
        # The SQL the model wrote for c10 on 2026-11-17.
        sql = (
            "SELECT codigo_contrato, titulo_contrato, fecha_inicio, fecha_fin, fecha_fin_antes_inicio "
            "FROM clean.v_contratos_agente WHERE fecha_fin_antes_inicio AND fecha_inicio_valida "
            "AND fuente = 'comprasmx' LIMIT 50"
        )
        execute = FakeExecutor()
        result = ask(FakeClient(sql_answer(sql)), question=self.C10, execute=execute)
        self.assertEqual(result["tipo"], "sin_datos")
        self.assertIn("cancelaciones", result["motivo"])
        self.assertIn("fecha_fin_antes_inicio", result["sql_descartado"])
        self.assertEqual(execute.queries, [])

    def test_a_clarification_about_a_missing_concept_becomes_no_data(self):
        answer = {"tipo": "aclaracion", "pregunta": "¿De qué fuente?", "opciones": ["ComprasMX", "Histórico"]}
        result = ask(FakeClient(json.dumps(answer)), question=self.C10)
        self.assertEqual(result["tipo"], "sin_datos")
        self.assertNotIn("sql_descartado", result)

    def test_the_reason_comes_from_code_even_if_the_model_said_no_data(self):
        # The model's reason for c10 on 2026-11-19 also claimed end dates are not recorded.
        answer = {"tipo": "sin_datos", "motivo": "No se registran cancelaciones ni fechas de finalización."}
        result = ask(FakeClient(json.dumps(answer)), question=self.C10)
        self.assertEqual(result["tipo"], "sin_datos")
        self.assertIn("no registran cancelaciones de contratos", result["motivo"])
        self.assertNotIn("fechas de finalización", result["motivo"])


class CoverageNotesTests(unittest.TestCase):
    """A5, mejora 6: only the coverage check writes notes about coverage."""

    def test_detects_the_model_notes_seen_in_a4(self):
        for note in (
            "el año 2024 está completo",
            "El año del periodo está incompleto",
            "El año 2026 está completo",
            "Cobertura incompleta en CompraNet histórico para 2024.",
            "Los datos de 2010 son parciales.",
            "No hay datos para 2025.",
        ):
            with self.subTest(supuesto=note):
                self.assertTrue(talks_about_coverage(note))

    def test_keeps_notes_about_interpretation(self):
        for note in (
            "Se cuentan registros de contrato, no contratos únicos.",
            "El importe es importe registrado, no gasto pagado.",
            "Se excluyen contratos sin fecha válida.",
            LIMIT_ADDED_NOTE,
        ):
            with self.subTest(supuesto=note):
                self.assertFalse(talks_about_coverage(note))

    def test_system_notes_survive_even_if_a_name_sounds_like_coverage(self):
        sql = (
            "SELECT COUNT(*) AS contratos FROM clean.v_contratos_agente "
            "WHERE fuente = 'comprasmx' AND proveedor_normalizado = 'Servicios Completos' LIMIT 1"
        )
        result = ask(FakeClient(sql_answer(sql)))
        self.assertIn(provider_note("SERVICIOS COMPLETOS"), result["supuestos"])

    def test_a_false_model_note_is_replaced_by_the_coverage_check(self):
        # q04 on 2026-11-17: the model said 2024 was complete next to the correct warning.
        sql = (
            "SELECT COUNT(*) AS contratos FROM clean.v_contratos_agente "
            "WHERE fuente = 'historico' AND EXTRACT(YEAR FROM fecha_inicio) = 2024 LIMIT 1"
        )
        model_notes = ["El año 2024 está completo.", "Se cuentan registros de contrato."]
        result = ask(FakeClient(sql_answer(sql, supuestos=model_notes)))
        self.assertEqual(
            result["supuestos"],
            ["Se cuentan registros de contrato.", "Cobertura incompleta en CompraNet histórico para 2024."],
        )


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
        client = FakeClient(sql_answer(GROUPING_SQL), sql_answer(VALID_SQL))
        execute = FakeExecutor(pg_errors.GroupingError(GROUPING_ERROR), ROWS)
        result = ask(client, execute=execute)
        self.assertEqual(result["tipo"], "sql")
        self.assertEqual(result["intentos"], 2)
        self.assertEqual(result["filas"], ROWS)
        self.assertIn(f"PostgreSQL rechazó la consulta: {GROUPING_ERROR}", client.prompts[1])
        self.assertIn("SELECT c.*", client.prompts[1])
        self.assertEqual(len(execute.queries), 2)

    def test_a_second_rejection_returns_error_with_the_rejected_sql(self):
        client = FakeClient(sql_answer(GROUPING_SQL), sql_answer(GROUPING_SQL))
        execute = FakeExecutor(pg_errors.GroupingError(GROUPING_ERROR), pg_errors.GroupingError(GROUPING_ERROR))
        result = ask(client, execute=execute)
        self.assertEqual(result["tipo"], "error")
        self.assertEqual(result["intentos"], MAX_ATTEMPTS)
        self.assertIn("PostgreSQL rechazó la consulta", result["motivo"])
        self.assertIn("SELECT c.*", result["sql_rechazado"])

    def test_a_misplaced_column_is_caught_before_the_database(self):
        # A5, mejora 3: q07's mistake no longer reaches PostgreSQL.
        client = FakeClient(
            sql_answer("SELECT COUNT(*) FROM clean.v_contratos_agente WHERE rfc_exacto LIMIT 1"),
            sql_answer(VALID_SQL),
        )
        execute = FakeExecutor(ROWS)
        result = ask(client, execute=execute)
        self.assertEqual(result["tipo"], "sql")
        self.assertEqual(result["intentos"], 2)
        self.assertIn("JOIN por codigo_contrato", client.prompts[1])
        self.assertEqual(len(execute.queries), 1)

    def test_a_format_error_after_a_rejection_does_not_keep_the_rejected_sql(self):
        client = FakeClient(sql_answer(GROUPING_SQL), "no es JSON")
        execute = FakeExecutor(pg_errors.GroupingError(GROUPING_ERROR))
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
