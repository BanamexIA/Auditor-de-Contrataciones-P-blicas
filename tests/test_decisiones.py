import unittest

from backend.app import create_app
from backend.casos import estados as e
from backend.casos.decisiones import DecisionInvalida, validar_decision
from backend.casos.estados import TransicionInvalida, transitar
from tests.fakes_casos import RepositorioEnMemoria

SENALES = [
    {"tipo": "adjudicacion_directa_recurrente",
     "datos": {"criterio": "Proporción de AD", "valor": 0.64, "umbral": 0.30}},
    {"tipo": "proveedor_69b", "datos": {"situacion": "Presunto", "fecha": "2025-03-01"}},
]


class ValidarDecisionTest(unittest.TestCase):
    def test_decisiones_validas(self):
        self.assertEqual(validar_decision("relevante", None), ("relevante", None))
        self.assertEqual(validar_decision("pendiente", "  revisar  "), ("pendiente", "revisar"))
        self.assertEqual(validar_decision("descartada", "Patente"), ("descartada", "Patente"))

    def test_decision_desconocida(self):
        for valor in ("fraude", None, "", 1):
            with self.assertRaisesRegex(DecisionInvalida, "desconocida"):
                validar_decision(valor, None)

    def test_descartar_requiere_comentario(self):
        for comentario in (None, "", "   "):
            with self.assertRaisesRegex(DecisionInvalida, "comentario"):
                validar_decision("descartada", comentario)

    def test_comentario_debe_ser_texto(self):
        with self.assertRaises(DecisionInvalida):
            validar_decision("relevante", 5)


class CierreConSenalesTest(unittest.TestCase):
    def test_no_cierra_con_senales_sin_decision(self):
        with self.assertRaisesRegex(TransicionInvalida, "faltan decisiones en 2"):
            transitar(e.EN_REVISION, None, e.CERRADO, senales_sin_decision=2)

    def test_cierra_sin_faltantes(self):
        self.assertEqual(transitar(e.EN_REVISION, None, e.CERRADO).estado, e.CERRADO)


