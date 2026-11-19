import csv
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

from backend.app import create_app
from backend.casos.bitacora import llamar_llm
from llm.base import LLMResponse
from telemetry.tracking import contexto_llamada, track_llm_call
from tests.fakes_casos import RepositorioEnMemoria


class ClienteRemoto:
    """Como OllamaClient apuntando a una laptop por Tailscale."""

    provider = "ollama"
    model = "qwen2.5:7b"

    def __init__(self, base_url="http://laptop-mich:11434", falla=False):
        self.base_url = base_url
        self.falla = falla

    @track_llm_call
    def generate(self, system, prompt, temperature=0.0):
        if self.falla:
            raise TimeoutError("sin respuesta")
        return LLMResponse(text="ok", input_tokens=100, output_tokens=20, latency_ms=800.0,
                           ollama_version="0.12.3")


@patch("telemetry.tracking.record_llm_call")
class ContextoTest(unittest.TestCase):
    def test_llamar_llm_liga_caso_agente_y_laptop(self, record):
        eventos = []
        llamar_llm(lambda *a, **k: eventos.append(a), "caso-1", "consultas",
                   ClienteRemoto(), "s", "p")
        fila = record.call_args.args[0]
        self.assertEqual(fila["caso_id"], "caso-1")
        self.assertEqual(fila["agent"], "consultas")
        self.assertEqual(fila["equipment"], "laptop-mich")
        self.assertEqual(len(eventos), 1)  # y la bitácora sigue igual

    def test_error_tambien_queda_ligado(self, record):
        with self.assertRaises(TimeoutError):
            llamar_llm(lambda *a, **k: None, "caso-1", "normas",
                       ClienteRemoto(falla=True), "s", "p")
        fila = record.call_args.args[0]
        self.assertEqual((fila["caso_id"], fila["status"], fila["error_type"]),
                         ("caso-1", "error", "TimeoutError"))

    def test_fuera_de_un_caso_no_hay_caso_id(self, record):
        ClienteRemoto().generate("s", "p")
        self.assertIsNone(record.call_args.args[0]["caso_id"])
        with contexto_llamada("caso-2", "reportes"):
            pass
        ClienteRemoto().generate("s", "p")
        self.assertIsNone(record.call_args.args[0]["caso_id"])  # el contexto no se filtra

    def test_ollama_local_conserva_la_descripcion_del_equipo(self, record):
        ClienteRemoto(base_url="http://localhost:11434").generate("s", "p")
        self.assertIn("|", record.call_args.args[0]["equipment"])


class TelemetriaNoTumbaElCasoTest(unittest.TestCase):
    def test_falla_al_registrar_no_rompe_la_llamada(self):
        with patch("telemetry.tracking.record_llm_call", side_effect=OSError("BD caída")):
            with self.assertLogs("telemetry.tracking", "WARNING"):
                respuesta = ClienteRemoto().generate("s", "p")
        self.assertEqual(respuesta.text, "ok")

    def test_csv_ignora_caso_id(self):
        with tempfile.TemporaryDirectory() as tmp:
            ruta = Path(tmp) / "calls.csv"
            with patch.dict("os.environ", {"TELEMETRY_SINK": "csv",
                                           "TELEMETRY_CSV_PATH": str(ruta)}):
                with contexto_llamada("caso-1", "consultas"):
                    ClienteRemoto().generate("s", "p")
            with ruta.open(encoding="utf-8-sig", newline="") as f:
                filas = list(csv.DictReader(f))
        self.assertEqual(filas[0]["agent"], "consultas")
        self.assertNotIn("caso_id", filas[0])


class ApiTelemetriaTest(unittest.TestCase):
    def setUp(self):
        self.repo = RepositorioEnMemoria()
        self.client = create_app(repositorio=self.repo).test_client()
        self.caso_id = self.client.post("/casos", json={"solicitud": "X"}).get_json()["id"]
        t = datetime(2026, 11, 20, 18, 0, tzinfo=timezone.utc)

        def llamada(agente, ent, sal, lat, estado="ok", caso=self.caso_id):
            return {"caso_id": caso, "started_at": t, "agente": agente, "modelo": "qwen2.5:7b",
                    "equipo": "laptop-mich", "tokens_entrada": ent, "tokens_salida": sal,
                    "latencia_ms": lat, "tokens_por_segundo": None, "estado": estado,
                    "tipo_error": None if estado == "ok" else "TimeoutError"}

        self.repo.llamadas_llm = [
            llamada("consultas", 100, 20, 800.0),
            llamada("consultas", None, None, 3000.0, "error"),
            llamada("reportes", 500, 300, 4200.5),
            llamada("consultas", 1, 1, 1.0, caso="otro-caso"),
        ]

    def test_totales_y_por_agente(self):
        r = self.client.get(f"/casos/{self.caso_id}/telemetria")
        self.assertEqual(r.status_code, 200)
        d = r.get_json()
        self.assertEqual(d["totales"], {"llamadas": 3, "errores": 1, "tokens_entrada": 600,
                                        "tokens_salida": 320, "latencia_ms": 8000.5})
        self.assertEqual([a["agente"] for a in d["por_agente"]], ["consultas", "reportes"])
        self.assertEqual(d["por_agente"][0]["errores"], 1)
        self.assertEqual(len(d["llamadas"]), 3)
        self.assertTrue(d["llamadas"][0]["started_at"].endswith("Z"))

    def test_caso_sin_llamadas_y_caso_inexistente(self):
        otro = self.client.post("/casos", json={"solicitud": "Y"}).get_json()["id"]
        d = self.client.get(f"/casos/{otro}/telemetria").get_json()
        self.assertEqual(d["totales"]["llamadas"], 0)
        r = self.client.get("/casos/no-existe/telemetria")
        self.assertEqual(r.status_code, 404)
        self.assertEqual(r.get_json()["error"]["codigo"], "caso_no_encontrado")


if __name__ == "__main__":
    unittest.main()
