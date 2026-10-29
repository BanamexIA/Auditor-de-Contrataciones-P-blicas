# AVANCE 1 (v2): Base de datos y prueba de modelos

> Instrucciones para Claude Code. Lee este archivo completo y también `ARQUITECTURA.md` antes de tocar nada.
> Trabaja **fase por fase**. Al terminar cada fase, ejecuta sus verificaciones, resume lo hecho y **espera confirmación** antes de pasar a la siguiente.
> Esta versión reemplaza a la anterior: refleja la arquitectura v2 y el estado real del proyecto.

## 0. Contexto

Agente de IA **auditor de contrataciones públicas** (proyecto Banamex, Tec de Monterrey). Consulta datos públicos con SQL de solo lectura, detecta señales de riesgo, recupera normatividad con RAG y genera reportes con evidencia, fuentes y limitaciones. Sus resultados son **señales para revisión humana, nunca determinaciones de fraude, corrupción o responsabilidad legal**.

**Arquitectura vigente (detalle en `ARQUITECTURA.md`):**
- **Nube (EC2, Docker):** front-end (React, TS, Vite), backend (Flask) con el **orquestador LangGraph dentro**, y Postgres + pgvector.
- **Local (laptop de cada auditor):** **solo Ollama** (inferencia y embeddings), conectado por **Tailscale**. La laptop no tiene lógica de negocio, tools ni acceso a la BD.
- **S3** (privado) guarda los reportes finales; la BD guarda la ruta y el hash.
- **3 agentes**, con lógica en el backend y flujo de orden fijo: **Consulta** (Tool SQL + validador), **Detección + Normativo** (Tool 1 detección determinista, Tool 2 normativo con RAG) y **Reportes** (Tool Reporte).
- **Docker solo contiene backend, front y BD.** Ollama NO va en el compose.
- El LLM interpreta, selecciona fragmentos y redacta; **no calcula montos ni define umbrales**.

**Objetivo de este avance (se presenta pronto):**
1. Base de datos funcionando con las 3 fuentes cargadas y su calidad documentada.
2. Pruebas de modelos **locales** con datos medidos (la decisión de que los agentes corran en local ya está tomada: el benchmark debe **justificarla** y elegir el modelo, usando un modelo en nube solo como referencia).
3. Pruebas de rendimiento, telemetría (tokens y GPU) y un diseño de despliegue.

**Fuera de alcance en este avance:** implementar los agentes completos, el RAG completo (solo el esqueleto de pgvector), el front-end, la LSTM y el despliegue real en AWS (solo su diseño).

## 1. Reglas de trabajo

- **Inspecciona antes de cambiar.** No asumas columnas, nombres ni encodings; verifícalos contra la BD y los archivos.
- Los CSV originales **no se modifican ni se suben a git** (`data/raw/` ignorado; `data/README.md` documenta URL, fecha y `sha256`).
- **Todo cambio de esquema va en archivos `.sql` numerados de `etl/sql/`**, nunca aplicado a mano en la BD. Python solo los ejecuta en orden, dentro de una transacción, con conteos antes y después.
- **Cada tabla que se recree** debe recuperar sus `COMMENT ON` y el `GRANT SELECT` a `agent_ro`. El proceso debe ser **idempotente** (correrlo dos veces da el mismo resultado).
- Sin secretos en el repo: `.env` ignorado y `.env.example` versionado.
- Nada de filas descartadas en silencio: lo que no entre a `clean` queda en una tabla de excluidos con motivo (`raw = clean + excluidos`).
- Los criterios de negocio (clasificación de etiquetas, umbrales) quedan marcados **"pendiente de confirmar"** con el socio formador.
- Commits pequeños y con mensajes claros. Si algo es ambiguo, pregunta.
- En Windows el punto de entrada es `python etl/run_etl.py` (no asumas `make`).

## 2. Estado de las fases

