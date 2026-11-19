"""Almacenamiento de reportes detrás de una interfaz (docs/contratos/reportes.md)."""

from __future__ import annotations

import os
import re
import uuid
from pathlib import Path
from typing import Any, Protocol

ESQUEMA_LOCAL = "local://"
ESQUEMA_S3 = "s3://"
_CLAVE_VALIDA = re.compile(r"^[A-Za-z0-9_-]+(/[A-Za-z0-9_.-]+)*$")


class ArchivoNoEncontrado(LookupError):
    pass


class AlmacenNoDisponible(RuntimeError):
    """El almacén no responde o rechaza las credenciales (p. ej. S3 con el laboratorio apagado)."""


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
        temporal = ruta.with_name(f"{ruta.name}.{uuid.uuid4().hex}.tmp")  # único por escritura
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


class AlmacenS3:
    """Reportes en un bucket S3 privado, cifrados en reposo.

    Las credenciales salen de la cadena estándar de boto3; en la EC2, del rol de
    la instancia (LabRole). No hay claves en archivos.
    """

    def __init__(self, bucket: str, cliente: Any = None, region: str | None = None) -> None:
        if not bucket:
            raise ValueError("Falta el bucket de S3 (REPORTES_S3_BUCKET).")
        self.bucket = bucket
        if cliente is None:
            import boto3
            from botocore.config import Config

            cliente = boto3.client("s3", region_name=region, config=Config(
                signature_version="s3v4", retries={"max_attempts": 3, "mode": "standard"},
            ))
        self.cliente = cliente

    def _clave(self, uri: str) -> str:
        prefijo = f"{ESQUEMA_S3}{self.bucket}/"
        if not uri.startswith(prefijo):
            raise ValueError(f"AlmacenS3({self.bucket}) no puede leer {uri!r}.")
        return validar_clave(uri[len(prefijo):])

    def _no_disponible(self, operacion: str, exc: Exception) -> AlmacenNoDisponible:
        codigo = getattr(exc, "response", {}).get("Error", {}).get("Code") or type(exc).__name__
        return AlmacenNoDisponible(f"S3 {operacion} en {self.bucket} falló: {codigo}.")

    def guardar(self, clave: str, contenido: bytes, content_type: str) -> str:
        clave = validar_clave(clave)
        try:
            self.cliente.put_object(
                Bucket=self.bucket, Key=clave, Body=contenido,
                ContentType=content_type, ServerSideEncryption="AES256",
            )
        except Exception as exc:
            raise self._no_disponible("put_object", exc) from exc
        return f"{ESQUEMA_S3}{self.bucket}/{clave}"

    def leer(self, uri: str) -> bytes:
        clave = self._clave(uri)
        try:
            return self.cliente.get_object(Bucket=self.bucket, Key=clave)["Body"].read()
        except Exception as exc:
            codigo = getattr(exc, "response", {}).get("Error", {}).get("Code")
            if codigo in {"NoSuchKey", "404"}:
                raise ArchivoNoEncontrado(uri) from exc
            raise self._no_disponible("get_object", exc) from exc

    def url_descarga(self, uri: str, expira_s: int = 300) -> str | None:
        clave = self._clave(uri)
        nombre = clave.rsplit("/", 1)[-1]
        try:
            return self.cliente.generate_presigned_url(
                "get_object",
                Params={"Bucket": self.bucket, "Key": clave,
                        "ResponseContentDisposition": f'inline; filename="{nombre}"'},
                ExpiresIn=expira_s,
            )
        except Exception as exc:
            raise self._no_disponible("presign", exc) from exc

    def verificar(self) -> None:
        """Comprueba credenciales y acceso al bucket (lanza AlmacenNoDisponible)."""
        try:
            self.cliente.head_bucket(Bucket=self.bucket)
        except Exception as exc:
            raise self._no_disponible("head_bucket", exc) from exc


class AlmacenPorEsquema:
    """Escribe en un almacén y lee de cualquiera según el esquema de la uri.

    Al pasar de local a S3, los reportes viejos (``local://``) se siguen sirviendo.
    """

    def __init__(self, escritura: AlmacenReportes, lectores: dict[str, AlmacenReportes]) -> None:
        self.escritura = escritura
        self.lectores = lectores

    def _para(self, uri: str) -> AlmacenReportes:
        for esquema, almacen in self.lectores.items():
            if uri.startswith(esquema):
                return almacen
        raise ValueError(f"No hay almacén para {uri!r}.")

    def guardar(self, clave: str, contenido: bytes, content_type: str) -> str:
        return self.escritura.guardar(clave, contenido, content_type)

    def leer(self, uri: str) -> bytes:
        return self._para(uri).leer(uri)

    def url_descarga(self, uri: str, expira_s: int = 300) -> str | None:
        return self._para(uri).url_descarga(uri, expira_s)


def almacen_desde_entorno() -> AlmacenReportes:
    tipo = os.environ.get("REPORTES_ALMACEN", "local").lower()
    local = AlmacenLocal(os.environ.get("REPORTES_DIR", "data/reportes"))
    if tipo == "local":
        return local
    if tipo == "s3":
        s3 = AlmacenS3(
            os.environ.get("REPORTES_S3_BUCKET", ""),
            region=os.environ.get("AWS_REGION") or os.environ.get("AWS_DEFAULT_REGION"),
        )
        return AlmacenPorEsquema(s3, {ESQUEMA_S3: s3, ESQUEMA_LOCAL: local})
    raise RuntimeError(f"REPORTES_ALMACEN={tipo!r} no es válido; usa 'local' o 's3'.")
