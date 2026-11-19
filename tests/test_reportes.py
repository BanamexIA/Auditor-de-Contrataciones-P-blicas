import hashlib
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from backend.app import create_app
from backend.casos.decisiones import CasoCerrado
from backend.casos.repositorio import CasoNoEncontrado
from backend.reportes.almacen import (
    AlmacenLocal,
    ArchivoNoEncontrado,
    almacen_desde_entorno,
    validar_clave,
)
from backend.reportes.servicio import (
    FormatoInvalido,
    ReporteCorrupto,
    clave_reporte,
    guardar_reporte,
    leer_reporte,
)
from tests.fakes_casos import RepositorioEnMemoria

PDF = b"%PDF-1.7\nreporte de prueba\n%%EOF"


class AlmacenEnMemoriaTipoS3:
    """Otro almacén con la misma interfaz: así se verá S3 para el resto del sistema."""

    def __init__(self):
        self.objetos = {}

    def guardar(self, clave, contenido, content_type):
        self.objetos[clave] = contenido
        return f"s3://bucket-prueba/{clave}"

    def leer(self, uri):
        return self.objetos[uri.removeprefix("s3://bucket-prueba/")]

    def url_descarga(self, uri, expira_s=300):
        return f"https://bucket-prueba.s3.amazonaws.com/{uri.split('/', 3)[3]}?firma=x"


class AlmacenLocalTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.almacen = AlmacenLocal(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def test_guardar_y_leer(self):
        uri = self.almacen.guardar("reportes/c1/1.pdf", PDF, "application/pdf")
        self.assertEqual(uri, "local://reportes/c1/1.pdf")
        self.assertEqual(self.almacen.leer(uri), PDF)
        self.assertTrue((Path(self.tmp.name) / "reportes/c1/1.pdf").is_file())
        self.assertFalse(list(Path(self.tmp.name).rglob("*.tmp")))
        self.assertIsNone(self.almacen.url_descarga(uri))

    def test_rechaza_claves_peligrosas(self):
        for clave in ("../fuera.pdf", "/etc/passwd", "reportes/../../x", "reportes/./x",
                      "", "reportes//x", "reportes/a b.pdf", "C:\\x"):
            with self.assertRaises(ValueError, msg=clave):
                self.almacen.guardar(clave, PDF, "application/pdf")

    def test_leer_inexistente_o_de_otro_almacen(self):
        with self.assertRaises(ArchivoNoEncontrado):
            self.almacen.leer("local://reportes/no/existe.pdf")
        with self.assertRaises(ValueError):
            self.almacen.leer("s3://bucket/reportes/c1/1.pdf")

    def test_clave_valida(self):
        self.assertEqual(validar_clave("reportes/6f1c-2a/1.pdf"), "reportes/6f1c-2a/1.pdf")

    def test_desde_entorno(self):
        with patch.dict(os.environ, {"REPORTES_ALMACEN": "local",
                                     "REPORTES_DIR": self.tmp.name}):
            self.assertIsInstance(almacen_desde_entorno(), AlmacenLocal)
        with patch.dict(os.environ, {"REPORTES_ALMACEN": "desconocido"}):
            with self.assertRaises(RuntimeError):
                almacen_desde_entorno()


class GuardarReporteTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.almacen = AlmacenLocal(self.tmp.name)
        self.repo = RepositorioEnMemoria()
        self.caso_id = self.repo.crear("pregunta")["id"]

    def tearDown(self):
        self.tmp.cleanup()

    def test_guarda_registra_y_recupera(self):
        r = guardar_reporte(self.repo, self.almacen, self.caso_id, PDF, "pdf",
                            modelo="qwen2.5:7b", equipo="laptop-mich")
        self.assertEqual(r["version"], 1)
        self.assertEqual(r["uri"], f"local://{clave_reporte(self.caso_id, 1, 'pdf')}")
        self.assertEqual(r["sha256"], hashlib.sha256(PDF).hexdigest())
        self.assertEqual((r["content_type"], r["tamano_bytes"]), ("application/pdf", len(PDF)))
        self.assertEqual(leer_reporte(self.almacen, r), PDF)

        [ev] = self.repo.eventos(self.caso_id, "reporte_guardado")
        self.assertEqual(ev["detalle"], {"ruta": r["uri"], "sha256": r["sha256"], "version": 1})
        self.assertEqual((ev["modelo"], ev["equipo"]), ("qwen2.5:7b", "laptop-mich"))

    def test_versiones_incrementan(self):
        v1 = guardar_reporte(self.repo, self.almacen, self.caso_id, PDF, "pdf")
        v2 = guardar_reporte(self.repo, self.almacen, self.caso_id, b"# Reporte v2", "md")
        self.assertEqual((v1["version"], v2["version"]), (1, 2))
        self.assertEqual(leer_reporte(self.almacen, v1), PDF)
        self.assertEqual(v2["content_type"], "text/markdown; charset=utf-8")

    def test_formato_y_contenido_invalidos(self):
        for contenido, formato in ((PDF, "docx"), (b"", "pdf"), ("texto", "md")):
            with self.assertRaises(FormatoInvalido):
                guardar_reporte(self.repo, self.almacen, self.caso_id, contenido, formato)
        self.assertEqual(self.repo.reportes, [])

    def test_caso_inexistente_no_escribe_archivo(self):
        with self.assertRaises(CasoNoEncontrado):
            guardar_reporte(self.repo, self.almacen, "no-existe", PDF, "pdf")
        self.assertFalse(list(Path(self.tmp.name).rglob("*")))

    def test_caso_cerrado(self):
        for estado in ("consultado", "detectado", "normado", "reportado", "en_revision",
                       "cerrado"):
            self.repo.transitar(self.caso_id, estado, None)
        with self.assertRaises(CasoCerrado):
            guardar_reporte(self.repo, self.almacen, self.caso_id, PDF, "pdf")

    def test_detecta_archivo_alterado(self):
        r = guardar_reporte(self.repo, self.almacen, self.caso_id, PDF, "pdf")
        (Path(self.tmp.name) / clave_reporte(self.caso_id, 1, "pdf")).write_bytes(b"alterado")
        with self.assertRaises(ReporteCorrupto):
            leer_reporte(self.almacen, r)


class ApiReportesTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.repo = RepositorioEnMemoria()

    def tearDown(self):
        self.tmp.cleanup()

    def cliente(self, almacen):
        self.almacen = almacen
        client = create_app(repositorio=self.repo, almacen=almacen).test_client()
        caso_id = client.post("/casos", json={"solicitud": "X"}).get_json()["id"]
        return client, caso_id

    def test_listar_y_descargar_local(self):
        client, caso_id = self.cliente(AlmacenLocal(self.tmp.name))
        guardar_reporte(self.repo, self.almacen, caso_id, PDF, "pdf", modelo="m")

        lista = client.get(f"/casos/{caso_id}/reportes").get_json()["reportes"]
        self.assertEqual([r["version"] for r in lista], [1])
        self.assertNotIn("uri", lista[0])
        self.assertTrue(lista[0]["created_at"].endswith("Z"))

        r = client.get(f"/casos/{caso_id}/reportes/1/archivo")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.data, PDF)
        self.assertEqual(r.mimetype, "application/pdf")
        self.assertIn(f"reporte_{caso_id}_v1.pdf", r.headers["Content-Disposition"])
        self.assertEqual(r.headers["X-Content-SHA256"], hashlib.sha256(PDF).hexdigest())

    def test_mismo_flujo_con_otro_almacen_redirige(self):
        """Cambiar de almacén no toca al agente ni al endpoint: solo cambia la descarga."""
        client, caso_id = self.cliente(AlmacenEnMemoriaTipoS3())
        r = guardar_reporte(self.repo, self.almacen, caso_id, PDF, "pdf")
        self.assertTrue(r["uri"].startswith("s3://"))
        respuesta = client.get(f"/casos/{caso_id}/reportes/1/archivo")
        self.assertEqual(respuesta.status_code, 302)
        self.assertIn("firma=x", respuesta.headers["Location"])

    def test_errores(self):
        client, caso_id = self.cliente(AlmacenLocal(self.tmp.name))
        self.assertEqual(client.get("/casos/no-existe/reportes").status_code, 404)
        r = client.get(f"/casos/{caso_id}/reportes/1/archivo")
        self.assertEqual(r.status_code, 404)
        self.assertEqual(r.get_json()["error"]["codigo"], "reporte_no_encontrado")
        self.assertEqual(client.get(f"/casos/{caso_id}/reportes/abc/archivo").status_code, 404)

    def test_archivo_alterado_o_borrado_da_500(self):
        client, caso_id = self.cliente(AlmacenLocal(self.tmp.name))
        guardar_reporte(self.repo, self.almacen, caso_id, PDF, "pdf")
        ruta = Path(self.tmp.name) / clave_reporte(caso_id, 1, "pdf")
        ruta.write_bytes(b"alterado")
        r = client.get(f"/casos/{caso_id}/reportes/1/archivo")
        self.assertEqual(r.status_code, 500)
        self.assertEqual(r.get_json()["error"]["codigo"], "reporte_corrupto")
        ruta.unlink()
        self.assertEqual(client.get(f"/casos/{caso_id}/reportes/1/archivo").status_code, 500)


if __name__ == "__main__":
    unittest.main()