class ApiDecisionesTest(unittest.TestCase):
    def setUp(self):
        self.repo = RepositorioEnMemoria()
        self.client = create_app(repositorio=self.repo).test_client()
        self.caso_id = self.client.post("/casos", json={"solicitud": "X"}).get_json()["id"]
        self.senales = self.repo.registrar_senales(self.caso_id, SENALES)

    def decidir(self, senal_id, decision, comentario=None, caso_id=None):
        cuerpo = {"decision": decision}
        if comentario is not None:
            cuerpo["comentario"] = comentario
        return self.client.post(
            f"/casos/{caso_id or self.caso_id}/senales/{senal_id}/decision", json=cuerpo)

    def llevar_a_revision(self):
        for estado in ("consultado", "detectado", "normado", "reportado", "en_revision"):
            r = self.client.post(f"/casos/{self.caso_id}/transiciones", json={"estado": estado})
            self.assertEqual(r.status_code, 200)

    def cerrar(self):
        return self.client.post(f"/casos/{self.caso_id}/transiciones",
                                json={"estado": "cerrado"})

    def test_listar_senales_sin_decision(self):
        r = self.client.get(f"/casos/{self.caso_id}/senales")
        self.assertEqual(r.status_code, 200)
        senales = r.get_json()["senales"]
        self.assertEqual([s["tipo"] for s in senales],
                         ["adjudicacion_directa_recurrente", "proveedor_69b"])
        self.assertTrue(all(s["decision"] is None for s in senales))
        self.assertEqual(senales[0]["datos"]["umbral"], 0.30)

    def test_decidir_y_ver_decision_vigente(self):
        sid = self.senales[0]["id"]
        r = self.decidir(sid, "relevante", "Revisar contratos de marzo")
        self.assertEqual(r.status_code, 201)
        self.assertEqual(r.get_json()["decision"], "relevante")
        senal = self.client.get(f"/casos/{self.caso_id}/senales").get_json()["senales"][0]
        self.assertEqual(senal["decision"]["decision"], "relevante")
        self.assertEqual(senal["decision"]["comentario"], "Revisar contratos de marzo")
        self.assertTrue(senal["decision"]["created_at"].endswith("Z"))

    def test_cambiar_decision_guarda_historial(self):
        sid = self.senales[0]["id"]
        self.decidir(sid, "pendiente")
        self.decidir(sid, "descartada", "Proveedor único por patente")
        vigente = self.client.get(f"/casos/{self.caso_id}/senales").get_json()["senales"][0]
        self.assertEqual(vigente["decision"]["decision"], "descartada")
        self.assertEqual(len([d for d in self.repo.decisiones if d["senal_id"] == sid]), 2)
        eventos = [ev["detalle"] for ev in self.repo.eventos(self.caso_id, "decision")]
        self.assertEqual([(ev["decision"], ev["anterior"]) for ev in eventos],
                         [("pendiente", None), ("descartada", "pendiente")])

    def test_errores(self):
        sid = self.senales[0]["id"]
        casos = [
            (self.decidir(sid, "fraude"), 400, "solicitud_invalida"),
            (self.decidir(sid, "descartada"), 400, "solicitud_invalida"),
            (self.decidir(sid, "descartada", "  "), 400, "solicitud_invalida"),
            (self.decidir("no-existe", "relevante"), 404, "senal_no_encontrada"),
            (self.decidir(sid, "relevante", caso_id="no-existe"), 404, "caso_no_encontrado"),
        ]
        for r, http, codigo in casos:
            self.assertEqual(r.status_code, http)
            self.assertEqual(r.get_json()["error"]["codigo"], codigo)
        r = self.client.post(f"/casos/{self.caso_id}/senales/{sid}/decision",
                             data="x", content_type="application/json")
        self.assertEqual(r.status_code, 400)
        self.assertEqual(self.repo.decisiones, [])

    def test_senal_de_otro_caso(self):
        otro = self.client.post("/casos", json={"solicitud": "Y"}).get_json()["id"]
        r = self.decidir(self.senales[0]["id"], "relevante", caso_id=otro)
        self.assertEqual(r.status_code, 404)
        self.assertEqual(r.get_json()["error"]["codigo"], "senal_no_encontrada")

    def test_no_cierra_hasta_decidir_todas(self):
        self.llevar_a_revision()
        self.decidir(self.senales[0]["id"], "relevante")
        r = self.cerrar()
        self.assertEqual(r.status_code, 409)
        self.assertIn("faltan decisiones en 1", r.get_json()["error"]["mensaje"])

        self.decidir(self.senales[1]["id"], "pendiente")
        self.assertEqual(self.cerrar().status_code, 200)

    def test_caso_cerrado_no_acepta_decisiones(self):
        for s in self.senales:
            self.decidir(s["id"], "pendiente")
        self.llevar_a_revision()
        self.assertEqual(self.cerrar().status_code, 200)
        r = self.decidir(self.senales[0]["id"], "relevante")
        self.assertEqual(r.status_code, 409)
        self.assertEqual(r.get_json()["error"]["codigo"], "caso_cerrado")

    def test_caso_sin_senales_se_cierra(self):
        caso_id = self.client.post("/casos", json={"solicitud": "Z"}).get_json()["id"]
        for estado in ("consultado", "detectado", "normado", "reportado", "en_revision",
                       "cerrado"):
            r = self.client.post(f"/casos/{caso_id}/transiciones", json={"estado": estado})
            self.assertEqual(r.status_code, 200)

    def test_senales_de_caso_inexistente(self):
        r = self.client.get("/casos/no-existe/senales")
        self.assertEqual(r.status_code, 404)


if __name__ == "__main__":
    unittest.main()
