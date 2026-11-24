"""Verificación de tokens de Amazon Cognito (docs/guia-cognito.md).

Cognito solo dice *quién eres*. El rol y si el usuario está activo siguen saliendo de
``audit.usuarios``: el ``username`` del token se busca ahí (en minúsculas).

Siempre: firma RS256 con las llaves públicas (JWKS) del pool, ``iss`` del pool y ``exp`` vigente.
Además, según el tipo de token:

- **ID token** (``token_use == "id"``): ``aud`` = app client y ``email_verified``. Se enlaza por
  **correo** con ``audit.usuarios.email``. Es lo que manda el front: en un pool que inicia sesión
  con correo, el ``username`` de Cognito es un identificador interno ilegible (UUID).
- **Access token** (``token_use == "access"``): ``client_id`` = app client. Se enlaza por
  ``username`` con ``audit.usuarios.usuario`` (pools que usan nombre de usuario).

Variables de entorno (si falta alguna de las tres primeras, Cognito queda desactivado):
  COGNITO_REGION, COGNITO_USER_POOL_ID, COGNITO_CLIENT_ID, COGNITO_DOMINIO (para cerrar sesión).
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Any, Protocol

import jwt

from backend.usuarios.seguridad import TokenInvalido

TOLERANCIA_RELOJ_S = 30


@dataclass(frozen=True)
class ConfigCognito:
    region: str
    user_pool_id: str
    client_id: str
    dominio: str | None = None  # https://<prefijo>.auth.<region>.amazoncognito.com

    @property
    def issuer(self) -> str:
        return f"https://cognito-idp.{self.region}.amazonaws.com/{self.user_pool_id}"

    @property
    def jwks_url(self) -> str:
        return f"{self.issuer}/.well-known/jwks.json"

    @classmethod
    def desde_entorno(cls) -> "ConfigCognito | None":
        region = os.environ.get("COGNITO_REGION", "").strip()
        pool = os.environ.get("COGNITO_USER_POOL_ID", "").strip()
        cliente = os.environ.get("COGNITO_CLIENT_ID", "").strip()
        if not (region and pool and cliente):
            return None
        dominio = os.environ.get("COGNITO_DOMINIO", "").strip().rstrip("/") or None
        return cls(region, pool, cliente, dominio)

    def publico(self) -> dict[str, Any]:
        """Lo que necesita el front para redirigir al inicio de sesión (datos públicos)."""
        return {"authority": self.issuer, "client_id": self.client_id, "dominio": self.dominio}


@dataclass(frozen=True)
class Identidad:
    """Quién es, según Cognito. Exactamente uno de los dos se usa para buscar en audit.usuarios."""
    email: str | None = None
    usuario: str | None = None
    detalle: dict[str, Any] = field(default_factory=dict, compare=False)

    @property
    def descripcion(self) -> str:
        return self.email or self.usuario or "desconocido"


class FuenteLlaves(Protocol):
    def get_signing_key_from_jwt(self, token: str) -> Any: ...


class VerificadorCognito:
    def __init__(self, config: ConfigCognito, llaves: FuenteLlaves | None = None) -> None:
        self.config = config
        # PyJWKClient descarga el JWKS una vez y lo guarda; si llega un kid nuevo (rotación), lo vuelve a pedir.
        self._llaves = llaves or jwt.PyJWKClient(config.jwks_url, cache_keys=True, lifespan=3600, timeout=5)

    @staticmethod
    def parece_jwt(token: str) -> bool:
        """Los tokens locales tienen 2 partes (cuerpo.firma); un JWT tiene 3."""
        return token.count(".") == 2

    def identidad(self, token: str) -> Identidad:
        """Verifica el token (ID o access) y dice con qué buscar al usuario."""
        try:
            llave = self._llaves.get_signing_key_from_jwt(token).key
        except jwt.PyJWKClientError as exc:
            raise TokenInvalido("No se pudo verificar el token de Cognito.") from exc
        except jwt.PyJWTError as exc:
            raise TokenInvalido("Token mal formado.") from exc
        try:
            uso = jwt.decode(token, options={"verify_signature": False}).get("token_use")
        except jwt.PyJWTError as exc:
            raise TokenInvalido("Token mal formado.") from exc
        if uso == "id":
            datos = self._decodificar(token, llave, audiencia=self.config.client_id,
                                      requeridos=["exp", "iss", "aud", "token_use", "email"])
            if datos.get("email_verified") not in (True, "true"):
                raise TokenInvalido("El correo de la cuenta no está verificado en Cognito.")
            email = str(datos["email"]).strip().lower()
            if not email:
                raise TokenInvalido("El token no trae correo.")
            return Identidad(email=email, detalle={"sub": datos.get("sub")})
        if uso == "access":
            datos = self._decodificar(token, llave, audiencia=None,
                                      requeridos=["exp", "iss", "token_use", "client_id", "username"])
            if datos.get("client_id") != self.config.client_id:
                raise TokenInvalido("El token es de otra aplicación.")
            usuario = str(datos.get("username", "")).strip().lower()
            if not usuario:
                raise TokenInvalido("El token no trae usuario.")
            return Identidad(usuario=usuario, detalle={"sub": datos.get("sub")})
        raise TokenInvalido("Tipo de token de Cognito no aceptado.")

    def _decodificar(self, token: str, llave: Any, audiencia: str | None, requeridos: list[str]) -> dict:
        try:
            return jwt.decode(
                token,
                llave,
                algorithms=["RS256"],
                issuer=self.config.issuer,
                audience=audiencia,
                leeway=TOLERANCIA_RELOJ_S,
                options={"require": requeridos, "verify_aud": audiencia is not None},
            )
        except jwt.ExpiredSignatureError as exc:
            raise TokenInvalido("La sesión expiró.") from exc
        except jwt.InvalidAudienceError as exc:
            raise TokenInvalido("El token es de otra aplicación.") from exc
        except jwt.PyJWTError as exc:
            raise TokenInvalido("Token de Cognito inválido.") from exc
