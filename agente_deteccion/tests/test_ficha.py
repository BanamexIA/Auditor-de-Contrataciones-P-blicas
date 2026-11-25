import unittest

from agente_deteccion.esquema import validar_resultado
from agente_deteccion.ficha import ficha_empresa

F = "ComprasMX 2026"
H = "CompraNet histórico"


def fila(i, prov, rfc, monto, proc="Adjudicación directa", fecha="2026-03-02", dep="Dependencia A", fuente=F):
    return {"id": i, "proveedor": prov, "rfc": rfc, "monto": monto, "dependencia": dep,
            "tipo_procedimiento": proc, "fecha": fecha, "fuente": fuente}


ALFA = "Servicios Alfa SA de CV"
RFC_ALFA = "SAL010101AAA"
EMPRESA = [
    fila("A1", ALFA, RFC_ALFA, 1500000, fecha="2026-03-02"),
    fila("A2", ALFA, RFC_ALFA, 1650000, fecha="2026-03-09"),
    fila("A3", ALFA, None, 1700000, fecha="2026-03-15", fuente=H),        # sin RFC: entra por nombre
]
# base de comparación: licitaciones de otras empresas, con un atípico propio que NO debe salir en la ficha
OTROS = [fila(f"L{i}", f"Otra {i}", f"OTR01010{i}AA1", m, proc="Licitación pública", dep="Dependencia B")
         for i, m in enumerate([1000000, 1100000, 900000, 1050000, 950000, 1200000, 1000000], 1)]
OTRO_ATIPICO = fila("L99", "Otra 99", "OTR010199AA1", 500000000, proc="Licitación pública", dep="Dependencia B")
LISTADO = [{"rfc": RFC_ALFA, "nombre_del_contribuyente": "SERVICIOS ALFA SA DE CV",
            "situacion_del_contribuyente": "Definitivo"}]


def codigos(res, codigo):
    return [s for s in res["senales"] if s["codigo"] == codigo]


class Identificacion(unittest.TestCase):
    def test_rfc_y_nombre_filtran_la_empresa_y_el_json_cumple_el_contrato(self):
        res = ficha_empresa(EMPRESA + OTROS, rfc=RFC_ALFA, nombre=ALFA, moneda_por_defecto="MXN")
        self.assertEqual(validar_resultado(res), [])
        self.assertEqual(sorted(c["id"] for c in res["contratos"]), ["A1", "A2", "A3"])
        ident = res["empresa"]["identificacion"]
        self.assertEqual((ident["contratos_por_rfc"], ident["contratos_por_nombre"], ident["ids_por_nombre"]),
                         (2, 1, ["A3"]))
        self.assertTrue(any("sin RFC válido" in a for a in res["empresa"]["advertencias"]))

    def test_llave_unica_y_confianza_baja_por_el_contrato_sin_rfc(self):
        res = ficha_empresa(EMPRESA + OTROS, rfc=RFC_ALFA, nombre=ALFA, moneda_por_defecto="MXN")
        (s,) = codigos(res, "ADJ_DIRECTA_RECURRENTE")                 # un solo grupo, no dos
        self.assertEqual(s["valores_calculados"]["num_adjudicaciones_directas"], 3)
        self.assertEqual(s["confianza"], "media")                     # un contrato entró solo por nombre

    def test_solo_rfc_infiere_el_nombre_y_lo_avisa(self):
        res = ficha_empresa(EMPRESA + OTROS, rfc=RFC_ALFA, moneda_por_defecto="MXN")
        self.assertEqual(len(res["contratos"]), 3)
        self.assertTrue(any("infirieron" in a for a in res["empresa"]["advertencias"]))

    def test_homonimo_con_otro_rfc_no_se_mezcla(self):
        homonimo = fila("H1", ALFA, "OTR010101BBB", 700000)
        res = ficha_empresa(EMPRESA + [homonimo], rfc=RFC_ALFA, nombre=ALFA, moneda_por_defecto="MXN")
        self.assertNotIn("H1", [c["id"] for c in res["contratos"]])
        aviso = " ".join(res["empresa"]["advertencias"])
        self.assertIn("NO se incluyeron", aviso)
        self.assertIn("H1", aviso)

    def test_rfc_y_nombre_discordantes(self):
        res = ficha_empresa(EMPRESA, rfc=RFC_ALFA, nombre="Constructora Zeta", moneda_por_defecto="MXN")
        self.assertTrue(any("no coinciden" in a for a in res["empresa"]["advertencias"]))

    def test_solo_nombre_con_dos_rfc_avisa(self):
        filas = [fila("X1", ALFA, RFC_ALFA, 1), fila("X2", ALFA, "OTR010101BBB", 1)]
        res = ficha_empresa(filas, nombre=ALFA, moneda_por_defecto="MXN")
        self.assertEqual(len(res["contratos"]), 2)
        self.assertTrue(any("RFC distintos" in a for a in res["empresa"]["advertencias"]))

    def test_rfc_invalido_sin_nombre_es_error(self):
        with self.assertRaises(ValueError):
            ficha_empresa(EMPRESA, rfc="123", moneda_por_defecto="MXN")