| Fase | Contenido | Estado |
|---|---|---|
| 1 | Entorno Docker (db + backend) | Hecha; **ajuste pendiente (Fase 1B)** |
| 2 | Carga a `raw` (3 fuentes) | Hecha |
| 3 | Reporte de calidad | Hecha (regenerar tras la 4B) |
| 4 | `staging` y `clean`, cruce con 69-B | Hecha (Fase 4B ejecutada con fecha de descarga 2026-10-16; 2,441,285 contratos, 14,837 filas 69-B y cero rechazos) |
| 5 | Diccionario de datos | Hecha: siete tablas y 76 columnas verificadas; comentarios, permisos y consultas de ejemplo comprobados |
| 5B | Esqueleto pgvector | En curso: muestra oficial de seis fragmentos cargada y cinco consultas evaluadas; filtro temporal y citas probados; falta ampliar el corpus y revisión jurídica |
| 6 | Cliente de modelos | Hecha: interfaz común, cliente Ollama, referencia cloud configurable y pruebas con mocks |
| 6B | Telemetría | Pendiente |
| 7 | Benchmark | Pendiente |
| 8 | Comparativa y decisión | Pendiente |
| 9 | Diseño de despliegue (documento) | Pendiente |

**Baseline previo a la Fase 4B:** `raw.contratos_comprasmx` 84,676 · `raw.compranet_historico` 2,356,609 · `raw.listado_69b` 14,837 · `clean.contratos` 2,432,330 · `clean.proveedores` 298,131 · `clean.listado_69b` 14,837 · `clean.coincidencias_69b` 817. El clean histórico previo omitía 8,955 filas rechazadas por fechas; esos conteos no son el resultado esperado después de aplicar la Fase 4B.

## 3. Estructura objetivo del repo (adáptala a lo que ya existe)

```
.
├── docker-compose.yml        # db, backend, (front cuando exista). SIN ollama
├── .env.example
├── README.md
├── agent_host/               # guía y utilidades para la laptop del auditor
│   ├── README.md             # instalar Ollama + Tailscale, OLLAMA_HOST, firewall
│   └── check_agent.py        # prueba de conexión, tokens/s y GPU/VRAM
├── backend/                  # Flask (+ orquestador a futuro)
├── data/  (README.md; raw/ ignorado)
├── etl/
│   ├── sql/                  # DDL y transformaciones numeradas
│   ├── seeds/                # map_tipo_procedimiento.csv
│   ├── run_etl.py            # punto de entrada único
│   └── quality_report.py
├── llm/                      # base.py, ollama_client.py, cloud_client.py (solo referencia)
├── telemetry/
├── rag/
├── eval/                     # golden_set.yaml, run_benchmark.py, results/
├── scripts/                  # check_comentarios.sql, check_calidad.sql, check_conteos.sql
├── tests/
└── docs/                     # arquitectura, diccionario, calidad, comparativa, despliegue
```

---

## FASE 1B: Ajustar el entorno a la arquitectura v2

**Tareas**
1. Quitar el servicio `ollama` del `docker-compose.yml` (y su `profile`). Quitar cualquier `depends_on` hacia él.
2. En el backend, la URL del modelo se lee de la variable `AGENT_BASE_URL` (por defecto `http://host.docker.internal:11434`, que en desarrollo apunta al Ollama de Windows). Mantén `extra_hosts: ["host.docker.internal:host-gateway"]`. Actualiza `.env.example`.
3. Crear `agent_host/README.md` con la guía para la laptop: instalar Ollama, descargar el modelo, instalar Tailscale, cambiar `OLLAMA_HOST` y **limitar el acceso con el firewall a la interfaz de Tailscale** (Ollama no tiene autenticación).
4. Crear `agent_host/check_agent.py`: llama a `/api/tags`, hace una generación corta y reporta tokens/s, latencia y (si hay GPU NVIDIA) uso de VRAM. Si no hay GPU, imprime `null` y no falla.
5. Crear (solo DDL) las tablas `audit.bitacora` y `audit.reportes` (`caso_id`, `s3_uri`, `sha256`, `version`, `modelo`, `equipo`, `created_at`) y un registro de agentes `audit.agentes` (`usuario`, `nombre_tailnet`, `modelo`, `estado`, `ultima_verificacion`). Sin lógica todavía.
6. Actualizar el README.

