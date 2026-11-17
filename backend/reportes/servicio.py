"""Guardar y recuperar reportes de un caso sin que los agentes conozcan el almacén."""

from __future__ import annotations

import hashlib
from typing import Any

from backend.reportes.almacen import AlmacenReportes

FORMATOS = {
    "pdf": "application/pdf",
    "md": "text/markdown; charset=utf-8",
}


class FormatoInvalido(ValueError):
    pass


class ReporteCorrupto(RuntimeError):
    """El contenido leído no coincide con el hash registrado."""


def clave_reporte(caso_id: str, version: int, formato: str) -> str:
    return f"reportes/{caso_id}/{version}.{formato}"


def guardar_reporte(
    repo: Any,
    almacen: AlmacenReportes,
    caso_id: str,
    contenido: bytes,
    formato: str,
    modelo: str | None = None,
    equipo: str | None = None,
) -> dict[str, Any]:
    """Guarda el archivo primero y luego lo registra en la BD y la bitácora."""
    if formato not in FORMATOS:
        raise FormatoInvalido(
            f"Formato no soportado: {formato!r}. Usa: {', '.join(sorted(FORMATOS))}."
        )
    if not isinstance(contenido, bytes) or not contenido:
        raise FormatoInvalido("El reporte está vacío o no es bytes.")

    version = repo.siguiente_version_reporte(caso_id)  # valida caso existente y no cerrado
    content_type = FORMATOS[formato]
    uri = almacen.guardar(clave_reporte(caso_id, version, formato), contenido, content_type)
    return repo.registrar_reporte(
        caso_id=caso_id,
        version=version,
        uri=uri,
        sha256=hashlib.sha256(contenido).hexdigest(),
        formato=formato,
        content_type=content_type,
        tamano_bytes=len(contenido),
        modelo=modelo,
        equipo=equipo,
    )


def leer_reporte(almacen: AlmacenReportes, reporte: dict[str, Any]) -> bytes:
    contenido = almacen.leer(reporte["uri"])
    if hashlib.sha256(contenido).hexdigest() != reporte["sha256"]:
        raise ReporteCorrupto(f"El hash del reporte {reporte['uri']} no coincide.")
    return contenido
