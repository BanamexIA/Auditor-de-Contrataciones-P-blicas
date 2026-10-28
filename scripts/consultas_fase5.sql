-- 1. ¿Cuántos contratos hay por fuente y clasificación preliminar?
SELECT fuente, tipo_procedimiento_norm, COUNT(*) AS contratos
FROM clean.v_contratos_agente
GROUP BY fuente, tipo_procedimiento_norm
ORDER BY fuente, contratos DESC;

-- 2. ¿Qué cobertura anual tiene cada fuente?
SELECT anio, fuente, filas
FROM clean.v_cobertura_fuentes
ORDER BY anio NULLS FIRST, fuente;

-- 3. ¿Qué instituciones de ComprasMX tienen más contratos con fecha de inicio válida en 2026?
SELECT institucion, COUNT(*) AS contratos
FROM clean.v_contratos_agente
WHERE fuente = 'comprasmx'
  AND fecha_inicio_valida
  AND fecha_inicio >= DATE '2026-01-01'
  AND fecha_inicio < DATE '2027-01-01'
  AND institucion IS NOT NULL
GROUP BY institucion
ORDER BY contratos DESC, institucion
LIMIT 10;

-- 4. ¿Cómo se distribuyen los procedimientos de ComprasMX por artículo de excepción?
SELECT tipo_procedimiento_norm, articulo_de_excepcion, COUNT(*) AS contratos
FROM clean.v_contratos_agente
WHERE fuente = 'comprasmx'
GROUP BY tipo_procedimiento_norm, articulo_de_excepcion
ORDER BY contratos DESC
LIMIT 20;

-- 5. ¿Cuántas señales 69-B requieren revisión humana y por qué criterio?
SELECT nivel_confianza, requiere_revision_humana, COUNT(*) AS coincidencias
FROM clean.v_coincidencias_69b_agente
GROUP BY nivel_confianza, requiere_revision_humana
ORDER BY nivel_confianza, requiere_revision_humana;
