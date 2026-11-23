import unittest

from eval.run_escenario import evidence_entry, load_scenario, to_markdown, visible_rows


class ScenarioFileTests(unittest.TestCase):
    def test_one_question_per_criterion(self):
        items = load_scenario()
        ids = [item["id"] for item in items]
        self.assertEqual(len(ids), len(set(ids)))
        self.assertGreaterEqual(len(items), 6)


class EvidenceTests(unittest.TestCase):
    def test_hides_columns_that_can_hold_names_of_people(self):
        rows = [{"codigo_contrato": "C-1", "proveedor": "X", "proveedor_normalizado": "X", "rfc": "Y", "importe": 1}]
        self.assertEqual(visible_rows(rows), [{"codigo_contrato": "C-1", "importe": 1}])

    def test_markdown_has_sql_notes_count_and_failed_attempts(self):
        item = {"id": "s1", "criterio": "Cuenta registros", "pregunta": "¿Cuántos?", "esperado": "Un conteo"}
        answer = {
            "tipo": "sql", "intentos": 2, "sql": "SELECT 1", "supuestos": ["Una nota"],
            "conteo": {"filas": 1, "filas_totales": 1, "truncado": False, "registros": 5},
            "filas": [{"n": 5}],
            "intentos_fallidos": [{"intento": 1, "etapa": "validador", "error": "Mal", "sql": None}],
        }
        text = to_markdown([evidence_entry(item, answer, 1.0)], "modelo", "2026-11-23T12:00:00")
        for fragment in ("SELECT 1", "Supuesto: Una nota", "5 registros detrás", "| n |", "Intento 1 rechazado (validador): Mal"):
            self.assertIn(fragment, text)

    def test_clarification_shows_the_question_and_options(self):
        item = {"id": "s3", "criterio": "Pide precisión", "pregunta": "¿Cuántos?", "esperado": "Aclaración"}
        answer = {"tipo": "aclaracion", "intentos": 1, "pregunta": "¿Cuál?", "opciones": ["A", "B"], "intentos_fallidos": []}
        text = to_markdown([evidence_entry(item, answer, 1.0)], "modelo", "2026-11-23T12:00:00")
        self.assertIn("> ¿Cuál?", text)
        self.assertIn("> - B", text)


if __name__ == "__main__":
    unittest.main()
