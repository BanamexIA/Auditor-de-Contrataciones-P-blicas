"""Inicio de sesión con Cognito: el backend verifica la firma y el rol sale de audit.usuarios."""
import time
import unittest
from unittest.mock import patch

import jwt
from cryptography.hazmat.primitives.asymmetric import rsa

from backend.app import create_app
from backend.usuarios.cognito import ConfigCognito, VerificadorCognito
from backend.usuarios.seguridad import TokenInvalido, emitir_token
from tests.fakes_casos import RepositorioEnMemoria
from tests.fakes_usuarios import SECRETO, RepositorioUsuariosEnMemoria

CONFIG = ConfigCognito("us-east-1", "us-east-1_Prueba", "cliente-123",
                       "https://prueba.auth.us-east-1.amazoncognito.com")
LLAVE = rsa.generate_private_key(public_exponent=65537, key_size=2048)
OTRA_LLAVE = rsa.generate_private_key(public_exponent=65537, key_size=2048)


class LlavesFalsas:
    """Hace el papel del JWKS del pool: solo conoce la llave pública de LLAVE."""

    class _Llave:
        def __init__(self, key):
            self.key = key

    def get_signing_key_from_jwt(self, token):
        if jwt.get_unverified_header(token).get("kid") != "k1":
            raise jwt.PyJWKClientError("kid desconocido")
        return self._Llave(LLAVE.public_key())


def token(llave=LLAVE, kid="k1", **cambios):
    """Access token (se enlaza por username)."""
    ahora = int(time.time())
    datos = {"iss": CONFIG.issuer, "token_use": "access", "client_id": CONFIG.client_id,
             "username": "Ana", "sub": "uuid-ana", "iat": ahora, "exp": ahora + 3600,
             "scope": "openid email"}
    datos.update(cambios)
    datos = {k: v for k, v in datos.items() if v is not None}
    return jwt.encode(datos, llave, algorithm="RS256", headers={"kid": kid})


def id_token(llave=LLAVE, kid="k1", **cambios):
    """ID token de un pool que inicia sesión con correo: el username es un UUID."""
    ahora = int(time.time())
    datos = {"iss": CONFIG.issuer, "token_use": "id", "aud": CONFIG.client_id,
             "cognito:username": "3f2a9c1e-0000-4000-8000-000000000000", "sub": "3f2a9c1e",
             "email": "Ana@Ejemplo.MX", "email_verified": True, "iat": ahora, "exp": ahora + 3600}
    datos.update(cambios)
    datos = {k: v for k, v in datos.items() if v is not None}
    return jwt.encode(datos, llave, algorithm="RS256", headers={"kid": kid})


class VerificadorTest(unittest.TestCase):
    def setUp(self):
        self.v = VerificadorCognito(CONFIG, LlavesFalsas())

    def test_access_token_da_el_usuario(self):
        self.assertEqual(self.v.identidad(token()).usuario, "ana")

    def test_id_token_da_el_correo_en_minusculas(self):
        i = self.v.identidad(id_token())
        self.assertEqual((i.email, i.usuario), ("ana@ejemplo.mx", None))

    def test_rechazos(self):
        casos = {
            "firma de otra llave": token(llave=OTRA_LLAVE),
            "kid desconocido": token(kid="otro"),
            "vencido": token(exp=int(time.time()) - 3600),
            "otro pool": token(iss="https://cognito-idp.us-east-1.amazonaws.com/otro"),
            "access de otro app client": token(client_id="otro-cliente"),
            "access sin username": token(username=None),
            "ID de otro app client": id_token(aud="otro-cliente"),
            "ID con correo sin verificar": id_token(email_verified=False),
            "ID sin correo": id_token(email=None),
            "ID firmado con otra llave": id_token(llave=OTRA_LLAVE),
            "otro token_use": token(token_use="refresh"),
            "basura": "a.b.c",
        }
        for nombre, t in casos.items():
            with self.assertRaises(TokenInvalido, msg=nombre):
                self.v.identidad(t)

    def test_no_acepta_hs256_con_la_llave_publica(self):
        """Ataque clásico: firmar con HMAC usando la llave pública como secreto."""
        t = jwt.encode({"iss": CONFIG.issuer, "token_use": "access", "client_id": CONFIG.client_id,
                        "username": "ana", "exp": int(time.time()) + 60}, "x" * 32,
                       algorithm="HS256", headers={"kid": "k1"})
        with self.assertRaises(TokenInvalido):
            self.v.identidad(t)

    def test_config_desde_entorno(self):
        with patch.dict("os.environ", {"COGNITO_REGION": "", "COGNITO_USER_POOL_ID": "x",
                                       "COGNITO_CLIENT_ID": "y"}):
            self.assertIsNone(ConfigCognito.desde_entorno())
        with patch.dict("os.environ", {"COGNITO_REGION": "us-east-1", "COGNITO_USER_POOL_ID": "p",
                                       "COGNITO_CLIENT_ID": "c", "COGNITO_DOMINIO": "https://d/"}):
            c = ConfigCognito.desde_entorno()
        self.assertEqual((c.issuer, c.dominio), ("https://cognito-idp.us-east-1.amazonaws.com/p", "https://d"))


