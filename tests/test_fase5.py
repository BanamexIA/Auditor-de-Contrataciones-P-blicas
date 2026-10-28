import importlib.util
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "verify_fase5", ROOT / "scripts" / "verify_fase5.py"
)
verify_fase5 = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(verify_fase5)


class Fase5DictionaryTests(unittest.TestCase):
    def test_dictionary_has_complete_metadata_for_each_documented_table_column(self):
        tables = verify_fase5.parse_dictionary(ROOT / "docs" / "diccionario_datos.md")
        self.assertEqual(
            set(tables),
            {
                "contratos",
                "proveedores",
                "listado_69b",
                "coincidencias_69b",
                "config_calidad",
                "map_tipo_procedimiento",
                "contratos_excluidos",
            },
        )
        self.assertEqual(sum(map(len, tables.values())), 76)

    def test_schema_comparison_checks_tables_columns_and_types(self):
        documented = {
            "contratos": {"importe": "numeric", "fecha_inicio": "date"},
        }
        actual = {
            "contratos": {"importe": "numeric", "fecha_inicio": "text", "fuente": "text"},
            "proveedores": {"proveedor": "text"},
        }
        self.assertEqual(
            verify_fase5.compare_schema(documented, actual),
            [
                "Tabla clean.proveedores ausente del diccionario",
                "Columna sin documentar: clean.contratos.fuente",
                "Tipo distinto en clean.contratos.fecha_inicio: diccionario=date, BD=text",
            ],
        )


if __name__ == "__main__":
    unittest.main()
