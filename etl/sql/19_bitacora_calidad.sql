\set ON_ERROR_STOP on

-- Nuevo tipo de evento: calidad_evaluada (Agente de Calidad / herramienta MCP evaluar_calidad).
-- Se reemplaza la restricción de 11_audit_bitacora.sql; NOT VALID como la original.

BEGIN;

ALTER TABLE audit.bitacora DROP CONSTRAINT IF EXISTS bitacora_evento_valido;
ALTER TABLE audit.bitacora
    ADD CONSTRAINT bitacora_evento_valido CHECK (evento IN (
        'transicion', 'solicitud', 'llamada_llm', 'sql_generado',
        'sql_rechazado', 'sql_ejecutado', 'calidad_evaluada', 'reglas_evaluadas',
        'normas_recuperadas', 'reporte_guardado', 'decision', 'error'
    )) NOT VALID;

COMMIT;
