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
- La cobertura revisada no incluye contratos con fecha de inicio en 2025; los
  registros de 2023 y 2024 son parciales y no deben interpretarse como años
  completos. Consulta `clean.v_cobertura_fuentes` tras cada carga.
- `project_code`, `work_category_id`, `ff_fecha_inicio` y `ff_fecha_fin` existen
  en el histórico raw, pero no se incorporan a `clean` mientras su significado
  y uso no estén definidos: **POR CONFIRMAR**.
- RFC y nombre de proveedor pueden identificar a personas físicas. Aunque las
  fuentes son públicas, limitar el acceso y evitar publicar datos personales
  innecesarios. Una coincidencia 69-B es una señal para revisión, no una
  determinación de fraude o responsabilidad.
- En las tablas, las filas que pueden contener datos personales lo indican
  expresamente como **Dato personal: sí** en la columna de riesgos y privacidad;
  las demás columnas no están identificadas como datos personales directos.
- Las preguntas derivadas de incertidumbres semánticas se mantienen en
  [Preguntas pendientes para el socio formador](./preguntas_socio_formador.md).

## `clean.contratos`

| Columna | Tipo | Significado | Origen raw | Limpieza / transformación | Riesgos de calidad y privacidad |
|---|---|---|---|---|---|
| `fuente` | `TEXT` | Fuente de origen normalizada. | Tabla raw: `compranet_historico` o `contratos_comprasmx`. | El ETL asigna `historico` o `comprasmx`. | La fuente indica procedencia técnica, no la versión ni fecha de publicación del archivo. |
| `codigo_contrato` | `TEXT` | Identificador del contrato. | Histórico: `codigo_contrato`; ComprasMX: `codigo_del_contrato`. | Recorte de espacios exteriores. | Puede faltar o no ser globalmente único entre fuentes; **POR CONFIRMAR** la regla de unicidad entre catálogos. |
| `codigo_expediente` | `TEXT` | Identificador del expediente/procedimiento asociado. | Histórico: `codigo_expediente`; ComprasMX: `codigo_del_expediente`. | Recorte de espacios exteriores. | No asumir que equivale al identificador de contrato ni que es único. |
| `rfc` | `TEXT` | RFC del proveedor, cuando lo proporciona la fuente. | ComprasMX: `rfc`; histórico: no tiene columna equivalente. | Recorte de espacios; el cruce RFC compara en mayúsculas. | **Dato personal: sí**, especialmente para personas físicas. Puede faltar o tener formato inválido. |
| `proveedor` | `TEXT` | Nombre de proveedor o contratista tal como aparece en la fuente. | Histórico: `proveedor`; ComprasMX: `proveedor_o_contratista`. | Normalización Unicode NFKC, recorte y colapso de espacios repetidos. | **Dato personal: sí**, puede corresponder a una persona física. Variantes y homónimos; el nombre no prueba identidad legal. |
| `proveedor_normalizado` | `TEXT` | Clave textual normalizada para agrupar o comparar nombres exactamente. | Derivado de `proveedor`. | Mayúsculas; elimina diacríticos; `&` se convierte en `Y`; elimina puntuación; remueve sufijos societarios reconocidos (`SA`, `SOCIEDAD ANONIMA`, `DE RL`, `DE CV`, `SRL`, `SC` y variantes); colapsa espacios. | **Dato personal: sí, potencialmente**, porque deriva del nombre. Puede unir entidades distintas o no unir variantes reales; no es identificador legal ni fuzzy match. |
| `titulo_contrato` | `TEXT` | Título del contrato. | Histórico: `titulo_contrato`; ComprasMX: `titulo_del_contrato`. | Normalización Unicode, recorte y colapso de espacios. | Texto fuente puede ser incompleto o contener abreviaturas; significado oficial **POR CONFIRMAR** con el diccionario de la fuente. |
| `descripcion_contrato` | `TEXT` | Descripción textual asociada al contrato. | Histórico: `descripcion_contrato`; ComprasMX: `descripcion_del_contrato`. | Normalización Unicode, recorte y colapso de espacios. | Texto libre, potencialmente extenso o con datos personales; no es una categoría controlada. |
| `contract_type` | `TEXT` | Tipo/clasificación contractual según el campo disponible. | Histórico: `contract_type`; ComprasMX: `tipo_de_contrato`. | Normalización Unicode, recorte y colapso de espacios. | Los catálogos de origen pueden no ser equivalentes. **POR CONFIRMAR** la correspondencia semántica entre fuentes. |
| `tipo_contratacion` | `TEXT` | Tipo de contratación según la fuente. | Histórico: `tipo_contratacion`; ComprasMX: `tipo_de_contratacion`. | Normalización Unicode, recorte y colapso de espacios. | Las etiquetas y categorías pueden diferir por fuente y periodo; conservar el origen al comparar. |
| `tipo_expediente` | `TEXT` | Etiqueta original del tipo de expediente. | Histórico: `tipo_expediente`; ComprasMX no contiene esa columna. | Normalización Unicode, recorte y colapso de espacios. Se conserva como etiqueta original para histórico. | Los nombres históricos incluyen versiones y numeración; la interpretación como procedimiento es preliminar. |
| `tipo_procedimiento` | `TEXT` | Etiqueta original del procedimiento. | ComprasMX: `tipo_procedimiento`; histórico no contiene una columna equivalente. | Normalización Unicode, recorte y colapso de espacios. No reemplaza `tipo_expediente`. | Puede contener motivos y modalidades distintos; no inferir por sí sola el fundamento legal. |
| `importe` | `NUMERIC` | Importe monetario normalizado conforme al mapeo actual del ETL. | Histórico: `importe`; ComprasMX: `importe_drc`. | Quita `$`, separadores de coma y espacios; paréntesis se interpretan como signo negativo; conversión a `NUMERIC`. Filas con conversión inválida se registran en `staging.rechazados`. | El significado de `importe_drc` debe confirmarse antes de tratarlo como gasto ejercido o pagado. Si viene vacío, el ETL no recurre a `monto_sin_imp_maximo`. Los importes de distintas monedas no son comparables sin conversión. **POR CONFIRMAR** la semántica de `importe_drc`. |
| `moneda` | `TEXT` | Código o etiqueta monetaria declarada por la fuente. | Histórico: `moneda`; ComprasMX: primera columna `moneda`. | Normalización Unicode, recorte y colapso de espacios. | Puede haber distintas etiquetas/códigos. No se convierte moneda ni se valida contra catálogo. |
| `fecha_inicio` | `DATE` | Fecha de inicio del contrato según el campo mapeado. | Histórico: `fecha_inicio`; ComprasMX: `fecha_de_inicio_del_contrato` (o `fecha_de_inicio` si existe). | Acepta formatos configurados e ISO timestamp; se conserva solo la fecha. Vacíos y valores no parseables se conservan como `NULL` y su condición se registra en `fecha_inicio_estado`. | Se pierde hora/zona horaria. Las fechas nulas o ilegibles permanecen en `clean` y se excluyen de análisis por periodo. |
| `fecha_fin` | `DATE` | Fecha de fin del contrato según el campo mapeado. | Histórico: `fecha_fin`; ComprasMX: `fecha_de_fin_del_contrato` (o `fecha_de_fin` si existe). | Acepta formatos configurados e ISO timestamp; se conserva solo la fecha. | Se pierde hora/zona horaria; la fecha puede ser estimada, modificada o no representar la terminación efectiva. `fecha_fin_antes_inicio` identifica fechas invertidas. |
| `tipo_procedimiento_norm` | `TEXT` | Categoría preliminar del procedimiento: `adjudicacion_directa`, `invitacion_tres_personas`, `licitacion_publica`, `otro` o `sin_dato`. | ComprasMX: `tipo_procedimiento`; histórico: `tipo_expediente`. | Elimina prefijo de versión/numeración, elimina acentos y pone en mayúsculas; usa el prefijo coincidente de menor prioridad numérica de `clean.map_tipo_procedimiento`. Vacío o `Sin dato` se clasifica como `sin_dato`; sin regla, como `otro`. | Todas las reglas iniciales tienen estado `pendiente`; reportes deben llamarla “clasificación preliminar”. Etiquetas `sin_regla` se listan en `clean.v_tipos_procedimiento_sin_regla`. |
| `tipo_procedimiento_estado` | `TEXT` | Estado de validación de la categoría normalizada. | Derivado de `clean.map_tipo_procedimiento` y la etiqueta original. | `pendiente` para una regla aplicada, `sin_regla` para etiqueta no mapeada y `sin_dato` para etiqueta vacía o “Sin dato”. | `pendiente` significa que el socio formador aún no aprobó la regla. |
| `ley` | `TEXT` | Ley asociada al procedimiento cuando la fuente la proporciona o la etiqueta la identifica. | ComprasMX: `ley`; histórico: sufijo reconocido en `tipo_expediente`. | Histórico extrae al final `LAASSP`, `LOPSRM`, `LAPP` o `ESTATAL`; ComprasMX conserva su valor de origen. | Si la etiqueta histórica no termina en una de esas siglas, queda `NULL`; versiones intermedias de LOPSRM son una limitación documentada. |
| `institucion` | `TEXT` | Institución contratante. | ComprasMX: `institucion`; histórico: sin columna equivalente. | Copia normalizada de espacios desde staging. | `NULL` para histórico porque la fuente no contiene este campo. |
| `clave_institucion` | `TEXT` | Clave de la institución contratante. | ComprasMX: `clave_institucion`; histórico: sin columna equivalente. | Copia normalizada de espacios desde staging. | `NULL` para histórico porque la fuente no contiene este campo. |
| `siglas_de_la_institucion` | `TEXT` | Siglas de la institución. | ComprasMX: `siglas_de_la_institucion`; histórico: sin columna equivalente. | Copia normalizada de espacios desde staging. | `NULL` para histórico porque la fuente no contiene este campo. |
| `tipo_de_institucion` | `TEXT` | Tipo de institución. | ComprasMX: `tipo_de_institucion`; histórico: sin columna equivalente. | Copia normalizada de espacios desde staging. | `NULL` para histórico porque la fuente no contiene este campo. |
| `clave_ramo` | `TEXT` | Clave del ramo. | ComprasMX: `clave_ramo`; histórico: sin columna equivalente. | Copia normalizada de espacios desde staging. | `NULL` para histórico porque la fuente no contiene este campo. |
| `descripcion_ramo` | `TEXT` | Descripción del ramo. | ComprasMX: `descripcion_ramo`; histórico: sin columna equivalente. | Copia normalizada de espacios desde staging. | `NULL` para histórico porque la fuente no contiene este campo. |
| `clave_de_la_uc` | `TEXT` | Clave de la unidad compradora. | ComprasMX: `clave_de_la_uc`; histórico: sin columna equivalente. | Copia normalizada de espacios desde staging. | `NULL` para histórico porque la fuente no contiene este campo. |
| `nombre_de_la_uc` | `TEXT` | Nombre de la unidad compradora. | ComprasMX: `nombre_de_la_uc`; histórico: sin columna equivalente. | Copia normalizada de espacios desde staging. | `NULL` para histórico porque la fuente no contiene este campo. |
| `numero_de_procedimiento` | `TEXT` | Número del procedimiento. | ComprasMX: `numero_de_procedimiento`; histórico: sin columna equivalente. | Copia normalizada de espacios desde staging. | `NULL` para histórico porque la fuente no contiene este campo. |
| `caracter_del_procedimiento` | `TEXT` | Carácter del procedimiento. | ComprasMX: `caracter_del_procedimiento`; histórico: sin columna equivalente. | Copia normalizada de espacios desde staging. | `NULL` para histórico porque la fuente no contiene este campo. |
| `articulo_de_excepcion` | `TEXT` | Artículo invocado como excepción al procedimiento ordinario. | ComprasMX: `articulo_de_excepcion`; histórico: sin columna equivalente. | Copia normalizada de espacios desde staging. | `NULL` para histórico porque la fuente no contiene este campo; conservarlo para analizar fundamentos distintos de adjudicación directa. |
| `descripcion_excepcion` | `TEXT` | Descripción del fundamento de excepción. | ComprasMX: `descripcion_excepcion`; histórico: sin columna equivalente. | Copia normalizada de espacios desde staging. | `NULL` para histórico porque la fuente no contiene este campo; no sustituye validar el fundamento en la norma aplicable. |
| `fecha_inicio_estado` | `TEXT` | Estado de parseo y rango de `fecha_inicio`. | Derivado de la fecha original y `clean.config_calidad`. | Valores: `valida`, `nula`, `no_parseable` o `fuera_de_rango`. `Sin dato` se considera nula. | Fechas `nula`, `no_parseable` y `fuera_de_rango` se conservan en `clean` pero quedan fuera del análisis temporal. |
| `fecha_inicio_valida` | `BOOLEAN` | Indica si la fecha de inicio está dentro del rango de análisis. | Derivado de `fecha_inicio` y `clean.config_calidad`. | `TRUE` solo entre `fecha_inicio_minima` y `fecha_inicio_maxima`, inclusivas. | Límite inicial: 2010-01-01 a 2026-12-31. La fila nunca se elimina por esta bandera. |
| `fecha_inicio_futura` | `BOOLEAN` | Bandera informativa para una fecha posterior a la descarga de los datos. | Derivado de `fecha_inicio` y `clean.config_calidad.fecha_descarga`. | `TRUE` si la fecha es posterior a la fecha real de descarga indicada al ETL. | No invalida una fecha de inicio programada. La fecha de descarga es un parámetro obligatorio, no se infiere de `_loaded_at`. |
| `fecha_fin_antes_inicio` | `BOOLEAN` | Indica que la fecha fin es anterior a la fecha inicio. | Derivado de `fecha_fin` y `fecha_inicio`. | `TRUE` solo si ambas fechas existen y `fecha_fin < fecha_inicio`. | Bandera independiente; no excluye ni corrige la fila. |
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
| `rfc` | `TEXT` | RFC incluido en el listado del SAT. | `Listado_completo_69-B.csv`: `rfc`. | Recorte/colapso de espacios; el cruce por RFC compara en mayúsculas. | **Dato personal: sí**, especialmente para personas físicas. Puede contener errores, duplicados o cambios de situación en el tiempo. |
| `nombre_del_contribuyente` | `TEXT` | Nombre o razón social publicado en 69-B. | `nombre_del_contribuyente` (alternativa admitida por el ETL: `nombre_o_razon_social`). | Recorte y colapso de espacios; sin normalización destructiva en esta tabla. | **Dato personal: sí, potencialmente**, puede identificar personas físicas; variaciones de nombre no prueban identidad. |
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
| `proveedor` | `TEXT` | Nombre del proveedor del contrato coincidente. | `clean.contratos.proveedor`. | Copia directa. | **Dato personal: sí, potencialmente**, si corresponde a persona física. |
| `rfc` | `TEXT` | RFC del registro 69-B que coincide. | `clean.listado_69b.rfc`. | Copia directa. | **Dato personal: sí**, especialmente para personas físicas; limitar su exposición. |
| `nombre_del_contribuyente` | `TEXT` | Nombre publicado para el registro 69-B coincidente. | `clean.listado_69b.nombre_del_contribuyente`. | Copia directa. | **Dato personal: sí, potencialmente**; no prueba por sí solo identidad jurídica con el proveedor. |
| `created_at` | `TIMESTAMPTZ` | Momento de creación de la fila de coincidencia. | Generado por `DEFAULT NOW()`. | Automático en PostgreSQL. | Tiempo de ejecución del cruce, no fecha de la coincidencia ni vigencia del registro. |

