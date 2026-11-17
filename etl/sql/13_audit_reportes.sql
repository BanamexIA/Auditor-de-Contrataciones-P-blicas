\set ON_ERROR_STOP on
-- El backend se conecta con ETL_USER (ver DB_USER en docker-compose.yml).
\getenv reportes_backend_user ETL_USER

-- audit.reportes deja de depender de S3 (docs/contratos/reportes.md).
-- Supone que la tabla no tiene filas con version no numérica (no la usaba ningún código).

BEGIN;

DO $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_schema = 'audit' AND table_name = 'reportes' AND column_name = 's3_uri'
    ) THEN
        ALTER TABLE audit.reportes RENAME COLUMN s3_uri TO uri;
    END IF;

    IF EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_schema = 'audit' AND table_name = 'reportes'
          AND column_name = 'version' AND data_type = 'text'
    ) THEN
        ALTER TABLE audit.reportes ALTER COLUMN version TYPE INTEGER USING version::INTEGER;
    END IF;

    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'reportes_version_positiva') THEN
        ALTER TABLE audit.reportes
            ADD CONSTRAINT reportes_version_positiva CHECK (version >= 1);
    END IF;

    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'reportes_caso_version_uq') THEN
        ALTER TABLE audit.reportes
            ADD CONSTRAINT reportes_caso_version_uq UNIQUE (caso_id, version);
    END IF;

    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'reportes_caso_fk') THEN
        ALTER TABLE audit.reportes
            ADD CONSTRAINT reportes_caso_fk
            FOREIGN KEY (caso_id) REFERENCES audit.casos (id) NOT VALID;
    END IF;
END
$$;

ALTER TABLE audit.reportes ADD COLUMN IF NOT EXISTS formato TEXT NOT NULL DEFAULT 'pdf';
ALTER TABLE audit.reportes ADD COLUMN IF NOT EXISTS content_type TEXT NOT NULL DEFAULT 'application/pdf';
ALTER TABLE audit.reportes ADD COLUMN IF NOT EXISTS tamano_bytes BIGINT;

COMMENT ON TABLE audit.reportes IS
'Versiones de los reportes de cada caso. El archivo se guarda primero en el almacén (local o S3) y después se registra aquí.';
COMMENT ON COLUMN audit.reportes.uri IS
'Ubicación devuelta por el almacén: local://reportes/... o s3://bucket/reportes/...';
COMMENT ON COLUMN audit.reportes.version IS
'Versión del reporte dentro del caso, entera desde 1.';
COMMENT ON COLUMN audit.reportes.sha256 IS
'Hash SHA-256 del contenido; se verifica al leer.';
COMMENT ON COLUMN audit.reportes.formato IS 'Formato del reporte: pdf o md.';
COMMENT ON COLUMN audit.reportes.content_type IS 'Tipo MIME con que se sirve el reporte.';
COMMENT ON COLUMN audit.reportes.tamano_bytes IS 'Tamaño del contenido en bytes.';
COMMENT ON COLUMN audit.reportes.modelo IS 'Modelo que redactó el reporte, si aplica.';
COMMENT ON COLUMN audit.reportes.equipo IS 'Laptop que ejecutó la inferencia del reporte, si aplica.';

GRANT USAGE ON SCHEMA audit TO :"reportes_backend_user";
GRANT SELECT, INSERT ON audit.reportes TO :"reportes_backend_user";
GRANT USAGE, SELECT ON SEQUENCE audit.reportes_id_seq TO :"reportes_backend_user";

COMMIT;
