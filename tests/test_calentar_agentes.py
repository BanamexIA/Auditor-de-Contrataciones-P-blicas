"""Calentar las laptops antes de una demo (backend/agentes/calentar.py, 2026-11-26)."""

import io
import unittest
from contextlib import redirect_stdout
from unittest.mock import patch

from backend.agentes.calentar import calentar, resumen


class CalentarTest(unittest.TestCase):
    def setUp(self):
        self.pedidos = []
        self.ps = {"models": [
            {"name": "qwen2.5:7b", "size": 5_500_000_000, "size_vram": 5_500_000_000},
            {"name": "nomic-embed-text:latest", "size": 600_000_000, "size_vram": 300_000_000}]}

    def post(self, url, cuerpo, timeout):
        self.pedidos.append((url, cuerpo))
        return {}

    def test_carga_los_dos_modelos_con_keep_alive_y_mide_la_gpu(self):
        with patch.dict("os.environ", {"OLLAMA_KEEP_ALIVE": "2h"}, clear=False):
            r = calentar("http://msi:11434/", "qwen2.5:7b", "nomic-embed-text", post=self.post,
                         get=lambda url, t: self.ps)
        self.assertEqual([u for u, _ in self.pedidos], ["http://msi:11434/api/generate", "http://msi:11434/api/embed"])
        self.assertTrue(all(c["keep_alive"] == "2h" for _, c in self.pedidos))
        self.assertNotIn("prompt", self.pedidos[0][1])  # sin prompt: solo carga el modelo
        self.assertEqual(r["modelos"]["qwen2.5:7b"], {"memoria_gb": 5.5, "gpu_pct": 100})
        self.assertEqual(r["modelos"]["nomic-embed-text:latest"]["gpu_pct"], 50)

    def test_el_resumen_avisa_si_algo_corre_en_cpu(self):
        r = calentar("http://msi:11434", "qwen2.5:7b", post=self.post, get=lambda url, t: self.ps)
        self.assertIn("corre en CPU", resumen("msi", r))
        self.ps["models"][1]["size_vram"] = 600_000_000
        r = calentar("http://msi:11434", "qwen2.5:7b", post=self.post, get=lambda url, t: self.ps)
        self.assertNotIn("CPU", resumen("msi", r))


class CliCalentarTest(unittest.TestCase):
    def test_omite_las_laptops_no_disponibles(self):
        from backend.agentes.__main__ import main
        agentes = [{"nombre_tailnet": "msi", "estado": "disponible", "modelo": None},
                   {"nombre_tailnet": "apagada", "estado": "apagado", "modelo": None}]
        salida = io.StringIO()
        with patch("backend.agentes.__main__.verificar_todos", return_value=agentes), \
                patch("backend.agentes.calentar.calentar", return_value={"llm_s": 1.0, "embed_s": 0.5, "modelos": {}}), \
                redirect_stdout(salida):
            self.assertEqual(main(["calentar"], repo=object()), 0)
        self.assertIn("msi: listo", salida.getvalue())
        self.assertIn("apagada: se omite (apagado)", salida.getvalue())


if __name__ == "__main__":
    unittest.main()
