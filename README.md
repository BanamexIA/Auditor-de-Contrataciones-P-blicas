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
   `pgvector`. Los servicios publican puertos solo en `localhost`.
3. Verifica los servicios:

   ```powershell
   Invoke-RestMethod http://localhost:5000/health
   Invoke-RestMethod http://localhost:5000/health/db
   docker compose exec db psql -U postgres -d auditor_contrataciones -c "SELECT extname FROM pg_extension WHERE extname = 'vector';"
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

## Roles de base de datos

- `etl_user`: puede crear objetos y escribir en `raw`, `staging` y `clean`.
- `agent_ro`: tiene `USAGE` solo en `clean` y `rag`, y `SELECT` en sus tablas;
  no puede crear objetos ni escribir. La conexión de la futura herramienta SQL
  debe usar este rol, no el ORM del backend.
- El backend mínimo usa `etl_user` para su comprobación de conexión.

Los permisos por defecto de lectura para objetos futuros de `clean` y `rag`
están configurados para objetos creados por `etl_user` o `postgres`. Si se
crean objetos con otro rol propietario, hay que concederle también esos
permisos por defecto.

## Ollama

Ollama publica su API local en `http://localhost:11434` y conserva modelos en
un volumen. Descarga un modelo de forma explícita cuando se elija el hardware
y modelo para las pruebas; por ejemplo:

```powershell
docker compose exec ollama ollama pull qwen2.5:7b
```

La configuración de GPU NVIDIA está comentada en `docker-compose.yml` y
requiere instalar NVIDIA Container Toolkit. Sin ella, Ollama puede funcionar
en CPU, aunque la inferencia será más lenta.

## Etapas de ETL

Carga las fuentes raw y luego ejecuta las transformaciones:

```powershell
python etl\load_raw.py --dry-run
python etl\load_raw.py
python etl/build_staging.py --dry-run
python etl/build_staging.py
python etl/build_clean.py --dry-run
python etl/build_clean.py
```

El modo `--dry-run` del loader detecta estructura y cuenta filas, sin escribir.
La carga usa COPY en streaming para no materializar los CSV completos en
memoria. El staging integra ambas fuentes de contratos (`compranet_historico` y
ComprasMX 2026) con sus esquemas de origen y registra conversiones inválidas en
`staging.rechazados`. El último paso materializa `clean` y prepara un cruce de
proveedores con el listado 69-B usando RFC exacto o nombre normalizado exacto,
sin fuzzy matching. Los scripts leen automáticamente las variables de conexión
desde `.env` al ejecutarse desde el repositorio; en la terminal solo asegúrate
de que el contenedor `db` esté iniciado (`docker compose up -d db`).
Los nombres de columnas raw se normalizan a identificadores de PostgreSQL de
hasta 63 caracteres y se desambiguan cuando se repiten o colisionan al truncarse.
Al recargar un CSV, el loader agrega a la tabla raw cualquier columna que falte
en una tabla creada por una versión anterior del esquema, antes de truncar y
recargar los datos.

Consulta el [diccionario de datos de la capa clean](docs/diccionario_datos.md)
para los tipos, significados, linaje, transformaciones, riesgos de calidad y
consideraciones de privacidad de sus columnas.

## Datos públicos

Consulta [data/README.md](data/README.md) para las fuentes y la ubicación de los
CSV originales. Los archivos se mantienen fuera del repositorio en
`data/raw/`.
