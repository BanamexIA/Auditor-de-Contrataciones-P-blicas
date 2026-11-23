import json
import unittest

from agents.consulta.agencies import uppercase_agency_literals
from agents.consulta.prompt import agency_note, is_system_note, parse_response

V = "clean.v_contratos_agente"


class UppercaseAgencyLiteralsTests(unittest.TestCase):
    """A5, mejora 26: agency names are stored in upper case."""

    def test_s3_as_the_model_wrote_it(self):
        # Escenario 1 s3 on 2026-11-23: 0 contracts instead of 239.
        sql, names = uppercase_agency_literals(
            f"SELECT COUNT(*) AS contratos FROM {V} WHERE fuente = 'comprasmx' AND institucion = 'Secretaría de Salud' LIMIT 1"
        )
        self.assertIn("institucion = 'SECRETARÍA DE SALUD'", sql)
        self.assertIn("fuente = 'comprasmx'", sql)
        self.assertEqual(names, ["SECRETARÍA DE SALUD"])

    def test_every_agency_column_and_operator(self):
        for condition, expected in (
            ("nombre_de_la_uc = 'Dirección de Adquisiciones'", "'DIRECCIÓN DE ADQUISICIONES'"),
            ("'Ramo Salud' = descripcion_ramo", "'RAMO SALUD'"),
            ("c.institucion <> 'Secretaría de Salud'", "'SECRETARÍA DE SALUD'"),
            ("institucion IN ('Secretaría de Salud', 'IMSS')", "IN ('SECRETARÍA DE SALUD', 'IMSS')"),
            ("institucion LIKE '%Salud%'", "LIKE '%SALUD%'"),
            ("UPPER(institucion) = 'secretaría de salud'", "'SECRETARÍA DE SALUD'"),
            ("siglas_de_la_institucion = 'ssa'", "'SSA'"),
        ):
            with self.subTest(condition=condition):
                sql, names = uppercase_agency_literals(f"SELECT COUNT(*) AS c FROM {V} AS c WHERE {condition} LIMIT 1")
                self.assertIn(expected, sql)
                self.assertTrue(names)

    def test_leaves_other_columns_and_case_free_comparisons(self):
        for query in (
            f"SELECT COUNT(*) AS c FROM {V} WHERE institucion = 'SECRETARÍA DE SALUD' LIMIT 1",
            f"SELECT COUNT(*) AS c FROM {V} WHERE institucion ILIKE '%salud%' LIMIT 1",
            f"SELECT COUNT(*) AS c FROM {V} WHERE LOWER(institucion) = 'secretaría de salud' LIMIT 1",
            f"SELECT COUNT(*) AS c FROM {V} WHERE fuente = 'comprasmx' AND moneda = 'MXN' LIMIT 1",
            "SELECT * FROM",
        ):
            with self.subTest(query=query):
                self.assertEqual(uppercase_agency_literals(query), (query, []))


class AgencyNoteTests(unittest.TestCase):
    def test_parse_response_rewrites_and_notes_the_name(self):
        response = parse_response(json.dumps({
            "tipo": "sql",
            "sql": f"SELECT COUNT(*) AS contratos FROM {V} WHERE institucion = 'Secretaría de Salud' LIMIT 1",
        }))
        self.assertIn("'SECRETARÍA DE SALUD'", response["sql"])
        self.assertIn(agency_note("SECRETARÍA DE SALUD"), response["supuestos"])
        self.assertTrue(is_system_note(agency_note("SECRETARÍA DE SALUD")))


if __name__ == "__main__":
    unittest.main()
