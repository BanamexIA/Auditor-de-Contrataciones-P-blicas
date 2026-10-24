# Diccionario de datos: capa `clean`

Este documento describe las columnas definidas por el ETL de la capa `clean`.
Los tipos corresponden a los `CREATE TABLE` de `etl/build_clean.py`. Los
significados se basan en los nombres y mapeos de los CSV inspeccionados; donde
el origen no permite asegurar la semántica se indica **POR CONFIRMAR**.

## Alcance y advertencias

- Las fuentes de contratos son `compranet_historico.csv` y
  `contratos_comprasmx_2026.csv`. El ETL las combina en `clean.contratos`.
- `importe` requiere especial cuidado: en Compranet histórico se toma de
  `importe`; en ComprasMX se toma de `importe_drc`. El mapeo actual no usa
  `monto_sin_imp_maximo` cuando `importe_drc` está vacío, porque la columna
  existe y se prioriza aunque su valor sea una cadena vacía. **POR CONFIRMAR**
  qué medida de ComprasMX debe representar la columna unificada `importe` y si
  `importe_drc` corresponde a gasto ejecutado, contratado u otro concepto.
- No todas las fuentes tienen las mismas columnas. Un campo sin equivalente
  directo se almacena vacío en `clean`; no se infiere.
- RFC y nombre de proveedor pueden identificar a personas físicas. Aunque las
  fuentes son públicas, limitar el acceso y evitar publicar datos personales
  innecesarios. Una coincidencia 69-B es una señal para revisión, no una
  determinación de fraude o responsabilidad.

## `clean.contratos`

| Columna | Tipo | Significado | Origen raw | Limpieza / transformación | Riesgos de calidad y privacidad |
|---|---|---|---|---|---|
| `codigo_contrato` | `TEXT` | Identificador del contrato. | Histórico: `codigo_contrato`; ComprasMX: `codigo_del_contrato`. | Recorte de espacios exteriores. | Puede faltar o no ser globalmente único entre fuentes; **POR CONFIRMAR** la regla de unicidad entre catálogos. |
| `codigo_expediente` | `TEXT` | Identificador del expediente/procedimiento asociado. | Histórico: `codigo_expediente`; ComprasMX: `codigo_del_expediente`. | Recorte de espacios exteriores. | No asumir que equivale al identificador de contrato ni que es único. |
| `rfc` | `TEXT` | RFC del proveedor, cuando lo proporciona la fuente. | ComprasMX: `rfc`; histórico: no tiene columna equivalente. | Recorte de espacios; el cruce RFC compara en mayúsculas. | Dato identificable, especialmente para personas físicas; puede faltar o tener formato inválido. |
| `proveedor` | `TEXT` | Nombre de proveedor o contratista tal como aparece en la fuente. | Histórico: `proveedor`; ComprasMX: `proveedor_o_contratista`. | Normalización Unicode NFKC, recorte y colapso de espacios repetidos. | Variantes ortográficas, homónimos y personas físicas; el nombre no prueba identidad legal. |
| `proveedor_normalizado` | `TEXT` | Clave textual normalizada para agrupar o comparar nombres exactamente. | Derivado de `proveedor`. | Mayúsculas; elimina diacríticos; `&` se convierte en `Y`; elimina puntuación; remueve sufijos societarios reconocidos (`SA`, `SOCIEDAD ANONIMA`, `DE RL`, `DE CV`, `SRL`, `SC` y variantes); colapsa espacios. | Puede unir entidades distintas o no unir variantes reales. Elimina información societaria; no usar como identificador legal ni como fuzzy match. |
| `titulo_contrato` | `TEXT` | Título del contrato. | Histórico: `titulo_contrato`; ComprasMX: `titulo_del_contrato`. | Normalización Unicode, recorte y colapso de espacios. | Texto fuente puede ser incompleto o contener abreviaturas; significado oficial **POR CONFIRMAR** con el diccionario de la fuente. |
| `descripcion_contrato` | `TEXT` | Descripción textual asociada al contrato. | Histórico: `descripcion_contrato`; ComprasMX: `descripcion_del_contrato`. | Normalización Unicode, recorte y colapso de espacios. | Texto libre, potencialmente extenso o con datos personales; no es una categoría controlada. |
| `contract_type` | `TEXT` | Tipo/clasificación contractual según el campo disponible. | Histórico: `contract_type`; ComprasMX: `tipo_de_contrato`. | Normalización Unicode, recorte y colapso de espacios. | Los catálogos de origen pueden no ser equivalentes. **POR CONFIRMAR** la correspondencia semántica entre fuentes. |
| `tipo_contratacion` | `TEXT` | Tipo de contratación según la fuente. | Histórico: `tipo_contratacion`; ComprasMX: `tipo_de_contratacion`. | Normalización Unicode, recorte y colapso de espacios. | Las etiquetas y categorías pueden diferir por fuente y periodo; conservar el origen al comparar. |
| `tipo_expediente` | `TEXT` | Tipo de expediente según el campo disponible. | Histórico: `tipo_expediente`; ComprasMX: `tipo_de_expediente` si existe. | Normalización Unicode, recorte y colapso de espacios. | El encabezado de ComprasMX inspeccionado no contiene `tipo_de_expediente`; para esas filas queda vacío. **POR CONFIRMAR** si otra columna representa el mismo concepto. |
| `importe` | `NUMERIC` | Importe monetario normalizado conforme al mapeo actual del ETL. | Histórico: `importe`; ComprasMX: `importe_drc`. | Quita `$`, separadores de coma y espacios; paréntesis se interpretan como signo negativo; conversión a `NUMERIC`. Filas con conversión inválida se registran en `staging.rechazados`. | El significado de `importe_drc` debe confirmarse antes de tratarlo como gasto ejercido o pagado. Si viene vacío, el ETL no recurre a `monto_sin_imp_maximo`. Los importes de distintas monedas no son comparables sin conversión. **POR CONFIRMAR** la semántica de `importe_drc`. |
| `moneda` | `TEXT` | Código o etiqueta monetaria declarada por la fuente. | Histórico: `moneda`; ComprasMX: primera columna `moneda`. | Normalización Unicode, recorte y colapso de espacios. | Puede haber distintas etiquetas/códigos. No se convierte moneda ni se valida contra catálogo. |
| `fecha_inicio` | `DATE` | Fecha de inicio del contrato según el campo mapeado. | Histórico: `fecha_inicio`; ComprasMX: `fecha_de_inicio_del_contrato` (o `fecha_de_inicio` si existe). | Acepta formatos de fecha configurados e ISO timestamp; se conserva solo la fecha. | Se pierde hora/zona horaria de timestamps; conversiones inválidas se registran como rechazo. |
| `fecha_fin` | `DATE` | Fecha de fin del contrato según el campo mapeado. | Histórico: `fecha_fin`; ComprasMX: `fecha_de_fin_del_contrato` (o `fecha_de_fin` si existe). | Acepta formatos de fecha configurados e ISO timestamp; se conserva solo la fecha. | Se pierde hora/zona horaria; la fecha puede ser estimada, modificada o no representar la terminación efectiva. |
| `_source_file` | `TEXT` | Nombre del archivo raw del que proviene el registro. | Metadato raw `_source_file`. | Se copia sin transformación semántica. | Trazabilidad técnica; no identifica por sí solo versión, URL ni fecha de publicación de la fuente. |
| `_loaded_at` | `TIMESTAMPTZ` | Marca temporal de inserción en staging, copiada a clean. | Generado por el `DEFAULT NOW()` de `staging.contratos`; no es el `_loaded_at` original de raw. | Se conserva como timestamp con zona horaria. | Representa la corrida ETL, no la fecha del contrato ni necesariamente la fecha original de carga raw. |

