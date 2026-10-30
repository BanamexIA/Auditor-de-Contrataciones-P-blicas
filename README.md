# Auditor de Contrataciones Públicas

Base del entorno para el avance de datos y evaluación de modelos. Este avance
trata los resultados como señales de riesgo, no como determinaciones de fraude,
corrupción o responsabilidad legal.

## Requisitos

- Docker Desktop con Docker Compose v2.
- Git.

## Levantar el entorno desde cero

1. Copia `.env.example` a `.env` y configura contraseñas locales únicas:

   ```powershell
   Copy-Item .env.example .env
   ```

   No subas `.env` ni reutilices estos valores de ejemplo en despliegues.
2. Ejecuta:

   ```powershell
   docker compose up -d --build
   docker compose ps
   ```

   La primera inicialización crea `raw`, `staging`, `clean`, `rag`,
   `telemetry` y `audit`, crea los roles `etl_user` y `agent_ro`, y habilita
   `pgvector` y `unaccent`. Los servicios publican puertos solo en `localhost`.
3. Verifica los servicios:

   ```powershell
   Invoke-RestMethod http://localhost:5000/health
   Invoke-RestMethod http://localhost:5000/health/db
   docker compose exec db psql -U postgres -d auditor_contrataciones -c "SELECT extname FROM pg_extension WHERE extname = 'vector';"
   docker compose exec db psql -U postgres -d auditor_contrataciones -c "SELECT extname FROM pg_extension WHERE extname = 'unaccent';"
   ```

   Si cambiaste `POSTGRES_USER` o `POSTGRES_DB`, usa esos valores en el comando
   `psql`.
4. Para aplicar los SQL de `etl/sql/` en orden alfabético, también en una
   instancia ya inicializada, ejecuta `.\scripts\init_db.ps1`. La primera
   inicialización ya habilita pgvector; los scripts deben ser idempotentes
   antes de aplicarlos nuevamente.

La base persiste en `postgres_data`. Para detener los servicios sin borrar los
datos, ejecuta `docker compose down`. No borres volúmenes para una
reinicialización sin confirmar primero que no necesitas los datos almacenados.

## Uso de la base de datos en equipo

Para una prueba temporal, pueden conectarse a la base que ya tiene los datos
en tu computadora. Así no necesitan volver a descargar los CSV. Sin embargo,
el `docker-compose.yml` actual publica PostgreSQL solo en `localhost`
(`127.0.0.1`), por lo que tus compañeros no pueden conectarse desde sus
equipos con la configuración actual. `git pull` tampoco comparte la base ni
el volumen Docker.

Para habilitar acceso remoto hace falta configurar intencionalmente la red,
PostgreSQL y el firewall del equipo anfitrión. Usen una red privada/VPN y
permitan el acceso solo a los dispositivos o direcciones de los compañeros.
No abran el puerto 5432 a Internet ni cambien el bind a todas las interfaces
sin controles de acceso. Cada compañero debe conectarse usando la dirección
privada/VPN de tu equipo, el puerto y una cuenta PostgreSQL con permisos
mínimos; no compartas la contraseña de administrador ni el archivo `.env`.

Para un uso continuo del equipo, es preferible mover la base a un servidor o
servicio administrado con acceso privado. Si cada integrante usa su propia
base local, los datos se deben transferir por un respaldo/restauración o
cargar los CSV una vez en cada instancia.

## Roles de base de datos

- `etl_user`: puede crear objetos y escribir en `raw`, `staging`, `clean` y
  `rag`.
- `agent_ro`: tiene `USAGE` solo en `clean` y `rag`, y `SELECT` en sus tablas;
  no puede crear objetos ni escribir. La conexión de la futura herramienta SQL
  debe usar este rol, no el ORM del backend.
- El backend mínimo usa `etl_user` para su comprobación de conexión.

Los permisos por defecto de lectura para objetos futuros de `clean` y `rag`
están configurados para objetos creados por `etl_user` o `postgres`. Si se
crean objetos con otro rol propietario, hay que concederle también esos
permisos por defecto.

