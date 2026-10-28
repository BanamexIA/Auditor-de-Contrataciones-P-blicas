CREATE TABLE IF NOT EXISTS clean.proveedores (
    proveedor TEXT,
    proveedor_normalizado TEXT,
    fuente TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (proveedor_normalizado)
);

CREATE TABLE IF NOT EXISTS clean.contratos (
    codigo_contrato TEXT,
    codigo_expediente TEXT,
    rfc TEXT,
    proveedor TEXT,
    proveedor_normalizado TEXT,
    titulo_contrato TEXT,
    descripcion_contrato TEXT,
    contract_type TEXT,
    tipo_contratacion TEXT,
    tipo_expediente TEXT,
    importe NUMERIC,
    moneda TEXT,
    fecha_inicio DATE,
    fecha_fin DATE,
    fuente TEXT,
    tipo_procedimiento TEXT,
    tipo_procedimiento_norm TEXT,
    tipo_procedimiento_estado TEXT,
    ley TEXT,
    institucion TEXT,
    clave_institucion TEXT,
    siglas_de_la_institucion TEXT,
    tipo_de_institucion TEXT,
    clave_ramo TEXT,
    descripcion_ramo TEXT,
    clave_de_la_uc TEXT,
    nombre_de_la_uc TEXT,
    numero_de_procedimiento TEXT,
    caracter_del_procedimiento TEXT,
    articulo_de_excepcion TEXT,
    descripcion_excepcion TEXT,
    fecha_inicio_estado TEXT,
    fecha_inicio_valida BOOLEAN NOT NULL DEFAULT false,
    fecha_inicio_futura BOOLEAN NOT NULL DEFAULT false,
    fecha_fin_antes_inicio BOOLEAN NOT NULL DEFAULT false,
    _source_file TEXT,
    _loaded_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS clean.listado_69b (
    rfc TEXT,
    nombre_del_contribuyente TEXT,
    situacion_del_contribuyente TEXT,
    _source_file TEXT,
    _loaded_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS clean.coincidencias_69b (
    codigo_contrato TEXT,
    rfc_exacto BOOLEAN DEFAULT false,
    nombre_normalizado_exacto BOOLEAN DEFAULT false,
    nivel_confianza TEXT,
    requiere_revision_humana BOOLEAN DEFAULT true,
    proveedor TEXT,
    rfc TEXT,
    nombre_del_contribuyente TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

COMMENT ON TABLE clean.contratos IS
'Contratos integrados desde compranet_historico.csv y contratos_comprasmx_2026.csv. Las columnas varían entre fuentes y los campos sin equivalente directo se almacenan vacíos. La coincidencia 69-B es una señal para revisión, no una determinación de fraude o responsabilidad.';
COMMENT ON COLUMN clean.contratos.codigo_contrato IS
'Identificador del contrato. Puede faltar o no ser globalmente único entre fuentes; POR CONFIRMAR la regla de unicidad entre catálogos.';
COMMENT ON COLUMN clean.contratos.codigo_expediente IS
'Identificador del expediente/procedimiento asociado. No asumir que equivale al identificador de contrato ni que es único.';
COMMENT ON COLUMN clean.contratos.rfc IS
'RFC del proveedor, cuando lo proporciona la fuente. Dato identificable, especialmente para personas físicas; puede faltar o tener formato inválido.';
COMMENT ON COLUMN clean.contratos.proveedor IS
'Nombre de proveedor o contratista tal como aparece en la fuente. Variantes ortográficas, homónimos y personas físicas; el nombre no prueba identidad legal.';
COMMENT ON COLUMN clean.contratos.proveedor_normalizado IS
'Clave textual normalizada para agrupar o comparar nombres exactamente. Puede unir entidades distintas o no unir variantes reales; no usar como identificador legal ni como fuzzy match.';
COMMENT ON COLUMN clean.contratos.titulo_contrato IS
'Título del contrato. Texto fuente puede ser incompleto o contener abreviaturas; significado oficial POR CONFIRMAR con el diccionario de la fuente.';
COMMENT ON COLUMN clean.contratos.descripcion_contrato IS
'Descripción textual asociada al contrato. Texto libre, potencialmente extenso o con datos personales; no es una categoría controlada.';
COMMENT ON COLUMN clean.contratos.contract_type IS
'Tipo/clasificación contractual según el campo disponible. Los catálogos de origen pueden no ser equivalentes. POR CONFIRMAR la correspondencia semántica entre fuentes.';
COMMENT ON COLUMN clean.contratos.tipo_contratacion IS
'Tipo de contratación según la fuente. Las etiquetas y categorías pueden diferir por fuente y periodo; conservar el origen al comparar.';
COMMENT ON COLUMN clean.contratos.tipo_expediente IS
'Tipo de expediente según el campo disponible. El encabezado de ComprasMX inspeccionado no contiene tipo_de_expediente; para esas filas queda vacío. POR CONFIRMAR si otra columna representa el mismo concepto.';
COMMENT ON COLUMN clean.contratos.importe IS
'Importe monetario normalizado conforme al mapeo actual del ETL. El significado de importe_drc debe confirmarse antes de tratarlo como gasto ejercido o pagado. Si viene vacío, el ETL no recurre a monto_sin_imp_maximo. Los importes de distintas monedas no son comparables sin conversión. POR CONFIRMAR la semántica de importe_drc.';
COMMENT ON COLUMN clean.contratos.moneda IS
'Código o etiqueta monetaria declarada por la fuente. Puede haber distintas etiquetas/códigos. No se convierte moneda ni se valida contra catálogo.';
COMMENT ON COLUMN clean.contratos.fecha_inicio IS
'Fecha de inicio del contrato según el campo mapeado. Se conserva solo la fecha; se pierde hora/zona horaria de timestamps y las conversiones inválidas se registran como rechazo.';
COMMENT ON COLUMN clean.contratos.fecha_fin IS
'Fecha de fin del contrato según el campo mapeado. Se conserva solo la fecha; se pierde hora/zona horaria y la fecha puede ser estimada, modificada o no representar la terminación efectiva.';
COMMENT ON COLUMN clean.contratos._source_file IS
'Nombre del archivo raw del que proviene el registro. Trazabilidad técnica; no identifica por sí solo versión, URL ni fecha de publicación de la fuente.';
COMMENT ON COLUMN clean.contratos._loaded_at IS
'Marca temporal de inserción en staging, copiada a clean. Representa la corrida ETL, no la fecha del contrato ni necesariamente la fecha original de carga raw.';

COMMENT ON TABLE clean.proveedores IS
'Nombres de proveedor observados en staging junto con una clave normalizada y una etiqueta de procedencia asignada por el ETL. No tratarla como catálogo completo de alias.';
COMMENT ON COLUMN clean.proveedores.proveedor IS
'Una forma del nombre de proveedor observada en staging. La tabla no conserva actualmente todas las variantes por proveedor; no tratarla como catálogo completo de alias.';
COMMENT ON COLUMN clean.proveedores.proveedor_normalizado IS
'Clave normalizada empleada para agrupar proveedores. Puede colisionar por eliminación de sufijos o puntuación; no es identificador legal.';
COMMENT ON COLUMN clean.proveedores.fuente IS
'Etiqueta de procedencia asignada por el ETL; actualmente el valor constante es contratos_comprasmx y no se deriva de _source_file. Limitación conocida: también se insertan proveedores de Compranet histórico, por lo que el valor actual no identifica necesariamente la fuente real. POR CORREGIR antes de usarlo para análisis de procedencia.';
COMMENT ON COLUMN clean.proveedores.created_at IS
'Momento en que se insertó el registro del proveedor en clean. Es tiempo de procesamiento, no fecha de alta legal del proveedor.';

COMMENT ON TABLE clean.listado_69b IS
'Registros del listado del SAT 69-B cargados desde la fuente pública. La situación debe interpretarse considerando la fecha y etapa legal de la publicación.';
COMMENT ON COLUMN clean.listado_69b.rfc IS
'RFC incluido en el listado del SAT. Dato identificable; puede contener errores, duplicados o cambios de situación en el tiempo.';
COMMENT ON COLUMN clean.listado_69b.nombre_del_contribuyente IS
'Nombre o razón social publicado en 69-B. Puede identificar personas físicas; variaciones de nombre no prueban que sea la misma entidad.';
COMMENT ON COLUMN clean.listado_69b.situacion_del_contribuyente IS
'Situación publicada para el contribuyente en el listado. Verificar fecha y etapa legal en la publicación antes de interpretarla.';
COMMENT ON COLUMN clean.listado_69b._source_file IS
'Archivo raw del listado que originó el registro. Trazabilidad técnica; no sustituye fecha de publicación/actualización del listado.';
COMMENT ON COLUMN clean.listado_69b._loaded_at IS
'Momento de inserción en staging, copiado a clean. No representa cuándo el SAT publicó o actualizó la situación.';

COMMENT ON TABLE clean.coincidencias_69b IS
'Registros de contratos vinculados al listado 69-B por RFC exacto o nombre normalizado exacto. Son señales para revisión, no determinaciones legales.';
COMMENT ON COLUMN clean.coincidencias_69b.codigo_contrato IS
'Contrato asociado con una coincidencia 69-B. La unicidad entre fuentes no está confirmada.';
COMMENT ON COLUMN clean.coincidencias_69b.rfc_exacto IS
'Indica coincidencia exacta de RFC entre contrato y listado. Solo es confiable si ambos RFC están correctamente capturados; es una señal, no una conclusión legal.';
COMMENT ON COLUMN clean.coincidencias_69b.nombre_normalizado_exacto IS
'Indica igualdad exacta de nombres después de aplicar la normalización de proveedor. Puede generar falsos positivos por homónimos o pérdida de sufijos; requiere revisión humana.';
COMMENT ON COLUMN clean.coincidencias_69b.nivel_confianza IS
'Etiqueta heurística del criterio: alta para RFC exacto; media para nombre normalizado exacto. No es una probabilidad estadística ni una evaluación jurídica.';
COMMENT ON COLUMN clean.coincidencias_69b.requiere_revision_humana IS
'Señala coincidencias basadas solo en nombre para revisión manual. Aun el match por RFC puede requerir verificar vigencia y contexto antes de cualquier conclusión.';
COMMENT ON COLUMN clean.coincidencias_69b.proveedor IS
'Nombre del proveedor del contrato coincidente. Puede ser dato personal si corresponde a persona física.';
COMMENT ON COLUMN clean.coincidencias_69b.rfc IS
'RFC del registro 69-B que coincide. Dato identificable; limitar su exposición.';
COMMENT ON COLUMN clean.coincidencias_69b.nombre_del_contribuyente IS
'Nombre publicado para el registro 69-B coincidente. No prueba por sí solo identidad jurídica con el proveedor del contrato.';
COMMENT ON COLUMN clean.coincidencias_69b.created_at IS
'Momento de creación de la fila de coincidencia. Es tiempo de ejecución del cruce, no fecha de la coincidencia ni vigencia del registro.';

CREATE INDEX IF NOT EXISTS idx_clean_contratos_proveedor ON clean.contratos (proveedor_normalizado, fecha_inicio);
CREATE INDEX IF NOT EXISTS idx_clean_contratos_importe ON clean.contratos (importe);
CREATE INDEX IF NOT EXISTS idx_clean_contratos_tipo ON clean.contratos (tipo_contratacion, fecha_inicio);
CREATE INDEX IF NOT EXISTS idx_clean_69b_rfc ON clean.listado_69b (rfc);
CREATE INDEX IF NOT EXISTS idx_clean_69b_nombre ON clean.listado_69b (nombre_del_contribuyente);
