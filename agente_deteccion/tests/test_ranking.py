"""D9 · ranking por nivel de señal (HU-08)."""
import unittest

from agente_deteccion.agente import ejecutar
from agente_deteccion.ranking import rankear, rankear_casos, rankear_proveedores


def s(sid, nivel, conf="alta", estado="evaluada", cod="X"):
    return {"senal_id": sid, "codigo": cod, "estado": estado, "nivel": nivel if estado == "evaluada" else None, "confianza": conf}


def orden(r):
    return [(f["clave"], f["posicion"]) for f in r["lista"]]


class Ranking(unittest.TestCase):
    def test_primero_los_altos_luego_medios_luego_bajos(self):
        r = rankear([{"clave": "A", "senales": [s("1", "medio"), s("2", "medio"), s("3", "medio")]},
                     {"clave": "B", "senales": [s("4", "alto")]},
                     {"clave": "C", "senales": [s("5", "bajo"), s("6", "bajo")]}])
        self.assertEqual(orden(r), [("B", 1), ("A", 2), ("C", 3)])       # un alto le gana a tres medios

    def test_empate_por_confianza_alta(self):
        r = rankear([{"clave": "A", "senales": [s("1", "alto", "baja")]}, {"clave": "B", "senales": [s("2", "alto", "alta")]}])
        self.assertEqual(orden(r), [("B", 1), ("A", 2)])

    def test_empates_comparten_posicion(self):
        r = rankear([{"clave": "B", "senales": [s("1", "alto")]}, {"clave": "A", "senales": [s("2", "alto")]},
                     {"clave": "C", "senales": [s("3", "medio")]}])
        self.assertEqual(orden(r), [("A", 1), ("B", 1), ("C", 3)])
        self.assertTrue(r["lista"][0]["empate"] and not r["lista"][2]["empate"])

    def test_no_evaluables_no_suman_pero_se_cuentan(self):
        r = rankear([{"clave": "A", "senales": [s("1", None, estado="no_evaluable"), s("2", "bajo")]}])
        f = r["lista"][0]
        self.assertEqual((f["conteo"], f["senales_no_evaluables"]), ({"alto": 0, "medio": 0, "bajo": 1}, 1))

    def test_las_descartadas_por_el_auditor_no_cuentan(self):
        unidades = [{"clave": "A", "senales": [s("1", "alto"), s("2", "bajo")]}, {"clave": "B", "senales": [s("3", "medio")]}]
        self.assertEqual(orden(rankear(unidades))[0][0], "A")
        r = rankear(unidades, {"1": "descartada"})
        self.assertEqual(orden(r)[0][0], "B")
        self.assertEqual(next(f for f in r["lista"] if f["clave"] == "A")["senales_descartadas"], 1)

    def test_sin_senales_al_final_y_sin_posicion(self):
        r = rankear([{"clave": "Z", "senales": []}, {"clave": "A", "senales": [s("1", "bajo")]}])
        self.assertEqual(orden(r), [("A", 1), ("Z", None)])
        self.assertEqual(r["con_senales"], 1)

    def test_el_criterio_va_en_la_salida_y_es_provisional(self):
        r = rankear([])
        self.assertIn("alto", r["criterio"])
        self.assertEqual(r["estado_criterio"], "provisional")

    def test_el_orden_no_depende_del_orden_de_entrada(self):
        a = [{"clave": "A", "senales": [s("1", "medio")]}, {"clave": "B", "senales": [s("2", "medio")]}]
        self.assertEqual(orden(rankear(a)), orden(rankear(a[::-1])))

    def test_casos(self):
        r = rankear_casos([{"caso_id": "c1", "titulo": "Uno", "senales": [s("1", "bajo")]},
                           {"caso_id": "c2", "titulo": "Dos", "senales": [s("2", "alto")]}])
        self.assertEqual([f["nombre"] for f in r["lista"]], ["Dos", "Uno"])

    def test_proveedores_de_un_resultado_de_deteccion(self):
        base = {"moneda": "MXN", "dependencia": "D", "tipo_procedimiento": "Adjudicación directa", "fuente": "F"}
        filas = ([{**base, "id": f"A{i}", "proveedor": "Alfa SA", "rfc": "ALF010101AA1", "monto": 100, "fecha": f"2026-01-0{i}"} for i in range(1, 4)]
                 + [{**base, "id": "B1", "proveedor": "Beta SA", "rfc": "BET010101BB2", "monto": 100, "fecha": "2026-02-01"}])
        res = ejecutar(filas)
        r = res["ranking_proveedores"]
        self.assertEqual(r["lista"][0]["clave"], "ALF010101AA1")
        self.assertEqual(r["lista"][0]["conteo"]["medio"], 1)
        self.assertEqual(rankear_proveedores(res)["lista"][0]["nombre"], "Alfa SA")


if __name__ == "__main__":
    unittest.main()
