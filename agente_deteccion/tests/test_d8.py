"""D8 · inconsistencias entre fuentes como señal y grupo de comparación por ley + tipo de procedimiento + año."""
import unittest

from agente_deteccion.agente import ejecutar
from agente_deteccion.detectores import Parametros
from agente_deteccion.esquema import validar_resultado

BASE = {"moneda": "MXN", "dependencia": "Dep 1", "tipo_procedimiento": "Licitación pública", "rfc": None}


def fila(i, monto, fecha="2026-03-02", fuente="ComprasMX 2026", **extra):
    return {**BASE, "id": i, "proveedor": f"Proveedor {i}", "monto": monto, "fecha": fecha, "fuente": fuente, **extra}


def senales(res, codigo):
    return [s for s in res["senales"] if s["codigo"] == codigo]


class Inconsistencias(unittest.TestCase):
    def test_una_senal_por_contrato_con_ambos_valores(self):
        filas = [fila("C1", 100, rfc="ABC010101AB1"), fila("C1", 120, fuente="Doc", rfc="ABC010101AB1")]
        res = ejecutar(filas, prioridad_fuentes=("ComprasMX 2026", "Doc"))
        (s,) = senales(res, "INCONSISTENCIA_FUENTES")
        self.assertEqual(s["contratos_ids"], ["C1"])
        self.assertTrue(s["requiere_revision_humana"] and s["afectada_por_contradiccion"])
        d = s["valores_calculados"]["diferencias"][0]
        self.assertEqual((d["valor_a"], d["valor_b"]), ("100.00", "120.00"))
        self.assertEqual(validar_resultado(res), [])

    def test_sin_contradiccion_no_hay_senal(self):
        res = ejecutar([fila("C1", 100), fila("C1", 100, fuente="Doc")])
        self.assertEqual(senales(res, "INCONSISTENCIA_FUENTES"), [])

    def test_no_se_pide_norma_para_la_inconsistencia(self):
        res = ejecutar([fila("C1", 100), fila("C1", 120, fuente="Doc")], recuperador=lambda *a, **k: [])
        (s,) = senales(res, "INCONSISTENCIA_FUENTES")
        self.assertIn(s["senal_id"], [x["senal_id"] for x in res["sin_norma_aplicable"]])


class GrupoComparable(unittest.TestCase):
    def _montos(self, ley=None):
        extra = {"ley": ley} if ley else {}
        return [fila(f"A{i}", m, **extra) for i, m in enumerate([900e3, 950e3, 1e6, 1.05e6, 1.1e6, 6e6])]

    def test_el_grupo_por_defecto_es_ley_tipo_y_anio(self):
        self.assertEqual(Parametros().monto_columnas_grupo, ("ley", "tipo_proc_norm", "anio"))

    def test_contratos_de_otra_ley_o_anio_no_se_mezclan(self):
        otra_ley = [fila(f"B{i}", m, ley="LOPSRM") for i, m in enumerate([5.5e6, 5.8e6, 6e6, 6e6, 6.2e6, 6.5e6])]
        otro_anio = [fila(f"Y{i}", m, fecha="2025-03-02", ley="LAASSP") for i, m in enumerate([5.5e6, 5.8e6, 6e6, 6e6, 6.2e6, 6.5e6])]
        res = ejecutar(self._montos("LAASSP") + otra_ley + otro_anio)
        ms = senales(res, "MONTO_ATIPICO")
        self.assertEqual([s["contratos_ids"] for s in ms], [["A5"]])
        self.assertEqual(ms[0]["valores_calculados"]["grupo"], {"ley": "LAASSP", "tipo_proc_norm": "licitacion_publica", "anio": 2026})

    def test_ley_faltante_se_declara_no_se_adivina(self):
        res = ejecutar(self._montos())
        (s,) = senales(res, "MONTO_ATIPICO")
        self.assertEqual(s["valores_calculados"]["grupo"]["ley"], "sin_dato")
        self.assertEqual(s["valores_calculados"]["dimensiones_sin_dato"], ["ley"])

    def test_los_parametros_siguen_pudiendose_cambiar(self):
        res = ejecutar(self._montos("LAASSP"), parametros=Parametros(monto_columnas_grupo=("tipo_proc_norm",)))
        self.assertEqual(senales(res, "MONTO_ATIPICO")[0]["valores_calculados"]["grupo"], {"tipo_proc_norm": "licitacion_publica"})


if __name__ == "__main__":
    unittest.main()
