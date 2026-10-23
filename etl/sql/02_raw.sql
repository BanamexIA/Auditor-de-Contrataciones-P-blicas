CREATE SCHEMA IF NOT EXISTS raw;

-- Las tablas reales de origen se crean dinámicamente por el ETL para respetar
-- la estructura exacta de cada CSV y guardar todas las columnas como TEXT.
-- El script principal de carga (`etl/load_raw.py`) crea, trunca y recarga
a las tablas raw para mantener idempotencia.
