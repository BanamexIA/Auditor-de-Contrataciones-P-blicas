import json
import unittest
from pathlib import Path

import yaml

from agents.consulta.prompt import (
    BUILT_IN_EXAMPLES,
    ResponseFormatError,
    build_system_prompt,
    build_user_prompt,
    parse_response,
)
from agents.consulta.validator import MAX_SQL_ROWS, SQLValidationError


ROOT = Path(__file__).resolve().parents[1]
VALID_SQL = "SELECT fuente, COUNT(*) AS contratos FROM clean.v_contratos_agente GROUP BY fuente LIMIT 20"


class SystemPromptTests(unittest.TestCase):
    def setUp(self):
        self.examples = yaml.safe_load((ROOT / "eval" / "examples.yaml").read_text(encoding="utf-8"))
        self.prompt = build_system_prompt('{"v_contratos_agente": "esquema de prueba"}', self.examples)

    def test_includes_the_schema_views_and_row_limit(self):
        self.assertIn("esquema de prueba", self.prompt)
        self.assertIn("clean.v_contratos_agente", self.prompt)
        self.assertIn("clean.v_coincidencias_69b_agente", self.prompt)
        self.assertIn(f"entre 1 y {MAX_SQL_ROWS}", self.prompt)

    def test_describes_the_three_response_types(self):
        for response_type in ("sql", "aclaracion", "sin_datos"):
            self.assertIn(f'"tipo": "{response_type}"', self.prompt)

    def test_includes_the_data_rules(self):
        self.assertIn("No hay contratos con inicio en 2025", self.prompt)
        self.assertIn("COUNT(DISTINCT codigo_contrato)", self.prompt)

    def test_renders_every_example_as_a_valid_response(self):
        self.assertEqual(self.prompt.count("Pregunta: "), len(self.examples) + len(BUILT_IN_EXAMPLES))
        for line in self.prompt.splitlines():
            if line.startswith("Respuesta: "):
                with self.subTest(respuesta=line[:60]):
                    parse_response(line.removeprefix("Respuesta: "))

    def test_built_in_examples_do_not_repeat_golden_questions(self):
        golden = yaml.safe_load((ROOT / "eval" / "golden_set.yaml").read_text(encoding="utf-8"))
        questions = {case["pregunta"].casefold() for case in golden}
        for example in BUILT_IN_EXAMPLES:
            self.assertNotIn(example["pregunta"].casefold(), questions)

    def test_user_prompt_carries_the_question(self):
        self.assertEqual(build_user_prompt("  ¿Cuántos contratos hay?  "), "Pregunta del auditor: ¿Cuántos contratos hay?")


class ParseResponseTests(unittest.TestCase):
    def test_parses_a_sql_response_and_validates_it(self):
        response = parse_response(json.dumps({
            "tipo": "sql",
            "sql": VALID_SQL,
            "filtros": ["todas las fuentes"],
            "supuestos": [],
        }))
        self.assertEqual(response["tipo"], "sql")
        self.assertIn("clean.v_contratos_agente", response["sql"])
        self.assertEqual(response["filtros"], ["todas las fuentes"])

    def test_accepts_json_inside_a_code_fence_with_surrounding_text(self):
        text = 'Claro:\n```json\n{"tipo": "sin_datos", "motivo": "No hay inicios en 2025."}\n```'
        self.assertEqual(parse_response(text), {"tipo": "sin_datos", "motivo": "No hay inicios en 2025."})

    def test_missing_lists_default_to_empty(self):
        response = parse_response(json.dumps({"tipo": "sql", "sql": VALID_SQL}))
        self.assertEqual(response["filtros"], [])
        self.assertEqual(response["supuestos"], [])

    def test_parses_a_clarification_with_options(self):
        response = parse_response(json.dumps({
            "tipo": "aclaracion",
            "pregunta": "¿Qué periodo?",
            "opciones": ["2024", "2026"],
        }))
        self.assertEqual(response["opciones"], ["2024", "2026"])

    def test_sql_that_fails_the_validator_is_rejected(self):
        with self.assertRaisesRegex(SQLValidationError, "Tabla no permitida"):
            parse_response(json.dumps({"tipo": "sql", "sql": "SELECT * FROM clean.contratos LIMIT 1"}))

    def test_rejects_malformed_responses(self):
        cases = {
            "texto sin JSON": "SELECT 1",
            "JSON roto": '{"tipo": "sql", "sql": }',
            "lista en vez de objeto": '[{"tipo": "sql"}]',
            "tipo desconocido": '{"tipo": "respuesta"}',
            "sql vacío": '{"tipo": "sql", "sql": "  "}',
            "filtros no es lista": json.dumps({"tipo": "sql", "sql": VALID_SQL, "filtros": "fuente"}),
            "aclaración con una opción": '{"tipo": "aclaracion", "pregunta": "¿Cuál?", "opciones": ["a"]}',
            "sin datos sin motivo": '{"tipo": "sin_datos"}',
            "dos bloques": '```json\n{"tipo": "sin_datos", "motivo": "a"}\n```\n```json\n{}\n```',
        }
        for name, text in cases.items():
            with self.subTest(caso=name):
                with self.assertRaises(ResponseFormatError):
                    parse_response(text)


if __name__ == "__main__":
    unittest.main()
