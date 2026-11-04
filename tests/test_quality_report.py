import tempfile
import unittest
from pathlib import Path

from etl.quality_report import analyze_69b, render_quality_report


class QualityReportTests(unittest.TestCase):
    def test_69b_analysis_skips_informational_preamble(self):
        contents = (
            "Información actualizada al 31 de agosto de 2026,,,,\n"
            "No,RFC,Nombre del Contribuyente,Situación del contribuyente\n"
            "1,ABC123456XYZ,Ejemplo Uno,Definitivo\n"
            "2,ABC123456XYZ,Ejemplo Dos,Presunto\n"
        )
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "Listado_completo_69-B.csv"
            path.write_text(contents, encoding="utf-8")
            report = analyze_69b(path)

        self.assertEqual(report["rows"], 2)
        self.assertEqual(
            report["columns"],
            ["no", "rfc", "nombre_del_contribuyente", "situacion_del_contribuyente"],
        )
        self.assertEqual(report["metrics"]["duplicate_rfc"], 1)
        self.assertEqual(
            report["metrics"]["situacion_del_contribuyente"],
            {"Definitivo": 1, "Presunto": 1},
        )

    def test_report_does_not_repeat_pre_fase_4b_cleaning_recommendations(self):
        listado = {
            "rows": 1,
            "columns": ["rfc"],
            "metrics": {
                "file_size_bytes": 1,
                "nulls_by_column": {},
                "cardinality_by_column": {},
                "invalid_rfc": 0,
                "duplicate_rfc": 0,
                "situacion_del_contribuyente": {},
            },
        }

        report = render_quality_report([], listado)

        self.assertIn("Fase 4B conserva en `clean`", report)
        self.assertNotIn("Registrar `staging.rechazados` para filas con fechas", report)


if __name__ == "__main__":
    unittest.main()
