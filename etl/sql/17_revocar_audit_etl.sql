\set ON_ERROR_STOP on
-- Correr DESPUÉS de cambiar el backend a BACKEND_USER (16_rol_backend.sql).
-- El ETL no necesita audit: se le retiran los permisos que tuvo mientras el
-- backend usaba etl_user (migraciones 10 a 14). Conserva telemetry para los
-- benchmarks que corren desde las laptops.
\getenv etl_user ETL_USER

BEGIN;
REVOKE ALL ON ALL TABLES IN SCHEMA audit FROM :"etl_user";
REVOKE ALL ON ALL SEQUENCES IN SCHEMA audit FROM :"etl_user";
REVOKE USAGE ON SCHEMA audit FROM :"etl_user";
COMMIT;
