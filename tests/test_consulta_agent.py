import json
import unittest

from agents.consulta.agent import MAX_ATTEMPTS, answer_question
from agents.consulta.coverage import Coverage
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


def sql_answer(sql, supuestos=()):
    return json.dumps({"tipo": "sql", "sql": sql, "filtros": [], "supuestos": list(supuestos)})


def ask(client, question="¿Cuántos contratos hay?", clarifications=()):
    return answer_question(question, client, "sistema", COVERAGE, clarifications)


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

    def test_clarifications_reach_the_model(self):
        client = FakeClient(sql_answer(VALID_SQL))
        ask(client, clarifications=[("¿Por número o por importe?", "Por número de contratos")])
        self.assertIn("Respuesta del auditor: Por número de contratos", client.prompts[0])
        self.assertIn("no vuelvas a preguntar", client.prompts[0])


if __name__ == "__main__":
    unittest.main()
