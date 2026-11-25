"""Listas de contratos sin código y cruces con el 69-B que la pregunta no pidió (2026-11-24).

La pregunta «Lista las adjudicaciones directas de ComprasMX 2026 con su artículo de
excepción, proveedor e importe» volvió con un JOIN al 69-B (19 contratos en lugar de
miles) y sin codigo_contrato, así que el orquestador no pudo buscar señales.
"""

import unittest

from agents.consulta.agent import UNASKED_69B
from agents.consulta.concepts import mentions_69b
from agents.consulta.prompt import CONTRACT_CODE_NOTE, parse_response
from agents.consulta.validator import add_contract_code, uses_69b_view, validate_sql
from tests.test_consulta_agent import FakeClient, ask, sql_answer

CONTRATOS = "clean.v_contratos_agente"
COINCIDENCIAS = "clean.v_coincidencias_69b_agente"
PREGUNTA = (
    "Lista las adjudicaciones directas de ComprasMX 2026 con su artículo de excepción, proveedor e importe."
)
SQL_DEL_MODELO = (
    f"SELECT c.titulo_contrato, c.articulo_de_excepcion, c.proveedor, c.importe FROM {CONTRATOS} AS c "
    f"JOIN {COINCIDENCIAS} AS m ON m.codigo_contrato = c.codigo_contrato WHERE c.fuente = 'comprasmx' "
    "AND c.tipo_procedimiento_norm = 'adjudicacion_directa' AND NOT c.articulo_de_excepcion IS NULL LIMIT 200"
)
SQL_CORREGIDO = (
    f"SELECT c.codigo_contrato, c.articulo_de_excepcion, c.proveedor, c.importe FROM {CONTRATOS} AS c "
    "WHERE c.fuente = 'comprasmx' AND c.tipo_procedimiento_norm = 'adjudicacion_directa' LIMIT 200"
)


class CodigoDeContratoTest(unittest.TestCase):
    def test_una_lista_sin_codigo_lo_recibe_con_el_alias_de_la_vista(self):
        sql, agregado = add_contract_code(SQL_DEL_MODELO)
        self.assertTrue(agregado)
        self.assertTrue(sql.startswith("SELECT c.codigo_contrato, c.titulo_contrato"))
        validate_sql(sql)

    def test_sin_alias_usa_la_columna_sola(self):
        sql, agregado = add_contract_code(f"SELECT proveedor, importe FROM {CONTRATOS} LIMIT 10")
        self.assertTrue(agregado)
        self.assertTrue(sql.startswith("SELECT codigo_contrato, proveedor"))
        validate_sql(sql)

    def test_conteos_totales_y_listas_con_codigo_no_cambian(self):
        for sql in (
            f"SELECT articulo_de_excepcion, COUNT(*) AS contratos FROM {CONTRATOS} GROUP BY articulo_de_excepcion LIMIT 20",
            f"SELECT SUM(importe) AS total FROM {CONTRATOS} WHERE moneda = 'MXN' LIMIT 1",
            f"SELECT DISTINCT proveedor FROM {CONTRATOS} LIMIT 20",
            f"SELECT codigo_contrato AS codigo, importe FROM {CONTRATOS} LIMIT 10",
            f"SELECT c.codigo_contrato, c.importe FROM {CONTRATOS} AS c LIMIT 10",
            f"SELECT proveedor, RANK() OVER (ORDER BY importe DESC) AS lugar FROM {CONTRATOS} LIMIT 10",
            f"SELECT t.proveedor FROM (SELECT proveedor FROM {CONTRATOS}) AS t LIMIT 10",
        ):
            with self.subTest(sql=sql):
                self.assertEqual(add_contract_code(sql), (sql, False))

    def test_parse_response_lo_agrega_y_lo_dice_en_los_supuestos(self):
        sql = f"SELECT c.proveedor, c.importe FROM {CONTRATOS} AS c ORDER BY c.importe DESC LIMIT 10"
        r = parse_response(sql_answer(sql))
        self.assertIn("c.codigo_contrato", r["sql"].split("FROM")[0])
        self.assertIn("ORDER BY c.importe DESC, c.codigo_contrato", r["sql"])  # el desempate también llega
        self.assertIn(CONTRACT_CODE_NOTE, r["supuestos"])


