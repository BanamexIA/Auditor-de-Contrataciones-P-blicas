# Contrato 3: tools del Agente Consulta

**Estado:** Borrador del Agente Consulta (16 nov) · **Usan:** Orquestación, Backend, Front-end · **Código:** `agents/consulta/`

El Agente Consulta convierte la solicitud del auditor en un SQL de solo lectura
validado, o explica por qué no puede: porque la pregunta es ambigua o porque las
fuentes no tienen ese dato. El modelo solo interpreta y propone; validar, revisar
la cobertura y ejecutar es código determinista que corre en el backend. La
laptop solo ejecuta el modelo y nunca recibe credenciales de la base.

## Las tools (4 + 1)

| # | Tool | Función | Tipo | Entrada | Salida | Errores |
|---|---|---|---|---|---|---|
| 1 | Describir esquema | `schema_context()` | Determinista | — | JSON con las 2 vistas aprobadas y el comentario de cada columna | `RuntimeError` si falta una vista |
| 2 | Generar consulta | `answer_question(...)` | LLM | Solicitud, aclaraciones, cliente del modelo, prompt de sistema, cobertura | Una respuesta de la sección siguiente | Las del modelo se reintentan una vez; los errores de conexión con el modelo se propagan |
| 3 | Revisar cobertura | `check_coverage(sql, coverage)` | Determinista | SQL validado y cobertura | `sin_datos` (motivo o `null`) y `supuestos` (lista) | — |
| 4 | Ejecutar consulta | `execute_read_only(sql)` | Determinista | SQL validado | Filas como objetos JSON, máximo 200 | Errores de PostgreSQL, incluido el límite de 60 s |
| +1 | Validar SQL | `validate_sql(sql)` | Determinista | SQL | SQL normalizado | `SQLValidationError` con un motivo legible |