**Verificación**
- `docker compose up -d --build` levanta solo `db` y `backend`, sin errores de puerto.
- `/health` y `/health/db` responden 200.
- Desde el backend: `docker compose exec backend python -c "import urllib.request,os; print(urllib.request.urlopen(os.environ['AGENT_BASE_URL']+'/api/tags', timeout=5).read()[:200])"` devuelve el JSON de Ollama.
- `python agent_host/check_agent.py` funciona en la laptop.

---

## FASE 4B: Cerrar la limpieza de `clean.contratos`

Problemas detectados con datos reales:
- `clean.contratos` mezcla dos fuentes. **ComprasMX trae institución, ramo, unidad compradora, ley y fundamento de excepción; el histórico NO** (solo 16 columnas útiles, sin dependencia ni RFC).
- `tipo_expediente` está **vacío para las 84,676 filas de ComprasMX** (el dato equivalente está en `tipo_procedimiento`).
- El histórico tiene 56 etiquetas distintas de procedimiento con prefijos de versión y numeración (`V20151220 12. Adjudicación Directa …`).
- Antes de la Fase 4B, 8,955 filas del histórico estaban en `staging.rechazados`: 3,648 por fecha fin, 17 por fecha inicio y 5,290 por ambas; los rechazos observados corresponden a fechas vacías/no parseables, no a duplicados exactos. La consulta de duplicados exactos del histórico encontró cero grupos.
- Hay fechas imposibles (1900-01-11 y otras anteriores a 2010) y no hay datos con fecha de inicio en 2025; 2023 y 2024 tienen cobertura parcial.

**Tareas** (todo en SQL dentro de `etl/sql/`, ejecutado por `etl/run_etl.py`)
1. Habilitar la extensión `unaccent` (en el script de init, como superusuario).
2. Crear `clean.map_tipo_procedimiento` cargada desde `etl/seeds/map_tipo_procedimiento.csv`. Aplicar la regla de **menor prioridad cuyo prefijo coincida con el inicio** de la etiqueta normalizada:
   ```sql
   upper(unaccent(regexp_replace(btrim(etiqueta), '^(V[0-9]{8}\s+)?([0-9]+\.\s*)?', '')))
   ```
   Vacío y `Sin dato` → `sin_dato`. Sin regla → `otro` con la marca `sin_regla`, y lista esas etiquetas al final del proceso. No uses `split_part` ni `LIKE '%…%'` para clasificar.
3. Contenido inicial del seed (todo `pendiente` de confirmar con el socio formador):
   ```csv
   fuente,prefijo,tipo_normalizado,prioridad,estado
   comprasmx,ADJUDICACION DIRECTA,adjudicacion_directa,10,pendiente
   comprasmx,INVITACION A CUANDO MENOS 3,invitacion_tres_personas,20,pendiente
   comprasmx,LICITACION PUBLICA,licitacion_publica,30,pendiente
   comprasmx,PROCEDIMIENTO DE ASIGNACION DERIVADO DE UN ACUERDO MARCO,otro,40,pendiente
   comprasmx,ENTRE ENTES PUBLICOS,otro,50,pendiente
   historico,ADJUDICACION DIRECTA,adjudicacion_directa,10,pendiente
   historico,INVITACION A CUANDO MENOS TRES,invitacion_tres_personas,20,pendiente
   historico,LICITACION PUBLICA,licitacion_publica,30,pendiente
   historico,PROYECTO DE CONVOCATORIA,otro,40,pendiente
   historico,PROYECTO DE ASOCIACION PUBLICO PRIVADA,otro,40,pendiente
   historico,CONTRATOS ENTRE ENTES PUBLICOS,otro,40,pendiente
   historico,VENTA BIENES NO UTILES,otro,40,pendiente
   historico,REPORTE DE OTRAS CONTRATACIONES,otro,40,pendiente
   ```
