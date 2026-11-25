"""Autenticación de la API (docs/contratos/autenticacion.md).

- ``POST /auth/login`` cambia usuario y contraseña por un token firmado (8 h).
- Con Cognito configurado (``backend/usuarios/cognito.py``) también se acepta el access token
  de Cognito; el rol y si el usuario está activo siguen saliendo de ``audit.usuarios``.
- Todas las demás rutas exigen ``Authorization: Bearer <token>``, salvo
  ``/health``, ``/health/db`` y la descarga de un reporte con firma temporal.
- Si el usuario se da de baja, su token deja de servir en la siguiente petición.
"""

from __future__ import annotations

import os
import threading
import time
from collections import defaultdict, deque
from dataclasses import dataclass
from functools import wraps
from typing import Any, Callable

from flask import Blueprint, Flask, current_app, g, jsonify, request

from backend.usuarios.cognito import ConfigCognito, VerificadorCognito
from backend.usuarios.repositorio import RepositorioUsuarios
from backend.usuarios.seguridad import (
    HASH_SEÑUELO,
    TokenInvalido,
    emitir_token,
    leer_token,
    verificar_contrasena,
    verificar_descarga,
)

bp = Blueprint("auth", __name__)

RUTAS_PUBLICAS = {"health", "database_health", "auth.login", "static",
                  "front.indice", "front.recurso"}  # la página del front (backend/front.py); la API sigue protegida
INTENTOS_MAX = 5
VENTANA_S = 300


@dataclass
class ConfigAuth:
    secreto: str
    repo: RepositorioUsuarios
    horas: float = 8.0
    cognito: VerificadorCognito | None = None


def _error(http: int, codigo: str, mensaje: str):
    return jsonify(error={"codigo": codigo, "mensaje": mensaje}), http


def _config() -> ConfigAuth | None:
    return current_app.extensions.get("auth")


def usuario_actual() -> str | None:
    """Usuario autenticado de la petición, o None si la autenticación está desactivada."""
    datos = g.get("usuario")
    return datos["usuario"] if datos else None


def requiere_rol(*roles: str) -> Callable:
    def decorar(vista: Callable) -> Callable:
        @wraps(vista)
        def envuelta(*args, **kwargs):
            datos = g.get("usuario")
            if _config() is not None and (not datos or datos["rol"] not in roles):
                return _error(403, "sin_permiso", "Tu rol no permite esta acción.")
            return vista(*args, **kwargs)
        return envuelta
    return decorar


class _LimiteIntentos:
    """Bloquea un usuario tras INTENTOS_MAX fallos en VENTANA_S segundos (en memoria)."""

    def __init__(self) -> None:
        self._fallos: dict[str, deque[float]] = defaultdict(deque)
        self._lock = threading.Lock()

    def _vigentes(self, clave: str, ahora: float) -> deque[float]:
        fallos = self._fallos[clave]
        while fallos and fallos[0] < ahora - VENTANA_S:
            fallos.popleft()
        return fallos

    def bloqueado(self, clave: str) -> bool:
        with self._lock:
            return len(self._vigentes(clave, time.time())) >= INTENTOS_MAX

    def fallo(self, clave: str) -> None:
        with self._lock:
            self._vigentes(clave, time.time()).append(time.time())

    def limpiar(self, clave: str) -> None:
        with self._lock:
            self._fallos.pop(clave, None)


@bp.post("/auth/login")
def login():
    cfg = _config()
    if cfg is None:
        return _error(503, "auth_no_configurada", "La autenticación no está configurada.")
    datos = request.get_json(silent=True)
    usuario = datos.get("usuario") if isinstance(datos, dict) else None
    contrasena = datos.get("contrasena") if isinstance(datos, dict) else None
    if not isinstance(usuario, str) or not isinstance(contrasena, str) or not usuario or not contrasena:
        return _error(400, "solicitud_invalida", "Envía 'usuario' y 'contrasena'.")
    clave = usuario.strip().lower()
    limite: _LimiteIntentos = current_app.extensions["auth_limite"]
    if limite.bloqueado(clave):
        return _error(429, "demasiados_intentos",
                      f"Demasiados intentos fallidos. Espera {VENTANA_S // 60} minutos.")

    fila = cfg.repo.credenciales(clave)
    # Siempre se verifica un hash, exista o no el usuario: mismo tiempo de respuesta.
    valida = verificar_contrasena(contrasena, fila["hash_contrasena"] if fila else HASH_SEÑUELO)
    if not fila or not valida:
        limite.fallo(clave)
        return _error(401, "credenciales_invalidas", "Usuario o contraseña incorrectos.")

    limite.limpiar(clave)
    cfg.repo.registrar_acceso(fila["usuario"])
    token, exp = emitir_token(cfg.secreto, fila["usuario"], fila["rol"], cfg.horas)
    return jsonify(token=token, expira=exp,
                   usuario={"usuario": fila["usuario"], "nombre": fila["nombre"], "rol": fila["rol"]})


