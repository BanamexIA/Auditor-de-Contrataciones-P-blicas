"""Corre los casos de referencia de eval/casos_deteccion.yaml (escenarios 3, 4, 5 y 6) como parte de la suite."""
import unittest

from eval.run_deteccion import cargar_casos, ejecutar_casos


class CasosDeReferencia(unittest.TestCase):
    def test_todos_los_casos_coinciden_con_lo_esperado(self):
        for r in ejecutar_casos(cargar_casos()):
            with self.subTest(caso=r["id"], titulo=r["titulo"]):
                fallas = [f"{c['que']}: esperado {c['esperado']!r}, obtenido {c['obtenido']!r}" for c in r["checks"] if not c["ok"]]
                self.assertIsNone(r["error"])
                self.assertEqual(fallas, [])

    def test_cubren_los_cuatro_escenarios(self):
        self.assertEqual({c["escenario"] for c in cargar_casos()}, {3, 4, 5, 6})


if __name__ == "__main__":
    unittest.main()
