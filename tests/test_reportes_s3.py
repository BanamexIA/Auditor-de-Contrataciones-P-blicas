import io
import os
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from unittest.mock import patch
from urllib.parse import parse_qs, urlparse

from backend.app import create_app
from backend.reportes.__main__ import main as cli
from backend.reportes.almacen import (
    AlmacenLocal,
    AlmacenNoDisponible,
    AlmacenPorEsquema,
    AlmacenS3,
    ArchivoNoEncontrado,
    almacen_desde_entorno,
)
from backend.reportes.servicio import guardar_reporte
from tests.fakes_casos import RepositorioEnMemoria

PDF = b"%PDF-1.7\nreporte\n%%EOF"


class ErrorAws(Exception):
    """Imita botocore.exceptions.ClientError (tiene .response)."""

    def __init__(self, codigo):
        super().__init__(codigo)
        self.response = {"Error": {"Code": codigo}}


class S3Simulado:
    def __init__(self, error=None):
        self.objetos = {}
        self.error = error
        self.llamadas = []

    def _fallar(self):
        if self.error:
            raise ErrorAws(self.error)

    def put_object(self, **kw):
        self._fallar()
        self.llamadas.append(("put", kw))
        self.objetos[(kw["Bucket"], kw["Key"])] = kw["Body"]

    def get_object(self, Bucket, Key):
        self._fallar()
        if (Bucket, Key) not in self.objetos:
            raise ErrorAws("NoSuchKey")
        return {"Body": io.BytesIO(self.objetos[(Bucket, Key)])}

    def generate_presigned_url(self, operacion, Params, ExpiresIn):
        self._fallar()
        return f"https://{Params['Bucket']}.s3.amazonaws.com/{Params['Key']}?X-Amz-Expires={ExpiresIn}"

    def head_bucket(self, Bucket):
        self._fallar()


class AlmacenS3Test(unittest.TestCase):
    def setUp(self):
        self.s3 = S3Simulado()
        self.almacen = AlmacenS3("bucket-prueba", cliente=self.s3)

    def test_guardar_cifrado_y_leer(self):
        uri = self.almacen.guardar("reportes/c1/1.pdf", PDF, "application/pdf")
        self.assertEqual(uri, "s3://bucket-prueba/reportes/c1/1.pdf")
        put = self.s3.llamadas[0][1]
        self.assertEqual(put["ServerSideEncryption"], "AES256")
        self.assertEqual(put["ContentType"], "application/pdf")
        self.assertEqual(self.almacen.leer(uri), PDF)

    def test_claves_y_uris_ajenas(self):
        with self.assertRaises(ValueError):
            self.almacen.guardar("../x.pdf", PDF, "application/pdf")
        for uri in ("s3://otro-bucket/reportes/c1/1.pdf", "local://reportes/c1/1.pdf",
                    "s3://bucket-prueba/../x"):
            with self.assertRaises(ValueError, msg=uri):
                self.almacen.leer(uri)

    def test_inexistente_y_no_disponible(self):
        with self.assertRaises(ArchivoNoEncontrado):
            self.almacen.leer("s3://bucket-prueba/reportes/no/1.pdf")
        caido = AlmacenS3("bucket-prueba", cliente=S3Simulado(error="ExpiredToken"))
        with self.assertRaisesRegex(AlmacenNoDisponible, "ExpiredToken"):
            caido.guardar("reportes/c1/1.pdf", PDF, "application/pdf")
        with self.assertRaises(AlmacenNoDisponible):
            caido.verificar()

    def test_sin_bucket(self):
        with self.assertRaises(ValueError):
            AlmacenS3("", cliente=self.s3)

    def test_url_prefirmada_real_sin_red(self):
        """boto3 firma localmente: no necesita red ni credenciales válidas."""
        with patch.dict(os.environ, {"AWS_ACCESS_KEY_ID": "AKIAPRUEBA",
                                     "AWS_SECRET_ACCESS_KEY": "secreto"}):
            almacen = AlmacenS3("bucket-prueba", region="us-east-1")
            url = almacen.url_descarga("s3://bucket-prueba/reportes/c1/1.pdf", 300)
        partes = urlparse(url)
        q = parse_qs(partes.query)
        self.assertEqual(partes.scheme, "https")
        self.assertTrue(partes.path.endswith("reportes/c1/1.pdf"))
        self.assertEqual(q["X-Amz-Expires"], ["300"])
        self.assertEqual(q["X-Amz-Algorithm"], ["AWS4-HMAC-SHA256"])
        self.assertIn('inline; filename="1.pdf"', q["response-content-disposition"][0])


