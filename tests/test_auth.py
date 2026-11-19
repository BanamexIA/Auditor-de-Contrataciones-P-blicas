import io
import tempfile
import time
import unittest
from contextlib import redirect_stderr, redirect_stdout
from urllib.parse import parse_qs, urlparse

from backend.app import create_app
from backend.reportes.almacen import AlmacenLocal
from backend.reportes.servicio import guardar_reporte
from backend.usuarios.__main__ import main as cli
from backend.usuarios.seguridad import (
    TokenInvalido,
    emitir_token,
    firmar_descarga,
    hashear,
    leer_token,
    verificar_contrasena,
    verificar_descarga,
)
from tests.fakes_casos import RepositorioEnMemoria
from tests.fakes_usuarios import SECRETO, RepositorioUsuariosEnMemoria

CLAVE = "contrasena-larga-1"


class SeguridadTest(unittest.TestCase):
    def test_hash_no_guarda_la_contrasena_y_verifica(self):
        h = hashear(CLAVE)
        self.assertNotIn(CLAVE, h)
        self.assertTrue(h.startswith("scrypt$"))
        self.assertNotEqual(h, hashear(CLAVE))  # sal distinta
        self.assertTrue(verificar_contrasena(CLAVE, h))
        self.assertFalse(verificar_contrasena("otra-contrasena", h))
        self.assertFalse(verificar_contrasena(CLAVE, "basura"))
        with self.assertRaises(ValueError):
            hashear("corta")

    def test_token(self):
        token, exp = emitir_token(SECRETO, "ana", "auditor", horas=1, ahora=1000)
        self.assertEqual(exp, 1000 + 3600)
        self.assertEqual(leer_token(SECRETO, token, ahora=2000)["sub"], "ana")
        with self.assertRaisesRegex(TokenInvalido, "expiró"):
            leer_token(SECRETO, token, ahora=exp + 1)
        with self.assertRaisesRegex(TokenInvalido, "Firma"):
            leer_token("x" * 40, token, ahora=2000)
        cuerpo, firma = token.split(".")
        with self.assertRaises(TokenInvalido):  # cambiar el rol invalida la firma
            leer_token(SECRETO, cuerpo[:-2] + "xx." + firma, ahora=2000)
        with self.assertRaises(TokenInvalido):
            leer_token(SECRETO, "sin-punto")

    def test_firma_de_descarga(self):
        exp, firma = firmar_descarga(SECRETO, "c1/1", 300, ahora=1000)
        self.assertTrue(verificar_descarga(SECRETO, "c1/1", str(exp), firma, ahora=1100))
        self.assertFalse(verificar_descarga(SECRETO, "c1/2", str(exp), firma, ahora=1100))
        self.assertFalse(verificar_descarga(SECRETO, "c1/1", str(exp), firma, ahora=exp + 1))
        self.assertFalse(verificar_descarga(SECRETO, "c1/1", None, None))


class ApiAuthTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.repo = RepositorioEnMemoria()
        self.usuarios = RepositorioUsuariosEnMemoria()
        self.usuarios.alta("ana", "Ana P.", "auditor", CLAVE)
        self.almacen = AlmacenLocal(self.tmp.name)
        self.client = create_app(repositorio=self.repo, almacen=self.almacen,
                                 repositorio_usuarios=self.usuarios,
                                 auth_secreto=SECRETO).test_client()

    def tearDown(self):
        self.tmp.cleanup()

    def login(self, usuario="ana", contrasena=CLAVE):
        return self.client.post("/auth/login", json={"usuario": usuario, "contrasena": contrasena})

    def h(self):
        return {"Authorization": "Bearer " + self.login().get_json()["token"]}

    def test_rutas_protegidas_y_publicas(self):
        for metodo, ruta in [("get", "/casos"), ("post", "/casos"), ("get", "/agentes"),
                             ("get", "/auth/yo"), ("get", "/casos/x/bitacora")]:
            r = getattr(self.client, metodo)(ruta, json={})
            self.assertEqual(r.status_code, 401, ruta)
            self.assertEqual(r.get_json()["error"]["codigo"], "no_autenticado")
        self.assertEqual(self.client.get("/health").get_json()["auth"], "activa")
        self.assertEqual(self.client.get("/no-existe").status_code, 404)

    def test_login_y_uso_del_token(self):
        r = self.login()
        self.assertEqual(r.status_code, 200)
        d = r.get_json()
        self.assertEqual(d["usuario"], {"usuario": "ana", "nombre": "Ana P.", "rol": "auditor"})
        self.assertGreater(d["expira"], time.time())
        self.assertNotIn("hash_contrasena", r.get_data(as_text=True))
        self.assertEqual(self.client.get("/auth/yo", headers=self.h()).get_json()["usuario"]["rol"],
                         "auditor")
        self.assertIsNotNone(self.usuarios.usuarios["ana"]["ultimo_acceso"])

    def test_credenciales_invalidas_mismo_mensaje(self):
        mal = self.login(contrasena="incorrecta-123")
        nadie = self.login(usuario="nadie")
        self.assertEqual(mal.status_code, 401)
        self.assertEqual(mal.get_json(), nadie.get_json())
        self.assertEqual(mal.get_json()["error"]["codigo"], "credenciales_invalidas")
        self.assertEqual(self.client.post("/auth/login", json={}).status_code, 400)

    def test_bloqueo_tras_intentos_fallidos(self):
        for _ in range(5):
            self.assertEqual(self.login(contrasena="incorrecta-123").status_code, 401)
        r = self.login()  # ni con la contraseña correcta, durante la ventana
        self.assertEqual(r.status_code, 429)
        self.assertEqual(r.get_json()["error"]["codigo"], "demasiados_intentos")

    def test_token_invalido_y_usuario_dado_de_baja(self):
        r = self.client.get("/casos", headers={"Authorization": "Bearer x.y"})
        self.assertEqual(r.status_code, 401)
        h = self.h()
        self.assertEqual(self.client.get("/casos", headers=h).status_code, 200)
        self.usuarios.baja("ana")
        r = self.client.get("/casos", headers=h)
        self.assertEqual(r.status_code, 401)
        self.assertIn("ya no está activo", r.get_json()["error"]["mensaje"])
        self.assertEqual(self.login().status_code, 401)

    def test_identidad_sale_del_token(self):
        h = self.h()
        caso = self.client.post("/casos", json={"solicitud": "X", "creado_por": "otro"},
                                headers=h).get_json()
        self.assertEqual(caso["creado_por"], "ana")
        self.client.post(f"/casos/{caso['id']}/transiciones", json={"estado": "consultado"},
                         headers=h)
        self.repo.registrar_senales(caso["id"], [{"tipo": "t", "datos": {}}])
        senal = self.repo.listar_senales(caso["id"])[0]
        d = self.client.post(f"/casos/{caso['id']}/senales/{senal['id']}/decision",
                             json={"decision": "relevante"}, headers=h).get_json()
        self.assertEqual(d["decidido_por"], "ana")
        eventos = self.client.get(f"/casos/{caso['id']}/bitacora", headers=h).get_json()["eventos"]
        transicion = [e for e in eventos if e["evento"] == "transicion" and e["detalle"]["a"] == "consultado"]
        self.assertEqual(transicion[0]["detalle"]["usuario"], "ana")

    def test_enlace_firmado_para_iframe(self):
        h = self.h()
        cid = self.client.post("/casos", json={"solicitud": "X"}, headers=h).get_json()["id"]
        guardar_reporte(self.repo, self.almacen, cid, b"%PDF-1.7 x", "pdf")
        self.assertEqual(self.client.get(f"/casos/{cid}/reportes/1/archivo").status_code, 401)

        d = self.client.get(f"/casos/{cid}/reportes/1/enlace", headers=h).get_json()
        url = urlparse(d["url"])
        self.assertEqual(url.path, f"/casos/{cid}/reportes/1/archivo")
        r = self.client.get(d["url"])  # sin header: vale la firma
        self.assertEqual((r.status_code, r.data), (200, b"%PDF-1.7 x"))

        q = parse_qs(url.query)
        otra = f"/casos/{cid}/reportes/2/archivo?exp={q['exp'][0]}&firma={q['firma'][0]}"
        self.assertEqual(self.client.get(otra).status_code, 401)  # la firma es de la versión 1
        self.assertEqual(self.client.get(f"/casos/{cid}/reportes/9/enlace", headers=h).status_code, 404)

    def test_sin_secreto_queda_desactivada(self):
        client = create_app(repositorio=RepositorioEnMemoria(), auth_secreto="").test_client()
        self.assertEqual(client.get("/casos").status_code, 200)
        self.assertEqual(client.get("/health").get_json()["auth"], "desactivada")
        self.assertEqual(client.post("/auth/login", json={"usuario": "a", "contrasena": "b"}).status_code, 503)

    def test_secreto_corto_no_arranca(self):
        with self.assertRaisesRegex(RuntimeError, "32"):
            create_app(repositorio=self.repo, repositorio_usuarios=self.usuarios, auth_secreto="corto")


