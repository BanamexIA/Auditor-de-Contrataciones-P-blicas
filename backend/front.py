"""Sirve el front compilado (``frontend/dist``) desde el mismo Flask, para usarlo sin Vite.

En desarrollo, Vite sirve el front y redirige ``/api/...`` al backend quitando el prefijo. Aquí pasa lo
mismo: ``PrefijoApi`` quita ``/api`` antes de llegar a las rutas, así que el front compilado funciona igual
y la API sigue respondiendo en la raíz (``/casos``, ``/health``…) para los scripts que ya la usan.

El front solo se sirve si ``FRONT_DIR`` apunta a una carpeta con ``index.html`` (la imagen de Docker lo
compila y lo deja en ``/app/frontend_dist``). Sin ella, el backend se comporta como antes.
"""
from __future__ import annotations

import mimetypes
import os
from pathlib import Path

from flask import Blueprint, Flask, send_from_directory

# python:3.12-slim no conoce .mjs (el worker de pdf.js); con otro tipo el navegador no carga el módulo.
mimetypes.add_type("text/javascript", ".mjs")

RUTAS_FRONT = {"front.indice", "front.recurso"}


class PrefijoApi:
    """Middleware WSGI: ``/api/casos`` llega a la ruta ``/casos``."""

    def __init__(self, app):
        self.app = app

    def __call__(self, environ, start_response):
        ruta = environ.get("PATH_INFO", "")
        if ruta == "/api" or ruta.startswith("/api/"):
            environ["PATH_INFO"] = ruta[4:] or "/"
            environ["SCRIPT_NAME"] = environ.get("SCRIPT_NAME", "") + "/api"
        return self.app(environ, start_response)


def configurar_front(app: Flask, carpeta: str | os.PathLike | None = None) -> bool:
    """Monta el front si hay una compilación; devuelve si quedó montado."""
    app.wsgi_app = PrefijoApi(app.wsgi_app)
    ruta = carpeta or os.environ.get("FRONT_DIR")
    if not ruta or not (Path(ruta) / "index.html").is_file():
        return False
    base = Path(ruta).resolve()
    bp = Blueprint("front", __name__)

    @bp.get("/")
    def indice():
        respuesta = send_from_directory(base, "index.html")
        respuesta.cache_control.no_cache = True  # que una nueva versión se vea al recargar
        return respuesta

    @bp.get("/assets/<path:archivo>")
    def recurso(archivo: str):
        # Los nombres llevan hash de contenido: se pueden guardar en caché un año.
        return send_from_directory(base / "assets", archivo, max_age=31_536_000)

    app.register_blueprint(bp)
    return True
