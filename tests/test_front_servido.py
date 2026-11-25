"""El backend sirve el front compilado (backend/front.py) y la API también responde bajo /api."""

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from backend.app import create_app
from tests.fakes_casos import RepositorioEnMemoria

SECRETO = "s" * 40


class FrontServidoTest(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        base = Path(self.dir.name)
        (base / "assets").mkdir()
        (base / "index.html").write_text("<!doctype html><title>Auditor</title>", encoding="utf-8")
        (base / "assets" / "pdf.worker.min-abc.mjs").write_text("export {}", encoding="utf-8")
        with patch.dict("os.environ", {"FRONT_DIR": str(base)}):
            self.app = create_app(repositorio=RepositorioEnMemoria(), auth_secreto=SECRETO)
        self.c = self.app.test_client()

    def tearDown(self):
        self.dir.cleanup()

    def test_la_pagina_y_sus_archivos_son_publicos(self):
        r = self.c.get("/")
        self.assertEqual(r.status_code, 200)
        self.assertIn(b"Auditor", r.data)
        self.assertIn("no-cache", r.headers["Cache-Control"])
        r = self.c.get("/assets/pdf.worker.min-abc.mjs")
        self.assertEqual(r.status_code, 200)
        self.assertTrue(r.mimetype.endswith("javascript"))

    def test_la_api_responde_igual_con_y_sin_prefijo(self):
        self.assertEqual(self.c.get("/api/health").get_json()["status"], "ok")
        self.assertEqual(self.c.get("/health").status_code, 200)
        self.assertEqual(self.c.get("/api/casos").get_json(), self.c.get("/casos").get_json())

    def test_las_rutas_del_front_son_las_unicas_publicas_nuevas(self):
        from backend.usuarios.auth import RUTAS_PUBLICAS
        self.assertTrue({"front.indice", "front.recurso"} <= RUTAS_PUBLICAS)
        self.assertNotIn("casos.listar_casos", RUTAS_PUBLICAS)

    def test_no_sale_de_la_carpeta(self):
        self.assertEqual(self.c.get("/assets/../index.html").status_code, 404)


class SinFrontTest(unittest.TestCase):
    def test_sin_compilacion_todo_sigue_como_antes(self):
        with patch.dict("os.environ", {"FRONT_DIR": ""}):
            c = create_app(repositorio=RepositorioEnMemoria(), auth_secreto=SECRETO).test_client()
        self.assertNotEqual(c.get("/").status_code, 200)
        self.assertEqual(c.get("/api/health").status_code, 200)


if __name__ == "__main__":
    unittest.main()