class Senales(unittest.TestCase):
    def test_69b_por_rfc(self):
        res = ficha_empresa(EMPRESA, rfc=RFC_ALFA, nombre=ALFA, listado_69b=LISTADO, moneda_por_defecto="MXN")
        s = [x for x in codigos(res, "PROVEEDOR_LISTA_69B") if x["estado"] == "evaluada" and x["confianza"] == "alta"]
        self.assertEqual(len(s), 1)
        self.assertEqual(s[0]["nivel"], "alto")

    def test_69b_solo_por_nombre_es_de_baja_confianza(self):
        filas = [fila("B1", "Comercial Beta", None, 100000)]
        listado = [{"rfc": "BET010101AAA", "nombre_del_contribuyente": "COMERCIAL BETA",
                    "situacion_del_contribuyente": "Presunto"}]
        res = ficha_empresa(filas, nombre="Comercial Beta", listado_69b=listado, moneda_por_defecto="MXN")
        (s,) = [x for x in codigos(res, "PROVEEDOR_LISTA_69B") if x["estado"] == "evaluada"]
        self.assertEqual((s["confianza"], s["nivel"]), ("baja", "bajo"))

    def test_monto_atipico_solo_de_la_empresa_contra_comparables(self):
        atipico = fila("A4", ALFA, RFC_ALFA, 90000000, proc="Licitación pública", fecha="2026-04-01")
        res = ficha_empresa(EMPRESA + [atipico] + OTROS + [OTRO_ATIPICO], rfc=RFC_ALFA, nombre=ALFA,
                            moneda_por_defecto="MXN")
        ms = codigos(res, "MONTO_ATIPICO")
        self.assertEqual([m["contratos_ids"] for m in ms], [["A4"]])  # el atípico de otra empresa no aparece
        self.assertEqual(ms[0]["senal_id"], "MONTO_ATIPICO-001")
        self.assertGreaterEqual(ms[0]["valores_calculados"]["tamano_grupo"], 8)
        self.assertEqual(validar_resultado(res), [])

    def test_datos_faltantes_se_excluyen_sin_estimar(self):
        filas = EMPRESA + [fila("A5", ALFA, RFC_ALFA, None, fecha="2026-05-01")]
        res = ficha_empresa(filas, rfc=RFC_ALFA, nombre=ALFA, moneda_por_defecto="MXN")
        self.assertIn(("A5", "sin monto"), [(e["contrato_id"], e["motivo"]) for e in res["excluidos"]])
        self.assertEqual(res["empresa"]["resumen"]["contratos_sin_monto_en_pesos"], 1)


class Periodo(unittest.TestCase):
    def test_periodo_sin_datos_en_las_fuentes_se_declara(self):
        res = ficha_empresa(EMPRESA + OTROS, rfc=RFC_ALFA, nombre=ALFA, desde="2025-01-01", hasta="2025-12-31",
                            moneda_por_defecto="MXN")
        e = res["empresa"]
        self.assertTrue(e["sin_datos"])
        self.assertIn("2025", e["motivo_sin_datos"])
        self.assertIn("no hay datos de ese periodo", e["motivo_sin_datos"])
        self.assertEqual((res["contratos"], res["senales"]), ([], []))
        self.assertEqual(validar_resultado(res), [])

    def test_empresa_sin_contratos_se_distingue_de_periodo_sin_datos(self):
        res = ficha_empresa(OTROS, rfc=RFC_ALFA, nombre=ALFA, moneda_por_defecto="MXN")
        self.assertTrue(res["empresa"]["sin_datos"])
        self.assertIn("No se encontraron contratos de esta empresa", res["empresa"]["motivo_sin_datos"])

    def test_periodo_con_datos_filtra_y_cuenta_fuera(self):
        res = ficha_empresa(EMPRESA, rfc=RFC_ALFA, nombre=ALFA, desde="2026-03-05", hasta="2026-03-31",
                            moneda_por_defecto="MXN")
        self.assertEqual(sorted(c["id"] for c in res["contratos"]), ["A2", "A3"])
        self.assertEqual(res["empresa"]["resumen"]["contratos_fuera_del_periodo"], 1)


if __name__ == "__main__":
    unittest.main()
