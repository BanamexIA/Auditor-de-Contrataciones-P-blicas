import unittest
from datetime import date

from agente_deteccion.agente import ejecutar
from agente_deteccion.detectores import Parametros
from agente_deteccion.esquema import validar_resultado
from agente_deteccion.normalizacion import normalizar_monto, normalizar_procedimiento, normalizar_rfc

F = "ComprasMX 2026"
BASE = [
    {"id": "CMX-2026-0001", "proveedor": "Servicios Alfa SA de CV", "rfc": "SAL010101AAA", "monto": 1500000.00,
     "dependencia": "Dependencia Demo A", "tipo_procedimiento": "Adjudicación directa", "fecha": "2026-03-02", "fuente": F},
    {"id": "CMX-2026-0002", "proveedor": "Servicios Alfa SA de CV", "rfc": "SAL010101AAA", "monto": 1650000.00,
     "dependencia": "Dependencia Demo A", "tipo_procedimiento": "Adjudicación directa", "fecha": "2026-03-09", "fuente": F},
    {"id": "CMX-2026-0003", "proveedor": "Servicios Alfa SA de CV", "rfc": "SAL010101AAA", "monto": 1700000.00,
     "dependencia": "Dependencia Demo A", "tipo_procedimiento": "Adjudicación directa", "fecha": "2026-03-15", "fuente": F},
    {"id": "CMX-2026-0004", "proveedor": "Comercial Beta", "rfc": None, "monto": 320000.00,
     "dependencia": "Dependencia Demo B", "tipo_procedimiento": "Invitación a cuando menos tres personas",
     "fecha": "2026-04-01", "fuente": F},
]
DOC = {"id": "CMX-2026-0002", "proveedor": "Servicios Alfa SA de CV", "rfc": "SAL010101AAA", "monto": 1560000.00,
       "dependencia": "Dependencia Demo A", "tipo_procedimiento": "Adjudicación directa", "fecha": "2026-03-09",
       "fuente": "documento del contrato"}
LISTADO = [{"rfc": "SAL010101AAA", "nombre_del_contribuyente": "SERVICIOS ALFA SA DE CV",
            "situacion_del_contribuyente": "Definitivo", "fecha_publicacion": "2025-06-30"}]


def por_codigo(res, codigo):
    return [s for s in res["senales"] if s["codigo"] == codigo]


class Normalizacion(unittest.TestCase):
    def test_rfc(self):
        self.assertEqual(normalizar_rfc("sal010101aaa"), ("SAL010101AAA", True, None))
        self.assertEqual(normalizar_rfc(None)[2], "faltante")
        self.assertEqual(normalizar_rfc("XAXX010101000")[2], "generico")
        self.assertEqual(normalizar_rfc("SAL991399AAA")[2], "fecha_en_rfc")      # mes 13
        self.assertEqual(normalizar_rfc("ABC")[2], "formato")

    def test_monto_y_procedimiento(self):
        self.assertEqual(normalizar_monto("$1,500,000.50"), 1500000.50)
        self.assertIsNone(normalizar_monto("Sin dato"))
        self.assertEqual(normalizar_procedimiento("Adjudicación directa"), "adjudicacion_directa")
        self.assertEqual(normalizar_procedimiento("INVITACION A CUANDO MENOS 3 PERSONAS"), "invitacion_tres_personas")
        self.assertEqual(normalizar_procedimiento("Sin dato"), "sin_dato")


