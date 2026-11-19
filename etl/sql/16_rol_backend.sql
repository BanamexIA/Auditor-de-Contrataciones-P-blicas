\set ON_ERROR_STOP on
-- Rol propio del backend (mínimo privilegio). Solo audit y telemetry; nada de
-- raw, staging, clean ni rag. El SQL que generan los agentes no usa este rol:
-- va por una conexión aparte con agent_ro (solo lectura).
\getenv backend_user BACKEND_USER
\getenv backend_password BACKEND_PASSWORD

SELECT format('CREATE ROLE %I LOGIN PASSWORD %L', :'backend_user', :'backend_password')
WHERE NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = :'backend_user')
\gexec
SELECT format('ALTER ROLE %I WITH LOGIN PASSWORD %L', :'backend_user', :'backend_password')
\gexec

BEGIN;

GRANT CONNECT ON DATABASE :"DBNAME" TO :"backend_user";

GRANT USAGE ON SCHEMA audit TO :"backend_user";
GRANT SELECT, INSERT, UPDATE ON audit.casos, audit.agentes TO :"backend_user";
GRANT SELECT, INSERT ON audit.bitacora, audit.senales, audit.decisiones, audit.reportes
    TO :"backend_user";
GRANT USAGE, SELECT ON SEQUENCE audit.bitacora_id_seq, audit.decisiones_id_seq,
    audit.reportes_id_seq, audit.agentes_id_seq TO :"backend_user";

GRANT USAGE ON SCHEMA telemetry TO :"backend_user";
GRANT SELECT, INSERT ON telemetry.llm_calls TO :"backend_user";
GRANT USAGE, SELECT ON SEQUENCE telemetry.llm_calls_id_seq TO :"backend_user";

COMMIT;
