# AVANCE 1: Base de datos y prueba de modelos (nube vs local)

> Instrucciones para Claude Code. Lee este archivo completo antes de tocar nada.
> Trabaja **fase por fase**. Al terminar cada fase, ejecuta sus verificaciones, resume lo hecho y **espera confirmación** antes de pasar a la siguiente.

## 0. Contexto del proyecto

Agente de IA **auditor de contrataciones públicas** (proyecto Banamex, Tec de Monterrey). Genera consultas SQL sobre datos públicos para detectar señales de riesgo (adjudicaciones directas, concentración de proveedores, montos atípicos, coincidencias con el listado 69-B del SAT) y usa RAG para citar normatividad. Los resultados son **señales de riesgo, nunca determinaciones de fraude, corrupción o responsabilidad legal**.

**Stack acordado:** React + TypeScript + Vite (frontend), Python + Flask (backend), LangGraph (orquestación), Postgres + pgvector (datos y vectores), Ollama (modelos locales). El diseño usa 4 agentes: consulta, detección, normativo, reportes.

**Objetivo de este avance (se presenta la próxima semana):**
1. Base de datos funcionando con los datos reales cargados y su calidad documentada.
2. Comparación medida de modelos **locales (Ollama) vs nube** para generar SQL, para decidir cuál conviene.
3. Pruebas de rendimiento, telemetría (tokens y GPU) y opciones de despliegue en la nube, para elegir la **opción más eficiente**.

**Fuera de alcance en este avance:** agentes completos, RAG completo (solo el esqueleto de pgvector), frontend, LSTM.

### Arquitectura de referencia (`Arquitectura_de_IA.png`)

Flujo: Usuario → Front-end (React, TS, Vite) → Backend (Python, Flask) → Orchestrator (LangGraph) → 4 agentes en secuencia (**Consulta** genera el SQL → **Detección** de señales de riesgo → **Normativo** recupera normas por señal → **Reportes** como auditor de IA) → Reporte Final de vuelta al front-end. Cada agente tiene 5 tools (4 genéricas + `Tool SQL`, `Tool Análisis`, `Tool RAG`, `Tool Reporte`). Los agentes corren dentro del bloque "LLM Ollama + Modelo". Postgres (con ORM) se conecta al backend; la **BD vectorial pgvector** queda entre el RAG (Docs, Normas, Enterprise Data) y los agentes; la Ingesta ETL (limpieza, consulta, carga) toma las fuentes públicas. Todo vive dentro del bloque "Contenedores".

Qué toca este avance:

| Componente del diagrama | ¿Se toca en este avance? |
|---|---|
| Contenedores (Docker) | Sí (Fase 1) |
| Front-end React/TS/Vite | No |
| Backend Flask + ORM | Solo esqueleto con `/health` (Fase 1) |
| Orchestrator LangGraph | No |
| LLM Ollama + modelo | Sí (Fases 6, 6B y 7) |
| 4 agentes y sus tools | No se implementan; el benchmark prueba la capacidad del agente de Consulta (`Tool SQL`) |
| Postgres (datos) | Sí (Fases 2 a 5) |
| BD vectorial pgvector | Esqueleto y prueba (Fase 5B) |
| RAG (Docs, Normas, Enterprise Data) | Solo una muestra mínima de Normas |
| Ingesta ETL | Sí, para las fuentes tabulares; la ingesta de documentos para RAG queda para después |
| Telemetría (tokens y GPU) | Sí (Fase 6B); no aparece en el diagrama, pero fue pedida en el feedback |

## 1. Reglas de trabajo

- **Primero inspecciona el repo** (estructura, lenguajes, dependencias) y adapta este plan a lo que ya existe. No reestructures lo que ya funciona sin avisar.
- **No asumas columnas ni encodings.** Abre los CSV, lee los encabezados y una muestra antes de escribir el ETL.
- Los CSV originales **no se modifican ni se suben a git** (agrégalos a `.gitignore`; pueden ser muy grandes). Documenta dónde descargarlos en `data/README.md`.
- Ningún secreto en el repo. Usa `.env` (ignorado) y `.env.example` (versionado).
- Todo debe correr con comandos documentados. Si algo requiere un paso manual, anótalo en el README.
- Commits pequeños y con mensajes claros, uno por tarea lógica.
- Si hay una decisión ambigua, pregunta antes de decidir.

## 2. Estructura objetivo (adáptala si el repo ya tiene otra)