class ApiConCognitoTest(unittest.TestCase):
    def setUp(self):
        self.usuarios = RepositorioUsuariosEnMemoria()
        self.usuarios.alta("ana", "Ana", "auditor", "contrasena-larga-1", email="ana@ejemplo.mx")
        self.client = create_app(repositorio=RepositorioEnMemoria(), repositorio_usuarios=self.usuarios,
                                 auth_secreto=SECRETO,
                                 cognito=VerificadorCognito(CONFIG, LlavesFalsas())).test_client()

    def get(self, ruta, t):
        return self.client.get(ruta, headers={"Authorization": f"Bearer {t}"})

    def test_health_publica_la_config_del_front(self):
        d = self.client.get("/health").get_json()
        self.assertEqual(d["cognito"], {"authority": CONFIG.issuer, "client_id": "cliente-123",
                                        "dominio": CONFIG.dominio})

    def test_token_de_cognito_da_acceso_con_el_rol_de_la_bd(self):
        r = self.get("/auth/yo", token())
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json()["usuario"]["rol"], "auditor")
        self.assertIsNotNone(self.usuarios.usuarios["ana"]["ultimo_acceso"])
        caso = self.client.post("/casos", json={"solicitud": "x"},
                                headers={"Authorization": f"Bearer {token()}"}).get_json()
        self.assertEqual(caso["creado_por"], "ana")  # la bitácora registra al usuario de Cognito

    def test_id_token_entra_por_correo_y_la_bitacora_dice_ana(self):
        r = self.get("/auth/yo", id_token())
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json()["usuario"]["usuario"], "ana")
        caso = self.client.post("/casos", json={"solicitud": "x"},
                                headers={"Authorization": f"Bearer {id_token()}"}).get_json()
        self.assertEqual(caso["creado_por"], "ana")  # no el UUID de Cognito

    def test_correo_no_registrado(self):
        r = self.get("/casos", id_token(email="beto@ejemplo.mx"))
        self.assertEqual(r.status_code, 401)
        self.assertIn("beto@ejemplo.mx", r.get_json()["error"]["mensaje"])

    def test_cognito_sin_alta_en_el_sistema(self):
        r = self.get("/casos", token(username="beto"))
        self.assertEqual(r.status_code, 401)
        self.assertIn("beto", r.get_json()["error"]["mensaje"])

    def test_baja_corta_el_acceso_aunque_el_token_siga_vigente(self):
        t = id_token()
        self.assertEqual(self.get("/casos", t).status_code, 200)
        self.usuarios.baja("ana")
        self.assertEqual(self.get("/casos", t).status_code, 401)

    def test_token_invalido(self):
        self.assertEqual(self.get("/casos", token(client_id="otro")).status_code, 401)

    def test_el_login_local_sigue_funcionando(self):
        t, _ = emitir_token(SECRETO, "ana", "auditor")
        self.assertEqual(self.get("/casos", t).status_code, 200)
        r = self.client.post("/auth/login", json={"usuario": "ana", "contrasena": "contrasena-larga-1"})
        self.assertEqual(r.status_code, 200)

    def test_sin_cognito_un_jwt_no_sirve(self):
        with patch.dict("os.environ", {"COGNITO_REGION": ""}):  # aunque la terminal tenga Cognito
            client = create_app(repositorio=RepositorioEnMemoria(), repositorio_usuarios=self.usuarios,
                                auth_secreto=SECRETO).test_client()
        r = client.get("/casos", headers={"Authorization": f"Bearer {token()}"})
        self.assertEqual(r.status_code, 401)
        self.assertNotIn("cognito", client.get("/health").get_json())


class CliCorreoTest(unittest.TestCase):
    def test_alta_con_correo_y_cambio(self):
        import io
        from contextlib import redirect_stderr, redirect_stdout
        from backend.usuarios.__main__ import main as cli
        repo = RepositorioUsuariosEnMemoria()
        salida = io.StringIO()
        with redirect_stdout(salida):
            cli(["alta", "--usuario", "ana", "--rol", "auditor", "--email", "Ana@Ejemplo.mx",
                 "--contrasena-stdin"], repo=repo, entrada=io.StringIO("contrasena-larga-1\n"))
            cli(["alta", "--usuario", "beto", "--rol", "auditor", "--contrasena-stdin"], repo=repo,
                entrada=io.StringIO("contrasena-larga-1\n"))
        self.assertEqual(repo.activo_por_email("ana@ejemplo.mx")["usuario"], "ana")
        with redirect_stdout(salida), redirect_stderr(io.StringIO()) as err:
            self.assertEqual(cli(["correo", "--usuario", "beto", "--email", "ana@ejemplo.mx"], repo=repo), 2)
            self.assertEqual(cli(["correo", "--usuario", "beto", "--email", "no-es-correo"], repo=repo), 2)
            self.assertEqual(cli(["correo", "--usuario", "beto", "--email", "beto@ejemplo.mx"], repo=repo), 0)
        self.assertIn("ya está asignado", err.getvalue())
        self.assertEqual(repo.activo_por_email("beto@ejemplo.mx")["usuario"], "beto")


if __name__ == "__main__":
    unittest.main()