## Tablas y vistas auxiliares de Fase 4B

### `clean.map_tipo_procedimiento`

Seed versionado en `etl/seeds/map_tipo_procedimiento.csv`; contiene `fuente`,
`prefijo`, `tipo_normalizado`, `prioridad` y `estado`. Las reglas iniciales
están en estado `pendiente`; gana el prefijo coincidente de menor prioridad
numérica. La clasificación no usa coincidencia parcial dentro de la etiqueta.

| Columna | Tipo | Significado | Origen raw | Limpieza / transformación | Riesgos de calidad y privacidad |
|---|---|---|---|---|---|
| `fuente` | `TEXT` | Fuente a la que aplica la regla: `comprasmx` o `historico`. | `etl/seeds/map_tipo_procedimiento.csv`. | Se carga sin cambios desde el seed versionado. | Catálogo preliminar; no contiene datos personales. |
| `prefijo` | `TEXT` | Inicio de etiqueta normalizada que debe coincidir. | `etl/seeds/map_tipo_procedimiento.csv`. | Se guarda sin acentos y en mayúsculas; coincide solo contra el inicio de la etiqueta normalizada. | Un prefijo incompleto puede clasificar etiquetas no previstas; no contiene datos personales. |
| `tipo_normalizado` | `TEXT` | Categoría preliminar asignada por el seed. | `etl/seeds/map_tipo_procedimiento.csv`. | Se asigna por el prefijo coincidente de menor prioridad numérica. | Reglas pendientes de validación; presentarla siempre como clasificación preliminar. |
| `prioridad` | `INTEGER` | Prioridad numérica; gana el valor menor. | `etl/seeds/map_tipo_procedimiento.csv`. | Se conserva como entero. | Un orden equivocado cambia la categoría asignada; no contiene datos personales. |
| `estado` | `TEXT` | Estado de validación; las reglas iniciales usan `pendiente`. | `etl/seeds/map_tipo_procedimiento.csv`. | Se conserva desde el seed; las etiquetas sin regla reciben el estado calculado `sin_regla`. | No interpretar `pendiente` como una categoría validada; no contiene datos personales. |