```
.
├── docker-compose.yml
├── .env.example
├── README.md
├── data/
│   ├── README.md          # de dónde bajar cada archivo
│   └── raw/               # ignorado por git
├── etl/
│   ├── sql/               # DDL: 01_schemas.sql, 02_raw.sql, 03_staging.sql, 04_clean.sql
│   ├── load_raw.py
│   ├── build_staging.py
│   ├── build_clean.py
│   └── quality_report.py
├── llm/
│   ├── base.py            # interfaz común de modelo
│   ├── ollama_client.py
│   └── cloud_client.py
├── backend/               # solo esqueleto Flask (/health) en este avance
├── telemetry/             # tokens, latencia y GPU/VRAM por llamada
├── rag/                   # esqueleto del esquema pgvector y prueba de embeddings
├── eval/
│   ├── golden_set.yaml
│   ├── run_benchmark.py
│   └── results/           # CSV/MD de resultados
└── docs/
    ├── diccionario_datos.md
    ├── reporte_calidad.md
    └── comparativa_modelos.md
```

---

## FASE 1: Entorno reproducible

**Tareas**
1. Crear `docker-compose.yml` con:
   - Servicio `db`: imagen `pgvector/pgvector` (versión de Postgres estable reciente), volumen persistente, puerto configurable por `.env`, healthcheck.
   - Servicio `ollama`: imagen oficial `ollama/ollama`, volumen para modelos. Dejar comentada la sección de GPU con instrucciones.
2. Crear `.env.example` con: usuario, contraseña, nombre de BD, host, puerto, URL de Ollama.
3. Script o comando para inicializar la BD ejecutando los `.sql` de `etl/sql/` en orden.
4. Habilitar la extensión `vector` en un script de init.
5. Crear **dos roles** en Postgres:
   - `etl_user`: puede escribir en `raw`, `staging`, `clean`.
   - `agent_ro`: **solo lectura** únicamente sobre `clean` y `rag` (y vistas). Este será el rol que use el agente.
6. Crear los esquemas `raw`, `staging`, `clean`, `rag`, `telemetry` y `audit` en el script de init. **Decisión por defecto:** una sola instancia de Postgres con pgvector, con los vectores en el esquema `rag` (el diagrama dibuja la BD y la BD vectorial como cajas separadas; si el equipo prefiere dos instancias, documenta el motivo).
7. Servicio `backend` mínimo (Dockerfile propio, Flask con `/health` y `/health/db`, conexión con SQLAlchemy) para respetar la arquitectura de contenedores. Sin lógica de negocio todavía. Ojo: la `Tool SQL` del agente no debe pasar por el ORM; usará una conexión directa con `agent_ro`.
8. Documentar en el README cómo levantar todo desde cero.

**Verificación**
- `docker compose up -d` deja `db` y `ollama` saludables.
- `SELECT extname FROM pg_extension;` muestra `vector`.
- Con `agent_ro`, un `INSERT` o `DROP` **falla** y un `SELECT` sobre `clean` funciona.
- `/health/db` responde OK desde el contenedor `backend`.

---

## FASE 2: Ingesta a la capa `raw`

**Archivos de entrada** (en `data/raw/`):
- `contratos_comprasmx_2026.csv`: contratos de Datos Abiertos ComprasMX (la exploración del equipo reporta 84,676 registros y 73 columnas, ~102 MB; las columnas observadas en el visor incluyen `codigo_contrato`, `codigo_expediente`, `proveedor`, `titulo_contrato`, `descripcion_contrato`, `contract_type`, `tipo_contratacion`, `tipo_expediente`, `importe`, `moneda`, `fecha_inicio`, `fecha_fin`; **verifica contra el archivo real**).
- `Listado_completo_69-B.csv`: listado del artículo 69-B del SAT (la exploración reporta 14,837 registros y 20 columnas, actualizado al 31 de agosto de 2026). Suele traer líneas de encabezado/notas antes de la tabla y encoding no UTF-8; **inspecciónalo**.

**Tareas**
1. Escribir un script que detecte encoding y delimitador de cada CSV y los reporte.
2. Crear tablas `raw.contratos_comprasmx` y `raw.listado_69b` con **todas las columnas como `TEXT`** (sin transformar nada) más columnas de trazabilidad: `_source_file`, `_loaded_at`, `_row_number`.
3. Cargar con `COPY` (o `psycopg` `copy`) por lotes; **no usar inserts fila por fila**. Mostrar progreso.
4. El script debe ser **idempotente**: volver a correrlo no duplica datos (truncar y recargar la tabla raw, o usar un identificador de carga).
5. Registrar conteos: filas en el archivo vs filas en la tabla.

