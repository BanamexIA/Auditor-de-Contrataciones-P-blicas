import io
import os
import unittest
from contextlib import redirect_stderr, redirect_stdout
from unittest.mock import patch

from backend.agentes import __main__ as cli
from backend.agentes.repositorio import AgenteDuplicado
from backend.agentes.servicio import (
    AgenteNoDisponible,
    MonitorAgentes,
    seleccionar_agente,
    verificar_todos,
)
from backend.agentes.verificacion import (
    APAGADO,
    DISPONIBLE,
    SIN_MODELO,
    NombreInvalido,
    url_de,
    validar_nombre,
    verificar,
)
from backend.app import create_app
from tests.fakes_agentes import OllamaSimulado, RepositorioAgentesEnMemoria
from tests.fakes_casos import RepositorioEnMemoria

MODELO = "qwen2.5:7b"


class NombreTest(unittest.TestCase):
    def test_nombres_validos(self):
        self.assertEqual(validar_nombre("Laptop-Alean "), "laptop-alean")
        self.assertEqual(url_de("laptop-mich"), "http://laptop-mich:11434")

    def test_rechaza_urls_y_direcciones(self):
        for nombre in ("http://laptop", "laptop:11434", "169.254.169.254", "evil.com",
                       "laptop/x", "-laptop", "laptop-", "", "a" * 64, "localhost:80"):
            with self.assertRaises(NombreInvalido, msg=nombre):
                validar_nombre(nombre)


class VerificarTest(unittest.TestCase):
    def test_disponible(self):
        r = verificar("laptop-a", MODELO, http=OllamaSimulado({"laptop-a": [MODELO, "nomic-embed-text:latest"]}))
        self.assertEqual(r.estado, DISPONIBLE)
        self.assertEqual(r.version_ollama, "0.12.3")
        self.assertIsNone(r.error)

    def test_sin_modelo(self):
        r = verificar("laptop-a", MODELO, http=OllamaSimulado({"laptop-a": ["llama3.2:3b"]}))
        self.assertEqual(r.estado, SIN_MODELO)
        self.assertEqual(r.modelos, ["llama3.2:3b"])

    def test_apagado_no_lanza(self):
        r = verificar("laptop-a", MODELO, http=OllamaSimulado({}))
        self.assertEqual((r.estado, r.error), (APAGADO, "TimeoutError"))

    def test_modelo_sin_etiqueta_acepta_latest(self):
        http = OllamaSimulado({"laptop-a": ["nomic-embed-text:latest"]})
        self.assertEqual(verificar("laptop-a", "nomic-embed-text", http=http).estado, DISPONIBLE)

    def test_solo_llama_al_host_registrado(self):
        http = OllamaSimulado({"laptop-a": [MODELO]})
        verificar("laptop-a", MODELO, http=http)
        self.assertEqual(http.urls, ["http://laptop-a:11434/api/version",
                                     "http://laptop-a:11434/api/tags"])


class SeleccionTest(unittest.TestCase):
    def setUp(self):
        self.repo = RepositorioAgentesEnMemoria()
        self.repo.alta("alean", "laptop-alean")
        self.repo.alta("mich", "laptop-mich")

    def test_prefiere_el_del_usuario(self):
        http = OllamaSimulado({"laptop-alean": [MODELO], "laptop-mich": [MODELO]})
        agente = seleccionar_agente(self.repo, "mich", http=http)
        self.assertEqual(agente["nombre_tailnet"], "laptop-mich")
        self.assertEqual(agente["url"], "http://laptop-mich:11434")
        self.assertEqual(agente["modelo"], MODELO)

    def test_si_el_del_usuario_esta_apagado_usa_otro(self):
        http = OllamaSimulado({"laptop-alean": [MODELO]})
        agente = seleccionar_agente(self.repo, "mich", http=http)
        self.assertEqual(agente["nombre_tailnet"], "laptop-alean")
        self.assertEqual(self.repo.obtener(2)["estado"], APAGADO)

    def test_sin_usuario_usa_cualquiera(self):
        http = OllamaSimulado({"laptop-mich": [MODELO]})
        self.assertEqual(seleccionar_agente(self.repo, None, http=http)["nombre_tailnet"],
                         "laptop-mich")

    def test_ninguno_disponible_da_motivo_para_bloquear(self):
        http = OllamaSimulado({"laptop-alean": ["llama3.2:3b"]})
        with self.assertRaises(AgenteNoDisponible) as ctx:
            seleccionar_agente(self.repo, "mich", http=http)
        mensaje = str(ctx.exception)
        self.assertIn("laptop-mich (apagado)", mensaje)
        self.assertIn("laptop-alean (sin_modelo: falta qwen2.5:7b)", mensaje)
        self.assertIn("enciende laptop-mich", mensaje)
        self.assertIn("en laptop-alean ejecuta 'ollama pull qwen2.5:7b'", mensaje)
        self.assertIn("desbloquea el caso", mensaje)

    def test_sin_agentes_registrados(self):
        with self.assertRaisesRegex(AgenteNoDisponible, "No hay agentes"):
            seleccionar_agente(RepositorioAgentesEnMemoria(), "x", http=OllamaSimulado())

    def test_dados_de_baja_no_se_usan(self):
        self.repo.baja("laptop-alean")
        http = OllamaSimulado({"laptop-alean": [MODELO]})
        with self.assertRaises(AgenteNoDisponible):
            seleccionar_agente(self.repo, "alean", http=http)

    def test_modelo_preferido_del_agente(self):
        self.repo.baja("laptop-mich")
        self.repo.alta("mich", "laptop-mich", modelo="llama3.2:3b")
        http = OllamaSimulado({"laptop-mich": ["llama3.2:3b"]})
        agente = seleccionar_agente(self.repo, "mich", http=http)
        self.assertEqual(agente["modelo"], "llama3.2:3b")

    def test_verificar_todos_y_monitor(self):
        http = OllamaSimulado({"laptop-alean": [MODELO]})
        estados = {a["nombre_tailnet"]: a["estado"] for a in verificar_todos(self.repo, http)}
        self.assertEqual(estados, {"laptop-alean": DISPONIBLE, "laptop-mich": APAGADO})

        repo = RepositorioAgentesEnMemoria()
        repo.alta("ana", "laptop-ana")
        monitor = MonitorAgentes(repo, 0.01, http=OllamaSimulado({"laptop-ana": [MODELO]})).iniciar()
        try:
            for _ in range(200):
                if repo.obtener(1)["estado"] == DISPONIBLE:
                    break
                monitor._detener.wait(0.01)
        finally:
            monitor.detener()
        self.assertEqual(repo.obtener(1)["estado"], DISPONIBLE)