### `clean.config_calidad`

Contiene los límites inclusivos de fecha (`fecha_inicio_minima`,
`fecha_inicio_maxima`) y `fecha_descarga`. Los valores iniciales son
2010-01-01 y 2026-12-31. `run_etl.py` exige que se proporcione la fecha real de
descarga en cada ejecución; no se sustituye por `_loaded_at`.

| Columna | Tipo | Significado | Origen raw | Limpieza / transformación | Riesgos de calidad y privacidad |
|---|---|---|---|---|---|
| `id` | `SMALLINT` | Identificador fijo de la única fila de configuración. | No aplica; configuración ETL. | Se fija en `1` y está restringido por `CHECK`. | Una fila distinta de la esperada impide que se apliquen los parámetros; no contiene datos personales. |
| `fecha_inicio_minima` | `DATE` | Límite inferior inclusivo de validez. | Decisión de calidad del proyecto. | Se inicializa en `2010-01-01`; no se infiere de los contratos. | Cambiarlo altera qué filas cuentan para análisis temporal; no contiene datos personales. |
| `fecha_inicio_maxima` | `DATE` | Límite superior inclusivo, revisable al cargar nuevos datos. | Decisión de calidad del proyecto. | Se inicializa en `2026-12-31` y puede actualizarse con el parámetro del ETL. | Revisarlo en cada carga para no marcar fechas válidas como fuera de rango; no contiene datos personales. |
| `fecha_descarga` | `DATE` | Fecha real de descarga requerida por cada ejecución del ETL. | Parámetro `--fecha-descarga`. | Se escribe explícitamente en cada corrida; no se sustituye por `_loaded_at`. | Una fecha incorrecta cambia la bandera informativa `fecha_inicio_futura`; no contiene datos personales. |
| `updated_at` | `TIMESTAMPTZ` | Momento de actualización de los parámetros. | Generado por PostgreSQL. | `NOW()` al actualizar la configuración. | Tiempo de procesamiento, no fecha de descarga; no contiene datos personales. |

