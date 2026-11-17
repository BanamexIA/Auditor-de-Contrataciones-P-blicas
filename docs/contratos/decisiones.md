# Decisiones humanas sobre señales (HU-07)

**Estado:** Aprobado por Backend (14 nov) · **Usan:** Front-end, Agente Detección, Orquestación · **Tablas:** `audit.senales`, `audit.decisiones`

El sistema **nunca determina fraude**: marca señales que podrían requerir
revisión. El auditor decide sobre cada una si es relevante, si la descarta o si
la deja pendiente.

## Señal (forma mínima, mientras se congela el contrato 1)

El orquestador guarda en `audit.senales` cada señal que genera la Tool 1. El
backend controla `id`, `caso_id` y `tipo`; el contenido de `datos` lo define
el contrato 1 (Mario).

```json
{
  "id": "0b7e2f4c-…",
  "caso_id": "6f1c…",
  "tipo": "adjudicacion_directa_recurrente",
  "datos": {"criterio": "…", "valor": 0.64, "umbral": 0.30, "contratos": ["…"]},
  "created_at": "2026-11-14T18:05:00Z",
  "decision": null
}
```

`decision` es la decisión vigente (la más reciente) o `null` si aún no hay.

## Decisión

| Campo | Regla |
|---|---|
| `decision` | `relevante`, `descartada` o `pendiente` |
| `comentario` | Obligatorio y no vacío si la decisión es `descartada`; opcional en las demás |
| `decidido_por` | `null` hasta que exista autenticación |

## Reglas

1. **Cuándo:** se puede decidir sobre una señal en cualquier estado del caso excepto `cerrado`.
2. **Cambios:** el auditor puede cambiar su decisión. No se sobreescribe: cada decisión es una fila nueva en `audit.decisiones` y un evento `decision` en la bitácora. La vigente es la más reciente.
3. **Cierre:** un caso solo pasa a `cerrado` si **todas** sus señales tienen decisión. `pendiente` cuenta como decisión: el auditor puede cerrar dejando señales pendientes, pero de forma explícita.
4. Un caso sin señales se puede cerrar.

## API

### `GET /casos/<id>/senales`

**200** con las señales del caso y su decisión vigente:

```json
{"senales": [{"id": "0b7e…", "tipo": "adjudicacion_directa_recurrente", "datos": {…},
              "created_at": "…",
              "decision": {"decision": "descartada", "comentario": "Proveedor único justificado",
                           "decidido_por": null, "created_at": "…"}}]}
```

### `POST /casos/<id>/senales/<senal_id>/decision`

```json
{"decision": "descartada", "comentario": "Proveedor único justificado por patente."}
```

**201** con la decisión guardada.

| HTTP | `codigo` | Cuándo |
|---|---|---|
| 400 | `solicitud_invalida` | Decisión desconocida, o `descartada` sin comentario |
| 404 | `caso_no_encontrado` / `senal_no_encontrada` | No existe el caso, o la señal no es de ese caso |
| 409 | `caso_cerrado` | El caso ya está cerrado |

Al intentar cerrar con señales sin decisión, `POST /casos/<id>/transiciones`
responde **409** `transicion_invalida` con el número de señales faltantes.

## Evento de bitácora

```json
{"evento": "decision",
 "detalle": {"senal_id": "0b7e…", "decision": "descartada",
             "comentario": "Proveedor único justificado por patente.", "anterior": "pendiente"}}
```

`anterior` es la decisión previa sobre esa señal, o `null` si es la primera.