class Deteccion(unittest.TestCase):
    def test_adjudicaciones_recurrentes(self):
        res = ejecutar(BASE, listado_69b=LISTADO, moneda_por_defecto="MXN")
        (s,) = por_codigo(res, "ADJ_DIRECTA_RECURRENTE")
        self.assertEqual(s["valores_calculados"]["num_adjudicaciones_directas"], 3)
        self.assertEqual(s["valores_calculados"]["ventana_dias"], 13)
        self.assertEqual(s["valores_calculados"]["monto_total"], 4850000.00)
        self.assertEqual(s["confianza"], "alta")
        self.assertEqual(s["contratos_ids"], ["CMX-2026-0001", "CMX-2026-0002", "CMX-2026-0003"])

    def test_fuera_de_ventana_no_hay_senal(self):
        filas = [dict(f, fecha=d) for f, d in zip(BASE[:3], ["2026-01-01", "2026-03-01", "2026-05-01"])]
        self.assertEqual(por_codigo(ejecutar(filas, moneda_por_defecto="MXN"), "ADJ_DIRECTA_RECURRENTE"), [])

    def test_contradiccion_baja_confianza_y_se_reporta(self):
        res = ejecutar(BASE + [DOC], moneda_por_defecto="MXN", prioridad_fuentes=(F,))
        self.assertEqual(len(res["contradicciones"]), 1)
        c = res["contradicciones"][0]
        self.assertEqual((c["contrato_id"], c["campo"], c["valor_a"], c["valor_b"]), ("CMX-2026-0002", "monto", "1650000.00", "1560000.00"))
        (s,) = por_codigo(res, "ADJ_DIRECTA_RECURRENTE")
        self.assertTrue(s["afectada_por_contradiccion"])
        self.assertEqual(s["confianza"], "media")
        self.assertEqual(len(res["contratos"]), 4)

    def test_monto_atipico_no_evaluable_con_pocos_comparables(self):
        (s,) = por_codigo(ejecutar(BASE, moneda_por_defecto="MXN"), "MONTO_ATIPICO")
        self.assertEqual(s["estado"], "no_evaluable")
        self.assertIn("grupo_comparable_suficiente", s["campos_faltantes"])

    def test_monto_atipico_marca_solo_el_atipico(self):
        filas = [{"id": f"L{i}", "proveedor": f"P{i}", "rfc": None, "monto": 100000 + i * 1000, "dependencia": "D",
                  "tipo_procedimiento": "Licitación pública", "fecha": "2026-02-01", "fuente": F} for i in range(9)]
        filas.append(dict(filas[0], id="L-OUT", monto=5000000))
        senales = por_codigo(ejecutar(filas, moneda_por_defecto="MXN"), "MONTO_ATIPICO")
        self.assertEqual([s["contratos_ids"] for s in senales], [["L-OUT"]])
        v = senales[0]["valores_calculados"]
        self.assertEqual(v["tamano_grupo"], 10)
        self.assertGreater(v["monto"], v["umbral_superior"])

    def test_69b_por_rfc_y_no_evaluable_sin_rfc(self):
        res = ejecutar(BASE, listado_69b=LISTADO, moneda_por_defecto="MXN")
        senales = por_codigo(res, "PROVEEDOR_LISTA_69B")
        exacta = [s for s in senales if s["estado"] == "evaluada"][0]
        self.assertEqual((exacta["nivel"], exacta["confianza"]), ("alto", "alta"))
        self.assertEqual(exacta["valores_calculados"]["situacion_vigente"], "Definitivo")
        ne = [s for s in senales if s["estado"] == "no_evaluable"][0]
        self.assertEqual((ne["contratos_ids"], ne["campos_faltantes"]), (["CMX-2026-0004"], ["rfc"]))

    def test_escenario5_excluye_sin_monto_sin_estimar(self):
        filas = BASE + [dict(BASE[3], id="X-1", monto=None)]
        res = ejecutar(filas, moneda_por_defecto="MXN")
        self.assertIn(("X-1", "sin monto"), {(e["contrato_id"], e["motivo"]) for e in res["excluidos"]})
        self.assertEqual(res["calidad"]["sin_monto"], 1)

    def test_concentracion(self):
        res = ejecutar(BASE, moneda_por_defecto="MXN")
        alfa = res["concentracion"][0]
        self.assertEqual((alfa["num_contratos"], alfa["monto_total"], alfa["porcentaje_monto"],
                          alfa["porcentaje_adjudicaciones_directas"]), (3, 4850000.0, 93.8, 100.0))


class DatosReales(unittest.TestCase):
    def test_fecha_fuera_de_rango_del_etl_no_se_usa(self):
        filas = [dict(f, fecha_inicio_valida=(i != 0), fecha_inicio_estado="anterior_al_rango") for i, f in enumerate(BASE[:3])]
        res = ejecutar(filas, moneda_por_defecto="MXN")
        self.assertEqual(por_codigo(res, "ADJ_DIRECTA_RECURRENTE"), [])          # quedan 2 con fecha válida
        self.assertIn("fecha fuera del rango válido del ETL (anterior_al_rango)",
                      {e["motivo"] for e in res["excluidos"]})

    def test_montos_asimetricos_en_escala_logaritmica(self):
        # montos que crecen ~25%: en escala lineal los grandes parecen atípicos; en logaritmo, no
        filas = [{"id": f"L{i}", "proveedor": f"P{i}", "rfc": None, "monto": round(50000 * 1.25 ** i, 2),
                  "dependencia": "D", "tipo_procedimiento": "Licitación pública", "fecha": "2026-02-01", "fuente": F}
                 for i in range(20)]
        logaritmico = por_codigo(ejecutar(filas, moneda_por_defecto="MXN"), "MONTO_ATIPICO")
        lineal = por_codigo(ejecutar(filas, parametros=Parametros(monto_escala_log=False), moneda_por_defecto="MXN"), "MONTO_ATIPICO")
        self.assertEqual(logaritmico, [])
        self.assertGreater(len(lineal), 0)

    def test_diagnostico_de_fechas_repetidas(self):
        res = ejecutar(BASE[:3] * 1 + [dict(BASE[3], fecha="2026-03-02")], moneda_por_defecto="MXN")
        self.assertEqual(res["calidad"]["fechas_mas_frecuentes"][0]["fecha"], "2026-03-02")