### `clean.contratos_excluidos`

Conserva el motivo y el payload JSON raw de contratos que el ETL no pudo
representar. La fecha nula, ilegible o fuera del rango no es motivo de
exclusión. La reconciliación debe cumplir `raw = clean + excluidos` por fuente
y por `tipo_procedimiento_norm`.

| Columna | Tipo | Significado | Origen raw | Limpieza / transformación | Riesgos de calidad y privacidad |
|---|---|---|---|---|---|
| `id` | `BIGINT` | Identificador técnico de la exclusión. | Generado por PostgreSQL. | Secuencia identity al insertar una fila excluida. | Identificador de almacenamiento, no identifica el contrato en la fuente; no contiene datos personales. |
| `fuente` | `TEXT` | Fuente raw: `comprasmx` o `historico`. | Tabla raw indicada en `staging.rechazados.source_table`. | Mapea nombres de tablas raw a `comprasmx` o `historico`. | Procedencia técnica; no contiene datos personales. |
| `motivo` | `TEXT` | Motivo por el que la fila no se materializó en `clean.contratos`. | `staging.rechazados.motivo`. | Se copia desde staging. | Debe conservar el motivo sin ocultar rechazos; puede no cubrir escenarios no registrados por staging. |
| `tipo_expediente` | `TEXT` | Etiqueta original histórica cuando está presente en el payload raw. | `raw.compranet_historico.tipo_expediente`, dentro del payload rechazado. | Se extrae del JSON; cadena vacía se convierte a `NULL`. | Etiqueta de catálogo no validada semánticamente; no contiene datos personales directos. |
| `tipo_procedimiento` | `TEXT` | Etiqueta original de ComprasMX cuando está presente en el payload raw. | `raw.contratos_comprasmx.tipo_procedimiento`, dentro del payload rechazado. | Se extrae del JSON; cadena vacía se convierte a `NULL`. | La clasificación semántica se mantiene preliminar; no contiene datos personales directos. |
| `tipo_procedimiento_norm` | `TEXT` | Clasificación preliminar de la etiqueta. | Derivado de la etiqueta y `clean.map_tipo_procedimiento`. | Se aplica la misma regla de prefijo de menor prioridad que a clean.contratos. | Puede quedar `otro` por ausencia de regla; informar el estado. |
| `tipo_procedimiento_estado` | `TEXT` | Estado de la regla aplicada o de ausencia de dato/regla. | Derivado de la etiqueta y del seed. | Se asigna con las mismas reglas de clean.contratos. | `pendiente` no significa validación del socio formador. |
| `ley` | `TEXT` | Ley raw o sigla extraída del final de la etiqueta histórica. | `raw.contratos_comprasmx.ley` o `tipo_expediente` histórico, dentro del payload. | ComprasMX conserva su valor; histórico reconoce siglas al final; cadena vacía se convierte a `NULL`. | No identifica versiones intermedias de LOPSRM; limitación documentada. |
| `raw_payload` | `JSONB` | Payload original registrado por staging para trazabilidad. | Registro original de la tabla raw que fue rechazado. | Se conserva como JSONB sin descartar los campos recibidos. | Puede contener RFC, nombres y otros datos personales: acceso restringido y uso solo para auditoría del ETL. |
| `_source_file` | `TEXT` | Nombre del archivo raw de origen. | Metadato `_source_file` del payload raw. | Se extrae del JSON; cadena vacía se convierte a `NULL`. | Trazabilidad técnica; no prueba fecha ni versión de publicación. |
| `created_at` | `TIMESTAMPTZ` | Momento de creación del registro de exclusión. | Generado por PostgreSQL. | `NOW()` al insertar el registro. | Tiempo de procesamiento, no fecha del contrato; no contiene datos personales. |

