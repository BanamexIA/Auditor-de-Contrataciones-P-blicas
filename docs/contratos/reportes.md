# Almacenamiento de reportes (B5)

**Estado:** Borrador · **Usan:** Agente Reportes, Orquestación, Front-end · **Tabla:** `audit.reportes`

## Idea central

Los agentes **no saben dónde se guardan los reportes**. El Agente Reportes
devuelve el contenido (bytes) y su formato; el backend lo guarda detrás de una
interfaz `AlmacenReportes`. Cambiar de disco local a S3 (B8) es cambiar una
variable de entorno, sin tocar a los agentes ni al front.

> ARQUITECTURA.md dice que el Agente Reportes "lo sube a S3". Con este
> contrato lo sube el backend; el agente solo entrega el contenido.

## Interfaz

```python
class AlmacenReportes(Protocol):
    def guardar(self, clave: str, contenido: bytes, content_type: str) -> str: ...  # devuelve la uri
    def leer(self, uri: str) -> bytes: ...
    def url_descarga(self, uri: str, expira_s: int = 300) -> str | None: ...       # None: el backend sirve el archivo
```

| Implementación | `REPORTES_ALMACEN` | `uri` | Descarga |
|---|---|---|---|
| `AlmacenLocal` (ahora) | `local` | `local://reportes/<caso_id>/<version>.<ext>` | El backend envía el archivo |
| `AlmacenS3` (B8) | `s3` | `s3://<bucket>/reportes/<caso_id>/<version>.<ext>` | Redirección a una URL prefirmada |

La carpeta local se configura con `REPORTES_DIR` (en Docker, un volumen).

## Guardar un reporte (orquestador)

```python
guardar_reporte(repo, almacen, caso_id, contenido=b"%PDF-…", formato="pdf",
                modelo="qwen2.5:7b", equipo="laptop-mich")
```

1. Calcula el `sha256` del contenido y la siguiente `version` del caso (1, 2, 3…).
2. **Primero guarda el archivo**, después registra en la BD: la fila en
   `audit.reportes` y el evento `reporte_guardado` en la bitácora, en una
   transacción. Así la BD nunca apunta a un archivo que no existe.
3. No se puede guardar un reporte en un caso `cerrado`.

Formatos aceptados: `pdf` (`application/pdf`) y `md` (`text/markdown`). La
decisión final del formato es de R1; la interfaz no cambia.

## Fila en `audit.reportes`

| Columna | Regla |
|---|---|
| `caso_id`, `version` | Únicos juntos; `version` es entero desde 1 |
| `uri` | Ubicación devuelta por el almacén (antes `s3_uri`) |
| `sha256` | Hash del contenido; se verifica al leer |
| `formato`, `content_type`, `tamano_bytes` | Del contenido guardado |
| `modelo`, `equipo` | Modelo y laptop que redactaron el reporte |

## API

### `GET /casos/<id>/reportes`

**200** con las versiones, la más reciente al final:

```json
{"reportes": [{"version": 1, "formato": "pdf", "sha256": "9f2c…", "tamano_bytes": 48211,
               "modelo": "qwen2.5:7b", "equipo": "laptop-mich",
               "created_at": "2026-11-14T18:10:00Z"}]}
```

La `uri` no se expone al front.

### `GET /casos/<id>/reportes/<version>/archivo`

Descarga el reporte. Con `AlmacenLocal` responde **200** con el archivo; con S3
responderá **302** a la URL prefirmada.

| HTTP | `codigo` | Cuándo |
|---|---|---|
| 404 | `caso_no_encontrado` / `reporte_no_encontrado` | No existe el caso o esa versión |
| 500 | `reporte_corrupto` | El hash del archivo no coincide con el registrado |
