\set ON_ERROR_STOP on
-- B9: liga cada llamada al modelo con su caso. Las filas de benchmarks quedan
-- con caso_id NULL. `equipment` pasa a ser el equipo que hizo la inferencia
-- (nombre de Tailscale de la laptop), no el servidor que la pidió.

BEGIN;

ALTER TABLE telemetry.llm_calls ADD COLUMN IF NOT EXISTS caso_id TEXT;

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'llm_calls_caso_fk') THEN
        ALTER TABLE telemetry.llm_calls
            ADD CONSTRAINT llm_calls_caso_fk FOREIGN KEY (caso_id)
            REFERENCES audit.casos (id) NOT VALID;
    END IF;
END $$;

CREATE INDEX IF NOT EXISTS llm_calls_caso_idx
    ON telemetry.llm_calls (caso_id, started_at) WHERE caso_id IS NOT NULL;

COMMENT ON COLUMN telemetry.llm_calls.caso_id IS
'Caso de audit.casos al que pertenece la llamada; NULL en benchmarks.';
COMMENT ON COLUMN telemetry.llm_calls.equipment IS
'Equipo que ejecutó la inferencia: host de Tailscale del agente, o descripción local si el modelo corre en la misma máquina.';

COMMIT;
