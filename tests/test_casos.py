import unittest
import uuid
from datetime import datetime, timezone

from backend.app import create_app
from backend.casos import estados as e
from backend.casos.estados import TransicionInvalida, transitar
from backend.casos.repositorio import CasoNoEncontrado


class RepositorioEnMemoria:
    def __init__(self):
        self.casos = {}
        self.bitacora = []

    def crear(self, solicitud, creado_por=None):
        ahora = datetime.now(timezone.utc)
        caso = {"id": str(uuid.uuid4()), "solicitud": solicitud, "estado": e.RECIBIDO,
                "estado_previo": None, "motivo_bloqueo": None, "creado_por": creado_por,
                "created_at": ahora, "updated_at": ahora}
        self.casos[caso["id"]] = caso
        self.bitacora.append((caso["id"], {"de": None, "a": e.RECIBIDO}))
        return dict(caso)

    def obtener(self, caso_id):
        if caso_id not in self.casos:
            raise CasoNoEncontrado(caso_id)
        return dict(self.casos[caso_id])

    def listar(self, estado, limite):
        casos = [c for c in self.casos.values() if estado is None or c["estado"] == estado]
        return [dict(c) for c in reversed(casos)][:limite]

    def transitar(self, caso_id, destino, motivo):
        caso = self.casos.get(caso_id)
        if caso is None:
            raise CasoNoEncontrado(caso_id)
        nuevo = transitar(caso["estado"], caso["estado_previo"], destino, motivo)
        self.bitacora.append((caso_id, {"de": caso["estado"], "a": nuevo.estado}))
        caso.update(estado=nuevo.estado, estado_previo=nuevo.estado_previo,
                    motivo_bloqueo=nuevo.motivo_bloqueo)
        return dict(caso)


class MaquinaDeEstadosTest(unittest.TestCase):
    def test_flujo_completo_avanza_en_orden(self):
        estado = e.RECIBIDO
        for destino in e.FLUJO[1:]:
            estado = transitar(estado, None, destino).estado
        self.assertEqual(estado, e.CERRADO)

    def test_no_se_saltan_estados(self):
        with self.assertRaisesRegex(TransicionInvalida, "siguiente estado es 'consultado'"):
            transitar(e.RECIBIDO, None, e.NORMADO)

    def test_no_se_retrocede(self):
        with self.assertRaises(TransicionInvalida):
            transitar(e.DETECTADO, None, e.CONSULTADO)

    def test_bloqueo_requiere_motivo(self):
        for motivo in (None, "", "   "):
            with self.assertRaisesRegex(TransicionInvalida, "motivo"):
                transitar(e.CONSULTADO, None, e.BLOQUEADO, motivo)

    def test_bloqueo_guarda_estado_previo_y_motivo(self):
        r = transitar(e.CONSULTADO, None, e.BLOQUEADO, "  Ollama apagado ")
        self.assertEqual(r, e.Resultado(e.BLOQUEADO, e.CONSULTADO, "Ollama apagado"))

    def test_bloqueo_desde_todos_los_no_terminales(self):
        for estado in e.FLUJO[:-1]:
            self.assertEqual(transitar(estado, None, e.BLOQUEADO, "x").estado, e.BLOQUEADO)

    def test_desbloqueo_solo_al_estado_previo(self):
        r = transitar(e.BLOQUEADO, e.CONSULTADO, e.CONSULTADO)
        self.assertEqual(r, e.Resultado(e.CONSULTADO, None, None))
        with self.assertRaises(TransicionInvalida):
            transitar(e.BLOQUEADO, e.CONSULTADO, e.DETECTADO)

    def test_bloqueado_no_se_cierra(self):
        with self.assertRaises(TransicionInvalida):
            transitar(e.BLOQUEADO, e.EN_REVISION, e.CERRADO)

    def test_bloqueado_no_se_vuelve_a_bloquear(self):
        with self.assertRaises(TransicionInvalida):
            transitar(e.BLOQUEADO, e.CONSULTADO, e.BLOQUEADO, "otra vez")

    def test_cerrado_es_terminal(self):
        with self.assertRaises(TransicionInvalida):
            transitar(e.CERRADO, None, e.BLOQUEADO, "x")

    def test_estado_desconocido(self):
        with self.assertRaisesRegex(TransicionInvalida, "desconocido"):
            transitar(e.RECIBIDO, None, "aprobado")


