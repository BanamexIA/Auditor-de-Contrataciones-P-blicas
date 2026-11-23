# API del backend

Referencia de los endpoints del backend para el front-end y la orquestación.
Los ejemplos salen de la API corriendo con datos de prueba. Las reglas de negocio detrás de
cada endpoint están en [`docs/contratos/`](contratos/README.md).

> **Autenticación:** todas las rutas, salvo `/health`, `/health/db` y
> `POST /auth/login`, piden `Authorization: Bearer <token>`. Flujo completo,
> roles y seguridad en [autenticacion.md](contratos/autenticacion.md).
> `creado_por`, `decidido_por` y el usuario de la bitácora salen del token.

## Resumen

| Método | Ruta | Para qué | Quién la usa |
|---|---|---|---|
| `GET` | [`/health`](#get-health) | ¿El backend está vivo? | Docker, monitoreo |
| `GET` | [`/health/db`](#get-healthdb) | ¿El backend llega a la base? | Docker, monitoreo |
| `POST` | [`/auth/login`](#post-authlogin) | Iniciar sesión: usuario y contraseña → token | Front |
| `GET` | [`/auth/yo`](#get-authyo) | ¿Quién soy? ¿Sigue vigente mi token? | Front |
| `POST` | [`/casos`](#post-casos) | Crear un caso con la pregunta del auditor | Front |
| `GET` | [`/casos`](#get-casos) | Listar casos (filtro por estado) | Front |
| `GET` | [`/casos/<id>`](#get-casosid) | Ver un caso | Front |
| `POST` | [`/casos/<id>/transiciones`](#post-casosidtransiciones) | Cambiar el estado (avanzar, bloquear, desbloquear, cerrar) | Front, orquestador |
| `GET` | [`/casos/<id>/bitacora`](#get-casosidbitacora) | Rastro del caso (HU-06) | Front |
| `GET` | [`/casos/<id>/senales`](#get-casosidsenales) | Señales y su decisión vigente | Front |
| `POST` | [`/casos/<id>/senales/<senal_id>/decision`](#post-casosidsenalessenal_iddecision) | Decidir sobre una señal (HU-07) | Front |
| `GET` | [`/casos/<id>/reportes`](#get-casosidreportes) | Versiones del reporte | Front |
| `GET` | [`/casos/<id>/reportes/<version>/enlace`](#get-casosidreportesversionenlace) | URL temporal del reporte para un `<iframe>` | Front |
| `GET` | [`/casos/<id>/reportes/<version>/archivo`](#get-casosidreportesversionarchivo) | Descargar un reporte | Front |
| `GET` | [`/casos/<id>/reportes/<version>/contenido`](#get-casosidreportesversioncontenido) | Bytes del reporte vía backend (visor PDF) | Front |
| `GET` | [`/casos/<id>/telemetria`](#get-casosidtelemetria) | Tokens y latencia del modelo en el caso (B9) | Front, evaluación |
| `POST` | [`/demo/preguntar`](#post-demopreguntar) | Demo: el Agente Consulta contesta una pregunta | Front de demo |
| `POST` | [`/demo/casos/<id>/analizar`](#post-democasosidanalizar) | Demo: calidad, detección, normas y reporte de un caso consultado | Front |
| `GET` | [`/agentes`](#get-agentes) | Laptops con Ollama registradas y su estado | Front, monitoreo |
| `GET` | [`/agentes/<agente_id>`](#get-agentesagente_id) | Ver un agente | Front, monitoreo |
| `POST` | [`/agentes/<agente_id>/verificar`](#post-agentesagente_idverificar) | Verificar ahora si un agente responde | Front, administrador |

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
| 401 | `no_autenticado` | Falta el token, es inválido, expiró o el usuario fue dado de baja: lleva al login |
| 401 | `credenciales_invalidas` | Usuario o contraseña incorrectos (login) |
| 403 | `sin_permiso` | Tu rol no permite la acción |
| 429 | `demasiados_intentos` | 5 logins fallidos en 5 min; espera |
| 503 | `auth_no_configurada` | El backend corre sin `AUTH_SECRET` (solo desarrollo) |
| 404 | `caso_no_encontrado` | El caso no existe |
| 404 | `senal_no_encontrada` | La señal no existe o no es de ese caso |
| 404 | `reporte_no_encontrado` | No existe esa versión del reporte (o el caso) |
| 404 | `agente_no_encontrado` | El agente no existe |
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

**200** `{"status": "ok", "auth": "activa"}`. No toca la base. `auth` es `activa` o
`desactivada` (sin `AUTH_SECRET`, solo desarrollo). Si Cognito está configurado agrega
`"cognito": {"authority", "client_id", "dominio"}` (datos públicos) para que el front sepa a dónde
redirigir; ver [guia-cognito.md](guia-cognito.md).

## `GET /health/db`

**200** `{"status": "ok", "database": "connected"}` ·
**503** `{"status": "error", "database": "unavailable"}`.

Si da 503, revisa `docker compose logs backend`: el detalle (por ejemplo,
contraseña incorrecta) está ahí, no en la respuesta.

## `POST /auth/login`

```json
{"usuario": "ana", "contrasena": "…"}
```

**200**:

```json
{"token": "eyJzdWIi…", "expira": 1763569000,
 "usuario": {"usuario": "ana", "nombre": "Ana P.", "rol": "auditor"}}
```

`expira` es una marca Unix (segundos). **400** `solicitud_invalida` ·
**401** `credenciales_invalidas` · **429** `demasiados_intentos`.

## `GET /auth/yo`

**200** `{"usuario": {"usuario": "ana", "nombre": "Ana P.", "rol": "auditor"}}` ·
**401** `no_autenticado`.

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

## `GET /casos/<id>/reportes/<version>/enlace`

URL temporal (5 min) para poner en un `<iframe>` o enlace, que no pueden mandar
el header `Authorization`. Con S3 es la URL prefirmada; en local, la ruta
`/archivo` con `?exp=…&firma=…` (anteponle `/api` en el front).

```json
{"url": "/casos/6f1c…/reportes/1/archivo?exp=1763540000&firma=Qm9…", "expira": 1763540000}
```

**200** · **404** `reporte_no_encontrado` · **503** `almacen_no_disponible`.

## `GET /casos/<id>/reportes/<version>/archivo`

Descarga el archivo. Para mostrar el PDF en el front basta con un
`<iframe src="/api/casos/<id>/reportes/1/archivo">` o un enlace.

- **200** con el archivo (almacén local), `Content-Type` del reporte y
  `Content-Disposition: inline; filename="reporte_<id>_v1.pdf"`.
- **302** a una URL prefirmada de S3 válida 5 minutos (`REPORTES_ALMACEN=s3`).
  El navegador sigue la redirección solo; con `fetch` también. No guardes la URL:
  pide `/archivo` cada vez.
- **404** `reporte_no_encontrado` · **500** `reporte_corrupto` ·
  **503** `almacen_no_disponible` (S3 no responde o vencieron las credenciales del laboratorio).

## `GET /casos/<id>/reportes/<version>/contenido`

Igual que `/archivo`, pero **nunca redirige a S3**: el backend lee el archivo, verifica su SHA-256
y entrega los bytes (`X-Content-SHA256`). Es para visores que leen el PDF con `fetch` (pdf.js),
porque el navegador no puede leer el bucket directo sin CORS. Requiere sesión.
Errores: `404 reporte_no_encontrado`, `500 reporte_corrupto`, `503 almacen_no_disponible`.

## `POST /demo/casos/<id>/analizar`

Solo para la demo, mientras no existe el orquestador. Sobre un caso en `consultado` (creado con
`/demo/preguntar`) corre Calidad, Detección, Normativo y Reportes y deja el caso en `en_revision`.
**No acepta filas del navegador:** vuelve a ejecutar, con `agent_ro`, el SQL de la bitácora del caso.

```json
{"narrativa_llm": false}
```

Con `narrativa_llm: false` (por defecto) el PDF usa el texto de respaldo del Agente Reportes y
tarda segundos; con `true` redacta con el modelo (una llamada por señal: minutos). Sin laptop
disponible se omite el RAG (el reporte lo declara) salvo que se pida `narrativa_llm`.

Respuesta `200`: `caso_id`, `estado: "en_revision"`, `senales`, `evaluadas`, `no_evaluables`,
`normas`, `narrativa_llm`, `rag` y `reporte` (`version`, `formato`, `tamano_bytes`, `sha256`).
Si el caso no tiene contratos que analizar: `200` con `estado: "bloqueado"` y `motivo`.
Errores: `404 caso_no_encontrado`, `409 transicion_invalida` (el caso no está en `consultado`),
`409 sin_consulta`, `503 agente_no_disponible` (se pidió el modelo sin laptop),
`502 analisis_fallo`.

## `POST /demo/preguntar`

Solo para la demo, mientras no existe el orquestador. Crea un caso con la pregunta, corre el
Agente Consulta en la laptop disponible y espera la respuesta (con `qwen2.5:7b`, de 10 a 60 s).
El caso queda en `consultado`, o en `bloqueado` con el motivo.

```json
{"pregunta": "Lista 10 contratos de 2026 con proveedores en el 69-B"}
```

Respuesta `200` con `tipo: "sql"`: `caso_id`, `sql`, `supuestos`, `equipo`, `modelo`,
`total_filas` y `filas` (hasta 200). Si el agente pide aclarar o no hay datos, también es `200`,
con `tipo: "bloqueado"`, `codigo: "sin_respuesta"` y `motivo`. Sin laptop disponible: `503`
(`agente_no_disponible`); si el modelo falla: `502` (`agente_fallo`).

CORS: los orígenes permitidos van en `CORS_ORIGENES` (por defecto `http://localhost:8080`).

## `GET /casos/<id>/telemetria`

Cada llamada al modelo hecha dentro del caso (de `telemetry.llm_calls`), con
totales y desglose por agente. `equipo` es la laptop que hizo la inferencia
(nombre de Tailscale). Sin prompts ni respuestas.

```json
{"caso_id": "6f1c…",
 "totales": {"llamadas": 3, "errores": 1, "tokens_entrada": 600, "tokens_salida": 320, "latencia_ms": 8000.5},
 "por_agente": [{"agente": "consultas", "llamadas": 2, "errores": 1, "tokens_entrada": 100,
                 "tokens_salida": 20, "latencia_ms": 3800.0}, …],
 "llamadas": [{"started_at": "2026-11-20T18:00:00Z", "agente": "consultas", "modelo": "qwen2.5:7b",
               "equipo": "laptop-mich", "tokens_entrada": 100, "tokens_salida": 20,
               "latencia_ms": 800.0, "tokens_por_segundo": 25.0, "estado": "ok", "tipo_error": null}]}
```

**200** · **404** `caso_no_encontrado`.

Para que una llamada quede ligada al caso, el orquestador usa
`bitacora.llamar_llm(...)`: escribe el evento `llamada_llm` y la fila de
telemetría con `caso_id`, agente y laptop. Si la telemetría no se puede
escribir, se registra un aviso en el log y **el caso sigue**.

## `GET /agentes`

Agentes activos (laptops con Ollama) y el resultado de su última verificación.
El backend los revisa solo cada `AGENTES_VERIFICAR_CADA_S` segundos (60 por
defecto). El alta y la baja no son por API: las hace el administrador por CLI
(ver [agentes.md](contratos/agentes.md)).

```json
{"agentes": [{
  "id": 1, "usuario": "alean", "nombre_tailnet": "laptop-alean", "modelo": null,
  "estado": "disponible", "activo": true,
  "modelos": ["nomic-embed-text:latest", "qwen2.5:7b"], "version_ollama": "0.12.3",
  "latencia_ms": 42.7, "ultimo_error": null,
  "ultima_verificacion": "2026-11-15T07:10:00.512000Z", "created_at": "2026-11-15T07:00:00Z"
}]}
```

| `estado` | Significado |
|---|---|
| `disponible` | Responde y tiene el modelo |
| `sin_modelo` | Responde, pero no tiene el modelo requerido (`modelo` o `AGENT_MODEL`) |
| `apagado` | No responde (`ultimo_error` dice por qué, por ejemplo `TimeoutError`) |
| `desconocido` | Aún no se ha verificado |

**200** · **503** `bd_no_disponible` si el registro no está configurado.

## `GET /agentes/<agente_id>`

**200** con el agente · **404** `agente_no_encontrado`.

## `POST /agentes/<agente_id>/verificar`

Verifica en este momento. No recibe cuerpo: usa el nombre registrado y nunca
una dirección enviada por el cliente.

**200** con el agente actualizado · **404** `agente_no_encontrado`.

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
| `app.engine_agente_desde_entorno()` | Conexión para **ejecutar el SQL que genera el agente**: rol `agent_ro`, sesión de solo lectura y corte a los 30 s. Nunca uses `engine_desde_entorno()` para ese SQL |
| `agentes.servicio.seleccionar_agente(repo_agentes, usuario)` | Elegir una laptop disponible (verificada en ese momento); devuelve `url` y `modelo` para `OllamaClient`. Si ninguna responde lanza `AgenteNoDisponible`, cuyo mensaje es el motivo para bloquear el caso |

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