- **Tools 1 y 4** viven hoy en `eval/run_benchmark.py`; se mueven a `agents/consulta/` en A3. Usan el rol `agent_ro`, una transacción de solo lectura y un límite de 60 s.
- **Tool 2** llama a las tools 3 y +1 por dentro. Sin `execute` no ejecuta SQL. Con `execute` (la tool 4) también ejecuta el SQL que pasó la cobertura; si PostgreSQL lo rechaza (columna inexistente, `GROUP BY` mal armado, fecha inválida…), le pasa al modelo el SQL y el error de la base en el mismo y único reintento. Los errores de conexión y el límite de 60 s no se reintentan: se propagan.
- **Si el SQL del modelo no trae `LIMIT`**, la tool 2 le agrega `LIMIT 200` antes de validarlo y lo anota en `supuestos`, en lugar de gastar el reintento. Un `LIMIT` que sí viene pero no es válido (mayor a 200, `ALL`, texto o `FETCH`) se sigue rechazando. La tool +1 no cambia: sigue exigiendo el `LIMIT`, así que la tool 4 y el benchmark se comportan igual.
- **La tool +1 revisa cada columna** contra la vista donde la busca la consulta, siguiendo alias y subconsultas. Una columna en la vista equivocada (por ejemplo `rfc_exacto` en `v_contratos_agente`) se rechaza antes de llegar a PostgreSQL, con un mensaje que indica en qué vista está y que hay que unirlas por `codigo_contrato`. La lista de columnas es `VIEW_COLUMNS` en `agents/consulta/validator.py`; una prueba la compara con `etl/sql/07_fase4b_transform.sql`, así que si T6 cambia las vistas hay que actualizarla.
- **Erratas de alias:** si el SQL usa `alias_columna` (por ejemplo `c_fuente`) y esa columna no se resuelve, pero `alias.columna` sí, la tool 2 la corrige antes de validar y no gasta el reintento. Un nombre que la misma consulta define (como `COUNT(*) AS c_total`) no se toca.
- **Valores de columnas categóricas:** la tool +1 rechaza un texto comparado con `fuente`, `tipo_procedimiento_norm`, `fecha_inicio_estado` o `nivel_confianza` que esa columna nunca tiene, y el mensaje lista sus valores (`CATEGORY_VALUES` en `agents/consulta/validator.py`). Si la vista gana un valor nuevo, hay que agregarlo ahí.
- **Desempate del orden:** si el SQL selecciona `codigo_contrato` y tiene `ORDER BY` y `LIMIT`, pero no ordena por `codigo_contrato`, la tool 2 lo agrega al final del `ORDER BY`. Sin eso, los contratos que empatan (por ejemplo, con la misma fecha de inicio) salen en cualquier orden y el `LIMIT` puede quedarse con otros cada vez que se corre la misma consulta. No cambia lo que se pregunta, así que no se anota en `supuestos`. No se aplica a consultas con agregados, salvo que agrupen por `codigo_contrato`.
- **Nombres de proveedor:** si el SQL compara `proveedor_normalizado` con un texto (`=`, `<>`, `IN`, `LIKE`, `ILIKE`), la tool 2 pasa ese texto a la forma normalizada del ETL (`agents/consulta/providers.py`) y lo anota en `supuestos`. Además, `=`, `<>` e `IN` buscan el nombre con y sin su tipo de sociedad al final (`S A DE C V`, `S DE R L DE C V` y los demás de `SUFFIX_TAILS`), porque el ETL los conserva en parte de los contratos (decisión 9 de `docs/vistas_estrella.md`); también se anota en `supuestos`.
- **Conceptos que las fuentes no registran** (cancelaciones, rescisiones, convenios modificatorios, pagos, sanciones e inhabilitaciones, penalizaciones y multas) **y datos que las vistas no tienen** (la situación del contribuyente en el 69-B): si la pregunta trata de uno, la tool 2 responde `sin_datos` con un motivo escrito por el código, sin importar lo que propuso el modelo. Las listas están en `agents/consulta/concepts.py` (`MISSING_CONCEPTS` y `VIEW_GAPS`); el prompt usa la primera.
- **Los supuestos sobre cobertura** (años completos o incompletos, periodos sin datos) los escribe solo la tool 3. La tool 2 descarta los que escriba el modelo sobre ese tema y conserva los de interpretación. Si el modelo responde `sin_datos` para años que sí tienen contratos, la tool 2 lo reintenta con lo que dice la cobertura (etapa `cobertura` en `intentos_fallidos`).
- **Tool 4** vuelve a validar el SQL antes de ejecutarlo.
- **La cobertura** se carga una vez al arrancar el backend con `COVERAGE_QUERY` (`agents/consulta/coverage.py`), que es la métrica M9 de `docs/capa_semantica.md`.
- **El prompt de sistema** se arma una vez al arrancar con `build_system_prompt(schema_context(), ejemplos)` de `agents/consulta/prompt.py`. El benchmark tiene otra función con el mismo nombre que solo pide SQL; no es la del agente.

## Entrada de la tool 2

| Campo | Tipo | Regla |
|---|---|---|
| `question` | texto | La `solicitud` del caso, sin modificar |
| `clarifications` | lista de pares `(pregunta, respuesta)` | Las aclaraciones anteriores del auditor, en orden. Vacía la primera vez |
| `client` | cliente LLM (`llm/`) | Apunta a la laptop del auditor (`AGENT_BASE_URL`) |
| `system_prompt` | texto | El armado al arrancar |
| `coverage` | `Coverage` | La cargada al arrancar |
| `execute` | función `sql → filas`, opcional | La tool 4 (o una envoltura que además registre en la bitácora). Si se pasa, la tool 2 ejecuta y reintenta ante un rechazo de PostgreSQL |

## Salida de la tool 2

Siempre es un objeto con `tipo`, `intentos` (1 o 2) e `intentos_fallidos`: una lista, vacía si el primer intento salió bien, con `intento`, `etapa` (`formato`, `validador`, `cobertura` o `base`), `error` y el `sql` que propuso el modelo, si lo hubo. Sirve para registrar en la bitácora un `sql_rechazado` por intento.

