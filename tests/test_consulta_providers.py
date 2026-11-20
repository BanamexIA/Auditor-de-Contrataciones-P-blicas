import ast
import re
import unicodedata
import unittest
from pathlib import Path

from agents.consulta.providers import normalize_provider, normalize_provider_literals
from agents.consulta.validator import validate_sql

ROOT = Path(__file__).resolve().parents[1]
CONTRATOS = "clean.v_contratos_agente"


def etl_normalize_provider():
    """The ETL function itself, read from etl/build_clean.py without importing the module.

    Importing it would load the .env and need etl/ on the path; only the two
    functions are executed.
    """
    tree = ast.parse((ROOT / "etl" / "build_clean.py").read_text(encoding="utf-8"))
    functions = [node for node in tree.body
                 if isinstance(node, ast.FunctionDef) and node.name in {"normalize_text", "normalize_provider"}]
    namespace = {"re": re, "unicodedata": unicodedata}
    exec(compile(ast.Module(body=functions, type_ignores=[]), "build_clean.py", "exec"), namespace)
    return namespace["normalize_provider"]


class NormalizeProviderTests(unittest.TestCase):
    """A5, mejora 12: the same rule the ETL used to fill proveedor_normalizado."""

    def test_matches_the_etl_rule(self):
        etl = etl_normalize_provider()
        for name in (
            "Molinera de México", "MOLINERA DE MEXICO SA DE CV", "Brand and Push, S.A. de C.V.",
            "Molinos Azteca", "Construcciones & Servicios del Norte S. de R.L.", "  José  Pérez  López ",
            "ACTIVOS Y SOLUCIONES ANRO SC", None, "",
        ):
            with self.subTest(nombre=name):
                self.assertEqual(normalize_provider(name), etl(name))

    def test_company_cases_find_their_names(self):
        self.assertEqual(normalize_provider("Molinera de México"), "MOLINERA DE MEXICO")
        self.assertEqual(normalize_provider("Brand and Push"), "BRAND AND PUSH")


class NormalizeLiteralsTests(unittest.TestCase):
    def test_rewrites_an_equality_and_reports_the_name(self):
        sql, changed = normalize_provider_literals(
            f"SELECT COUNT(*) FROM {CONTRATOS} WHERE proveedor_normalizado = 'Molinera de México' LIMIT 1"
        )
        self.assertIn("proveedor_normalizado = 'MOLINERA DE MEXICO'", sql)
        self.assertEqual(changed, ["MOLINERA DE MEXICO"])
        validate_sql(sql)

    def test_rewrites_in_like_ilike_and_a_literal_on_the_left(self):
        cases = {
            f"SELECT * FROM {CONTRATOS} AS c WHERE c.proveedor_normalizado IN ('Brand and Push', 'Molinos Azteca') LIMIT 5":
                "IN ('BRAND AND PUSH', 'MOLINOS AZTECA')",
            f"SELECT * FROM {CONTRATOS} WHERE proveedor_normalizado ILIKE '%molinera de méxico%' LIMIT 5":
                "ILIKE '%MOLINERA DE MEXICO%'",
            f"SELECT * FROM {CONTRATOS} WHERE 'Molinos Azteca' = proveedor_normalizado LIMIT 5":
                "'MOLINOS AZTECA' = proveedor_normalizado",
            f"SELECT * FROM {CONTRATOS} WHERE UPPER(proveedor_normalizado) <> 'brand and push' LIMIT 5":
                "<> 'BRAND AND PUSH'",
        }
        for query, fragment in cases.items():
            with self.subTest(sql=query[60:120]):
                self.assertIn(fragment, normalize_provider_literals(query)[0])

    def test_leaves_other_columns_and_normalized_names_alone(self):
        for query in (
            f"SELECT * FROM {CONTRATOS} WHERE proveedor = 'Molinera de México' LIMIT 5",
            f"SELECT * FROM {CONTRATOS} WHERE nombre_de_la_uc = 'Molinera de México' LIMIT 5",
            f"SELECT * FROM {CONTRATOS} WHERE proveedor_normalizado = 'MOLINERA DE MEXICO' LIMIT 5",
            "SELECT FROM WHERE",
        ):
            with self.subTest(sql=query[:80]):
                self.assertEqual(normalize_provider_literals(query), (query, []))


if __name__ == "__main__":
    unittest.main()