@bp.get("/auth/yo")
def yo():
    datos = g.get("usuario")
    if not datos:
        return _error(503, "auth_no_configurada", "La autenticación no está configurada.")
    if g.get("via_cognito"):
        # Con Cognito no pasa por /auth/login: el front llama a /auth/yo al entrar.
        _config().repo.registrar_acceso(datos["usuario"])
    return jsonify(usuario={k: datos[k] for k in ("usuario", "nombre", "rol")})


def _descarga_firmada(cfg: ConfigAuth) -> bool:
    if request.endpoint != "casos.archivo_reporte":
        return False
    args = request.view_args or {}
    recurso = f"{args.get('caso_id')}/{args.get('version')}"
    return verificar_descarga(cfg.secreto, recurso, request.args.get("exp"), request.args.get("firma"))


def _autenticar():
    cfg = _config()
    if cfg is None or request.endpoint in RUTAS_PUBLICAS or request.endpoint is None:
        return None
    if _descarga_firmada(cfg):
        return None
    encabezado = request.headers.get("Authorization", "")
    if not encabezado.startswith("Bearer "):
        return _error(401, "no_autenticado", "Inicia sesión: falta 'Authorization: Bearer <token>'.")
    token = encabezado[len("Bearer "):].strip()
    via_cognito = cfg.cognito is not None and VerificadorCognito.parece_jwt(token)
    try:
        if via_cognito:
            identidad = cfg.cognito.identidad(token)
            fila = (cfg.repo.activo_por_email(identidad.email) if identidad.email
                    else cfg.repo.activo(identidad.usuario))
        else:
            fila = cfg.repo.activo(leer_token(cfg.secreto, token)["sub"])
    except TokenInvalido as exc:
        return _error(401, "no_autenticado", f"{exc} Vuelve a iniciar sesión.")
    if fila is None:
        if via_cognito:
            return _error(401, "no_autenticado",
                          f"Tu cuenta del equipo ({identidad.descripcion}) no está dada de alta en el "
                          "sistema o fue dada de baja. Pide al administrador que te registre.")
        return _error(401, "no_autenticado", "El usuario ya no está activo.")
    g.usuario = fila  # el rol vigente es el de la BD, no el del token
    g.via_cognito = via_cognito
    return None


def configurar_auth(app: Flask, repo: RepositorioUsuarios | None, secreto: str | None = None,
                    cognito: VerificadorCognito | None = None) -> None:
    """Activa la autenticación si hay secreto y repositorio; si no, avisa en el log.

    Cognito es opcional y se suma al login local (no lo reemplaza). Requiere AUTH_SECRET igual,
    porque las descargas firmadas de reportes usan ese secreto.
    """
    secreto = secreto if secreto is not None else os.environ.get("AUTH_SECRET", "")
    if cognito is None:
        config_cognito = ConfigCognito.desde_entorno()
        cognito = VerificadorCognito(config_cognito) if config_cognito else None
    if not secreto or repo is None:
        app.extensions["auth"] = None
        app.logger.warning("AUTENTICACIÓN DESACTIVADA: falta AUTH_SECRET. Solo para desarrollo.")
        if cognito is not None:
            app.logger.warning("Cognito configurado pero ignorado: la autenticación está desactivada.")
    else:
        if len(secreto) < 32:
            raise RuntimeError("AUTH_SECRET debe tener al menos 32 caracteres.")
        horas = float(os.environ.get("AUTH_TOKEN_HORAS", "8") or 8)
        app.extensions["auth"] = ConfigAuth(secreto=secreto, repo=repo, horas=horas, cognito=cognito)
    app.extensions["auth_limite"] = _LimiteIntentos()
    app.before_request(_autenticar)
    app.register_blueprint(bp)


def info_auth() -> dict[str, Any]:
    cfg = _config()
    info: dict[str, Any] = {"auth": "activa" if cfg else "desactivada"}
    if cfg and cfg.cognito:
        info["cognito"] = cfg.cognito.config.publico()
    return info
