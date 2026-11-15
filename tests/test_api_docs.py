import re
import unittest
from pathlib import Path
from unittest.mock import patch

from backend.app import create_app
from tests.fakes_casos import RepositorioEnMemoria

API_MD = Path(__file__).resolve().parents[1] / "docs" / "api.md"


def _ruta_documentada(regla: str) -> str:
    """'/casos/<caso_id>/reportes/<int:version>/archivo' -> '/casos/<id>/reportes/<version>/archivo'."""
    regla = re.sub(r"<(?:\w+:)?(\w+)>", r"<\1>", regla)
    return regla.replace("<caso_id>", "<id>")


class ApiDocumentadaTest(unittest.TestCase):
    def test_cada_endpoint_esta_en_el_resumen(self):
        doc = API_MD.read_text(encoding="utf-8")
        app = create_app(repositorio=RepositorioEnMemoria())
        faltan = []
        for regla in app.url_map.iter_rules():
            if regla.endpoint == "static":
                continue
            for metodo in sorted(regla.methods - {"HEAD", "OPTIONS"}):
                fila = f"| `{metodo}` | [`{_ruta_documentada(regla.rule)}`]"
                if fila not in doc:
                    faltan.append(f"{metodo} {regla.rule}")
        self.assertEqual(faltan, [], "Endpoints sin documentar en docs/api.md")

    def test_codigos_de_error_del_codigo_estan_documentados(self):
        doc = API_MD.read_text(encoding="utf-8")
        raiz = API_MD.parents[1] / "backend"
        codigos = set()
        for archivo in raiz.rglob("*.py"):
            texto = archivo.read_text(encoding="utf-8")
            codigos |= set(re.findall(r'_error\(\d{3}, "(\w+)"', texto))
            codigos |= set(re.findall(r'"codigo": "(\w+)"', texto))
            codigos |= set(re.findall(r'^\s+\d{3}: "(\w+)",$', texto, re.M))
        faltan = sorted(c for c in codigos if f"`{c}`" not in doc)
        self.assertEqual(faltan, [], "Códigos de error sin documentar en docs/api.md")


class ErroresEnJsonTest(unittest.TestCase):
    def setUp(self):
        self.app = create_app(repositorio=RepositorioEnMemoria())
        self.client = self.app.test_client()

    def test_ruta_inexistente(self):
        r = self.client.get("/no-existe")
        self.assertEqual(r.status_code, 404)
        self.assertEqual(r.get_json()["error"]["codigo"], "ruta_no_encontrada")

    def test_metodo_no_permitido(self):
        r = self.client.delete("/casos")
        self.assertEqual(r.status_code, 405)
        self.assertEqual(r.get_json()["error"]["codigo"], "metodo_no_permitido")

    def test_error_inesperado_no_filtra_detalles(self):
        with patch.object(RepositorioEnMemoria, "listar",
                          side_effect=RuntimeError("password=secreto")):
            with self.assertLogs(self.app.logger, level="ERROR"):
                r = self.client.get("/casos")
        self.assertEqual(r.status_code, 500)
        self.assertEqual(r.get_json()["error"]["codigo"], "error_interno")
        self.assertNotIn("secreto", r.get_data(as_text=True))


if __name__ == "__main__":
    unittest.main()
