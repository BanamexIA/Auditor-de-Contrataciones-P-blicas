import unittest
from pathlib import Path

import yaml

from agents.consulta.concepts import missing_concept, missing_concept_reason


ROOT = Path(__file__).resolve().parents[1]


class MissingConceptTests(unittest.TestCase):
    """A5, mejora 5: concepts the sources never record."""

    def test_c10_asks_about_cancellations(self):
        self.assertEqual(missing_concept("¿Qué contratos se cancelaron antes de terminar?"), "cancelaciones de contratos")

    def test_detects_each_concept_in_its_usual_forms(self):
        cases = {
            "¿Cuántas CANCELACIONES hubo en 2026?": "cancelaciones",
            "¿Qué contratos fueron rescindidos?": "rescisiones",
            "Muestra las rescisiones de la SEP.": "rescisiones",
            "¿Hubo convenios modificatorios?": "modificatorios",
            "¿Qué contratos se modificaron?": "modificatorios",
            "¿Cuánto se pagó a ese proveedor?": "pagos",
            "¿Qué contratos están pagados?": "pagos",
            "¿Qué proveedores fueron sancionados?": "sanciones",
            "¿Hay empresas inhabilitadas?": "inhabilitaciones",
            "¿Qué contratos tuvieron penalizaciones?": "penalizaciones",
            "¿Cuántas multas se aplicaron?": "multas",
        }
        for question, fragment in cases.items():
            with self.subTest(pregunta=question):
                self.assertIn(fragment, missing_concept(question) or "")

    def test_reason_names_the_concept_and_rules_out_substitutes(self):
        reason = missing_concept_reason("cancelaciones de contratos")
        self.assertIn("no registran cancelaciones de contratos", reason)
        self.assertIn("ninguna otra columna lo sustituye", reason)

    def test_no_reference_question_with_data_is_caught(self):
        questions = []
        for name in ("golden_set.yaml", "casos_consulta.yaml", "casos_empresa.yaml", "examples.yaml"):
            for case in yaml.safe_load((ROOT / "eval" / name).read_text(encoding="utf-8")):
                if case.get("id") != "c10":
                    questions.append(case["pregunta"])
        questions += ["¿Cuánto se gastó en adjudicaciones directas?", "Muestra la página 2 de resultados."]
        for question in questions:
            with self.subTest(pregunta=question):
                self.assertIsNone(missing_concept(question))


if __name__ == "__main__":
    unittest.main()
