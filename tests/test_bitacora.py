import unittest

from backend.app import create_app
from backend.casos import bitacora as b
from backend.casos.bitacora import EventoInvalido, equipo_de_cliente, llamar_llm, validar_evento
from backend.casos.repositorio import CasoNoEncontrado
from llm.base import LLMResponse
from tests.fakes_casos import RepositorioEnMemoria


class ClienteFalso:
    provider = "ollama"
    model = "qwen2.5:7b"
    base_url = "http://laptop-alean:11434"
    model_quantization = None
    ollama_version = None

    def __init__(self, falla=None):
        self.falla = falla
        self.llamadas = 0

    def generate(self, system, prompt, temperature=0.0):
        self.llamadas += 1
        if self.falla:
            raise self.falla
        return LLMResponse(text="SELECT 1", input_tokens=1840, output_tokens=96,
                           latency_ms=3120.5, model_quantization="Q4_K_M",
                           ollama_version="0.12.3")


def reloj_falso(*valores):
    iterador = iter(valores)
    return lambda: next(iterador)


class ValidarEventoTest(unittest.TestCase):
    def test_tipo_desconocido(self):
        with self.assertRaisesRegex(EventoInvalido, "desconocido"):
            validar_evento("otro", {})

    def test_detalle_debe_ser_objeto(self):
        with self.assertRaises(EventoInvalido):
            validar_evento(b.SQL_GENERADO, ["SELECT 1"])

    def test_campos_obligatorios(self):
        with self.assertRaisesRegex(EventoInvalido, "duracion_ms, filas"):
            validar_evento(b.SQL_EJECUTADO, {"sql": "SELECT 1", "vistas": [], "truncado": False})

    def test_claves_prohibidas_incluso_anidadas(self):
        with self.assertRaisesRegex(EventoInvalido, "prompt"):
            validar_evento(b.SQL_GENERADO, {"sql": "SELECT 1", "prompt": "texto completo"})
        with self.assertRaisesRegex(EventoInvalido, "password"):
            validar_evento(b.ERROR, {"tipo": "x", "mensaje": "y",
                                     "contexto": [{"password": "secreto"}]})

    def test_todos_los_tipos_tienen_campos(self):
        self.assertEqual(len(b.TIPOS_EVENTO), 11)


class LlamarLLMTest(unittest.TestCase):
    def setUp(self):
        self.repo = RepositorioEnMemoria()
        self.caso_id = self.repo.crear("pregunta")["id"]

    def test_llamada_exitosa_registra_tokens_modelo_y_equipo(self):
        respuesta = llamar_llm(self.repo.registrar_evento, self.caso_id, "consulta",
                               ClienteFalso(), "sys", "prompt")
        self.assertEqual(respuesta.text, "SELECT 1")
        [ev] = self.repo.eventos(self.caso_id, b.LLAMADA_LLM)
        self.assertEqual((ev["modelo"], ev["equipo"], ev["etapa"]),
                         ("qwen2.5:7b", "laptop-alean", "recibido"))
        self.assertEqual(ev["detalle"], {
            "agente": "consulta", "cuantizacion": "Q4_K_M", "version_ollama": "0.12.3",
            "tokens_entrada": 1840, "tokens_salida": 96, "latencia_ms": 3120.5,
            "estado": "ok", "tipo_error": None,
        })

    def test_no_guarda_el_prompt(self):
        llamar_llm(self.repo.registrar_evento, self.caso_id, "consulta",
                   ClienteFalso(), "sistema secreto", "pregunta con datos")
        [ev] = self.repo.eventos(self.caso_id, b.LLAMADA_LLM)
        self.assertNotIn("pregunta con datos", str(ev))
        self.assertNotIn("sistema secreto", str(ev))

    def test_error_registra_y_relanza(self):
        cliente = ClienteFalso(falla=TimeoutError("sin respuesta"))
        with self.assertRaises(TimeoutError):
            llamar_llm(self.repo.registrar_evento, self.caso_id, "consulta", cliente,
                       "sys", "prompt", reloj=reloj_falso(10.0, 70.0))
        [ev] = self.repo.eventos(self.caso_id, b.LLAMADA_LLM)
        self.assertEqual(ev["detalle"]["estado"], "error")
        self.assertEqual(ev["detalle"]["tipo_error"], "TimeoutError")
        self.assertEqual(ev["detalle"]["latencia_ms"], 60000.0)
        self.assertIsNone(ev["detalle"]["tokens_entrada"])

    def test_un_evento_por_intento(self):
        cliente = ClienteFalso(falla=ConnectionError())
        for _ in range(2):
            with self.assertRaises(ConnectionError):
                llamar_llm(self.repo.registrar_evento, self.caso_id, "consulta",
                           cliente, "s", "p")
        cliente.falla = None
        llamar_llm(self.repo.registrar_evento, self.caso_id, "consulta", cliente, "s", "p")
        estados = [ev["detalle"]["estado"]
                   for ev in self.repo.eventos(self.caso_id, b.LLAMADA_LLM)]
        self.assertEqual(estados, ["error", "error", "ok"])

    def test_caso_inexistente(self):
        with self.assertRaises(CasoNoEncontrado):
            llamar_llm(self.repo.registrar_evento, "no-existe", "consulta",
                       ClienteFalso(), "s", "p")

    def test_equipo_de_cliente(self):
        self.assertEqual(equipo_de_cliente(ClienteFalso()), "laptop-alean")
        self.assertIsNone(equipo_de_cliente(object()))


