"""Contraseñas (scrypt) y tokens firmados (HMAC-SHA256). Solo biblioteca estándar."""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import secrets
import time
from typing import Any

ROLES = ("auditor", "admin")
_N, _R, _P = 2**14, 8, 1
CONTRASENA_MIN = 10


class TokenInvalido(ValueError):
    pass


def _b64(datos: bytes) -> str:
    return base64.urlsafe_b64encode(datos).rstrip(b"=").decode()


def _de_b64(texto: str) -> bytes:
    return base64.urlsafe_b64decode(texto + "=" * (-len(texto) % 4))


def validar_contrasena(contrasena: str) -> None:
    if not isinstance(contrasena, str) or len(contrasena) < CONTRASENA_MIN:
        raise ValueError(f"La contraseña debe tener al menos {CONTRASENA_MIN} caracteres.")


def hashear(contrasena: str) -> str:
    validar_contrasena(contrasena)
    sal = secrets.token_bytes(16)
    h = hashlib.scrypt(contrasena.encode(), salt=sal, n=_N, r=_R, p=_P, dklen=32)
    return f"scrypt${_N}${_R}${_P}${_b64(sal)}${_b64(h)}"


def verificar_contrasena(contrasena: str, guardado: str) -> bool:
    try:
        _, n, r, p, sal, h = guardado.split("$")
        calculado = hashlib.scrypt(contrasena.encode(), salt=_de_b64(sal), n=int(n),
                                   r=int(r), p=int(p), dklen=len(_de_b64(h)))
    except (ValueError, TypeError):
        return False
    return hmac.compare_digest(calculado, _de_b64(h))


# Hash de una contraseña que nadie tiene: se verifica contra él cuando el usuario
# no existe, para que la respuesta tarde lo mismo y no revele qué usuarios hay.
HASH_SEÑUELO = hashear(secrets.token_urlsafe(16))


def _firmar(secreto: str, mensaje: str) -> str:
    return _b64(hmac.new(secreto.encode(), mensaje.encode(), hashlib.sha256).digest())


def emitir_token(secreto: str, usuario: str, rol: str, horas: float = 8,
                 ahora: float | None = None) -> tuple[str, int]:
    exp = int((ahora or time.time()) + horas * 3600)
    cuerpo = _b64(json.dumps({"sub": usuario, "rol": rol, "exp": exp},
                             separators=(",", ":")).encode())
    return f"{cuerpo}.{_firmar(secreto, cuerpo)}", exp


def leer_token(secreto: str, token: str, ahora: float | None = None) -> dict[str, Any]:
    try:
        cuerpo, firma = token.split(".")
    except ValueError as exc:
        raise TokenInvalido("Token mal formado.") from exc
    if not hmac.compare_digest(firma, _firmar(secreto, cuerpo)):
        raise TokenInvalido("Firma inválida.")
    try:
        datos = json.loads(_de_b64(cuerpo))
    except ValueError as exc:
        raise TokenInvalido("Token mal formado.") from exc
    if datos.get("exp", 0) < (ahora or time.time()):
        raise TokenInvalido("La sesión expiró.")
    return datos


def firmar_descarga(secreto: str, recurso: str, segundos: int = 300,
                    ahora: float | None = None) -> tuple[int, str]:
    """Firma de corta duración para un recurso (p. ej. el archivo de un reporte)."""
    exp = int((ahora or time.time()) + segundos)
    return exp, _firmar(secreto, f"descarga:{recurso}:{exp}")


def verificar_descarga(secreto: str, recurso: str, exp: str | None, firma: str | None,
                       ahora: float | None = None) -> bool:
    if not exp or not firma or not exp.isdigit() or int(exp) < (ahora or time.time()):
        return False
    return hmac.compare_digest(firma, _firmar(secreto, f"descarga:{recurso}:{exp}"))