## Ollama

Ollama conserva modelos en un volumen. Descarga un modelo de forma explícita
cuando se elija el hardware y modelo para las pruebas. El puerto expuesto por
el contenedor se configura con `OLLAMA_PORT_HOST` (predeterminado `11435`);
`OLLAMA_EMBED_BASE_URL` apunta a ese mismo puerto. Si el `.env` existente
todavía usa `11434` y ya hay otro Ollama ejecutándose localmente, configura
los tres valores en `.env` antes de iniciar el servicio:

```dotenv
OLLAMA_PORT_HOST=11435
OLLAMA_EMBED_BASE_URL=http://localhost:11435
OLLAMA_BASE_URL=http://host.docker.internal:11435
```

```powershell
docker compose --profile local-ollama up -d db ollama
docker compose exec ollama ollama pull qwen2.5:7b
```

Si cambiaste los valores después de iniciar el contenedor, recréalo:

```powershell
docker compose --profile local-ollama up -d --force-recreate ollama
```

La configuración de GPU NVIDIA está comentada en `docker-compose.yml` y
requiere instalar NVIDIA Container Toolkit. Sin ella, Ollama puede funcionar
en CPU, aunque la inferencia será más lenta.

## Fase 5B: pgvector y recuperación RAG

La extensión `vector` se habilita durante la inicialización. Para crear las
tablas de metadatos de RAG y configurar los permisos en una base existente,
ejecuta primero:

```powershell
.\scripts\init_db.ps1
```

El flujo de embeddings usa `nomic-embed-text` por defecto. Ollama debe estar
activo; descarga ese modelo una vez y descubre su dimensión real desde su API:

```powershell
docker compose exec ollama ollama pull nomic-embed-text
python -m rag.cli setup
```

`setup` registra el modelo y la dimensión observada, crea `rag.chunks` con el
tipo `vector(N)` correspondiente y el índice HNSW coseno. Para probar con
normatividad real, prepara de 5 a 10 fragmentos literales en
`rag/samples/normas.jsonl` siguiendo
[`rag/samples/README.md`](rag/samples/README.md); no se incluyen textos legales
de muestra inventados. Luego carga los fragmentos y ejecuta cinco consultas:

```powershell
python -m rag.cli ingest --jsonl rag\samples\normas.jsonl --sample
python -m rag.cli benchmark
```

El benchmark genera `rag/results/embedding_retrieval.csv`, que no se versiona.
La muestra actual contiene seis fragmentos de ambas versiones. El CSV conserva
versión, vigencia, hash, PDF local y cita por artículo/página; la revisión de
relevancia está registrada en [docs/comparativa_modelos.md](docs/comparativa_modelos.md).
La configuración local para el cliente de embeddings está en
`OLLAMA_EMBED_BASE_URL` y `OLLAMA_EMBEDDING_MODEL` dentro de `.env`; el valor
predeterminado de la URL es `http://localhost:11434`.

## Fase 6: clientes LLM

El paquete `llm` proporciona una interfaz `generate(system, prompt,
temperature=0.0)` común a Ollama y un proveedor cloud compatible con la API de
Chat Completions de OpenAI. Ollama lee `AGENT_BASE_URL` y `AGENT_MODEL`; en
Docker, la URL predeterminada es `http://host.docker.internal:11434`. Configura
la URL con el nombre o dirección Tailscale del equipo en despliegue. El cliente
devuelve texto, conteos de tokens reportados por el proveedor y latencia medida
de extremo a extremo.

El cliente cloud solo sirve como referencia de benchmark: no se invoca desde el
cliente Ollama ni es un fallback automático. Para activarlo, configura en `.env`
un modelo habilitado para tu cuenta y una clave válida:

```dotenv
CLOUD_BASE_URL=https://api.openai.com/v1/chat/completions
CLOUD_MODEL=<modelo habilitado>
CLOUD_API_KEY=<clave privada>
```

