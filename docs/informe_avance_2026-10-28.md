# Avance del proyecto

**Auditor de Contrataciones Públicas — 28 de octubre de 2026**

## Resumen

Se consolidó la base de datos de desarrollo con las fuentes públicas de
Compranet histórico, ComprasMX y el listado 69-B. El ETL ahora conserva los
registros con fechas nulas o fuera del rango de análisis, documenta las
transformaciones y permite verificar la consistencia entre las tablas
procesadas. También se completó la verificación del diccionario de datos de
`clean`.

## Qué está implementado

- **Datos integrados:** 2,356,609 contratos históricos y 84,676 de ComprasMX,
  para un total de **2,441,285 contratos** procesados.
- **Listado 69-B:** **14,837 registros** en staging y clean. El cruce generó
  **817 coincidencias** para revisión; son señales, no conclusiones legales.
- **Calidad de fechas:** 2,435,971 fechas de inicio dentro del rango, 5,307
  nulas y 7 fuera de rango. Las fechas nulas o fuera de rango no eliminan la
  fila del conjunto clean.
- **Procedimientos:** categorías normalizadas disponibles por fuente. En
  ComprasMX, los conteos son 58,868 adjudicaciones directas, 5,402 invitaciones
  a tres personas, 17,307 licitaciones públicas, 49 otros procedimientos y
  3,050 sin dato. No hubo etiquetas sin regla en la última corrida.
- **Trazabilidad y documentación:** campos de institución, unidad compradora,
  excepción, fuente y estado de fechas están documentados junto con sus
  transformaciones y riesgos.
- **Verificación del diccionario:** siete tablas y 76 columnas coinciden con
  el esquema de PostgreSQL, incluidos los tipos. No se encontraron tablas,
  vistas ni columnas de `clean` sin comentario; `agent_ro` tiene permisos de
  lectura verificados.
- **Consultas de demostración:** cinco ejemplos sobre las vistas aprobadas se
  ejecutaron correctamente. La suite del proyecto pasó **13 pruebas**.

## Demo sugerida

1. Mostrar el resultado de `python scripts\verify_fase5.py`: confirma que el
   diccionario y la estructura real de `clean` coinciden.
2. Consultar `clean.v_cobertura_fuentes` para mostrar el alcance temporal y
   comparar las dos fuentes.
3. Mostrar los conteos de `tipo_procedimiento_norm` por fuente, aclarando que
   la clasificación es **preliminar**.
4. Consultar las señales de `clean.v_coincidencias_69b_agente` y explicar que
   las coincidencias requieren contexto y revisión humana.
5. Mostrar las banderas de fecha para ilustrar cómo se conservan registros
   incompletos sin tratarlos como contratos válidos para análisis temporal.

Las consultas están en [`scripts/consultas_fase5.sql`](../scripts/consultas_fase5.sql)
y el perfil agregado de fechas y campos por fuente en
[`scripts/check_fase5_muestreo.sql`](../scripts/check_fase5_muestreo.sql).

## Qué falta y límites que deben comunicarse

- La clasificación de tipos de procedimiento es **preliminar** y queda
  pendiente de validación con el socio formador. No debe presentarse como una
  evaluación de riesgo por sí sola.
- Una coincidencia con el listado 69-B no determina fraude, corrupción ni
  responsabilidad; requiere revisión humana y contexto.
- El significado analítico de `importe_drc` y algunas equivalencias entre
  campos siguen pendientes de confirmación. No presentar los importes como
  gasto pagado o ejercido.
- La Fase 5B (prueba de búsqueda vectorial con fragmentos oficiales y
  consultas de similitud), el cliente de modelos, la telemetría y el benchmark
  aún no están cerrados.
- El histórico no tiene los campos institucionales de ComprasMX; la cobertura
  2023–2024 es parcial y no hay registros de inicio en 2025 en los datos
  revisados.

## Siguiente etapa

Continuar con la **Fase 5B**: validar el esquema vectorial, seleccionar un
modelo de embeddings de Ollama, cargar fragmentos normativos oficiales y medir
consultas de similitud, respetando la vigencia normativa por fecha del
contrato.

**Archivos de referencia:** [`AVANCE_1_PLAN.md`](../AVANCE_1_PLAN.md),
[`ARQUITECTURA.md`](../ARQUITECTURA.md) y
[`diccionario_datos.md`](./diccionario_datos.md).
