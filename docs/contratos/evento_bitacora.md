# Contrato 5: evento de bitácora

**Estado:** Aprobado por Backend (14 nov) · **Usan:** Backend, Orquestación, los 3 agentes, Front-end (rastro) · **Tabla:** `audit.bitacora`

La bitácora es el historial de un caso: qué se pidió, qué SQL se ejecutó, qué
reglas y normas se usaron, qué modelo respondió, en qué equipo, con cuántos
tokens y en cuánto tiempo. Con ella se reconstruye el rastro del caso (HU-06).

## Reglas generales

1. **Solo se agregan filas.** Nadie actualiza ni borra eventos. El rol del backend solo tiene `SELECT` e `INSERT`.
2. **Cada evento pertenece a un caso** (`caso_id` existente en `audit.casos`).
3. **Lo escribe el backend.** El orquestador y los agentes corren dentro del backend y llaman a una función; ningún agente ni modelo escribe directo en la tabla.
4. **Sin secretos ni prompts completos** en `detalle`: no contraseñas, no llaves, no el texto completo enviado al modelo. Sí el SQL, porque es evidencia.
5. Si escribir la bitácora falla, el paso falla. No se avanza un caso sin dejar registro.

## Forma de un evento

| Columna | Tipo | Regla |
|---|---|---|
| `caso_id` | texto | Obligatorio |
| `etapa` | texto | Estado del caso cuando ocurrió el evento (`recibido`, `consultado`, …) |
| `evento` | texto | Uno de los tipos de la tabla siguiente |
| `detalle` | JSON | Campos según el tipo de evento |
| `modelo` | texto o `null` | Modelo exacto (`qwen2.5:7b`) solo en eventos que usan un LLM |
| `equipo` | texto o `null` | Laptop que ejecutó la inferencia (nombre en Tailscale), no la EC2 |
| `created_at` | ISO 8601 UTC | Lo pone la base |

## Tipos de evento

| `evento` | Cuándo | Quién lo genera | `detalle` |
|---|---|---|---|
| `transicion` | Cada cambio de estado (ya implementado en B2) | Backend | `de`, `a`, y `motivo` o `motivo_desbloqueado` si aplica |
| `solicitud` | Al crear el caso | Backend | `texto` (la pregunta, sin modificar) |
| `llamada_llm` | Cada llamada a un modelo | Cliente LLM | `agente`, `cuantizacion`, `version_ollama`, `tokens_entrada`, `tokens_salida`, `latencia_ms`, `estado` (`ok`/`error`), `tipo_error` |
| `sql_generado` | El modelo propone un SQL | Agente Consulta | `sql` |
| `sql_rechazado` | El validador rechaza el SQL | Agente Consulta | `sql`, `motivo` |
| `sql_ejecutado` | El SQL corrió con `agent_ro` | Agente Consulta | `sql`, `vistas`, `filas`, `duracion_ms`, `truncado` (si se alcanzó el límite de filas) |
| `reglas_evaluadas` | Termina la Tool 1 | Agente Detección | `reglas`: lista de `{id, version, resultado, valor, umbral}`; `senales`: ids de las señales generadas |
| `normas_recuperadas` | Termina la Tool 2 | Agente Normativo | `normas`: lista de `{documento, articulo, version, fecha_vigencia, score}` por señal; `sin_soporte`: señales sin norma |
| `reporte_guardado` | Se guarda el reporte | Agente Reportes | `ruta`, `sha256`, `version` |
| `decision` | El auditor decide sobre una señal (B4) | Backend | `senal_id`, `decision` (`relevante`/`descartada`/`pendiente`), `comentario` |
| `error` | Fallo que no es de un LLM (BD, validación interna) | Backend | `tipo`, `mensaje` (sin datos sensibles) |

Agregar un tipo nuevo requiere actualizar esta tabla.

## Ejemplos reales

```json
{"caso_id": "6f1c…", "etapa": "recibido", "evento": "llamada_llm",
 "modelo": "qwen2.5:7b", "equipo": "laptop-alean",
 "detalle": {"agente": "consulta", "cuantizacion": "Q4_K_M", "version_ollama": "0.12.3",
             "tokens_entrada": 1840, "tokens_salida": 96, "latencia_ms": 3120.5,
             "estado": "ok", "tipo_error": null}}
```

```json
{"caso_id": "6f1c…", "etapa": "recibido", "evento": "sql_ejecutado",
 "modelo": null, "equipo": null,
 "detalle": {"sql": "SELECT … FROM clean.contratos WHERE proveedor_rfc = 'CBA010101AAA' AND anio = 2026 LIMIT 500",
             "vistas": ["clean.contratos"], "filas": 14, "duracion_ms": 212.0, "truncado": false}}
```

## Cómo se escribe y cómo se lee

- **Escribir (código):** `registrar_evento(caso_id, evento, detalle, modelo=None, equipo=None)` en el backend. La etapa se toma del estado actual del caso.
- **Leer (API):** `GET /casos/<id>/bitacora` devuelve los eventos del caso en orden cronológico:

  ```json
  {"eventos": [{"id": 1, "etapa": "recibido", "evento": "solicitud", "detalle": {...},
                "modelo": null, "equipo": null, "created_at": "2026-11-14T18:02:11Z"}]}
  ```

## Relación con `telemetry.llm_calls`

Las dos tablas registran las llamadas al modelo, con propósitos distintos:

- `audit.bitacora` (evento `llamada_llm`): evidencia **del caso**; la consulta el auditor.
- `telemetry.llm_calls`: métricas **de rendimiento** (GPU, tokens por segundo); la usan el benchmark y B9.

Para unirlas, B9 agregará `caso_id` a `telemetry.llm_calls`.

## Decisiones (14 nov 2026)

- **Equipo:** es la laptop que ejecuta el modelo, no la EC2. Se usará el nombre
  del agente registrado en `audit.agentes` (B7); mientras tanto, el host de
  `AGENT_BASE_URL` (por ejemplo `laptop-alean`). La telemetría actual guarda la
  máquina del cliente y se corregirá en B9.
- **Reintentos:** se registra un `llamada_llm` por cada intento, incluidos los
  fallidos, para que se vea cuántas veces falló el modelo.

## Implementación

- Función para el orquestador: `backend.casos.bitacora.llamar_llm(...)` llama al
  modelo y registra el evento; `repositorio.registrar_evento(...)` para los demás tipos.
- Validación en el backend (tipo, campos obligatorios, claves prohibidas) y en
  la base (`etl/sql/11_audit_bitacora.sql`: tipo válido y caso existente).