La clave no debe compartirse ni versionarse. Sin clave o modelo configurados,
`CloudClient` falla con un mensaje explícito. Para ejecutar sus pruebas con
mocks:

```powershell
python -m unittest tests.test_llm_clients
```

## Fase 6B: telemetría

Las llamadas `generate()` de ambos clientes quedan instrumentadas. El backend
guarda tokens, latencia, agente, proveedor/modelo, cuantización y versión de
Ollama en `telemetry.llm_calls`; no guarda prompts ni respuestas. El tiempo al
primer token es una estimación a partir de `total_duration` y `eval_duration`
de Ollama; queda `null` si el proveedor no lo reporta. Para aplicar idempotentemente la tabla a una BD ya
inicializada:

```powershell
.\scripts\init_db.ps1
```

En una laptop, Ollama se ejecuta localmente y no requiere PostgreSQL: el
decorador guarda CSV local. Desde la raíz, configura el modelo y ejecuta:

```powershell
$env:AGENT_BASE_URL = "http://localhost:11434"
$env:AGENT_MODEL = "qwen2.5:7b"
python agent_host\check_agent.py
```

El script mide GPU/VRAM durante la generación con `nvidia-smi`; sin GPU NVIDIA
ambos valores quedan `null`. Para usar otro modelo, indica el nombre exacto de
`ollama list`. Ver
[`agent_host/README.md`](agent_host/README.md) para detalles. Las filas del
backend se pueden exportar a CSV con:

```powershell
$env:TELEMETRY_SINK = "database"
python -m telemetry --output telemetry\results\llm_calls_export.csv
```

Ejecuta ese comando desde el host con los datos de conexión a PostgreSQL de
`.env` y `TELEMETRY_SINK=database`; para exportar las llamadas locales cambia
el sink a `csv`. `agent_host\check_agent.py` siempre guarda en CSV y no necesita
acceso a PostgreSQL.

## Fase 7: benchmark reproducible

El golden set está en `eval/golden_set.yaml`; contiene 20 preguntas con SQL
de referencia, notas de cobertura y dificultad. Antes de ejecutar modelos o
conectar a la base, valida el YAML y que cada SQL pase el analizador:

```powershell
python -m pip install -r requirements.txt
python -m eval.run_benchmark --validate-only
```

Para el benchmark completo, inicia PostgreSQL con las vistas aprobadas
actualizadas y permisos `SELECT` para `agent_ro`. Ollama debe estar accesible
desde esta máquina y tener dos modelos locales instalados, idealmente uno de
7–8B y otro mayor si el hardware lo permite. Configura los nombres exactos,
el proveedor cloud y sus precios vigentes en `.env`; el runner no inventa
tarifas:

```dotenv
BENCHMARK_OLLAMA_MODELS=qwen2.5:7b,qwen2.5:14b
CLOUD_MODEL=<modelo habilitado>
CLOUD_API_KEY=<clave privada>
CLOUD_INPUT_USD_PER_1M_TOKENS=<precio vigente de entrada>
CLOUD_OUTPUT_USD_PER_1M_TOKENS=<precio vigente de salida>
```

Después ejecuta desde la raíz:

```powershell
python -m eval.run_benchmark
```

El proceso consulta los comentarios de las vistas para construir el contexto,
calcula primero los resultados de referencia y compara filas/columnas
normalizadas, no el texto SQL. Solo permite `SELECT` de las dos vistas
aprobadas, `LIMIT` de 1 a 200, transacción PostgreSQL `READ ONLY` y timeout
de 60 segundos (las agregaciones sobre el histórico completo pueden exceder
10 segundos). Repite cada caso tres veces y mide concurrencia 1/2/4/8.
Las credenciales de la consulta se toman exclusivamente de
`AGENT_RO_USER`/`AGENT_RO_PASSWORD`; no se usa el usuario ETL para ejecutar
SQL generado.

