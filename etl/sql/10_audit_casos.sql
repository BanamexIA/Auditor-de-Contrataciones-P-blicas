\set ON_ERROR_STOP on
-- El backend se conecta con ETL_USER (ver DB_USER en docker-compose.yml).
\getenv casos_backend_user ETL_USER

BEGIN;

CREATE TABLE IF NOT EXISTS audit.casos (
    id TEXT PRIMARY KEY,
    solicitud TEXT NOT NULL CHECK (length(btrim(solicitud)) > 0),
    estado TEXT NOT NULL DEFAULT 'recibido' CHECK (estado IN (
        'recibido', 'consultado', 'detectado', 'normado',
        'reportado', 'en_revision', 'cerrado', 'bloqueado'
    )),
    estado_previo TEXT CHECK (estado_previo IS NULL OR estado_previo IN (
        'recibido', 'consultado', 'detectado', 'normado',
        'reportado', 'en_revision'
    )),
    motivo_bloqueo TEXT,
    creado_por TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT casos_bloqueo_consistente CHECK (
        (estado = 'bloqueado' AND estado_previo IS NOT NULL
            AND length(btrim(coalesce(motivo_bloqueo, ''))) > 0)
        OR (estado <> 'bloqueado' AND estado_previo IS NULL AND motivo_bloqueo IS NULL)
    )
);

CREATE INDEX IF NOT EXISTS casos_estado_created_at_idx
    ON audit.casos (estado, created_at DESC);
CREATE INDEX IF NOT EXISTS casos_created_at_idx
    ON audit.casos (created_at DESC);

COMMENT ON TABLE audit.casos IS
'Casos de auditoría y su estado actual (docs/contratos/estado_caso.md). El historial de transiciones está en audit.bitacora con evento = transicion.';
COMMENT ON COLUMN audit.casos.id IS
'Identificador del caso (UUID en texto); es el mismo caso_id de audit.bitacora.';
COMMENT ON COLUMN audit.casos.solicitud IS
'Pregunta o solicitud original del auditor, sin modificar.';
COMMENT ON COLUMN audit.casos.estado IS
'Estado actual: recibido, consultado, detectado, normado, reportado, en_revision, cerrado o bloqueado.';
COMMENT ON COLUMN audit.casos.estado_previo IS
'Estado en que estaba el caso al bloquearse; el desbloqueo regresa a él. NULL si no está bloqueado.';
COMMENT ON COLUMN audit.casos.motivo_bloqueo IS
'Motivo del bloqueo que el front muestra al auditor. NULL si no está bloqueado.';
COMMENT ON COLUMN audit.casos.creado_por IS
'Usuario que creó el caso; NULL hasta que exista autenticación.';
COMMENT ON COLUMN audit.casos.created_at IS
'Marca de tiempo UTC de creación del caso.';
COMMENT ON COLUMN audit.casos.updated_at IS
'Marca de tiempo UTC de la última transición.';

REVOKE ALL ON audit.casos FROM PUBLIC;

-- El backend administra casos y escribe la bitácora; agent_ro no tiene acceso a audit.
GRANT USAGE ON SCHEMA audit TO :"casos_backend_user";
GRANT SELECT, INSERT, UPDATE ON audit.casos TO :"casos_backend_user";
GRANT SELECT, INSERT ON audit.bitacora TO :"casos_backend_user";
GRANT USAGE, SELECT ON SEQUENCE audit.bitacora_id_seq TO :"casos_backend_user";

COMMIT;