| `tipo` | Campos | Significa |
|---|---|---|
| `sql` | `sql`, `filtros`, `supuestos`; `filas` y `conteo` si se pasó `execute` | Hay un SQL validado y con cobertura, listo para la tool 4, o ya ejecutado |
| `aclaracion` | `pregunta`, `opciones` (2 o más) | La solicitud es ambigua; no se generó SQL |
| `sin_datos` | `motivo`; `sql_descartado` si el SQL lo detuvo la tool 3 o la revisión de conceptos | Las fuentes no tienen ese periodo, ese campo o ese concepto |
| `error` | `motivo`; `sql_rechazado` si el último SQL lo rechazó PostgreSQL | El modelo no dio una respuesta válida en 2 intentos |

```json
{"tipo": "sql", "intentos": 1,
 "sql": "SELECT COUNT(*) AS contratos FROM clean.v_contratos_agente WHERE fuente = 'historico' AND fecha_inicio >= CAST('2024-01-01' AS DATE) AND fecha_inicio < CAST('2025-01-01' AS DATE) LIMIT 1",
 "filtros": ["fuente: histórico", "inicio en 2024"],
 "supuestos": ["Cobertura incompleta en CompraNet histórico para 2024."]}
```

**`conteo` (HU-01, A6).** Con `execute`, la respuesta `sql` dice cuántos registros
la respaldan (`agents/consulta/counts.py`):

| Campo | Qué es |
|---|---|
| `filas` | Las filas que devolvió la consulta |
| `filas_totales` | Las que habría sin el `LIMIT`. Solo se consulta a la base si las filas llegaron al `LIMIT` |
| `truncado` | `true` si el `LIMIT` cortó el resultado; entonces también se agrega un aviso en `supuestos` ("El resultado se cortó: se muestran 200 de 784 filas por el LIMIT.") |
| `registros` | Cuántos registros de las vistas resume la respuesta, antes del `LIMIT`. En una consulta con agregados (`COUNT`, `SUM`, `GROUP BY`) son los que entran a los grupos; en una lista, cada fila es un registro |

Las consultas de conteo salen del mismo SQL y pasan por el validador. Si fallan
(por ejemplo, por el límite de 60 s), los campos quedan en `null` y la respuesta
sigue. `count_records=False` lo apaga; el medidor lo apaga para que el tiempo
por pregunta siga siendo comparable con A4 y A5.

```json
{"tipo": "sql", "intentos": 1,
 "sql": "SELECT institucion, COUNT(*) AS contratos FROM clean.v_contratos_agente WHERE fuente = 'comprasmx' GROUP BY institucion ORDER BY contratos DESC, institucion LIMIT 200",
 "supuestos": ["El resultado se cortó: se muestran 200 de 784 filas por el LIMIT."],
 "conteo": {"filas": 200, "filas_totales": 784, "truncado": true, "registros": 84676}}
```

```json
{"tipo": "aclaracion", "intentos": 1,
 "pregunta": "¿Cómo quieres medir a la institución que más contrata?",
 "opciones": ["Por número de contratos en ComprasMX 2026", "Por importe registrado en ComprasMX 2026, por moneda"]}
```

```json
{"tipo": "sin_datos", "intentos": 1,
 "motivo": "No hay contratos con inicio en 2025. Cobertura disponible: ComprasMX: 2026; CompraNet histórico: 2010–2024.",
 "sql_descartado": "SELECT COUNT(*) AS contratos FROM clean.v_contratos_agente WHERE fecha_inicio >= CAST('2025-01-01' AS DATE) AND fecha_inicio < CAST('2026-01-01' AS DATE) LIMIT 1"}
```

## Qué hace el orquestador con cada salida

Usa los estados de [estado_caso.md](estado_caso.md).