class Contrato(unittest.TestCase):
    def test_el_json_cumple_el_contrato(self):
        res = ejecutar(BASE + [DOC], listado_69b=LISTADO, moneda_por_defecto="MXN", prioridad_fuentes=(F,))
        self.assertEqual(validar_resultado(res), [])

    def test_detecta_salidas_incompletas(self):
        res = ejecutar(BASE, moneda_por_defecto="MXN")
        res["senales"][0]["contratos_ids"].append("NO-EXISTE")
        del res["aviso"]
        problemas = validar_resultado(res)
        self.assertTrue(any("NO-EXISTE" in p for p in problemas))
        self.assertTrue(any("aviso" in p for p in problemas))


class Normativo(unittest.TestCase):
    def test_normas_para_senales_evaluadas_y_declara_ausencias(self):
        llamadas = []

        def recuperador(consulta, fecha, top_k):
            llamadas.append((consulta, fecha))
            return [{"id": 7, "ley": "LAASSP", "version": "Nueva Ley DOF 16-04-2025", "fecha_entrada_vigor": date(2025, 4, 17),
                     "fecha_abrogacion": None, "contenido": "[fragmento de prueba]", "articulo": "Artículo X",
                     "distancia": 0.3, "fuente": "ruta"}]
        res = ejecutar(BASE, listado_69b=LISTADO, recuperador=recuperador, moneda_por_defecto="MXN")
        self.assertEqual(validar_resultado(res), [])
        ligadas = {n["senal_codigo"] for n in res["normas_recuperadas"]}
        self.assertEqual(ligadas, {"ADJ_DIRECTA_RECURRENTE", "PROVEEDOR_LISTA_69B"})
        self.assertEqual(llamadas[0][1], date(2026, 3, 2))                     # fecha del contrato más antiguo de la señal
        self.assertTrue(all(n["texto"] == "[fragmento de prueba]" for n in res["normas_recuperadas"]))

    def test_monto_atipico_declara_que_no_hay_norma(self):
        filas = [{"id": f"L{i}", "proveedor": f"P{i}", "rfc": None, "monto": 100000 + i * 1000, "dependencia": "D",
                  "tipo_procedimiento": "Licitación pública", "fecha": "2026-02-01", "fuente": F} for i in range(9)]
        filas.append(dict(filas[0], id="L-OUT", monto=5000000))
        res = ejecutar(filas, recuperador=lambda *a: self.fail("no debe buscar norma para un monto atípico"),
                       moneda_por_defecto="MXN")
        self.assertEqual([s["senal_id"] for s in res["sin_norma_aplicable"]], ["MONTO_ATIPICO-001"])
        self.assertEqual(res["normas_recuperadas"], [])

    def test_sin_fragmentos_vigentes_se_declara(self):
        res = ejecutar(BASE, recuperador=lambda *a: [], moneda_por_defecto="MXN")
        self.assertEqual(res["normas_recuperadas"], [])
        self.assertTrue(any("ADJ_DIRECTA_RECURRENTE" in s["senal_id"] for s in res["sin_norma_aplicable"]))

    def test_umbral_de_distancia(self):
        rec = lambda *a: [{"id": 1, "ley": "L", "version": "v", "fecha_entrada_vigor": None, "fecha_abrogacion": None,
                           "contenido": "t", "articulo": "a", "distancia": 0.9, "fuente": None}]
        res = ejecutar(BASE, recuperador=rec, moneda_por_defecto="MXN", umbral_distancia=0.5)
        self.assertEqual(res["normas_recuperadas"], [])


if __name__ == "__main__":
    unittest.main()