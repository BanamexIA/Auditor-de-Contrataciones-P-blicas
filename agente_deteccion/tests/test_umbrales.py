"""D1 · los umbrales salen de config.umbrales con su estado y el JSON los declara."""
import unittest

from agente_deteccion.agente import ejecutar
from agente_deteccion.detectores import Parametros
from agente_deteccion.esquema import validar_resultado

FILAS = [
    {"clave": "adj_umbral_n", "valor": 4, "unidad": "adjudicaciones_directas", "motivo": "m1", "estado": "confirmado"},
    {"clave": "monto_columnas_grupo", "valor": ["tipo_proc_norm"], "unidad": None, "motivo": "m2", "estado": "provisional"},
]
CONTRATO = {"moneda": "MXN", "dependencia": "D", "tipo_procedimiento": "Adjudicación directa", "proveedor": "Alfa SA", "rfc": "ALF010101AA1",
            "fuente": "ComprasMX 2026"}


class Umbrales(unittest.TestCase):
    def test_los_valores_de_la_tabla_mandan_sobre_el_respaldo(self):
        p = Parametros.desde_filas(FILAS)
        self.assertEqual(p.adj_umbral_n, 4)
        self.assertEqual(p.monto_columnas_grupo, ("tipo_proc_norm",))
        self.assertEqual(p.adj_ventana_dias, 30)          # no venía en la tabla: respaldo

    def test_una_clave_desconocida_es_error(self):
        with self.assertRaises(ValueError):
            Parametros.desde_filas([{"clave": "umbral_inventado", "valor": 1}])

    def test_lo_que_no_vino_de_la_tabla_es_provisional(self):
        det = Parametros.desde_filas(FILAS).detalle()
        self.assertEqual(det["adj_umbral_n"]["estado"], "confirmado")
        self.assertEqual(det["monto_columnas_grupo"]["estado"], "provisional")
        self.assertEqual(det["adj_ventana_dias"]["estado"], "provisional")

    def test_estado_global_solo_es_confirmado_si_todos_lo_son(self):
        todas = [{"clave": k, "valor": v, "estado": "confirmado"} for k, v in Parametros().a_dict().items()]
        self.assertEqual(Parametros.desde_filas(todas).resumen_umbrales()["estado"], "confirmado")
        self.assertEqual(Parametros.desde_filas(FILAS).resumen_umbrales()["estado"], "provisional")

    def test_a_dict_no_incluye_la_procedencia(self):
        p = Parametros.desde_filas(FILAS)
        self.assertNotIn("origen", p.a_dict())
        self.assertNotIn("meta", p.a_dict())

    def test_el_json_declara_provisional_y_su_origen(self):
        res = ejecutar([{**CONTRATO, "id": "C1", "monto": 1, "fecha": "2026-01-01"}])
        u = res["umbrales"]
        self.assertEqual((u["estado"], u["origen"]), ("provisional", "codigo"))
        self.assertIn("respaldo", u["nota"])
        self.assertEqual(validar_resultado(res), [])

    def test_el_json_con_umbrales_de_la_tabla(self):
        res = ejecutar([{**CONTRATO, "id": "C1", "monto": 1, "fecha": "2026-01-01"}], parametros=Parametros.desde_filas(FILAS))
        u = res["umbrales"]
        self.assertEqual(u["origen"], "config.umbrales")
        self.assertEqual(u["parametros"]["adj_umbral_n"]["valor"], 4)
        self.assertNotIn("adj_umbral_n", u["provisionales"])
        self.assertIn("monto_columnas_grupo", u["provisionales"])

    def test_cambiar_el_umbral_cambia_el_resultado(self):
        filas = [{**CONTRATO, "id": f"C{i}", "monto": 100, "fecha": f"2026-01-0{i}"} for i in range(1, 4)]
        con_respaldo = [s for s in ejecutar(filas)["senales"] if s["codigo"] == "ADJ_DIRECTA_RECURRENTE"]
        con_tabla = [s for s in ejecutar(filas, parametros=Parametros.desde_filas(FILAS))["senales"] if s["codigo"] == "ADJ_DIRECTA_RECURRENTE"]
        self.assertEqual((len(con_respaldo), len(con_tabla)), (1, 0))      # 3 > 2 sí marca; 3 > 4 no

    def test_factor_de_nivel_alto_configurable(self):
        filas = [{**CONTRATO, "id": f"C{i}", "monto": 100, "fecha": f"2026-01-0{i}"} for i in range(1, 5)]
        nivel = lambda p: [s for s in ejecutar(filas, parametros=p)["senales"] if s["codigo"] == "ADJ_DIRECTA_RECURRENTE"][0]["nivel"]
        self.assertEqual(nivel(Parametros()), "alto")                         # 4 >= 2 x 2
        self.assertEqual(nivel(Parametros(adj_factor_nivel_alto=3)), "medio")  # 4 < 3 x 2


if __name__ == "__main__":
    unittest.main()
