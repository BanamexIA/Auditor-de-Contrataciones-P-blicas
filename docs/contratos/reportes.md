# Almacenamiento de reportes (B5)

**Estado:** Aprobado por Backend (18 nov) · **Usan:** Agente Reportes, Orquestación, Front-end · **Tabla:** `audit.reportes`

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
| `AlmacenLocal` | `local` | `local://reportes/<caso_id>/<version>.<ext>` | El backend envía el archivo |
| `AlmacenS3` | `s3` | `s3://<bucket>/reportes/<caso_id>/<version>.<ext>` | Redirección a una URL prefirmada (5 min) |

La carpeta local se configura con `REPORTES_DIR` (en Docker, un volumen).

## S3 (B8)

| Tema | Decisión |
|---|---|
| Bucket | `REPORTES_S3_BUCKET` (staging: `auditor-reportes-banamexia`, `us-east-1`), privado, acceso público bloqueado |
| Credenciales | Rol de la instancia (LabRole) por la cadena estándar de boto3. **Nunca** claves en `.env` |
| Cifrado | `ServerSideEncryption=AES256` en cada objeto |
| Descarga | `/archivo` responde 302 a una URL prefirmada de 5 min con `Content-Disposition: inline` |
| Reportes viejos | Con `s3` se siguen leyendo los `local://` ya registrados (`AlmacenPorEsquema`) |
| S3 caído o credenciales vencidas | Guardar lanza `AlmacenNoDisponible` y **no** se registra nada en la BD; `/archivo` responde 503 `almacen_no_disponible` |

Con la URL prefirmada el navegador baja el archivo directo de S3, así que el
backend no verifica el `sha256` en esa descarga. `GET /casos/<id>/reportes`
expone el hash para quien quiera comprobarlo.

Comprobar desde el contenedor:

```bash
docker compose exec backend python -m backend.reportes verificar
```

Sube `reportes/_verificacion/1.md`, lo lee, compara el hash e imprime una URL
prefirmada. Si da `NoCredentialsError` dentro del contenedor pero `aws s3 ls`
funciona en el host, el límite de saltos de IMDSv2 está en 1; súbelo a 2:

```bash
aws ec2 modify-instance-metadata-options --instance-id <id> --http-put-response-hop-limit 2 --http-endpoint enabled
```

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
4. Mientras se guarda, la fila del caso queda bloqueada (`FOR UPDATE`): dos
   reportes simultáneos del mismo caso reciben versiones distintas y nunca
   escriben el mismo archivo (encontrado y corregido en la prueba de carga B10).

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
responde **302** a la URL prefirmada.

| HTTP | `codigo` | Cuándo |
|---|---|---|
| 404 | `caso_no_encontrado` / `reporte_no_encontrado` | No existe el caso o esa versión |
| 500 | `reporte_corrupto` | El hash del archivo no coincide con el registrado |
| 503 | `almacen_no_disponible` | S3 no responde o vencieron las credenciales |