**Verificación**
- Conteo en la BD = conteo de líneas de datos del CSV (explica cualquier diferencia).
- Una muestra de 10 filas aleatorias coincide con el archivo original.
- Tiempos de carga anotados en `docs/reporte_calidad.md`.

---

## FASE 3: Reporte de calidad de datos

**Tareas** (`etl/quality_report.py` → genera `docs/reporte_calidad.md`)
Para cada tabla raw, calcular y reportar:
- Total de filas, columnas y tamaño en disco.
- % de nulos/vacíos por columna.
- Cardinalidad por columna (valores distintos).
- Duplicados en `codigo_contrato` y `codigo_expediente`.
- `importe`: valores en cero, negativos, no numéricos, y los percentiles (p50, p90, p99, máximo).
- `moneda`: distribución de valores y variantes.
- Fechas: formatos distintos, no parseables, `fecha_fin < fecha_inicio`, fechas fuera de rango razonable.
- `proveedor`: variantes del mismo nombre (mayúsculas, acentos, puntuación, sufijos como S.A. de C.V.), vacíos.
- Valores categóricos (`tipo_contratacion`, `tipo_expediente`, etc.): lista de valores y frecuencias, para ver inconsistencias.
- Para 69-B: distribución de la columna de situación del contribuyente, RFC con formato inválido, duplicados.

Terminar el reporte con una sección **"Hallazgos y decisiones de limpieza propuestas"**: lista priorizada de problemas y qué se propone hacer con cada uno.

**Verificación:** el reporte se regenera con un solo comando y es legible por humanos.

---

## FASE 4: Capas `staging` y `clean`

**Tareas**
1. **`staging`**: convertir tipos (fechas a `DATE`, importes a `NUMERIC`, normalizar moneda), recortar espacios, estandarizar mayúsculas. Las filas que no se puedan convertir **no se descartan en silencio**: van a una tabla `staging.rechazados` con el motivo.
2. **`clean`**: tablas listas para consulta, con nombres de columna claros en español o inglés (decide uno y sé consistente). Mínimo:
   - `clean.contratos`
   - `clean.proveedores` (nombre normalizado + variantes)
   - `clean.listado_69b`
3. **Normalización de proveedor**: función/columna `proveedor_normalizado` (sin acentos, mayúsculas, sin puntuación, sufijos societarios estandarizados). Documentar las reglas exactas.
4. **Cruce proveedor ↔ 69-B**: crear `clean.coincidencias_69b` indicando el criterio del match (`rfc_exacto` si existe RFC en ambos lados, si no `nombre_normalizado_exacto`). **No usar fuzzy matching todavía.** Incluir una columna de `nivel_confianza` y un campo `requiere_revision_humana = true` para coincidencias solo por nombre.
5. **Índices** sobre las columnas de filtro y join más probables (proveedor, fechas, tipo de contratación, importe, RFC). Documentar cuáles y por qué.
6. Crear **vistas** simplificadas para el agente (por ejemplo `clean.v_contratos_agente`) con nombres claros y comentarios (`COMMENT ON`) en tablas y columnas. Estos comentarios alimentarán el prompt del agente de consulta.
7. Dar `GRANT SELECT` solo sobre `clean` al rol `agent_ro`.

**Verificación**
- Conteos: raw = staging + rechazados (explica la diferencia si existe).
- Ninguna fila de `clean.contratos` con importe nulo no justificado.
- El cruce con 69-B reporta cuántas coincidencias salen por RFC y cuántas por nombre.
- Medir y anotar el tiempo de 4 consultas representativas **antes y después** de crear los índices:
  1. Total de contratos y suma de importes por año.
  2. Top 20 proveedores por importe.
  3. Proporción de adjudicaciones directas por dependencia.
  4. Contratos de proveedores que aparecen en 69-B.

---

## FASE 5: Diccionario de datos

**Tarea:** generar `docs/diccionario_datos.md` con, por cada columna de `clean`: nombre, tipo, significado, origen (columna raw), reglas de limpieza aplicadas, riesgos de calidad y consideraciones de privacidad (por ejemplo, proveedores que son personas físicas). Donde el significado no sea evidente, marcar **"POR CONFIRMAR"** en lugar de inventarlo.

---

## FASE 5B: Esqueleto de la BD vectorial (pgvector)

