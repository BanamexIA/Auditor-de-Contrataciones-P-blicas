-- D1 · Umbrales de las reglas de detección, fuera del código.
-- Cada valor lleva su motivo y su estado: 'provisional' hasta que el socio formador lo confirme
-- (decisión 5 de AVANCE_2_PLAN.md). El agente de detección los lee con agent_ro (solo lectura) y los
-- copia al JSON con su estado, para que el reporte diga que son provisionales.
-- Para confirmar uno:  UPDATE config.umbrales SET estado = 'confirmado', confirmado_por = '...',
--                      confirmado_en = NOW() WHERE clave = '...';   (con el rol administrador, no con agent_ro)
CREATE SCHEMA IF NOT EXISTS config;

CREATE TABLE IF NOT EXISTS config.umbrales (
    clave TEXT PRIMARY KEY,
    regla TEXT NOT NULL,
    valor JSONB NOT NULL,
    unidad TEXT,
    motivo TEXT NOT NULL,
    estado TEXT NOT NULL DEFAULT 'provisional' CHECK (estado IN ('provisional', 'confirmado')),
    confirmado_por TEXT,
    confirmado_en TIMESTAMPTZ,
    actualizado_en TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CHECK (estado = 'provisional' OR (confirmado_por IS NOT NULL AND confirmado_en IS NOT NULL))
);

INSERT INTO config.umbrales (clave, regla, valor, unidad, motivo) VALUES
 ('adj_umbral_n', 'ADJ_DIRECTA_RECURRENTE', '2', 'adjudicaciones_directas',
  'Señal si hay MÁS de n adjudicaciones directas al mismo proveedor dentro de la ventana. Valor propuesto por el equipo.'),
 ('adj_ventana_dias', 'ADJ_DIRECTA_RECURRENTE', '30', 'días',
  'Ventana deslizante para contar adjudicaciones directas. Valor propuesto por el equipo.'),
 ('adj_agrupar_por_dependencia', 'ADJ_DIRECTA_RECURRENTE', 'true', NULL,
  'Cuenta por proveedor y dependencia; si es false, solo por proveedor.'),
 ('adj_factor_nivel_alto', 'ADJ_DIRECTA_RECURRENTE', '2', 'veces el umbral n',
  'Nivel alto si el número de adjudicaciones en la ventana es al menos este factor por n; si no, medio.'),
 ('monto_columnas_grupo', 'MONTO_ATIPICO', '["ley", "tipo_proc_norm", "anio"]', NULL,
  'Criterio de contratos comparables: misma ley, tipo de procedimiento y año (AVANCE_2_PLAN.md).'),
 ('monto_min_grupo', 'MONTO_ATIPICO', '5', 'contratos',
  'Un grupo con menos contratos con monto válido en pesos no se evalúa (se declara no evaluable).'),
 ('monto_umbral_z', 'MONTO_ATIPICO', '3.5', 'puntaje z robusto',
  'Se marca un monto si |z| supera este valor; z se calcula con mediana y MAD (3.5 es el corte usual).'),
 ('monto_escala_log', 'MONTO_ATIPICO', 'true', NULL,
  'Los montos son muy asimétricos: se compara sobre el logaritmo del monto.'),
 ('monto_factor_nivel_alto', 'MONTO_ATIPICO', '2', 'veces el umbral z',
  'Nivel alto si |z| es al menos este factor por el umbral z; si no, medio.'),
 ('comparables_confianza_alta', 'MONTO_ATIPICO', '30', 'contratos',
  'Con al menos este número de comparables la confianza de la señal no baja.'),
 ('comparables_confianza_media', 'MONTO_ATIPICO', '10', 'contratos',
  'Con al menos este número (y menos que el anterior) la confianza baja un nivel; con menos, dos.')
ON CONFLICT (clave) DO NOTHING;

COMMENT ON TABLE config.umbrales IS
'Umbrales de las reglas de detección. estado=provisional hasta que el socio formador los confirme.';

GRANT USAGE ON SCHEMA config TO agent_ro;
GRANT SELECT ON config.umbrales TO agent_ro;
