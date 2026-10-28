

SELECT _source_file, count(*) AS total,
       count(*) FILTER (WHERE institucion IS NOT NULL) AS con_institucion
FROM clean.contratos GROUP BY 1 ORDER BY 1;

-- Tabla de equivalencias de institucion

SELECT _source_file, tipo_expediente, count(*)
FROM clean.contratos GROUP BY 1,2 ORDER BY 1, 3 DESC;

-- Conteo tablas 
SELECT (SELECT count(*) FROM raw.contratos_comprasmx)
     + (SELECT count(*) FROM raw.compranet_historico) AS raw_total,
       (SELECT count(*) FROM clean.contratos) AS clean_total;