## `clean.proveedores`

| Columna | Tipo | Significado | Origen raw | Limpieza / transformación | Riesgos de calidad y privacidad |
|---|---|---|---|---|---|
| `proveedor` | `TEXT` | Una forma del nombre de proveedor observada en staging. | Histórico: `proveedor`; ComprasMX: `proveedor_o_contratista`. | Copia del nombre ya recortado y normalizado en staging. | La tabla no conserva actualmente todas las variantes por proveedor: inserta filas distintas y la clave primaria normalizada descarta colisiones posteriores. No tratarla como catálogo completo de alias. |
| `proveedor_normalizado` | `TEXT` | Clave normalizada empleada para agrupar proveedores. | Derivado de los nombres de contratos. | Reglas iguales a `clean.contratos.proveedor_normalizado`. | Colisiones por eliminación de sufijos o puntuación; no es identificador legal. |
| `fuente` | `TEXT` | Etiqueta de procedencia asignada por el ETL. | Valor constante generado por el script: `contratos_comprasmx`. | No se deriva de `_source_file`. | **Limitación conocida:** también se insertan proveedores de Compranet histórico, por lo que el valor actual no identifica necesariamente la fuente real. **POR CORREGIR** antes de usarlo para análisis de procedencia. |
| `created_at` | `TIMESTAMPTZ` | Momento en que se insertó el registro del proveedor en clean. | Generado por `DEFAULT NOW()`. | Automático en PostgreSQL. | Es tiempo de procesamiento, no fecha de alta legal del proveedor. |

## `clean.listado_69b`

