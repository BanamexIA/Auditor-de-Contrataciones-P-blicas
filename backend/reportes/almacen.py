"""Almacenamiento de reportes detrás de una interfaz (docs/contratos/reportes.md)."""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Protocol

ESQUEMA_LOCAL = "local://"
_CLAVE_VALIDA = re.compile(r"^[A-Za-z0-9_-]+(/[A-Za-z0-9_.-]+)*$")


class ArchivoNoEncontrado(LookupError):
    pass


class AlmacenReportes(Protocol):
    def guardar(self, clave: str, contenido: bytes, content_type: str) -> str:
        """Guarda el contenido y devuelve su uri."""
        ...

    def leer(self, uri: str) -> bytes: ...

    def url_descarga(self, uri: str, expira_s: int = 300) -> str | None:
        """URL temporal de descarga, o None si el backend debe servir el archivo."""
        ...


def validar_clave(clave: str) -> str:
    """Rechaza claves con '..', rutas absolutas o caracteres fuera de [A-Za-z0-9_.-/]."""
    if not _CLAVE_VALIDA.match(clave) or any(p in {".", ".."} for p in clave.split("/")):
        raise ValueError(f"Clave de reporte inválida: {clave!r}.")
    return clave


class AlmacenLocal:
    """Reportes en una carpeta del disco. Para desarrollo y la Entrega 2."""

    def __init__(self, base_dir: str | Path) -> None:
        self.base_dir = Path(base_dir).resolve()

    def _ruta(self, clave: str) -> Path:
        ruta = (self.base_dir / validar_clave(clave)).resolve()
        if self.base_dir not in ruta.parents:
            raise ValueError(f"Clave fuera de la carpeta de reportes: {clave!r}.")
        return ruta

    def guardar(self, clave: str, contenido: bytes, content_type: str) -> str:
        ruta = self._ruta(clave)
        ruta.parent.mkdir(parents=True, exist_ok=True)
        temporal = ruta.with_name(ruta.name + ".tmp")
        temporal.write_bytes(contenido)
        os.replace(temporal, ruta)  # el archivo aparece completo o no aparece
        return ESQUEMA_LOCAL + clave

    def leer(self, uri: str) -> bytes:
        if not uri.startswith(ESQUEMA_LOCAL):
            raise ValueError(f"AlmacenLocal no puede leer {uri!r}.")
        ruta = self._ruta(uri[len(ESQUEMA_LOCAL):])
        if not ruta.is_file():
            raise ArchivoNoEncontrado(uri)
        return ruta.read_bytes()

    def url_descarga(self, uri: str, expira_s: int = 300) -> str | None:
        return None


def almacen_desde_entorno() -> AlmacenReportes:
    tipo = os.environ.get("REPORTES_ALMACEN", "local").lower()
    if tipo == "local":
        return AlmacenLocal(os.environ.get("REPORTES_DIR", "data/reportes"))
    raise RuntimeError(
        f"REPORTES_ALMACEN={tipo!r} no está implementado; usa 'local' (S3 llega en B8)."
    )