class PorEsquemaTest(unittest.TestCase):
    def test_escribe_en_s3_y_lee_reportes_locales_viejos(self):
        with tempfile.TemporaryDirectory() as tmp:
            local = AlmacenLocal(tmp)
            viejo = local.guardar("reportes/c1/1.pdf", PDF, "application/pdf")
            s3 = AlmacenS3("bucket-prueba", cliente=S3Simulado())
            mixto = AlmacenPorEsquema(s3, {"s3://": s3, "local://": local})

            nuevo = mixto.guardar("reportes/c1/2.pdf", PDF, "application/pdf")
            self.assertTrue(nuevo.startswith("s3://"))
            self.assertEqual(mixto.leer(viejo), PDF)
            self.assertIsNone(mixto.url_descarga(viejo))
            self.assertIn("X-Amz-Expires", mixto.url_descarga(nuevo))
            with self.assertRaises(ValueError):
                mixto.leer("ftp://x")

    def test_desde_entorno(self):
        with tempfile.TemporaryDirectory() as tmp, patch.dict(os.environ, {
            "REPORTES_ALMACEN": "s3", "REPORTES_S3_BUCKET": "bucket-prueba",
            "REPORTES_DIR": tmp, "AWS_REGION": "us-east-1",
            "AWS_ACCESS_KEY_ID": "AKIAPRUEBA", "AWS_SECRET_ACCESS_KEY": "secreto",
        }):
            almacen = almacen_desde_entorno()
            self.assertIsInstance(almacen, AlmacenPorEsquema)
            self.assertEqual(almacen.escritura.bucket, "bucket-prueba")
        with patch.dict(os.environ, {"REPORTES_ALMACEN": "s3", "REPORTES_S3_BUCKET": ""}):
            with self.assertRaises(ValueError):
                almacen_desde_entorno()
        with patch.dict(os.environ, {"REPORTES_ALMACEN": "ftp"}):
            with self.assertRaises(RuntimeError):
                almacen_desde_entorno()


class ApiS3Test(unittest.TestCase):
    def cliente(self, s3):
        self.repo = RepositorioEnMemoria()
        self.almacen = AlmacenS3("bucket-prueba", cliente=s3)
        client = create_app(repositorio=self.repo, almacen=self.almacen).test_client()
        caso_id = client.post("/casos", json={"solicitud": "X"}).get_json()["id"]
        return client, caso_id

    def test_descarga_redirige_a_url_prefirmada(self):
        client, caso_id = self.cliente(S3Simulado())
        guardar_reporte(self.repo, self.almacen, caso_id, PDF, "pdf")
        r = client.get(f"/casos/{caso_id}/reportes/1/archivo")
        self.assertEqual(r.status_code, 302)
        self.assertIn(f"reportes/{caso_id}/1.pdf", r.headers["Location"])
        self.assertIn("X-Amz-Expires=300", r.headers["Location"])

    def test_s3_caido_da_503(self):
        s3 = S3Simulado()
        client, caso_id = self.cliente(s3)
        guardar_reporte(self.repo, self.almacen, caso_id, PDF, "pdf")
        s3.error = "ExpiredToken"
        r = client.get(f"/casos/{caso_id}/reportes/1/archivo")
        self.assertEqual(r.status_code, 503)
        self.assertEqual(r.get_json()["error"]["codigo"], "almacen_no_disponible")
        self.assertNotIn("ExpiredToken", r.get_data(as_text=True))

    def test_s3_caido_al_guardar_no_registra_en_bd(self):
        client, caso_id = self.cliente(S3Simulado(error="AccessDenied"))
        with self.assertRaises(AlmacenNoDisponible):
            guardar_reporte(self.repo, self.almacen, caso_id, PDF, "pdf")
        self.assertEqual(client.get(f"/casos/{caso_id}/reportes").get_json()["reportes"], [])


class CliTest(unittest.TestCase):
    def correr(self, almacen):
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            codigo = cli(["verificar"], almacen=almacen)
        return codigo, out.getvalue(), err.getvalue()

    def test_verificar_s3(self):
        codigo, out, _ = self.correr(AlmacenS3("bucket-prueba", cliente=S3Simulado()))
        self.assertEqual(codigo, 0)
        self.assertIn("bucket accesible", out)
        self.assertIn("sha256 coincide", out)
        self.assertIn("X-Amz-Expires", out)

    def test_verificar_s3_sin_credenciales(self):
        codigo, _, err = self.correr(
            AlmacenS3("bucket-prueba", cliente=S3Simulado(error="NoCredentialsError")))
        self.assertEqual(codigo, 2)
        self.assertIn("NoCredentialsError", err)

    def test_verificar_local(self):
        with tempfile.TemporaryDirectory() as tmp:
            codigo, out, _ = self.correr(AlmacenLocal(tmp))
        self.assertEqual(codigo, 0)
        self.assertIn("la sirve el backend", out)


if __name__ == "__main__":
    unittest.main()