4. Conservar `tipo_expediente` y `tipo_procedimiento` originales y agregar `tipo_procedimiento_norm` y `ley` (en el histórico, extraída del final de la etiqueta: LAASSP, LOPSRM, LAPP o estatal; en ComprasMX, de la columna `ley`). Las reglas iniciales quedan en estado `pendiente`; los reportes deben llamarlas “clasificación preliminar”.
5. Agregar a `clean.contratos`, desde `raw.contratos_comprasmx`: `institucion`, `clave_institucion`, `siglas_de_la_institucion`, `tipo_de_institucion`, `clave_ramo`, `descripcion_ramo`, `clave_de_la_uc`, `nombre_de_la_uc`, `numero_de_procedimiento`, `caracter_del_procedimiento`, `articulo_de_excepcion`, `descripcion_excepcion`. **Nulas para el histórico**, y cada `COMMENT ON` debe decirlo.
6. Agregar `clean.config_calidad` con límites inclusivos de inicio 2010-01-01 y 2026-12-31. `run_etl.py` exige la fecha real de descarga; `fecha_inicio_estado` toma `valida`, `nula`, `no_parseable` o `fuera_de_rango`; `fecha_inicio_valida` es verdadera solo dentro del rango. Agregar `fecha_inicio_futura` como bandera informativa (no invalida) y `fecha_fin_antes_inicio`. No borres filas por sus fechas.
7. Las 8,955 filas con fechas vacías/no parseables vuelven a `clean`; no se excluyen por fechas. La tabla de excluidos se reserva para filas que no puedan representarse, como filas vacías o duplicados exactos. Debe cumplirse `raw = clean + excluidos` por fuente y por tipo normalizado. No excluir por duplicidad de `codigo_contrato` sin evidencia de duplicado exacto.
8. Crear la vista `clean.v_cobertura_fuentes` (año, fuente, filas) y documentar que no hay datos de 2025 y que 2023 y 2024 son parciales.
9. Recrear las tablas con sus `COMMENT ON` y `GRANT SELECT` a `agent_ro`. Actualizar el diccionario (`project_code`, `work_category_id` y `ff_fecha_inicio/fin` como "POR CONFIRMAR").
10. Crear las vistas aprobadas para el agente (`clean.v_contratos_agente`, `clean.v_coincidencias_69b_agente`), con comentarios en vistas y columnas.

**Verificación**
- **Conteos esperados de ComprasMX (exactos, derivados de `raw`):** `adjudicacion_directa` 58,868 · `invitacion_tres_personas` 5,402 · `licitacion_publica` 17,307 · `otro` 49 · `sin_dato` 3,050 · total **84,676**.
- Los conteos históricos anteriores (que sumaban 2,347,654) corresponden al clean previo y no son un esperado tras recuperar las 8,955 filas. Calcula un `GROUP BY` independiente sobre `raw` y valida `raw_tipo = clean_tipo + excluidos_tipo` con la misma clasificación.
- Cero etiquetas `sin_regla` (o una lista explicada).
- `raw = clean + excluidos` para cada fuente.
- `check_comentarios.sql` devuelve cero filas, `agent_ro` lee las tablas nuevas y el proceso se puede repetir con el mismo resultado.
- Regenerar `docs/reporte_calidad.md` por fuente.

---

## FASE 5: Verificar el diccionario de datos

**Tareas**
1. `scripts/verify_fase5.py`: compara las columnas de `clean` (desde `information_schema`) con `docs/diccionario_datos.md`, por tabla, e incluye los tipos. Termina con código distinto de 0 si hay discrepancias.
2. Cada columna del diccionario indica: significado, **fuente(s) de origen** (ComprasMX, histórico o ambas), columna original, regla de limpieza, riesgo de calidad y marca de datos personales. Los significados dudosos se marcan **"POR CONFIRMAR"**; no inventes ninguno.
3. Datos personales (nombre del proveedor persona física, RFC) marcados, y vistas del agente con los campos mínimos.
4. Generar la lista de preguntas para el socio formador a partir de los "POR CONFIRMAR".

**Verificación**
- `check_comentarios.sql`: cero filas (columnas, tablas y vistas de `clean`).
- `verify_fase5.py` sin discrepancias.
- Muestreo manual de 10 columnas contra datos reales.
- Prueba funcional: con solo el diccionario se puede escribir el SQL de 5 preguntas del golden set.

---

