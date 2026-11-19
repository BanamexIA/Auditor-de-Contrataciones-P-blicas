# Contrato front-end ↔ backend (FastAPI + S3)

El front-end nunca habla con el LLM ni con S3 usando credenciales propias.
Todo pasa por el backend FastAPI, que:

1. Recibe la petición del chat, llama al LLM y genera el informe PDF.
2. Guarda el PDF en S3 y devuelve un `document_id`.
3. Entrega **URLs prefirmadas** de S3 para que el navegador descargue o suba
   los PDF directamente (sin pasar los bytes por FastAPI).
4. Guarda las anotaciones del usuario como JSON (en S3 o en una base de datos).

```
┌──────────────┐  /api/chat, /api/documents/...   ┌──────────────┐   boto3   ┌─────┐
│  React (TS)  │ ───────────────────────────────▶ │   FastAPI    │ ────────▶ │ S3  │
│              │ ◀─────────────────────────────── │  (+ LLM)     │           └─────┘
│              │                                   └──────────────┘              ▲
│              │      GET/PUT con URL prefirmada                                 │
│              │ ────────────────────────────────────────────────────────────────┘
└──────────────┘
```

Todas las rutas cuelgan de `VITE_API_BASE_URL` (por defecto `/api`). JSON en
`snake_case`. Los errores siguen el formato de FastAPI: `{"detail": "mensaje"}`.

Las interfaces TypeScript de cada cuerpo están en `src/api/contracts.ts`.

---

## Chat

### `POST /chat`

Petición:

```json
{
  "conversation_id": "conv_123",          // opcional; null en el primer mensaje
  "message": "Elabora un informe de ventas del Q3",
  "history": [{ "role": "user", "content": "..." }, { "role": "assistant", "content": "..." }],
  "context_document_id": "doc_abc"        // opcional: documento abierto en el visor
}
```

Respuesta `200`:

```json
{
  "conversation_id": "conv_123",
  "message": { "id": "msg_1", "role": "assistant", "content": "Listo, preparé…", "created_at": "2026-11-04T18:00:00Z" },
  "report": { "document_id": "doc_xyz", "title": "Informe de ventas Q3", "file_name": "informe-q3.pdf" }
}
```

`report` es opcional (`null` si la respuesta no genera documento). Cuando
existe, el front lo abre automáticamente en el visor.

> Si `context_document_id` viene informado, el backend puede leer ese PDF y sus
> anotaciones (`GET /documents/{id}/annotations`) para dárselos al LLM.

---

## Documentos

Modelo `DocumentDTO`:

```json
{
  "document_id": "doc_xyz",
  "title": "Informe de ventas Q3",
  "file_name": "informe-q3.pdf",
  "size_bytes": 48211,
  "version": 0,                 // nº de versiones anotadas subidas (0 = solo original)
  "created_at": "2026-11-04T18:00:00Z",
  "updated_at": "2026-11-04T18:05:00Z"
}
```

Modelo `PresignedUrlDTO`:

```json
{
  "url": "https://bucket.s3.amazonaws.com/...&X-Amz-Signature=...",
  "method": "GET",              // o "PUT"
  "headers": { "Content-Type": "application/pdf" },   // opcional
  "s3_key": "documents/doc_xyz/original.pdf",
  "expires_in": 900
}
```

| Método | Ruta | Cuerpo | Respuesta | Uso |
|---|---|---|---|---|
| GET | `/documents/{id}` | — | `DocumentDTO` | Metadatos |
| GET | `/documents/{id}/download-url` | — | `PresignedUrlDTO` (GET) | Descargar el PDF original |
| POST | `/documents` | `{title, file_name, content_type, size_bytes}` | `{document: DocumentDTO, upload: PresignedUrlDTO}` | Registrar un PDF subido por el usuario |
| POST | `/documents/{id}/original` | `{s3_key, size_bytes}` | `DocumentDTO` | Confirmar que el original ya está en S3 |
| POST | `/documents/{id}/upload-url` | `{file_name, content_type, size_bytes}` | `PresignedUrlDTO` (PUT) | Pedir URL para subir una versión anotada |
| POST | `/documents/{id}/versions` | `{s3_key, size_bytes}` | `DocumentDTO` (con `version` incrementado) | Confirmar la versión subida |
| GET | `/documents/{id}/annotations` | — | `{annotations: [...], updated_at}` | Leer anotaciones |
| PUT | `/documents/{id}/annotations` | `{annotations: [...]}` | `{annotations: [...], updated_at}` | Guardar anotaciones (autoguardado) |

### Flujo de subida (abrir PDF local)

1. `POST /documents` → el backend crea el registro y firma un `PUT` a S3.
2. El navegador hace `PUT` del archivo a `upload.url`.
3. `POST /documents/{id}/original` → el backend verifica (`head_object`) y marca el documento como listo.

### Flujo de versión anotada

1. El front aplana las anotaciones en un PDF nuevo (pdf-lib).
2. `POST /documents/{id}/upload-url` → URL `PUT` (p. ej. `documents/{id}/versions/v2.pdf`).
3. `PUT` a S3.
4. `POST /documents/{id}/versions`.

El original nunca se sobrescribe: las anotaciones siguen siendo editables
porque se guardan aparte como JSON.

---

## Anotaciones

Se guardan tal cual las produce el front (`src/types/annotations.ts`).
Coordenadas en puntos PDF a escala 1, origen **arriba a la izquierda** de la página.

```json
{ "id": "ann_1", "type": "highlight", "page": 1, "color": "#ffd43b",
  "rects": [{ "x": 56, "y": 210, "width": 420, "height": 12 }],
  "text": "texto marcado", "comment": "", "createdAt": "...", "updatedAt": "..." }

{ "id": "ann_2", "type": "note", "page": 1, "x": 480, "y": 250, "text": "Revisar", "color": "#ffd43b", ... }
{ "id": "ann_3", "type": "text", "page": 1, "rect": {...}, "text": "Borrador", "fontSize": 12, "color": "#111827", ... }
{ "id": "ann_4", "type": "edit", "page": 1, "rect": {...}, "originalText": "antes", "text": "después", "fontSize": 11, "color": "#111827", ... }
```

`type` ∈ `highlight | underline | strike | note | text | edit`.

---

## Configuración de S3 necesaria

Como el navegador sube y descarga directamente, el bucket necesita CORS:

```json
[
  {
    "AllowedOrigins": ["http://localhost:5173", "https://tu-dominio"],
    "AllowedMethods": ["GET", "PUT"],
    "AllowedHeaders": ["Content-Type"],
    "MaxAgeSeconds": 3000
  }
]
```

## Esqueleto orientativo en FastAPI

```python
from fastapi import FastAPI
from pydantic import BaseModel
import boto3

app = FastAPI()
s3 = boto3.client("s3")
BUCKET = "mi-bucket"

class ChatRequest(BaseModel):
    conversation_id: str | None = None
    message: str
    history: list[dict] = []
    context_document_id: str | None = None

@app.post("/api/chat")
def chat(req: ChatRequest):
    # 1) llamar al LLM  2) generar PDF  3) s3.put_object(...)  4) devolver ChatResponse
    ...

@app.get("/api/documents/{document_id}/download-url")
def download_url(document_id: str):
    key = f"documents/{document_id}/original.pdf"
    url = s3.generate_presigned_url("get_object", Params={"Bucket": BUCKET, "Key": key}, ExpiresIn=900)
    return {"url": url, "method": "GET", "s3_key": key, "expires_in": 900}
```
