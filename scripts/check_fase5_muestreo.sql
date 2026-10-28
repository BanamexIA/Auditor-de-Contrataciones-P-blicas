-- Perfil de 10 columnas seleccionadas de clean.contratos, por fuente.
-- Los resultados son conteos agregados y no exponen RFC ni nombres.
SELECT
    fuente,
    COUNT(*) AS filas,
    COUNT(NULLIF(BTRIM(tipo_expediente), '')) AS con_tipo_expediente,
    COUNT(NULLIF(BTRIM(tipo_procedimiento), '')) AS con_tipo_procedimiento,
    COUNT(NULLIF(BTRIM(tipo_procedimiento_norm), '')) AS con_tipo_procedimiento_norm,
    COUNT(NULLIF(BTRIM(ley), '')) AS con_ley,
    COUNT(NULLIF(BTRIM(institucion), '')) AS con_institucion,
    COUNT(NULLIF(BTRIM(articulo_de_excepcion), '')) AS con_articulo_de_excepcion,
    COUNT(fecha_inicio) AS con_fecha_inicio,
    COUNT(NULLIF(BTRIM(fecha_inicio_estado), '')) AS con_fecha_inicio_estado,
    COUNT(*) FILTER (WHERE fecha_inicio_valida) AS con_fecha_inicio_valida
FROM clean.contratos
GROUP BY fuente
ORDER BY fuente;
