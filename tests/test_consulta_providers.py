import ast
import re
import unicodedata
import unittest
from pathlib import Path

from agents.consulta.providers import (
    SUFFIX_TAILS,
    add_suffix_variants,
    normalize_provider,
    normalize_provider_literals,
    provider_variants,
)
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


class SuffixVariantsTests(unittest.TestCase):
    """A5, mejora 19: f05 and f06 missed 'DISTRIBUIDORA UNIVERSAL TOBOSA S A DE C V'."""

    def test_variants_start_with_the_name_without_suffix(self):
        for name in ("DISTRIBUIDORA UNIVERSAL TOBOSA", "DISTRIBUIDORA UNIVERSAL TOBOSA S A DE C V"):
            with self.subTest(nombre=name):
                variants = provider_variants(name)
                self.assertEqual(variants[0], "DISTRIBUIDORA UNIVERSAL TOBOSA")
                self.assertIn("DISTRIBUIDORA UNIVERSAL TOBOSA S A DE C V", variants)
                self.assertEqual(len(variants), len(SUFFIX_TAILS) + 1)

    def test_the_longest_ending_is_removed(self):
        self.assertEqual(provider_variants("ACME S DE R L DE C V")[0], "ACME")
        self.assertEqual(provider_variants("ACME S DE R L MI")[0], "ACME")
        self.assertEqual(provider_variants("S A")[0], "S A")

    def test_equality_becomes_in_and_inequality_not_in(self):
        sql, names = add_suffix_variants(
            f"SELECT COUNT(*) FROM {CONTRATOS} WHERE proveedor_normalizado = 'DISTRIBUIDORA UNIVERSAL TOBOSA' "
            f"AND proveedor_normalizado <> 'ACME' LIMIT 1"
        )
        self.assertIn("proveedor_normalizado IN ('DISTRIBUIDORA UNIVERSAL TOBOSA', "
                      "'DISTRIBUIDORA UNIVERSAL TOBOSA S A DE C V'", sql)
        self.assertIn("NOT proveedor_normalizado IN ('ACME', 'ACME S A DE C V'", sql)
        self.assertEqual(names, ["DISTRIBUIDORA UNIVERSAL TOBOSA", "ACME"])
        validate_sql(sql)

    def test_an_in_list_gets_every_variant_once(self):
        sql, names = add_suffix_variants(
            f"SELECT * FROM {CONTRATOS} AS c WHERE c.proveedor_normalizado IN ('ACME', 'ACME S A DE C V') LIMIT 5"
        )
        self.assertEqual(sql.count("'ACME S A DE C V'"), 1)
        self.assertEqual(names, ["ACME"])

    def test_leaves_like_other_columns_and_subqueries_alone(self):
        for query in (
            f"SELECT * FROM {CONTRATOS} WHERE proveedor_normalizado LIKE 'ACME%' LIMIT 5",
            f"SELECT * FROM {CONTRATOS} WHERE proveedor = 'ACME' LIMIT 5",
            f"SELECT * FROM {CONTRATOS} WHERE proveedor_normalizado = '' LIMIT 5",
            f"SELECT * FROM {CONTRATOS} WHERE proveedor_normalizado IN (SELECT proveedor_normalizado FROM {CONTRATOS}) LIMIT 5",
            "SELECT FROM WHERE",
        ):
            with self.subTest(sql=query[:90]):
                self.assertEqual(add_suffix_variants(query), (query, []))


if __name__ == "__main__":
    unittest.main()
