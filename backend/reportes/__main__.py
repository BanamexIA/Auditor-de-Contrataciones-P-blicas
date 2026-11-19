"""Comprobar el almacén de reportes configurado.

En la EC2:
    docker compose exec backend python -m backend.reportes verificar
"""

from __future__ import annotations

import argparse
import hashlib
import sys

from backend.reportes.almacen import (
    AlmacenNoDisponible,
    AlmacenPorEsquema,
    AlmacenS3,
    almacen_desde_entorno,
)

CLAVE_PRUEBA = "reportes/_verificacion/1.md"


def main(argv: list[str] | None = None, almacen=None) -> int:
    parser = argparse.ArgumentParser(prog="python -m backend.reportes")
    sub = parser.add_subparsers(dest="comando", required=True)
    sub.add_parser("verificar", help="Subir, leer y firmar un archivo de prueba")
    parser.parse_args(argv)

    try:
        almacen = almacen or almacen_desde_entorno()
        destino = almacen.escritura if isinstance(almacen, AlmacenPorEsquema) else almacen
        print(f"Almacén: {type(destino).__name__}"
              + (f" (bucket {destino.bucket})" if isinstance(destino, AlmacenS3) else ""))
        if isinstance(destino, AlmacenS3):
            destino.verificar()
            print("  bucket accesible")
        contenido = "# Verificación\n\nArchivo de prueba del backend.\n".encode()
        uri = almacen.guardar(CLAVE_PRUEBA, contenido, "text/markdown; charset=utf-8")
        print(f"  guardado  {uri}")
        if hashlib.sha256(almacen.leer(uri)).digest() != hashlib.sha256(contenido).digest():
            print("Error: el contenido leído no coincide.", file=sys.stderr)
            return 1
        print("  leído     sha256 coincide")
        url = almacen.url_descarga(uri, 300)
        print(f"  descarga  {url or '(la sirve el backend)'}")
    except (AlmacenNoDisponible, ValueError, RuntimeError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
