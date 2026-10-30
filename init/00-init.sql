\set ON_ERROR_STOP on
\getenv etl_user ETL_USER
\getenv etl_password ETL_USER_PASSWORD
\getenv agent_user AGENT_RO_USER
\getenv agent_password AGENT_RO_PASSWORD
\getenv db_admin POSTGRES_USER

SELECT format('CREATE ROLE %I LOGIN PASSWORD %L', :'etl_user', :'etl_password')
WHERE NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = :'etl_user')
\gexec
SELECT format('ALTER ROLE %I WITH LOGIN PASSWORD %L', :'etl_user', :'etl_password')
\gexec

SELECT format('CREATE ROLE %I LOGIN PASSWORD %L', :'agent_user', :'agent_password')
WHERE NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = :'agent_user')
\gexec
SELECT format('ALTER ROLE %I WITH LOGIN PASSWORD %L', :'agent_user', :'agent_password')
\gexec

REVOKE CREATE ON SCHEMA public FROM PUBLIC;
CREATE EXTENSION IF NOT EXISTS unaccent;
CREATE SCHEMA IF NOT EXISTS raw;
CREATE SCHEMA IF NOT EXISTS staging;
CREATE SCHEMA IF NOT EXISTS clean;
CREATE SCHEMA IF NOT EXISTS rag;
CREATE SCHEMA IF NOT EXISTS telemetry;
CREATE SCHEMA IF NOT EXISTS audit;
REVOKE ALL ON SCHEMA raw, staging, clean, rag, telemetry, audit FROM PUBLIC;

GRANT USAGE, CREATE ON SCHEMA raw, staging, clean, rag TO :"etl_user";
GRANT SELECT, INSERT, UPDATE, DELETE, TRUNCATE, REFERENCES, TRIGGER
  ON ALL TABLES IN SCHEMA raw, staging, clean, rag TO :"etl_user";
GRANT USAGE ON SCHEMA clean, rag TO :"agent_user";
GRANT SELECT ON ALL TABLES IN SCHEMA clean, rag TO :"agent_user";

SELECT format(
  'ALTER DEFAULT PRIVILEGES FOR ROLE %I IN SCHEMA clean GRANT SELECT ON TABLES TO %I',
  :'etl_user', :'agent_user'
)
\gexec
SELECT format(
  'ALTER DEFAULT PRIVILEGES FOR ROLE %I IN SCHEMA rag GRANT SELECT ON TABLES TO %I',
  :'etl_user', :'agent_user'
)
\gexec
SELECT format(
  'ALTER DEFAULT PRIVILEGES FOR ROLE %I IN SCHEMA clean GRANT SELECT ON TABLES TO %I',
  :'db_admin', :'agent_user'
)
\gexec
SELECT format(
  'ALTER DEFAULT PRIVILEGES FOR ROLE %I IN SCHEMA rag GRANT SELECT ON TABLES TO %I',
  :'db_admin', :'agent_user'
)
\gexec

\ir /opt/etl/sql/01_vector.sql
\ir /opt/etl/sql/08_telemetry.sql
