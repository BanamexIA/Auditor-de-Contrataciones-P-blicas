-- Columnas de clean sin COMMENT ON
SELECT n.nspname AS esquema, c.relname AS tabla, a.attname AS columna
FROM pg_attribute a
JOIN pg_class c ON c.oid = a.attrelid
JOIN pg_namespace n ON n.oid = c.relnamespace
LEFT JOIN pg_description d ON d.objoid = a.attrelid AND d.objsubid = a.attnum
WHERE n.nspname = 'clean'
  AND c.relkind IN ('r','v','m','p')
  AND a.attnum > 0 AND NOT a.attisdropped
  AND d.description IS NULL
ORDER BY 2, 3;

-- Tablas y vistas de clean sin comentario propio
SELECT n.nspname AS esquema, c.relname AS objeto, c.relkind AS tipo
FROM pg_class c
JOIN pg_namespace n ON n.oid = c.relnamespace
LEFT JOIN pg_description d ON d.objoid = c.oid AND d.objsubid = 0
WHERE n.nspname = 'clean'
  AND c.relkind IN ('r','v','m','p')
  AND d.description IS NULL
ORDER BY 2;