class CliUsuariosTest(unittest.TestCase):
    def correr(self, repo, *args, stdin="", respuestas=()):
        out, err = io.StringIO(), io.StringIO()
        resp = iter(respuestas)
        with redirect_stdout(out), redirect_stderr(err):
            codigo = cli(list(args), repo=repo, leer=lambda _p: next(resp), entrada=io.StringIO(stdin))
        return codigo, out.getvalue(), err.getvalue()

    def test_ciclo_completo(self):
        repo = RepositorioUsuariosEnMemoria()
        codigo, out, _ = self.correr(repo, "alta", "--usuario", "Ana", "--rol", "auditor",
                                     respuestas=(CLAVE, CLAVE))
        self.assertEqual(codigo, 0)
        self.assertIn("ana", out)
        self.assertNotIn(CLAVE, out)
        self.assertEqual(self.correr(repo, "alta", "--usuario", "ana", "--rol", "auditor",
                                     respuestas=(CLAVE, CLAVE))[0], 2)  # duplicado
        self.assertEqual(self.correr(repo, "rol", "--usuario", "ana", "--rol", "admin")[0], 0)
        self.assertEqual(repo.usuarios["ana"]["rol"], "admin")
        self.assertEqual(self.correr(repo, "contrasena", "--usuario", "ana", "--contrasena-stdin",
                                     stdin="otra-contrasena-9\n")[0], 0)
        self.assertTrue(verificar_contrasena("otra-contrasena-9", repo.usuarios["ana"]["hash_contrasena"]))
        self.assertEqual(self.correr(repo, "baja", "--usuario", "ana")[0], 0)
        self.assertEqual(self.correr(repo, "listar")[1], "")
        self.assertIn("baja", self.correr(repo, "listar", "--todos")[1])

    def test_errores(self):
        repo = RepositorioUsuariosEnMemoria()
        codigo, _, err = self.correr(repo, "alta", "--usuario", "ana", "--rol", "auditor",
                                     respuestas=(CLAVE, "distinta-12345"))
        self.assertEqual(codigo, 2)
        self.assertIn("no coinciden", err)
        self.assertEqual(self.correr(repo, "alta", "--usuario", "ana", "--rol", "auditor",
                                     respuestas=("corta",))[0], 2)
        self.assertEqual(self.correr(repo, "alta", "--usuario", "Mal Nombre!", "--rol", "auditor",
                                     respuestas=(CLAVE, CLAVE))[0], 2)
        self.assertEqual(self.correr(repo, "baja", "--usuario", "nadie")[0], 2)


if __name__ == "__main__":
    unittest.main()