class CruceNoPedidoCon69bTest(unittest.TestCase):
    def test_la_pregunta_del_24_nov_no_habla_del_69b(self):
        self.assertFalse(mentions_69b(PREGUNTA))
        self.assertTrue(uses_69b_view(SQL_DEL_MODELO))

    def test_reconoce_las_formas_de_mencionarlo(self):
        for texto in ("contratos en el listado 69-B", "proveedores en el 69b", "empresas EFOS",
                      "coincidencias por RFC exacto", "contratos que requieren revisión humana",
                      "lista del SAT", "empresas factureras"):
            with self.subTest(texto=texto):
                self.assertTrue(mentions_69b(texto))

    def test_reintenta_sin_el_cruce_y_avisa_al_modelo(self):
        cliente = FakeClient(sql_answer(SQL_DEL_MODELO), sql_answer(SQL_CORREGIDO))
        r = ask(cliente, question=PREGUNTA)
        self.assertEqual(r["tipo"], "sql")
        self.assertFalse(uses_69b_view(r["sql"]))
        self.assertEqual(r["intentos"], 2)
        fallido = r["intentos_fallidos"][0]
        self.assertEqual((fallido["etapa"], fallido["error"]), ("validador", UNASKED_69B))
        self.assertIn("v_coincidencias_69b_agente", fallido["sql"])
        self.assertIn("no menciona el listado 69-B", cliente.prompts[1])

    def test_si_insiste_el_caso_termina_en_error(self):
        r = ask(FakeClient(sql_answer(SQL_DEL_MODELO), sql_answer(SQL_DEL_MODELO)), question=PREGUNTA)
        self.assertEqual(r["tipo"], "error")
        self.assertIn("no menciona el listado 69-B", r["motivo"])

    def test_si_la_pregunta_lo_pide_el_cruce_pasa(self):
        r = ask(FakeClient(sql_answer(SQL_DEL_MODELO)), question=PREGUNTA + " Solo las que coinciden con el 69-B.")
        self.assertEqual((r["tipo"], r["intentos"]), ("sql", 1))

    def test_una_aclaracion_que_lo_menciona_tambien_cuenta(self):
        r = ask(FakeClient(sql_answer(SQL_DEL_MODELO)), question=PREGUNTA,
                clarifications=[("¿Qué contratos?", "Los que coinciden con el listado 69-B")])
        self.assertEqual(r["tipo"], "sql")



class TipoContratacionTest(unittest.TestCase):
    """2026-11-25: «adjudicaciones directas de obra pública de ComprasMX 2026» dio 0 filas por el valor."""

    def test_un_valor_que_no_existe_se_rechaza_con_la_pista(self):
        from agents.consulta.validator import SQLValidationError
        for valor in ("OBRA PUBLICA", "obra pública", "Obra publica"):
            with self.subTest(valor=valor), self.assertRaisesRegex(SQLValidationError, "UPPER\(tipo_contratacion\)"):
                validate_sql(f"SELECT codigo_contrato FROM {CONTRATOS} WHERE tipo_contratacion = '{valor}' LIMIT 10")

    def test_los_valores_reales_y_upper_pasan(self):
        for cond in ("tipo_contratacion = 'OBRA PÚBLICA'", "tipo_contratacion = 'Obra Pública'",
                     "UPPER(tipo_contratacion) = 'OBRA PÚBLICA'", "ley = 'LOPSRM'"):
            with self.subTest(cond=cond):
                validate_sql(f"SELECT codigo_contrato FROM {CONTRATOS} WHERE {cond} LIMIT 10")


if __name__ == "__main__":
    unittest.main()