class AltaTest(unittest.TestCase):
    def test_duplicado_y_reactivacion(self):
        repo = RepositorioAgentesEnMemoria()
        repo.alta("alean", "laptop-alean")
        with self.assertRaises(AgenteDuplicado):
            repo.alta("alean", "laptop-alean")
        repo.baja("laptop-alean")
        self.assertEqual(repo.listar(), [])
        self.assertEqual(repo.alta("alean", "laptop-alean")["id"], 1)


class CliTest(unittest.TestCase):
    def correr(self, repo, *args):
        salida, errores = io.StringIO(), io.StringIO()
        with redirect_stdout(salida), redirect_stderr(errores):
            codigo = cli.main(list(args), repo=repo, http=OllamaSimulado({"laptop-ana": [MODELO]}))
        return codigo, salida.getvalue(), errores.getvalue()

    def test_alta_listar_verificar_baja(self):
        repo = RepositorioAgentesEnMemoria()
        codigo, salida, _ = self.correr(repo, "alta", "--usuario", "ana", "--nombre", "laptop-ana")
        self.assertEqual(codigo, 0)
        self.assertIn("disponible", salida)
        self.assertIn("laptop-ana", self.correr(repo, "listar")[1])
        self.assertIn("disponible", self.correr(repo, "verificar", "--nombre", "laptop-ana")[1])
        self.assertEqual(self.correr(repo, "baja", "--nombre", "laptop-ana")[0], 0)
        self.assertEqual(self.correr(repo, "listar")[1], "")
        self.assertIn("baja", self.correr(repo, "listar", "--todos")[1])

    def test_rechaza_urls_y_direcciones(self):
        for nombre in ("http://laptop", "laptop:11434", "169.254.169.254", "evil.com",
                       "laptop/x", "-laptop", "laptop-", "", "a" * 64, "localhost:80"):
            with self.assertRaises(NombreInvalido, msg=nombre):
                validar_nombre(nombre)

    def test_rechaza_url(self):
        codigo, _, errores = self.correr(RepositorioAgentesEnMemoria(), "alta", "--usuario", "x",
                                         "--nombre", "http://169.254.169.254")
        self.assertEqual(codigo, 2)
        self.assertIn("inválido", errores)

    def test_verificar_agente_inexistente(self):
        codigo, _, errores = self.correr(RepositorioAgentesEnMemoria(), "verificar", "--nombre", "nadie")
        self.assertEqual(codigo, 2)


class ApiAgentesTest(unittest.TestCase):
    def setUp(self):
        self.repo = RepositorioAgentesEnMemoria()
        self.repo.alta("alean", "laptop-alean")
        self.http = OllamaSimulado({"laptop-alean": [MODELO]})
        self.client = create_app(repositorio=RepositorioEnMemoria(), repositorio_agentes=self.repo,
                                 http_agentes=self.http).test_client()

    def test_listar_y_ver(self):
        agentes = self.client.get("/agentes").get_json()["agentes"]
        self.assertEqual([a["nombre_tailnet"] for a in agentes], ["laptop-alean"])
        self.assertEqual(agentes[0]["estado"], "desconocido")
        self.assertEqual(self.client.get("/agentes/1").get_json()["usuario"], "alean")

    def test_verificar_ahora(self):
        r = self.client.post("/agentes/1/verificar")
        self.assertEqual(r.status_code, 200)
        datos = r.get_json()
        self.assertEqual(datos["estado"], "disponible")
        self.assertTrue(datos["ultima_verificacion"].endswith("Z"))
        self.assertEqual(self.http.urls[0], "http://laptop-alean:11434/api/version")

    def test_no_hay_alta_por_api(self):
        self.assertEqual(self.client.post("/agentes", json={"nombre": "x"}).status_code, 405)

    def test_no_encontrado(self):
        for r in (self.client.get("/agentes/99"), self.client.post("/agentes/99/verificar")):
            self.assertEqual(r.status_code, 404)
            self.assertEqual(r.get_json()["error"]["codigo"], "agente_no_encontrado")

    def test_sin_registro_configurado(self):
        client = create_app(repositorio=RepositorioEnMemoria()).test_client()
        self.assertEqual(client.get("/agentes").status_code, 503)

    def test_monitor_desactivado_por_defecto(self):
        with patch.dict(os.environ, {"AGENTES_VERIFICAR_CADA_S": "0"}):
            app = create_app(repositorio=RepositorioEnMemoria(), repositorio_agentes=self.repo)
        self.assertNotIn("monitor_agentes", app.extensions)


if __name__ == "__main__":
    unittest.main()