El diagrama coloca la BD vectorial entre el RAG y los agentes. En este avance solo se valida que funcione y cuánto rinde; la ingesta completa de normas y documentos queda para el siguiente.

**Tareas**
1. Crear en el esquema `rag`: `rag.documentos` (id, fuente, tipo [`docs` | `normas` | `enterprise`], título, url o ruta, metadata JSONB, fecha de carga) y `rag.chunks` (id, documento_id, contenido, `embedding vector(N)`, metadata JSONB, posición).
2. Elegir un **modelo de embeddings disponible en Ollama** y leer su dimensión real (no asumirla); definir `N` con ese valor.
3. Cargar una **muestra pequeña de normatividad pública real** (5 a 10 fragmentos que el equipo descargue; no inventes texto normativo) y generar sus embeddings.
4. Crear un índice vectorial (HNSW o IVFFlat) y documentar por qué se eligió.
5. Probar 5 consultas de similitud, registrar la latencia y revisar a mano si los fragmentos recuperados son pertinentes.
6. Dar `GRANT SELECT` sobre `rag` a `agent_ro`.

**Verificación:** la consulta de similitud devuelve resultados ordenados por distancia, con tiempos anotados y la revisión manual registrada en `docs/comparativa_modelos.md` (sección de embeddings).

---

## FASE 6: Capa de modelos intercambiable

**Tareas**
1. `llm/base.py`: interfaz común, por ejemplo `generate(system: str, prompt: str, temperature: float = 0.0) -> LLMResponse`, donde `LLMResponse` incluye texto, tokens de entrada/salida (si el proveedor los entrega) y latencia.
2. `llm/ollama_client.py`: cliente para Ollama (URL y modelo por `.env`).
3. `llm/cloud_client.py`: cliente para un proveedor en nube (clave por `.env`; si no hay clave, el cliente debe fallar con un mensaje claro, no con un traceback críptico). Dejar el proveedor concreto configurable.
4. Selección del proveedor/modelo **solo por variable de entorno**, sin tocar código.
5. Pruebas mínimas (con mocks) de que la interfaz funciona.

---

## FASE 6B: Módulo de telemetría (tokens y GPU)

Fue pedido en el feedback de la arquitectura. Debe servir para el benchmark ahora y para cada agente después.

**Tareas**
1. Crear `telemetry/` con un decorador o context manager (`track_llm_call`) que envuelva cualquier llamada a un cliente de `llm/`.
2. Por llamada, registrar: marca de tiempo, agente (o `benchmark`), proveedor, modelo, tokens de entrada y salida, latencia total, tokens/s y, si hay streaming, tiempo al primer token. Para Ollama, usar los campos de conteo de tokens y duraciones que ya devuelve su API; para nube, los que reporte el proveedor.
3. Registrar métricas de hardware durante la llamada: utilización de GPU y VRAM usada (con `pynvml` o `nvidia-smi`), y CPU/RAM del proceso. Si no hay GPU NVIDIA (por ejemplo, una Mac con Apple Silicon), guardar `null`, documentarlo y **no fallar**.
4. Guardar en `telemetry.llm_calls` (Postgres) y permitir exportar a CSV.
5. Crear la tabla vacía `audit.bitacora` (pregunta, SQL generado, resultado, modelo, usuario, marca de tiempo) para la bitácora de auditoría del MVP. Sin lógica todavía.
6. Pruebas mínimas con un cliente falso.

**Verificación:** una llamada real a Ollama deja un registro en `telemetry.llm_calls` con tokens, latencia y VRAM (o `null` documentado).

---

## FASE 7: Benchmark de text-to-SQL

**Tareas**
1. `eval/golden_set.yaml`: **mínimo 20 preguntas** en lenguaje natural, cada una con `id`, `pregunta`, `dificultad` (simple/media/dificil), `sql_esperado` y `notas`. Cubrir: filtros simples, agregaciones, group by, joins con 69-B, fechas, montos y adjudicaciones directas. Generar el SQL esperado **y verificar que se ejecuta** contra la BD real.
2. `eval/run_benchmark.py`:
   - Construye el prompt con el esquema de las vistas del agente (tomando los `COMMENT ON` de la BD), reglas de seguridad y, opcionalmente, 2 o 3 ejemplos few-shot (que **no** estén en el golden set).
   - Recibe como parámetro la lista de modelos a probar.
   - Para cada pregunta y modelo: genera el SQL, lo **valida** (solo `SELECT`, tablas permitidas, `LIMIT`, timeout) y lo ejecuta con `agent_ro`.
   - Compara el **resultado** con el del SQL esperado (execution accuracy, no comparación de texto).
   - Repite cada pregunta 3 veces para medir consistencia.
   - Guarda resultados crudos en `eval/results/` (CSV) y un resumen.