## FASE 5B: Esqueleto de la BD vectorial

**Tareas**
1. Esquema `rag`: `rag.documentos` (fuente, tipo [`docs` | `normas` | `enterprise`], ley, versión, fecha de publicación en el DOF, fecha de entrada en vigor, fecha de abrogación, URL, `sha256`, fecha de carga) y `rag.chunks` (documento, contenido, `embedding vector(N)`, ruta jerárquica ley-título-capítulo-artículo, metadata JSONB).
2. Elegir un **modelo de embeddings de Ollama** y leer su dimensión real; ese mismo modelo se usará para indexar y para consultar (los embeddings se generan en la laptop).
3. Cargar **5 a 10 fragmentos reales** de normatividad pública descargados de fuentes oficiales (Cámara de Diputados o DOF), incluyendo artículos de la LAASSP vigente y de la abrogada, para probar el filtro por vigencia. **No inventes ni resumas el texto normativo.**
4. Índice vectorial (HNSW o IVFFlat) y justificación.
5. 5 consultas de similitud con latencia y revisión manual de pertinencia. El filtro por vigencia compara la fecha del contrato con las fechas de entrada en vigor y abrogación.
6. `GRANT SELECT` sobre `rag` a `agent_ro`.

**Verificación:** resultados ordenados por distancia, tiempos anotados y revisión registrada en `docs/comparativa_modelos.md` (sección de embeddings).

---

## FASE 6: Cliente de modelos

**Tareas**
1. `llm/base.py`: interfaz común `generate(system, prompt, temperature=0.0) -> LLMResponse` (texto, tokens de entrada y salida, latencia).
2. `llm/ollama_client.py`: usa `AGENT_BASE_URL` (en producción será el nombre del equipo en la red de Tailscale). Modelo por variable de entorno.
3. `llm/cloud_client.py`: **solo referencia de comparación** en el benchmark, con clave por `.env`; sin clave, falla con un mensaje claro.
4. Pruebas con mocks.

---

## FASE 6B: Telemetría (tokens y GPU)

**Tareas**
1. Decorador `track_llm_call` que envuelve cualquier llamada de `llm/`. Registra marca de tiempo, agente, proveedor, modelo, tokens de entrada y salida, latencia, tokens/s y tiempo al primer token. Para Ollama usa los campos de conteo y duración que devuelve su API.
2. Guardar en `telemetry.llm_calls` y permitir exportar a CSV.
3. **Las métricas de GPU y VRAM solo se pueden leer en la máquina que ejecuta el modelo.** Con Ollama en la laptop, el backend no las ve. Por eso las recoge `agent_host/check_agent.py` y el benchmark se **ejecuta en esa máquina**. En producción, el backend solo registra tokens y latencia. Si no hay GPU NVIDIA, guarda `null` y no falla.
4. La bitácora registra el modelo exacto, su cuantización, la versión de Ollama y el equipo en cada ejecución.
5. Pruebas con un cliente falso.

---

## FASE 7: Benchmark de text-to-SQL y rendimiento

**Tareas**
1. `eval/golden_set.yaml`: **20 o más preguntas** (`id`, `pregunta`, `dificultad`, `sql_esperado`, `notas`), cubriendo filtros, agregaciones, joins con 69-B, fechas, montos y adjudicaciones directas. Considera que **dependencia solo existe en ComprasMX 2026**; incluye casos de "sin datos para ese periodo" (2025) y de información inexistente. Verifica que cada `sql_esperado` se ejecute.
2. `eval/run_benchmark.py`: arma el prompt con el esquema de las **vistas del agente** (usando los `COMMENT ON`), reglas de seguridad y pocos ejemplos que no estén en el golden set; recibe la lista de modelos; valida el SQL (solo `SELECT`, tablas permitidas, `LIMIT`, tiempo máximo) y lo ejecuta con `agent_ro`; compara **resultados** (no texto); repite cada pregunta 3 veces.
3. Métricas por modelo: % de SQL válido, % de resultado correcto (global y por dificultad), % que respeta las reglas de seguridad, latencia p50 y p95, tokens y tokens/s, VRAM pico y uso de GPU, consistencia entre repeticiones y, para el modelo en nube, costo estimado por 1,000 consultas.
4. Modelos: **al menos 2 locales** (uno de ~7-8B y uno mayor si el hardware lo permite) más **1 en nube como referencia**. Verifica nombres y precios vigentes antes de correr.
5. Embeddings: latencia por fragmento, dimensión y calidad de recuperación.
6. **Rendimiento:** corre con 1, 2, 4 y 8 solicitudes concurrentes; registra throughput, p50 y p95, VRAM pico, errores y tiempos de espera, y la configuración de paralelismo de Ollama. Repite 4 consultas representativas de la BD bajo concurrencia.
7. Registra en cada resultado el hardware (CPU, RAM, GPU) y dónde corrió.

