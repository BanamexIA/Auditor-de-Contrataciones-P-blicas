# API del backend

Referencia de los endpoints del backend para el front-end y la orquestación.
Los ejemplos salen de la API corriendo con datos de prueba. Las reglas de negocio detrás de
cada endpoint están en [`docs/contratos/`](contratos/README.md).

> **Autenticación:** todavía no hay. Ningún endpoint pide usuario ni token y
> `creado_por` / `decidido_por` llegan en `null`. Cuando exista, se agregará un
> encabezado `Authorization` sin cambiar las rutas.

## Resumen

| Método | Ruta | Para qué | Quién la usa |
|---|---|---|---|
| `GET` | [`/health`](#get-health) | ¿El backend está vivo? | Docker, monitoreo |
| `GET` | [`/health/db`](#get-healthdb) | ¿El backend llega a la base? | Docker, monitoreo |
| `POST` | [`/casos`](#post-casos) | Crear un caso con la pregunta del auditor | Front |
| `GET` | [`/casos`](#get-casos) | Listar casos (filtro por estado) | Front |
| `GET` | [`/casos/<id>`](#get-casosid) | Ver un caso | Front |
| `POST` | [`/casos/<id>/transiciones`](#post-casosidtransiciones) | Cambiar el estado (avanzar, bloquear, desbloquear, cerrar) | Front, orquestador |
| `GET` | [`/casos/<id>/bitacora`](#get-casosidbitacora) | Rastro del caso (HU-06) | Front |
| `GET` | [`/casos/<id>/senales`](#get-casosidsenales) | Señales y su decisión vigente | Front |
| `POST` | [`/casos/<id>/senales/<senal_id>/decision`](#post-casosidsenalessenal_iddecision) | Decidir sobre una señal (HU-07) | Front |
| `GET` | [`/casos/<id>/reportes`](#get-casosidreportes) | Versiones del reporte | Front |
| `GET` | [`/casos/<id>/reportes/<version>/archivo`](#get-casosidreportesversionarchivo) | Descargar un reporte | Front |

Lo que **no** pasa por HTTP: registrar señales, guardar reportes y escribir
eventos de bitácora. El orquestador corre dentro del backend y usa funciones
de Python (ver [Para el orquestador](#para-el-orquestador)).

## Cómo conectarse

| Entorno | URL base |
|---|---|
| Local (`docker compose up`) | `http://localhost:5000` |
| EC2, desde tu laptop | `http://localhost:15000`, con el túnel `ssh -i <tu-llave> -N -L 15000:127.0.0.1:5000 ubuntu@auditor-ec2` |

**Front en desarrollo (Vite):** el backend no tiene CORS habilitado. Usa el
proxy de Vite para que el navegador vea un solo origen; en el código llama a
`/api/casos` en lugar de `http://localhost:5000/casos`:

```ts
// vite.config.ts
export default defineConfig({
  server: {
    proxy: {
      "/api": { target: "http://localhost:5000", rewrite: (p) => p.replace(/^\/api/, "") },
    },
  },
});
```

## Convenciones

- **Cuerpo y respuestas en JSON**, UTF-8 (`Content-Type: application/json`).
  Los acentos llegan tal cual, sin escapar.
- **Fechas** en ISO 8601 UTC, terminadas en `Z`: `"2026-11-15T06:42:02.175150Z"`.
  Convierte a hora local en el front.
- **Identificadores** de casos y señales: UUID en texto. Versiones de reporte: enteros desde 1.
- **Listas** siempre envueltas en un objeto: `{"casos": [...]}`, `{"eventos": [...]}`.

### Errores

Todos los errores, incluidas rutas inexistentes, tienen la misma forma.
Muestra `mensaje` al usuario; usa `codigo` para decidir qué hacer.

```json
{"error": {"codigo": "transicion_invalida",
           "mensaje": "Un caso bloqueado solo puede volver a 'recibido'; primero hay que desbloquearlo."}}
```

| HTTP | `codigo` | Significado |
|---|---|---|
| 400 | `solicitud_invalida` | Falta un campo, el JSON es inválido o un valor está fuera de rango |
| 404 | `caso_no_encontrado` | El caso no existe |
| 404 | `senal_no_encontrada` | La señal no existe o no es de ese caso |
| 404 | `reporte_no_encontrado` | No existe esa versión del reporte (o el caso) |
| 404 | `ruta_no_encontrada` | La URL no existe |
| 405 | `metodo_no_permitido` | Método equivocado (por ejemplo `GET` donde va `POST`) |
| 409 | `transicion_invalida` | El cambio de estado no está permitido |
| 409 | `caso_cerrado` | El caso está cerrado y no acepta decisiones |
| 500 | `reporte_corrupto` | El archivo del reporte no coincide con su hash |
| 500 | `error_interno` | Error inesperado; revisar los logs del backend |
| 503 | `bd_no_disponible` | La base de datos no responde |

## El caso

Objeto que devuelven `POST /casos`, `GET /casos/<id>` y las transiciones:

```json
{
  "id": "0925135e-98e5-4882-8d4a-bb80c89d2416",
  "solicitud": "¿Qué contratos tiene Construcciones del Bajío en 2026?",
  "estado": "bloqueado",
  "estado_previo": "recibido",
  "motivo_bloqueo": "El agente no respondió en 60 s.",
  "creado_por": null,
  "created_at": "2026-11-15T06:42:02.175150Z",
  "updated_at": "2026-11-15T06:43:10.004211Z"
}
```

`estado_previo` y `motivo_bloqueo` solo tienen valor cuando `estado` es
`bloqueado`. **Mientras el caso esté bloqueado, el front debe mostrar
`motivo_bloqueo`.**

### Estados

```
recibido → consultado → detectado → normado → reportado → en_revision → cerrado
   (cualquiera excepto cerrado) → bloqueado → (regresa a estado_previo)
```

Reglas completas en [estado_caso.md](contratos/estado_caso.md). En resumen:
solo se avanza al siguiente, bloquear exige `motivo`, desbloquear regresa a
`estado_previo`, y un caso con señales sin decisión no se cierra.

---

## `GET /health`

**200** `{"status": "ok"}`. No toca la base.

## `GET /health/db`

**200** `{"status": "ok", "database": "connected"}` ·
**503** `{"status": "error", "database": "unavailable"}`.

Si da 503, revisa `docker compose logs backend`: el detalle (por ejemplo,
contraseña incorrecta) está ahí, no en la respuesta.

## `POST /casos`

Crea un caso en estado `recibido`.

```json
{"solicitud": "¿Qué contratos tiene Construcciones del Bajío en 2026?"}
```

**201** con el caso y el encabezado `Location: /casos/<id>`.
**400** si `solicitud` falta, está vacía o no es texto.

## `GET /casos`

| Parámetro | Valores | Por defecto |
|---|---|---|
| `estado` | uno de los 8 estados | todos |
| `limite` | 1 a 100 | 50 |

Ejemplo: `GET /casos?estado=bloqueado&limite=20`. Orden: el más reciente primero.

**200** `{"casos": [<caso>, ...]}` · **400** si `estado` o `limite` no son válidos.

## `GET /casos/<id>`

**200** con el caso · **404** `caso_no_encontrado`.

## `POST /casos/<id>/transiciones`

```json
{"estado": "bloqueado", "motivo": "El agente no respondió en 60 s."}
```

`motivo` solo se usa (y es obligatorio) al bloquear. Para desbloquear, envía
el `estado_previo` del caso: `{"estado": "recibido"}`.

**200** con el caso actualizado · **400** si falta `estado` ·
**404** `caso_no_encontrado` · **409** `transicion_invalida` (salto de estado,
bloqueo sin motivo, cerrar con señales sin decisión, etc.).

## `GET /casos/<id>/bitacora`

Rastro del caso en orden cronológico. Cada evento tiene `evento` (el tipo),
`etapa` (estado del caso en ese momento) y `detalle` (depende del tipo; ver
[evento_bitacora.md](contratos/evento_bitacora.md)).

```json
{"eventos": [
  {"id": 1, "etapa": "recibido", "evento": "solicitud",
   "detalle": {"texto": "¿Qué contratos tiene Construcciones del Bajío en 2026?"},
   "modelo": null, "equipo": null, "created_at": "2026-11-15T06:42:02.175255Z"},
  {"id": 3, "etapa": "recibido", "evento": "transicion",
   "detalle": {"de": "recibido", "a": "bloqueado", "motivo": "El agente no respondió en 60 s."},
   "modelo": null, "equipo": null, "created_at": "2026-11-15T06:42:02.180901Z"},
  {"id": 5, "etapa": "normado", "evento": "llamada_llm",
   "detalle": {"agente": "reportes", "tokens_entrada": 1840, "tokens_salida": 96,
               "latencia_ms": 3120.5, "estado": "ok", "cuantizacion": "Q4_K_M",
               "version_ollama": "0.12.3", "tipo_error": null},
   "modelo": "qwen2.5:7b", "equipo": "laptop-mich", "created_at": "…"}
]}
```

**200** · **404** `caso_no_encontrado`.

## `GET /casos/<id>/senales`

Señales del caso con su decisión **vigente** (la más reciente) o `null`. El
contenido de `datos` lo define el Agente Detección (contrato 1, pendiente).

```json
{"senales": [{
  "id": "1782c424-8f77-4615-b38b-fe071d9408c9",
  "tipo": "adjudicacion_directa_recurrente",
  "datos": {"valor": 0.64, "umbral": 0.3},
  "created_at": "2026-11-15T06:42:02.183136Z",
  "decision": {"decision": "descartada", "comentario": "Proveedor único por patente.",
               "decidido_por": null, "created_at": "2026-11-15T06:42:02.184023Z"}
}]}
```

**200** · **404** `caso_no_encontrado`.

## `POST /casos/<id>/senales/<senal_id>/decision`

```json
{"decision": "descartada", "comentario": "Proveedor único por patente."}
```

| Campo | Regla |
|---|---|
| `decision` | `relevante`, `descartada` o `pendiente` |
| `comentario` | Obligatorio si es `descartada` |

Se puede cambiar la decisión cuantas veces haga falta; el historial queda en
la bitácora. **201**:

```json
{"id": 1, "senal_id": "1782c424-…", "decision": "descartada",
 "comentario": "Proveedor único por patente.", "decidido_por": null,
 "created_at": "2026-11-15T06:42:02.184023Z"}
```

**400** decisión inválida o descarte sin comentario · **404**
`caso_no_encontrado` / `senal_no_encontrada` · **409** `caso_cerrado`.

## `GET /casos/<id>/reportes`

Versiones del reporte, de la más antigua a la más reciente.

```json
{"reportes": [{"version": 1, "formato": "pdf", "content_type": "application/pdf",
               "tamano_bytes": 48211, "sha256": "ec2792f5…",
               "modelo": "qwen2.5:7b", "equipo": "laptop-mich",
               "created_at": "2026-11-15T06:42:02.195520Z"}]}
```

**200** · **404** `caso_no_encontrado`.

## `GET /casos/<id>/reportes/<version>/archivo`

Descarga el archivo. Para mostrar el PDF en el front basta con un
`<iframe src="/api/casos/<id>/reportes/1/archivo">` o un enlace.

- **200** con el archivo (almacén local), `Content-Type` del reporte y
  `Content-Disposition: inline; filename="reporte_<id>_v1.pdf"`.
- **302** a una URL temporal de S3 (cuando se active B8). El navegador sigue la
  redirección solo; con `fetch` también.
- **404** `reporte_no_encontrado` · **500** `reporte_corrupto`.

---

## Para el orquestador

Funciones de Python dentro del backend (no HTTP):

| Función | Para qué |
|---|---|
| `repo.transitar(caso_id, estado, motivo)` | Avanzar o bloquear el caso |
| `bitacora.llamar_llm(repo.registrar_evento, caso_id, agente, client, system, prompt)` | Llamar al modelo y registrar el evento `llamada_llm` |
| `repo.registrar_evento(caso_id, evento, detalle)` | Registrar `sql_ejecutado`, `reglas_evaluadas`, etc. |
| `repo.registrar_senales(caso_id, [{"tipo": …, "datos": {…}}])` | Guardar las señales de la Tool 1 |
| `servicio.guardar_reporte(repo, almacen, caso_id, contenido, formato)` | Guardar el reporte del Agente Reportes |

`repo` es `RepositorioCasosSQL` (`backend/casos/repositorio.py`); el almacén
sale de `almacen_desde_entorno()` (`backend/reportes/almacen.py`).

## Probar a mano (PowerShell)

```powershell
$api = "http://localhost:5000"
$caso = Invoke-RestMethod -Method Post "$api/casos" -ContentType "application/json; charset=utf-8" `
  -Body '{"solicitud": "Contratos de la empresa X en 2026"}'
Invoke-RestMethod "$api/casos/$($caso.id)/bitacora"
```

`Invoke-RestMethod` lanza una excepción con los 4xx/5xx; el JSON del error
está en `$_.ErrorDetails.Message` dentro de un `catch`.
