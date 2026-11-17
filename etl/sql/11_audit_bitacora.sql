\set ON_ERROR_STOP on

-- Reglas del contrato 5 (docs/contratos/evento_bitacora.md) aplicadas en la base.
-- NOT VALID: se exigen para filas nuevas sin revisar las existentes.

BEGIN;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = 'bitacora_caso_fk'
    ) THEN
        ALTER TABLE audit.bitacora
            ADD CONSTRAINT bitacora_caso_fk
            FOREIGN KEY (caso_id) REFERENCES audit.casos (id) NOT VALID;
    END IF;

    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = 'bitacora_evento_valido'
    ) THEN
        ALTER TABLE audit.bitacora
            ADD CONSTRAINT bitacora_evento_valido CHECK (evento IN (
                'transicion', 'solicitud', 'llamada_llm', 'sql_generado',
                'sql_rechazado', 'sql_ejecutado', 'reglas_evaluadas',
                'normas_recuperadas', 'reporte_guardado', 'decision', 'error'
            )) NOT VALID;
    END IF;
END
$$;

COMMENT ON TABLE audit.bitacora IS
'Historial de eventos de cada caso (contrato 5). Solo se agregan filas: el backend tiene SELECT e INSERT, sin UPDATE ni DELETE.';
COMMENT ON COLUMN audit.bitacora.etapa IS
'Estado del caso cuando ocurrió el evento.';
COMMENT ON COLUMN audit.bitacora.evento IS
'Tipo de evento definido en docs/contratos/evento_bitacora.md.';
COMMENT ON COLUMN audit.bitacora.equipo IS
'Equipo que ejecutó la inferencia (host del agente), no la EC2; NULL si el evento no usa un LLM.';

COMMIT;
