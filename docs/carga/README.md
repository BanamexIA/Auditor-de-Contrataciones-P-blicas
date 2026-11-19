# Prueba de carga (B10)

**Objetivo:** comprobar que el backend aguanta de 2 a 3 auditores trabajando a la
vez sin errores ni datos inconsistentes, y medir cuánto se alarga la inferencia
cuando varios casos usan el modelo al mismo tiempo.

## Cómo correrla

```bash
# Dentro del backend (en la EC2 o en local)
docker compose exec backend python -m backend.carga todo --usuarios 3 --repeticiones 10 --modelo qwen2.5:0.5b \
  --salida /app/data/reportes/carga.md
docker compose exec backend cat /app/data/reportes/carga.md
```

Con autenticación activa, agrega `--usuario <usuario>` y pasa la contraseña en
`CARGA_CONTRASENA` (`docker compose exec -e CARGA_CONTRASENA=… backend …`) o
escríbela cuando la pida (`exec -it`).

`todo` corre los cuatro escenarios; también se pueden correr uno por uno
(`api`, `carrera`, `reportes`, `llm`). Los casos que crea la prueba se quedan en
la BD con la solicitud "Carga …" o "Carrera …".

| Escenario | Qué hace | Aprueba si |
|---|---|---|
| `api` | Cada usuario repite el flujo del front: crear, ver, avanzar, bloquear, desbloquear, rastro, señales, telemetría, listar | 0 errores; se reporta p50/p95/máx por endpoint |
| `carrera` | Todos intentan la misma transición del mismo caso a la vez | Un 200, el resto 409, un solo evento en la bitácora |
| `reportes` | Todos guardan un reporte del mismo caso a la vez | Versiones 1..N, sin errores, todos los archivos con su hash |
| `llm` | Cada usuario hace una llamada al modelo en su propio caso, a la vez | Sin errores; se compara con una llamada sola |

## Resultados

| Fecha | Dónde | Resultado |
|---|---|---|
| 19 nov | Local (Docker Desktop) | `api`, `carrera`, `reportes`: OK — [local_2026-11-19.md](local_2026-11-19.md). `llm` no aplica (sin agentes registrados en local) |
| 19 nov | EC2 + S3 + 1 laptop por Tailscale (`qwen2.5:0.5b`) | Los 4 escenarios OK; 0 errores en 300 peticiones, p95 ≤ 54 ms; 3 llamadas LLM simultáneas sin degradación — [ec2_2026-11-19.md](ec2_2026-11-19.md) |
| | EC2 con `qwen2.5:7b` y 2+ laptops | Pendiente (antes de la entrega final) |

### Hallazgo y corrección (19 nov)

La primera corrida de `reportes` falló: con 3 guardados simultáneos del mismo
caso, dos calculaban la misma versión, el segundo **sobrescribía el archivo** del
primero y la BD quedaba con un hash que ya no coincidía (`ReporteCorrupto`).
Además, el almacén local usaba el mismo archivo temporal para todos.

Corrección: `RepositorioCasosSQL.reservar_reporte` bloquea la fila del caso
mientras se calcula la versión, se guarda el archivo y se registra; el temporal
del almacén local es único por escritura. Después: 5 de 5 corridas con 3
usuarios y una con 8, sin errores.

## Qué esperar en `llm`

Ollama atiende las peticiones de una laptop según `OLLAMA_NUM_PARALLEL`; si son
más que eso, se forman en cola. Con un solo agente encendido, la llamada más lenta
de 3 simultáneas puede tardar hasta ~3× la referencia. Con varias laptops
registradas, el registro de agentes reparte por usuario.