3. Métricas por modelo: % SQL válido, % resultado correcto (global y por dificultad), % que respeta las reglas de seguridad, latencia (mediana y p95), tokens y tokens/s, VRAM pico y utilización de GPU (desde el módulo de telemetría), costo estimado por 1,000 consultas (nube) y consistencia entre repeticiones.
4. Modelos a probar (confirmar con el equipo según hardware y créditos): **al menos 2 locales** en Ollama (uno de ~7-8B y uno mayor si el hardware lo permite) y **al menos 1 en nube**. Verifica nombres de modelos y precios vigentes antes de correr; cambian seguido.

5. **Embeddings:** medir el modelo de embeddings elegido en la Fase 5B (latencia por fragmento, dimensión y calidad de recuperación en las 5 consultas de prueba). Si hay tiempo, comparar uno local con uno en nube.
6. **Pruebas de rendimiento:** para cada modelo local y para el de nube, correr el benchmark con 1, 2, 4 y 8 solicitudes concurrentes. Registrar throughput (tokens/s totales), latencia p50/p95, VRAM pico, errores y timeouts. Documentar la configuración de paralelismo de Ollama usada. Repetir con las 4 consultas representativas de la BD bajo concurrencia, para ver si Postgres es el cuello de botella.

**Verificación:** un solo comando corre el benchmark y produce una tabla comparativa reproducible. Registrar en los resultados el hardware usado (CPU, RAM, GPU) para que las latencias locales sean interpretables.

---

## FASE 8: Documento de comparativa

**Tarea:** generar `docs/comparativa_modelos.md` con:
1. Metodología (golden set, métricas, hardware, fecha).
2. Tabla de resultados por modelo.
3. Análisis: dónde falla cada modelo (tipos de error más comunes).
4. Comparación cualitativa nube vs local: costo, latencia, privacidad, reproducibilidad, dependencias de despliegue.
5. **Recomendación preliminar** con sus límites (qué no se midió).
6. **Eficiencia:** definir y calcular métricas para identificar la opción más eficiente, por ejemplo costo por consulta correcta, tokens/s por GB de VRAM y exactitud por segundo. Explicar la fórmula usada.
7. **Opciones de despliegue en la nube:** describir 2 o 3 alternativas (por ejemplo, una VM con GPU que aloje todo; servicios gestionados para backend y BD con inferencia por API; un esquema híbrido) y compararlas por costo mensual estimado, escalabilidad, latencia, operación y privacidad. Verifica precios vigentes, no inventes cifras y marca cuáles son estimaciones.
8. Riesgos y siguientes pasos.

No presentes conclusiones que los datos no respalden. Si la muestra es pequeña, dilo.

---

## Definición de "avance listo"

- [ ] `docker compose up` levanta Postgres+pgvector y Ollama desde cero con el README.
- [ ] Datos reales cargados en `raw` con conteos verificados.
- [ ] `docs/reporte_calidad.md` generado y con hallazgos priorizados.
- [ ] `staging` y `clean` construidos; rechazados documentados.
- [ ] Cruce con 69-B hecho, con criterio y nivel de confianza.
- [ ] Rol `agent_ro` de solo lectura verificado.
- [ ] `docs/diccionario_datos.md` con "POR CONFIRMAR" donde corresponda.
- [ ] Contenedor `backend` mínimo respondiendo `/health` y `/health/db`.
- [ ] Esquema `rag` con pgvector probado con una muestra real de normas y 5 consultas de similitud.
- [ ] Interfaz de modelos intercambiable (Ollama / nube) por variable de entorno.
- [ ] Módulo de telemetría registrando tokens, latencia y GPU/VRAM por llamada.
- [ ] Benchmark ejecutado con al menos 3 modelos, incluidas las pruebas de concurrencia, y resultados guardados.
- [ ] `docs/comparativa_modelos.md` con tabla, métricas de eficiencia, opciones de despliegue en la nube y recomendación preliminar.

## Cómo empezar

Primera instrucción sugerida para Claude Code:

> Lee `AVANCE_1_PLAN.md`. Inspecciona el repo y dime qué ya existe y qué ajustarías del plan. No cambies nada todavía. Después ejecuta la Fase 1.
