# Preguntas pendientes para el socio formador

Estas preguntas se derivan de las incertidumbres marcadas como **POR CONFIRMAR**
en el [diccionario de datos](./diccionario_datos.md). No bloquean el uso técnico
del pipeline; sí limitan la interpretación analítica.

1. **Importe de ComprasMX:** ¿qué representa `importe_drc` y qué medida se debe
   usar en análisis? Si viene vacío, ¿se debe conservar nulo o usar
   `monto_sin_imp_maximo`? Hasta tener respuesta, no interpretar `importe` como
   gasto ejecutado o pagado.
2. **Tipos de contrato:** ¿son semánticamente equivalentes los catálogos
   histórico `contract_type` y ComprasMX `tipo_de_contrato`? Si no, deben
   analizarse por separado.
3. **Identificadores:** ¿`codigo_contrato` es único dentro de cada fuente y/o
   entre fuentes? No asumir unicidad global hasta confirmarlo.
4. **Título:** ¿qué definición oficial tiene `titulo_contrato` en cada fuente,
   y qué usos analíticos son válidos?
5. **Campos históricos pendientes:** ¿qué significan y cómo se deben usar
   `project_code`, `work_category_id`, `ff_fecha_inicio` y `ff_fecha_fin`?
   ¿Alguno debe incorporarse a `clean`?
6. **Datos personales:** ¿qué política de acceso, retención y publicación se
   debe aplicar al RFC y a los nombres de proveedores que puedan corresponder
   a personas físicas?

La equivalencia de procedencia en `clean.proveedores` está marcada **POR
CORREGIR**: el ETL asigna una fuente fija y no refleja siempre la procedencia
real. Es una limitación técnica conocida para corregir en el código; no se
presenta como una definición confirmada del socio formador.

La clasificación de tipos de procedimiento permanece **preliminar** y se
retomará con el socio formador más adelante, según la decisión del equipo.
