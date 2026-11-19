\set ON_ERROR_STOP on
-- El backend se conecta con ETL_USER (ver DB_USER en docker-compose.yml).
\getenv agentes_backend_user ETL_USER

-- Registro de agentes (B7, docs/contratos/agentes.md).
-- Solo se guarda el nombre en Tailscale; el backend arma la URL. Nunca una URL libre.

BEGIN;

ALTER TABLE audit.agentes ADD COLUMN IF NOT EXISTS activo BOOLEAN NOT NULL DEFAULT TRUE;
ALTER TABLE audit.agentes ADD COLUMN IF NOT EXISTS modelos JSONB NOT NULL DEFAULT '[]'::JSONB;
ALTER TABLE audit.agentes ADD COLUMN IF NOT EXISTS version_ollama TEXT;
ALTER TABLE audit.agentes ADD COLUMN IF NOT EXISTS latencia_ms DOUBLE PRECISION;
ALTER TABLE audit.agentes ADD COLUMN IF NOT EXISTS ultimo_error TEXT;
ALTER TABLE audit.agentes ADD COLUMN IF NOT EXISTS created_at TIMESTAMPTZ NOT NULL DEFAULT NOW();

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'agentes_nombre_tailnet_uq') THEN
        ALTER TABLE audit.agentes
            ADD CONSTRAINT agentes_nombre_tailnet_uq UNIQUE (nombre_tailnet);
    END IF;

    -- Nombre de equipo DNS (minúsculas, dígitos y guiones), sin puntos, esquema ni puerto.
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'agentes_nombre_tailnet_valido') THEN
        ALTER TABLE audit.agentes
            ADD CONSTRAINT agentes_nombre_tailnet_valido
            CHECK (nombre_tailnet ~ '^[a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?$') NOT VALID;
    END IF;

    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'agentes_estado_valido') THEN
        ALTER TABLE audit.agentes
            ADD CONSTRAINT agentes_estado_valido
            CHECK (estado IN ('desconocido', 'disponible', 'sin_modelo', 'apagado')) NOT VALID;
    END IF;
END
$$;

COMMENT ON TABLE audit.agentes IS
'Equipos de inferencia (laptops con Ollama) por usuario. Alta y baja solo por CLI del administrador; el backend verifica su estado.';
COMMENT ON COLUMN audit.agentes.nombre_tailnet IS
'Nombre del equipo en Tailscale; el backend arma http://<nombre>:11434. No se guardan URLs.';
COMMENT ON COLUMN audit.agentes.modelo IS
'Modelo preferido del agente; NULL usa AGENT_MODEL.';
COMMENT ON COLUMN audit.agentes.estado IS
'desconocido (sin verificar), disponible, sin_modelo (responde sin el modelo requerido) o apagado (no responde).';
COMMENT ON COLUMN audit.agentes.activo IS
'FALSE cuando el administrador da de baja al agente; no se borra para conservar el historial.';
COMMENT ON COLUMN audit.agentes.modelos IS
'Modelos instalados según la última verificación (/api/tags).';
COMMENT ON COLUMN audit.agentes.version_ollama IS
'Versión de Ollama según la última verificación.';
COMMENT ON COLUMN audit.agentes.latencia_ms IS
'Latencia de la última verificación, en milisegundos.';
COMMENT ON COLUMN audit.agentes.ultimo_error IS
'Tipo de error de la última verificación fallida; NULL si respondió.';
COMMENT ON COLUMN audit.agentes.created_at IS
'Marca de tiempo UTC del alta.';

GRANT USAGE ON SCHEMA audit TO :"agentes_backend_user";
GRANT SELECT, INSERT, UPDATE ON audit.agentes TO :"agentes_backend_user";
GRANT USAGE, SELECT ON SEQUENCE audit.agentes_id_seq TO :"agentes_backend_user";

COMMIT;