Cada corrida crea un subdirectorio ignorado por Git dentro de
`eval/results/` con `summary.md`, tablas CSV de detalle/resumen/concurrencia,
metadatos de hardware y resultados de embeddings. El costo cloud queda como
estimación basada en los precios configurados. La calidad de recuperación RAG
queda explícitamente “no medida” hasta que
`rag/test_queries.json` incluya etiquetas `articulos_relevantes` revisadas por
humanos. Si aún no hay índice RAG disponible, se puede ejecutar
`python -m eval.run_benchmark --skip-embeddings`; esto no reemplaza la medición
de embeddings requerida para cerrar la fase. La ejecución completa requiere
tarifas de entrada y salida configuradas; si faltan, se detiene antes de
generar llamadas cloud para no presentar un costo inventado.

## Etapas de ETL

El punto de entrada para staging, reconstrucción de `clean` y transformaciones
de Fase 4B es `etl/run_etl.py`. La fecha real de descarga es obligatoria; no se
deduce de la fecha en que los archivos se cargaron a PostgreSQL:

```powershell
python etl\load_raw.py --dry-run
python etl\run_etl.py --fecha-descarga 2026-10-25 --dry-run
python etl\run_etl.py --fecha-descarga 2026-10-25
```

La fecha del primer ejemplo es ilustrativa: reemplázala por la fecha real de
descarga. Para cambiar el límite superior inclusivo de `fecha_inicio_valida`,
indica `--fecha-inicio-maxima YYYY-MM-DD`; de lo contrario se conserva el valor
de `clean.config_calidad`. Agrega `--load-raw` para volver a cargar los CSV de
`data/raw/` antes de transformar; sin esa opción, el proceso usa las tablas
raw ya cargadas. El modo `--dry-run` valida argumentos, archivos SQL y seed,
sin escribir en la base.

El pipeline conserva en `clean` las fechas de inicio vacías o ilegibles con
`fecha_inicio_estado`; no las trata como motivo de rechazo. Verifica los
conteos raw contra `clean` más `clean.contratos_excluidos`, tanto por fuente
como por categoría de procedimiento. Las categorías siguen siendo
“clasificación preliminar” mientras las reglas del seed tengan estado
`pendiente`. Genera el reporte de calidad raw por archivo con:

```powershell
python etl\quality_report.py
```

La carga raw usa COPY en streaming para no materializar los CSV completos en
memoria. Las transformaciones SQL numeradas se ejecutan desde `run_etl.py`;
los scripts leen las variables de conexión desde `.env`. Asegúrate de que la
base esté iniciada (`docker compose up -d db`).
Los nombres de columnas raw se normalizan a identificadores de PostgreSQL de
hasta 63 caracteres y se desambiguan cuando se repiten o colisionan al truncarse.
Al recargar un CSV, el loader agrega a la tabla raw cualquier columna que falte
en una tabla creada por una versión anterior del esquema, antes de truncar y
recargar los datos.

Consulta el [diccionario de datos de la capa clean](docs/diccionario_datos.md)
para los tipos, significados, linaje, transformaciones, riesgos de calidad y
consideraciones de privacidad de sus columnas.
Después de cargar los datos, compara el esquema de PostgreSQL con el diccionario
y revisa consultas de ejemplo sobre las vistas aprobadas:

```powershell
python scripts\verify_fase5.py
```

Las consultas agregadas para el muestreo de columnas, los cinco ejemplos de
preguntas y la verificación de comentarios están en
`scripts/check_fase5_muestreo.sql`, `scripts/consultas_fase5.sql` y
`scripts/check_comentarios.sql`, respectivamente. Ejecútalas con un cliente
PostgreSQL que tenga acceso de lectura a la base.

La Fase 5B del RAG tiene instrucciones y formato de muestra en
[`rag/samples/README.md`](rag/samples/README.md). La ingestión normativa exige
fuente oficial, metadatos de versión y vigencia, hash SHA-256 del archivo y
una fecha de contrato para cada búsqueda. No uses fragmentos de ejemplo como
si fueran texto legal real.

## Datos públicos

Consulta [data/README.md](data/README.md) para las fuentes y la ubicación de los
CSV originales. Los archivos se mantienen fuera del repositorio en
`data/raw/`.