| Columna | Tipo | Significado | Origen raw | Limpieza / transformación | Riesgos de calidad y privacidad |
|---|---|---|---|---|---|
| `rfc` | `TEXT` | RFC incluido en el listado del SAT. | `Listado_completo_69-B.csv`: `rfc`. | Recorte/colapso de espacios; el cruce por RFC compara en mayúsculas. | Dato identificable; puede contener errores, duplicados o cambios de situación en el tiempo. |
| `nombre_del_contribuyente` | `TEXT` | Nombre o razón social publicado en 69-B. | `nombre_del_contribuyente` (alternativa admitida por el ETL: `nombre_o_razon_social`). | Recorte y colapso de espacios; sin normalización destructiva en esta tabla. | Puede identificar personas físicas; variaciones de nombre no prueban que sea la misma entidad. |
| `situacion_del_contribuyente` | `TEXT` | Situación publicada para el contribuyente en el listado. | `situacion_del_contribuyente`. | Recorte y colapso de espacios. | Es una situación del registro fuente; verificar fecha y etapa legal en la publicación antes de interpretarla. |
| `_source_file` | `TEXT` | Archivo raw del listado que originó el registro. | Metadato raw `_source_file`. | Copia directa. | Trazabilidad técnica; no sustituye fecha de publicación/actualización del listado. |
| `_loaded_at` | `TIMESTAMPTZ` | Momento de inserción en staging, copiado a clean. | Generado por `DEFAULT NOW()` de staging. | Se conserva como timestamp con zona horaria. | No representa cuándo el SAT publicó o actualizó la situación. |

## `clean.coincidencias_69b`

| Columna | Tipo | Significado | Origen raw | Limpieza / transformación | Riesgos de calidad y privacidad |
|---|---|---|---|---|---|
| `codigo_contrato` | `TEXT` | Contrato asociado con una coincidencia 69-B. | `clean.contratos.codigo_contrato`. | Copia del identificador limpio. | La unicidad entre fuentes no está confirmada. |
| `rfc_exacto` | `BOOLEAN` | Indica coincidencia exacta de RFC entre contrato y listado. | `clean.contratos.rfc` y `clean.listado_69b.rfc`. | Comparación exacta insensible a mayúsculas. | Solo es confiable si ambos RFC están correctamente capturados; es una señal, no una conclusión legal. |
| `nombre_normalizado_exacto` | `BOOLEAN` | Indica igualdad exacta de nombres después de aplicar la normalización de proveedor. | Nombre de contrato y `clean.listado_69b.nombre_del_contribuyente`. | Normalización de acentos, mayúsculas, puntuación, `&` y sufijos societarios. | Puede generar falsos positivos por homónimos o pérdida de sufijos; requiere revisión humana. |
| `nivel_confianza` | `TEXT` | Etiqueta heurística del criterio: `alta` para RFC exacto; `media` para nombre normalizado exacto. | Calculado por ETL. | Asignación fija según criterio de coincidencia. | No es una probabilidad estadística ni una evaluación jurídica. |
| `requiere_revision_humana` | `BOOLEAN` | Señala coincidencias basadas solo en nombre para revisión manual. | Calculado por ETL. | `false` para RFC exacto; `true` para nombre exacto. | Aun el match por RFC puede requerir verificar vigencia y contexto antes de cualquier conclusión. |
| `proveedor` | `TEXT` | Nombre del proveedor del contrato coincidente. | `clean.contratos.proveedor`. | Copia directa. | Puede ser dato personal si corresponde a persona física. |
| `rfc` | `TEXT` | RFC del registro 69-B que coincide. | `clean.listado_69b.rfc`. | Copia directa. | Dato identificable; limitar su exposición. |
| `nombre_del_contribuyente` | `TEXT` | Nombre publicado para el registro 69-B coincidente. | `clean.listado_69b.nombre_del_contribuyente`. | Copia directa. | No prueba por sí solo identidad jurídica con el proveedor del contrato. |
| `created_at` | `TIMESTAMPTZ` | Momento de creación de la fila de coincidencia. | Generado por `DEFAULT NOW()`. | Automático en PostgreSQL. | Tiempo de ejecución del cruce, no fecha de la coincidencia ni vigencia del registro. |

## Reglas de normalización de proveedor implementadas

La función `normalize_provider` en los scripts ETL aplica, en este orden:

1. Normaliza Unicode con NFKC y recorta espacios exteriores.
2. Convierte a mayúsculas y descompone diacríticos; elimina acentos.
3. Reemplaza `&` por `Y`.
4. Sustituye puntuación y caracteres no alfanuméricos por espacios.
5. Elimina las formas reconocidas de `SA`, `SOCIEDAD ANONIMA`, `DE RL`,
   `DE CV`, `SRL` y `SC`.
6. Colapsa espacios consecutivos y recorta de nuevo.

La regla es útil para comparación exacta reproducible, pero puede colisionar
nombres de entidades diferentes. No se aplica similitud difusa.

## Pendientes de validación semántica

- Confirmar qué medida de ComprasMX debe alimentar `importe` y qué significa
  `importe_drc`; hasta entonces, no interpretar sus sumas combinadas con
  Compranet histórico como gasto ejecutado.
- Confirmar la equivalencia de los catálogos `contract_type` y `tipo_de_contrato`.
- Definir cómo conservar todas las variantes de proveedor y procedencias reales
  en `clean.proveedores`; el ETL actual conserva una sola fila por clave
  normalizada y asigna una etiqueta fija de fuente.
- Confirmar la política de acceso, retención y publicación para RFC y nombres
  de proveedores que sean personas físicas.