| Salida | Siguiente paso | Estado del caso |
|---|---|---|
| `sql` | Ejecutar con la tool 4 (o usar `filas` si se pasó `execute`) y pasar las filas, el SQL, los filtros y los supuestos al Agente 2 | `recibido` → `consultado` |
| `aclaracion` | Bloquear con motivo `Aclaración: <pregunta> Opciones: <a>; <b>` | `recibido` → `bloqueado` |
| `sin_datos` | **Propuesta:** no bloquear; avanzar con cero filas y el motivo, para que el reporte declare la falta de datos (Escenario 5) | `recibido` → `consultado` |
| `error` | Bloquear con el `motivo` | `recibido` → `bloqueado` |
| Excepción de conexión con el modelo | Bloquear por agente apagado (O5) | `recibido` → `bloqueado` |
| Error de la tool 4 | Registrar el evento `error` y bloquear. Con `execute`, solo llegan aquí los errores que no se reintentan (conexión, límite de 60 s) | `recibido` → `bloqueado` |

**Después de una aclaración:** el auditor responde y desbloquea; el caso vuelve a
`recibido`, y el orquestador llama otra vez a la tool 2 con la misma solicitud y
la nueva pareja `(pregunta, respuesta)` agregada a `clarifications`.

## Eventos de bitácora

Según [evento_bitacora.md](evento_bitacora.md). El Agente Consulta no escribe en
la tabla: entrega los datos y el backend registra.

| Momento | Evento | `detalle` |
|---|---|---|
| Cada intento con el modelo | `llamada_llm` | Lo registra `backend.casos.bitacora.llamar_llm` |
| El modelo propone un SQL | `sql_generado` | `sql` |
| El validador lo rechaza | `sql_rechazado` | `sql`, `motivo` |
| La tool 3 lo descarta por falta de datos | `sql_rechazado` | `sql`, `motivo` (el de `sin_datos`) |
| La tool 4 lo ejecuta | `sql_ejecutado` | `sql`, `vistas`, `filas`, `duracion_ms`, `truncado` (de `conteo`: `true` si el `LIMIT` cortó el resultado) |
| Aclaración o error | `transicion` a `bloqueado` | El `motivo` del bloqueo |

## Lo que falta en el código (A3)

1. Mover `schema_context` y `execute_read_only` de `eval/run_benchmark.py` a `agents/consulta/`.
2. Que la tool 2 reciba una función para registrar eventos, o devuelva el SQL y el error de cada intento, para generar `sql_generado` y `sql_rechazado` por intento.
3. Que la tool 2 llame al modelo a través de `llamar_llm`, para registrar cada intento.
4. Pasar `AGENT_RO_USER` y `AGENT_RO_PASSWORD` al contenedor del backend en `docker-compose.yml`.
5. ~~Devolver, junto con las filas, el conteo (HU-01)~~: hecho el 2026-11-21 (`conteo`). Falta avisar de empates en el corte de un ranking (por ejemplo, si el lugar 10 y el 11 tienen el mismo número de contratos), pidiendo un registro más del `LIMIT`.

## Decisiones pendientes

| # | Decisión | Propuesta | Con quién |
|---|---|---|---|
| 1 | ¿`sin_datos` bloquea el caso o avanza? | Avanzar con cero filas y el motivo | Orquestación, Reportes |
| 2 | ¿Dónde se guarda la respuesta del auditor a una aclaración? | Un campo `respuesta_aclaracion` en el `POST /casos/<id>/transiciones` que desbloquea el caso; el orquestador lo agrega a `clarifications` | Backend, Front-end |
| 3 | ¿Un `sin_datos` que el modelo responde sin SQL necesita un evento propio? | Agregar el tipo `sin_datos` (`motivo`) al contrato 5 | Backend |
| 4 | El ejemplo de `sql_ejecutado` en el contrato 5 usa `clean.contratos` y `LIMIT 500`, que el validador rechaza | Cambiar el ejemplo a una vista aprobada con `LIMIT` de 200 o menos | Backend |
