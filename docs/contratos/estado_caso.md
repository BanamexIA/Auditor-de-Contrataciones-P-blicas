# Contrato 2: estado del caso

**Estado:** Borrador · **Usan:** Backend, Orquestación, Front-end · **Fuente:** ARQUITECTURA.md §4

## Estados

| Estado | Quién lo pone | Significado |
|---|---|---|
| `recibido` | Backend, al crear el caso | La solicitud del auditor quedó registrada |
| `consultado` | Orquestador | El Agente Consulta ejecutó un SQL validado con `agent_ro` |
| `detectado` | Orquestador | La Tool 1 evaluó las reglas de riesgo |
| `normado` | Orquestador | La Tool 2 asoció normas (o declaró que no hay soporte) |
| `reportado` | Orquestador | El reporte se guardó y su ruta y hash están en `audit.reportes` |
| `en_revision` | Front-end (auditor) | El auditor empezó a decidir sobre las señales |
| `cerrado` | Front-end (auditor) | El auditor terminó. Estado final |
| `bloqueado` | Orquestador o backend | Fallo, ambigüedad o agente apagado. Siempre con motivo, que el front muestra. Solo el auditor lo desbloquea |

Los nombres van en minúsculas y sin acentos, tal como aparecen aquí.

## Transiciones permitidas

```
recibido → consultado → detectado → normado → reportado → en_revision → cerrado
    │           │            │          │          │            │
    └───────────┴────────────┴──────────┴──────────┴────────────┴──▶ bloqueado
                                                                         │
                          (vuelve al estado en que se bloqueó) ◀─────────┘
```

1. **Avance:** solo al estado siguiente. No se puede saltar estados.
2. **Bloqueo:** desde cualquier estado excepto `cerrado`. El `motivo` es obligatorio y no puede estar vacío.
3. **Desbloqueo (lo hace el auditor):** desde `bloqueado` solo se puede volver al `estado_previo`. Al volver se borran `estado_previo` y `motivo_bloqueo`. El motivo queda en la bitácora.
4. `cerrado` no admite transiciones.

Cualquier otra transición se rechaza con `409` (ver [api_casos.md](api_casos.md)).

## Objeto caso

```json
{
  "id": "6f1c2a9e-3b7d-4c55-9a0e-2d8f41b7c013",
  "solicitud": "¿Qué contratos tiene la empresa Construcciones del Bajío SA de CV en 2026?",
  "estado": "bloqueado",
  "estado_previo": "consultado",
  "motivo_bloqueo": "El agente de inferencia no respondió en 60 s.",
  "creado_por": null,
  "created_at": "2026-11-11T18:02:11Z",
  "updated_at": "2026-11-11T18:03:40Z"
}
```

| Campo | Tipo | Regla |
|---|---|---|
| `id` | UUID en texto | Lo genera el backend. Es el mismo `caso_id` de la bitácora, los reportes y la telemetría |
| `solicitud` | texto | Obligatorio; se guarda sin modificar |
| `estado` | texto | Uno de los 8 estados |
| `estado_previo` | texto o `null` | Solo cuando `estado = bloqueado` |
| `motivo_bloqueo` | texto o `null` | Solo cuando `estado = bloqueado` |
| `creado_por` | texto o `null` | `null` hasta que exista autenticación |
| `created_at`, `updated_at` | ISO 8601 UTC | Los pone el backend |

## Evento de bitácora por transición

Cada transición, incluida la creación, escribe una fila en `audit.bitacora`
en la misma transacción que el cambio de estado:

```json
{
  "caso_id": "6f1c2a9e-3b7d-4c55-9a0e-2d8f41b7c013",
  "etapa": "consultado",
  "evento": "transicion",
  "detalle": {"de": "consultado", "a": "bloqueado", "motivo": "El agente de inferencia no respondió en 60 s."}
}
```

En la creación, `detalle` es `{"de": null, "a": "recibido"}`.

## Decisiones (11 nov 2026)

- **Desbloqueo:** lo hace el **auditor** desde el front, después de ver el
  motivo. El orquestador bloquea, pero no desbloquea por su cuenta.
- **Un caso bloqueado no se puede cerrar.** El front siempre muestra
  `motivo_bloqueo` mientras el caso esté en `bloqueado`, para que el auditor
  sepa por qué se detuvo.