class ApiCasosTest(unittest.TestCase):
    def setUp(self):
        self.repo = RepositorioEnMemoria()
        self.client = create_app(repositorio=self.repo).test_client()

    def crear(self, solicitud="¿Contratos de la empresa X en 2026?"):
        return self.client.post("/casos", json={"solicitud": solicitud})

    def transicion(self, caso_id, estado, motivo=None):
        cuerpo = {"estado": estado} if motivo is None else {"estado": estado, "motivo": motivo}
        return self.client.post(f"/casos/{caso_id}/transiciones", json=cuerpo)

    def test_crear_caso(self):
        r = self.crear()
        self.assertEqual(r.status_code, 201)
        caso = r.get_json()
        self.assertEqual(caso["estado"], "recibido")
        self.assertEqual(r.headers["Location"], f"/casos/{caso['id']}")
        self.assertTrue(caso["created_at"].endswith("Z"))
        self.assertEqual(self.repo.bitacora, [(caso["id"], {"de": None, "a": "recibido"})])

    def test_crear_sin_solicitud(self):
        for cuerpo in ({}, {"solicitud": "  "}, {"solicitud": 5}):
            r = self.client.post("/casos", json=cuerpo)
            self.assertEqual(r.status_code, 400)
            self.assertEqual(r.get_json()["error"]["codigo"], "solicitud_invalida")
        r = self.client.post("/casos", data="no json", content_type="application/json")
        self.assertEqual(r.status_code, 400)

    def test_obtener_y_no_encontrado(self):
        caso_id = self.crear().get_json()["id"]
        self.assertEqual(self.client.get(f"/casos/{caso_id}").get_json()["id"], caso_id)
        r = self.client.get("/casos/no-existe")
        self.assertEqual(r.status_code, 404)
        self.assertEqual(r.get_json()["error"]["codigo"], "caso_no_encontrado")

    def test_listar_con_filtros(self):
        a = self.crear("a").get_json()["id"]
        self.crear("b")
        self.transicion(a, "consultado")
        casos = self.client.get("/casos").get_json()["casos"]
        self.assertEqual([c["solicitud"] for c in casos], ["b", "a"])
        filtrados = self.client.get("/casos?estado=consultado").get_json()["casos"]
        self.assertEqual([c["id"] for c in filtrados], [a])
        self.assertEqual(len(self.client.get("/casos?limite=1").get_json()["casos"]), 1)
        for consulta in ("estado=otro", "limite=0", "limite=101", "limite=abc"):
            self.assertEqual(self.client.get(f"/casos?{consulta}").status_code, 400)

    def test_flujo_con_bloqueo_y_desbloqueo(self):
        caso_id = self.crear().get_json()["id"]
        self.assertEqual(self.transicion(caso_id, "consultado").status_code, 200)

        r = self.transicion(caso_id, "bloqueado", "El agente no respondió en 60 s.")
        caso = r.get_json()
        self.assertEqual((caso["estado"], caso["estado_previo"], caso["motivo_bloqueo"]),
                         ("bloqueado", "consultado", "El agente no respondió en 60 s."))

        r = self.transicion(caso_id, "consultado")
        caso = r.get_json()
        self.assertEqual((caso["estado"], caso["estado_previo"], caso["motivo_bloqueo"]),
                         ("consultado", None, None))
        self.assertEqual(len(self.repo.bitacora), 4)

    def test_transiciones_invalidas_dan_409(self):
        caso_id = self.crear().get_json()["id"]
        for estado, motivo in (("normado", None), ("bloqueado", None), ("bloqueado", " ")):
            r = self.transicion(caso_id, estado, motivo)
            self.assertEqual(r.status_code, 409)
            self.assertEqual(r.get_json()["error"]["codigo"], "transicion_invalida")
        self.assertEqual(self.client.get(f"/casos/{caso_id}").get_json()["estado"], "recibido")

    def test_transicion_con_cuerpo_invalido(self):
        caso_id = self.crear().get_json()["id"]
        self.assertEqual(self.client.post(f"/casos/{caso_id}/transiciones", json={}).status_code, 400)
        self.assertEqual(self.transicion(caso_id, "bloqueado", 3).status_code, 400)
        self.assertEqual(self.transicion("no-existe", "consultado").status_code, 404)

    def test_health_sin_bd(self):
        self.assertEqual(self.client.get("/health").status_code, 200)
        self.assertEqual(self.client.get("/health/db").status_code, 503)


if __name__ == "__main__":
    unittest.main()