**Verificación:** un solo comando produce una tabla comparativa reproducible en `eval/results/`.

---

## FASE 8: Comparativa y decisión

**`docs/comparativa_modelos.md`:**
1. Metodología (golden set, métricas, hardware, fecha).
2. Tabla de resultados por modelo.
3. Dónde falla cada modelo (tipos de error).
4. **Justificación de la decisión de ejecutar los agentes en local**, con los datos medidos: exactitud, latencia, privacidad, control y reproducibilidad, frente a la referencia en nube. Declara las desventajas (hardware por equipo, equipos apagados) y qué no se midió.
5. **Hardware mínimo recomendado** y lista de modelos permitidos.
6. Métricas de eficiencia (por ejemplo, costo por consulta correcta y tokens/s por GB de VRAM) con su fórmula.
7. Embeddings: modelo elegido y por qué.
8. Riesgos y siguientes pasos.

No presentes conclusiones que los datos no respalden; si la muestra es pequeña, dilo.

---

## FASE 9: Diseño de despliegue (documento, sin implementar)

**`docs/despliegue.md`:**
- Dimensionamiento de la instancia EC2 según el tamaño de la BD y el volumen EBS (sin cifras inventadas; márcalas como estimación).
- Grupo de seguridad: solo HTTPS expuesto; Postgres sin acceso público.
- Respaldos de la BD a S3 y el plan de recuperación.
- Bucket de reportes: privado, cifrado, acceso público bloqueado, rol IAM mínimo para la instancia, URLs prefirmadas y convención de rutas (`reportes/{caso_id}/{version}.pdf`).
- Borrador de ACLs de Tailscale por etiquetas (backend → agentes; agentes sin acceso entre sí) y cómo alcanza el contenedor del backend la red de Tailscale.
- Gestión de secretos.
- Manejo de agente apagado y de un registro de agentes por usuario.

---

## Definición de "avance listo"

- [ ] `docker compose up` levanta solo `db` y `backend` (sin Ollama) con el README.
- [ ] `agent_host/` con guía y `check_agent.py` funcionando en la laptop.
- [x] Las 3 fuentes cargadas en `raw` con conteos verificados.
- [x] `clean.contratos` con tipo de procedimiento normalizado, columnas de dependencia (ComprasMX), banderas de fecha, tabla de excluidos y `raw = clean + excluidos`.
- [x] Conteos por tipo normalizado coinciden con los esperados.
- [x] 0 columnas, tablas y vistas de `clean` sin comentario; `verify_fase5.py` sin discrepancias.
- [ ] Rol `agent_ro` de solo lectura verificado (también sobre `rag`).
- [ ] Esquema `rag` probado con una muestra real de normas y 5 consultas de similitud.
- [ ] Telemetría de tokens, latencia y GPU/VRAM en la máquina del modelo.
- [ ] Benchmark con al menos 3 modelos, pruebas de concurrencia y resultados guardados.
- [ ] `docs/comparativa_modelos.md` con la justificación de la decisión local y el hardware mínimo.
- [ ] `docs/despliegue.md` y `ARQUITECTURA.md` actualizados.

## Cómo empezar

> Lee `AVANCE_1_PLAN.md` y `ARQUITECTURA.md`. Inspecciona el repo y la BD, dime qué de lo descrito ya existe y qué ajustarías. No cambies nada todavía. Después ejecuta la Fase 1B.