### Vistas

- `clean.v_cobertura_fuentes`: año calendario de `fecha_inicio`, fuente y
  cantidad de filas. Las fechas nulas se muestran bajo `anio = NULL`; las
  fechas fuera de rango siguen contando en su año calendario.
- `clean.v_tipos_procedimiento_sin_regla`: etiquetas que quedaron como `otro`
  con estado `sin_regla`, para revisión al final del ETL.
- `clean.v_contratos_agente`: campos de contrato y procedencia aprobados para
  consultas del agente; no elimina la necesidad de proteger RFC y nombres.
- `clean.v_coincidencias_69b_agente`: coincidencias para revisión humana. Una
  coincidencia no es una determinación de fraude, corrupción o responsabilidad.

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

## Verificación de Fase 5

- `python scripts/verify_fase5.py` compara las siete tablas base de `clean`,
  incluidas sus 76 columnas y tipos, contra este diccionario.
- `scripts/check_comentarios.sql` no devuelve objetos ni columnas sin
  comentario en `clean`; el rol `agent_ro` tiene `USAGE` en el esquema y
  `SELECT` sobre las tablas y vistas verificadas.
- `scripts/check_fase5_muestreo.sql` perfila diez campos en datos reales por
  fuente sin mostrar nombres ni RFC. Confirma que las columnas exclusivas de
  ComprasMX están pobladas en esa fuente y vacías en el histórico, que
  `tipo_procedimiento` tiene valores solo en ComprasMX, y que las fechas
  nulas/fuera de rango se distinguen mediante sus estados y banderas. El
  muestreo trata las cadenas vacías como faltantes.
- Las cinco consultas de `scripts/consultas_fase5.sql`, escritas usando solo
  vistas de `clean`, se ejecutaron correctamente en la base de desarrollo.
- La validación no resuelve las preguntas semánticas pendientes; véase
  [Preguntas pendientes para el socio formador](./preguntas_socio_formador.md).
