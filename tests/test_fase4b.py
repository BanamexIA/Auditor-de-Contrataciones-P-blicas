import sys
import unittest
from datetime import date
from argparse import ArgumentTypeError
from pathlib import Path


ETL_DIR = Path(__file__).resolve().parents[1] / "etl"
sys.path.insert(0, str(ETL_DIR))

from build_staging import clean_date, fecha_inicio_estado
from run_etl import load_seed, parse_date


class FechaInicioEstadoTests(unittest.TestCase):
    def test_blank_or_sin_dato_is_nula(self):
        self.assertEqual(fecha_inicio_estado("", None), "nula")
        self.assertEqual(fecha_inicio_estado("Sin dato", None), "nula")

    def test_unparseable_date_is_retained_as_no_parseable(self):
        self.assertEqual(fecha_inicio_estado("fecha inválida", None), "no_parseable")

    def test_parsed_date_is_valid_for_range_evaluation(self):
        parsed = clean_date("2026-01-15")
        self.assertEqual(fecha_inicio_estado("2026-01-15", parsed), "valida")


class Fase4bConfigurationTests(unittest.TestCase):
    def test_seed_rules_are_pending_and_unique(self):
        rows = load_seed()
        self.assertEqual(len(rows), 13)
        self.assertTrue(all(row[4] == "pendiente" for row in rows))
        self.assertEqual(len({(row[0], row[1]) for row in rows}), len(rows))

    def test_download_date_requires_iso_format(self):
        self.assertEqual(parse_date("2026-10-27"), date(2026, 10, 27))
        with self.assertRaises(ArgumentTypeError):
            parse_date("27/10/2026")


if __name__ == "__main__":
    unittest.main()