class CasoCompletoTest(unittest.TestCase):
    """Simula un caso de principio a fin y revisa su rastro por la API."""

    def test_rastro_de_un_caso_completo(self):
        repo = RepositorioEnMemoria()
        client = create_app(repositorio=repo).test_client()
        caso_id = client.post("/casos", json={"solicitud": "Contratos de X en 2026"}).get_json()["id"]
        registrar = repo.registrar_evento
        avanzar = lambda estado: client.post(f"/casos/{caso_id}/transiciones",
                                             json={"estado": estado})

        sql = "SELECT * FROM clean.contratos WHERE anio = 2026 LIMIT 500"
        llamar_llm(registrar, caso_id, "consulta", ClienteFalso(), "s", "p")
        registrar(caso_id, b.SQL_GENERADO, {"sql": sql})
        registrar(caso_id, b.SQL_EJECUTADO, {"sql": sql, "vistas": ["clean.contratos"],
                                             "filas": 14, "duracion_ms": 212.0,
                                             "truncado": False})
        avanzar("consultado")
        registrar(caso_id, b.REGLAS_EVALUADAS, {
            "reglas": [{"id": "AD-01", "version": "1", "resultado": "señal",
                        "valor": 0.64, "umbral": 0.30}],
            "senales": ["s1"]})
        avanzar("detectado")
        llamar_llm(registrar, caso_id, "normativo", ClienteFalso(), "s", "p")
        registrar(caso_id, b.NORMAS_RECUPERADAS, {
            "normas": [{"senal": "s1", "documento": "LAASSP", "articulo": "41",
                        "version": "2025", "fecha_vigencia": "2025-04-17", "score": 0.82}],
            "sin_soporte": []})
        avanzar("normado")
        llamar_llm(registrar, caso_id, "reportes", ClienteFalso(), "s", "p")
        registrar(caso_id, b.REPORTE_GUARDADO, {"ruta": f"reportes/{caso_id}/1.pdf",
                                                "sha256": "a" * 64, "version": "1"})
        avanzar("reportado")
        avanzar("en_revision")
        registrar(caso_id, b.DECISION, {"senal_id": "s1", "decision": "relevante",
                                        "comentario": None})
        avanzar("cerrado")

        r = client.get(f"/casos/{caso_id}/bitacora")
        self.assertEqual(r.status_code, 200)
        eventos = r.get_json()["eventos"]
        self.assertEqual([ev["evento"] for ev in eventos], [
            "solicitud", "transicion",
            "llamada_llm", "sql_generado", "sql_ejecutado", "transicion",
            "reglas_evaluadas", "transicion",
            "llamada_llm", "normas_recuperadas", "transicion",
            "llamada_llm", "reporte_guardado", "transicion",
            "transicion", "decision", "transicion",
        ])
        self.assertEqual(eventos[4]["etapa"], "recibido")
        self.assertEqual(eventos[-2]["etapa"], "en_revision")
        self.assertTrue(all(ev["created_at"].endswith("Z") for ev in eventos))
        [ids] = [{ev["id"] for ev in eventos}]
        self.assertEqual(len(ids), len(eventos))

    def test_bitacora_de_caso_inexistente(self):
        client = create_app(repositorio=RepositorioEnMemoria()).test_client()
        r = client.get("/casos/no-existe/bitacora")
        self.assertEqual(r.status_code, 404)
        self.assertEqual(r.get_json()["error"]["codigo"], "caso_no_encontrado")


if __name__ == "__main__":
    unittest.main()
