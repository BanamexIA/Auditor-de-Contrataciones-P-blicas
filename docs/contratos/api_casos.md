# Contrato 6 (parte): API de casos y estados

**Estado:** Borrador · **Usan:** Front-end, Orquestación · **Base:** `http://<backend>:5000`

Todo el cuerpo va en JSON (`Content-Type: application/json`). El objeto
`caso` está definido en [estado_caso.md](estado_caso.md). Autenticación y
roles: pendientes; por ahora no se exigen.

## `POST /casos`: crear un caso

```json
{"solicitud": "¿Qué contratos tiene la empresa Construcciones del Bajío SA de CV en 2026?"}
```

**201** con el `caso` en estado `recibido` y el encabezado `Location: /casos/<id>`.

## `GET /casos/<id>`: consultar un caso

**200** con el `caso`. **404** si no existe.

## `GET /casos`: listar casos

Parámetros opcionales: `estado` (uno de los 8 estados) y `limite` (1 a 100, por defecto 50).
Orden: el más reciente primero.

```json
{"casos": [ { "...": "caso" } ]}
```

## `POST /casos/<id>/transiciones`: cambiar el estado

```json
{"estado": "bloqueado", "motivo": "El agente de inferencia no respondió en 60 s."}
```

`motivo` solo es obligatorio para `bloqueado`. **200** con el `caso` actualizado.

## Errores

Todos los errores tienen la misma forma:

```json
{"error": {"codigo": "transicion_invalida", "mensaje": "No se puede pasar de 'recibido' a 'normado'; el siguiente estado es 'consultado'."}}
```

| HTTP | `codigo` | Cuándo |
|---|---|---|
| 400 | `solicitud_invalida` | Falta un campo, el JSON es inválido o un parámetro está fuera de rango |
| 404 | `caso_no_encontrado` | El `id` no existe |
| 409 | `transicion_invalida` | La transición no está permitida, o se bloquea sin motivo |
| 503 | `bd_no_disponible` | La base de datos no responde |

## Ejemplo de flujo con bloqueo

```
POST /casos                       → recibido
POST /casos/<id>/transiciones     {"estado": "consultado"}                 → consultado
POST /casos/<id>/transiciones     {"estado": "bloqueado", "motivo": "..."} → bloqueado
POST /casos/<id>/transiciones     {"estado": "consultado"}                 → consultado (el auditor desbloquea)
```

Mientras el caso esté en `bloqueado`, el front muestra `motivo_bloqueo`. Un
caso bloqueado no puede pasar a `cerrado`: primero se desbloquea.
