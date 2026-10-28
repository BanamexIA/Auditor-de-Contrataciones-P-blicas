WITH etiquetas AS (
    SELECT
        c.ctid AS row_id,
        c.fuente,
        COALESCE(
            NULLIF(BTRIM(c.tipo_procedimiento), ''),
            NULLIF(BTRIM(c.tipo_expediente), ''),
            ''
        ) AS etiqueta_original,
        UPPER(UNACCENT(REGEXP_REPLACE(
            COALESCE(
                NULLIF(BTRIM(c.tipo_procedimiento), ''),
                NULLIF(BTRIM(c.tipo_expediente), ''),
                ''
            ),
            '^(V[0-9]{8}\s+)?([0-9]+\.\s*)?',
            ''
        ))) AS etiqueta_normalizada,
        CASE
            WHEN c.fuente = 'comprasmx' THEN NULLIF(BTRIM(c.ley), '')
            WHEN c.fuente = 'historico' THEN UPPER(SUBSTRING(
                c.tipo_expediente FROM '(?i)(LAASSP|LOPSRM|LAPP|ESTATAL)\s*$'
            ))
            ELSE NULL
        END AS ley_normalizada
    FROM clean.contratos AS c
),
clasificadas AS (
    SELECT
        e.row_id,
        e.ley_normalizada,
        CASE
            WHEN e.etiqueta_normalizada IN ('', 'SIN DATO') THEN 'sin_dato'
            ELSE COALESCE(regla.tipo_normalizado, 'otro')
        END AS tipo_normalizado,
        CASE
            WHEN e.etiqueta_normalizada IN ('', 'SIN DATO') THEN 'sin_dato'
            WHEN regla.tipo_normalizado IS NULL THEN 'sin_regla'
            ELSE regla.estado
        END AS estado
    FROM etiquetas AS e
    LEFT JOIN LATERAL (
        SELECT m.tipo_normalizado, m.estado
        FROM clean.map_tipo_procedimiento AS m
        WHERE m.fuente = e.fuente
          AND LEFT(e.etiqueta_normalizada, LENGTH(m.prefijo)) = m.prefijo
        ORDER BY m.prioridad, LENGTH(m.prefijo) DESC, m.prefijo
        LIMIT 1
    ) AS regla ON TRUE
)
UPDATE clean.contratos AS c
SET tipo_procedimiento_norm = clasificadas.tipo_normalizado,
    tipo_procedimiento_estado = clasificadas.estado,
    ley = clasificadas.ley_normalizada
FROM clasificadas
WHERE c.ctid = clasificadas.row_id;

UPDATE clean.contratos AS c
SET fecha_inicio_estado = CASE
        WHEN c.fecha_inicio_estado IN ('nula', 'no_parseable') THEN c.fecha_inicio_estado
        WHEN c.fecha_inicio BETWEEN cfg.fecha_inicio_minima AND cfg.fecha_inicio_maxima THEN 'valida'
        ELSE 'fuera_de_rango'
    END,
    fecha_inicio_valida = (
        c.fecha_inicio_estado NOT IN ('nula', 'no_parseable')
        AND c.fecha_inicio BETWEEN cfg.fecha_inicio_minima AND cfg.fecha_inicio_maxima
    ),
    fecha_inicio_futura = (
        c.fecha_inicio IS NOT NULL
        AND c.fecha_inicio > cfg.fecha_descarga
    ),
    fecha_fin_antes_inicio = (
        c.fecha_inicio IS NOT NULL
        AND c.fecha_fin IS NOT NULL
        AND c.fecha_fin < c.fecha_inicio
    )
FROM clean.config_calidad AS cfg
WHERE cfg.id = 1;

TRUNCATE TABLE clean.contratos_excluidos;

INSERT INTO clean.contratos_excluidos (
    fuente,
    motivo,
    tipo_expediente,
    tipo_procedimiento,
    ley,
    raw_payload,
    _source_file
)
SELECT
    CASE
        WHEN r.source_table = 'contratos_comprasmx' THEN 'comprasmx'
        WHEN r.source_table = 'compranet_historico' THEN 'historico'
        ELSE r.source_table
    END,
    r.motivo,
    NULLIF(r.raw_payload ->> 'tipo_expediente', ''),
    NULLIF(r.raw_payload ->> 'tipo_procedimiento', ''),
    NULLIF(r.raw_payload ->> 'ley', ''),
    r.raw_payload,
    NULLIF(r.raw_payload ->> '_source_file', '')
FROM staging.rechazados AS r
WHERE r.source_table IN ('contratos_comprasmx', 'compranet_historico');

WITH etiquetas AS (
    SELECT
        e.id,
        e.fuente,
        e.tipo_expediente,
        e.tipo_procedimiento,
        e.ley,
        COALESCE(
            NULLIF(BTRIM(e.tipo_procedimiento), ''),
            NULLIF(BTRIM(e.tipo_expediente), ''),
            ''
        ) AS etiqueta_normalizada
    FROM clean.contratos_excluidos AS e
),
normalizadas AS (
    SELECT
        e.id,
        e.fuente,
        e.tipo_expediente,
        e.tipo_procedimiento,
        e.ley,
        UPPER(UNACCENT(REGEXP_REPLACE(
            e.etiqueta_normalizada,
            '^(V[0-9]{8}\s+)?([0-9]+\.\s*)?',
            ''
        ))) AS etiqueta_normalizada
    FROM etiquetas AS e
),
clasificadas AS (
    SELECT
        e.id,
        CASE
            WHEN e.etiqueta_normalizada IN ('', 'SIN DATO') THEN 'sin_dato'
            ELSE COALESCE(regla.tipo_normalizado, 'otro')
        END AS tipo_normalizado,
        CASE
            WHEN e.etiqueta_normalizada IN ('', 'SIN DATO') THEN 'sin_dato'
            WHEN regla.tipo_normalizado IS NULL THEN 'sin_regla'
            ELSE regla.estado
        END AS estado,
        CASE
            WHEN e.fuente = 'comprasmx' THEN NULLIF(BTRIM(e.ley), '')
            WHEN e.fuente = 'historico' THEN UPPER(SUBSTRING(
                e.tipo_expediente FROM '(?i)(LAASSP|LOPSRM|LAPP|ESTATAL)\s*$'
            ))
            ELSE e.ley
        END AS ley_normalizada
    FROM normalizadas AS e
    LEFT JOIN LATERAL (
        SELECT m.tipo_normalizado, m.estado
        FROM clean.map_tipo_procedimiento AS m
        WHERE m.fuente = e.fuente
          AND LEFT(e.etiqueta_normalizada, LENGTH(m.prefijo)) = m.prefijo
        ORDER BY m.prioridad, LENGTH(m.prefijo) DESC, m.prefijo
        LIMIT 1
    ) AS regla ON TRUE
)
UPDATE clean.contratos_excluidos AS e
SET tipo_procedimiento_norm = c.tipo_normalizado,
    tipo_procedimiento_estado = c.estado,
    ley = c.ley_normalizada
FROM clasificadas AS c
WHERE e.id = c.id;

CREATE OR REPLACE VIEW clean.v_cobertura_fuentes AS
SELECT
    EXTRACT(YEAR FROM fecha_inicio)::INTEGER AS anio,
    fuente,
    COUNT(*)::BIGINT AS filas
FROM clean.contratos
GROUP BY EXTRACT(YEAR FROM fecha_inicio)::INTEGER, fuente;

CREATE OR REPLACE VIEW clean.v_tipos_procedimiento_sin_regla AS
WITH etiquetas AS (
    SELECT
        fuente,
        COALESCE(NULLIF(BTRIM(tipo_procedimiento), ''), NULLIF(BTRIM(tipo_expediente), ''), '') AS etiqueta
    FROM clean.contratos
    WHERE tipo_procedimiento_estado = 'sin_regla'
    UNION ALL
    SELECT
        fuente,
        COALESCE(NULLIF(BTRIM(tipo_procedimiento), ''), NULLIF(BTRIM(tipo_expediente), ''), '') AS etiqueta
    FROM clean.contratos_excluidos
    WHERE tipo_procedimiento_estado = 'sin_regla'
)
SELECT fuente, etiqueta, COUNT(*)::BIGINT AS filas
FROM etiquetas
GROUP BY fuente, etiqueta;

CREATE OR REPLACE VIEW clean.v_contratos_agente AS
SELECT
    codigo_contrato,
    codigo_expediente,
    fuente,
    proveedor,
    proveedor_normalizado,
    titulo_contrato,
    descripcion_contrato,
    tipo_contratacion,
    tipo_expediente,
    tipo_procedimiento,
    tipo_procedimiento_norm,
    tipo_procedimiento_estado,
    ley,
    contract_type,
    importe,
    moneda,
    fecha_inicio,
    fecha_fin,
    fecha_inicio_estado,
    fecha_inicio_valida,
    fecha_inicio_futura,
    fecha_fin_antes_inicio,
    institucion,
    clave_institucion,
    siglas_de_la_institucion,
    tipo_de_institucion,
    clave_ramo,
    descripcion_ramo,
    clave_de_la_uc,
    nombre_de_la_uc,
    numero_de_procedimiento,
    caracter_del_procedimiento,
    articulo_de_excepcion,
    descripcion_excepcion,
    _source_file
FROM clean.contratos;

CREATE OR REPLACE VIEW clean.v_coincidencias_69b_agente AS
SELECT
    codigo_contrato,
    rfc_exacto,
    nombre_normalizado_exacto,
    nivel_confianza,
    requiere_revision_humana,
    proveedor,
    rfc,
    nombre_del_contribuyente,
    created_at
FROM clean.coincidencias_69b;

COMMENT ON VIEW clean.v_cobertura_fuentes IS
'Conteo de contratos por año de fecha_inicio y fuente. Las filas con fecha_inicio nula aparecen con anio NULL; las fechas fuera de rango se conservan y también cuentan por su año calendario.';
COMMENT ON COLUMN clean.v_cobertura_fuentes.anio IS
'Año calendario derivado de fecha_inicio; NULL cuando la fecha no pudo obtenerse.';
COMMENT ON COLUMN clean.v_cobertura_fuentes.fuente IS
'Fuente de origen: comprasmx o historico.';
COMMENT ON COLUMN clean.v_cobertura_fuentes.filas IS
'Número de contratos de la fuente y año indicados.';

COMMENT ON VIEW clean.v_tipos_procedimiento_sin_regla IS
'Etiquetas de contratos clean o excluidos que no coincidieron con ningún prefijo de clean.map_tipo_procedimiento y quedaron como otro con estado sin_regla.';
COMMENT ON COLUMN clean.v_tipos_procedimiento_sin_regla.fuente IS
'Fuente de origen de la etiqueta no clasificada.';
COMMENT ON COLUMN clean.v_tipos_procedimiento_sin_regla.etiqueta IS
'Etiqueta original que no coincidió con una regla.';
COMMENT ON COLUMN clean.v_tipos_procedimiento_sin_regla.filas IS
'Número de contratos con la misma fuente y etiqueta sin regla.';

COMMENT ON VIEW clean.v_contratos_agente IS
'Vista aprobada de contratos y campos de auditoría para consultas del agente. Las categorías de procedimiento con estado pendiente son preliminares.';
COMMENT ON COLUMN clean.v_contratos_agente.codigo_contrato IS
'Identificador de contrato de la fuente. Puede faltar o no ser globalmente único entre catálogos.';
COMMENT ON COLUMN clean.v_contratos_agente.codigo_expediente IS
'Identificador de expediente o procedimiento asociado, según la fuente.';
COMMENT ON COLUMN clean.v_contratos_agente.fuente IS
'Procedencia normalizada del contrato: comprasmx o historico.';
COMMENT ON COLUMN clean.v_contratos_agente.proveedor IS
'Nombre del proveedor publicado por la fuente; puede identificar a una persona física.';
COMMENT ON COLUMN clean.v_contratos_agente.proveedor_normalizado IS
'Clave textual normalizada del proveedor. No es identificador legal.';
COMMENT ON COLUMN clean.v_contratos_agente.titulo_contrato IS
'Título del contrato según la fuente.';
COMMENT ON COLUMN clean.v_contratos_agente.descripcion_contrato IS
'Descripción textual del contrato; puede contener datos personales.';
COMMENT ON COLUMN clean.v_contratos_agente.tipo_contratacion IS
'Tipo de contratación tal como fue mapeado desde la fuente.';
COMMENT ON COLUMN clean.v_contratos_agente.tipo_expediente IS
'Etiqueta original tipo_expediente, disponible principalmente para histórico.';
COMMENT ON COLUMN clean.v_contratos_agente.tipo_procedimiento IS
'Etiqueta original tipo_procedimiento de ComprasMX; NULL para el histórico, cuya fuente usa tipo_expediente.';
COMMENT ON COLUMN clean.v_contratos_agente.tipo_procedimiento_norm IS
'Clasificación preliminar por prefijo de la etiqueta original.';
COMMENT ON COLUMN clean.v_contratos_agente.tipo_procedimiento_estado IS
'Estado de validación de la clasificación; pendiente indica que debe tratarse como preliminar.';
COMMENT ON COLUMN clean.v_contratos_agente.ley IS
'Ley de ComprasMX o sigla extraída del final de la etiqueta histórica.';
COMMENT ON COLUMN clean.v_contratos_agente.contract_type IS
'Tipo o clasificación contractual según el campo mapeado de la fuente.';
COMMENT ON COLUMN clean.v_contratos_agente.importe IS
'Importe monetario normalizado; la semántica de importe_drc está POR CONFIRMAR.';
COMMENT ON COLUMN clean.v_contratos_agente.moneda IS
'Código o etiqueta monetaria declarada por la fuente; no se realiza conversión.';
COMMENT ON COLUMN clean.v_contratos_agente.fecha_inicio IS
'Fecha de inicio interpretada desde la fuente, conservada incluso si es nula o no válida para análisis temporal.';
COMMENT ON COLUMN clean.v_contratos_agente.fecha_fin IS
'Fecha de fin interpretada desde la fuente.';
COMMENT ON COLUMN clean.v_contratos_agente.fecha_inicio_estado IS
'Estado de fecha_inicio: valida, nula, no_parseable o fuera_de_rango.';
COMMENT ON COLUMN clean.v_contratos_agente.fecha_inicio_valida IS
'Indica si fecha_inicio está dentro del rango configurado para análisis temporal.';
COMMENT ON COLUMN clean.v_contratos_agente.fecha_inicio_futura IS
'Bandera informativa para una fecha posterior a la descarga; no la invalida.';
COMMENT ON COLUMN clean.v_contratos_agente.fecha_fin_antes_inicio IS
'Indica si fecha_fin es anterior a fecha_inicio cuando ambas existen.';
COMMENT ON COLUMN clean.v_contratos_agente.institucion IS
'Institución de ComprasMX. NULL para el histórico porque la fuente no contiene el campo.';
COMMENT ON COLUMN clean.v_contratos_agente.clave_institucion IS
'Clave institucional de ComprasMX. NULL para el histórico porque la fuente no contiene el campo.';
COMMENT ON COLUMN clean.v_contratos_agente.siglas_de_la_institucion IS
'Siglas institucionales de ComprasMX. NULL para el histórico porque la fuente no contiene el campo.';
COMMENT ON COLUMN clean.v_contratos_agente.tipo_de_institucion IS
'Tipo de institución de ComprasMX. NULL para el histórico porque la fuente no contiene el campo.';
COMMENT ON COLUMN clean.v_contratos_agente.clave_ramo IS
'Clave de ramo de ComprasMX. NULL para el histórico porque la fuente no contiene el campo.';
COMMENT ON COLUMN clean.v_contratos_agente.descripcion_ramo IS
'Descripción del ramo de ComprasMX. NULL para el histórico porque la fuente no contiene el campo.';
COMMENT ON COLUMN clean.v_contratos_agente.clave_de_la_uc IS
'Clave de unidad compradora de ComprasMX. NULL para el histórico porque la fuente no contiene el campo.';
COMMENT ON COLUMN clean.v_contratos_agente.nombre_de_la_uc IS
'Nombre de unidad compradora de ComprasMX. NULL para el histórico porque la fuente no contiene el campo.';
COMMENT ON COLUMN clean.v_contratos_agente.numero_de_procedimiento IS
'Número de procedimiento de ComprasMX. NULL para el histórico porque la fuente no contiene el campo.';
COMMENT ON COLUMN clean.v_contratos_agente.caracter_del_procedimiento IS
'Carácter del procedimiento de ComprasMX. NULL para el histórico porque la fuente no contiene el campo.';
COMMENT ON COLUMN clean.v_contratos_agente.articulo_de_excepcion IS
'Artículo de excepción de ComprasMX. NULL para el histórico porque la fuente no contiene el campo.';
COMMENT ON COLUMN clean.v_contratos_agente.descripcion_excepcion IS
'Descripción de excepción de ComprasMX. NULL para el histórico porque la fuente no contiene el campo.';
COMMENT ON COLUMN clean.v_contratos_agente._source_file IS
'Nombre del archivo raw que originó el contrato.';

COMMENT ON VIEW clean.v_coincidencias_69b_agente IS
'Vista de señales de coincidencia con el listado 69-B. Las coincidencias no son determinaciones de fraude, corrupción o responsabilidad legal y requieren revisión humana.';
COMMENT ON COLUMN clean.v_coincidencias_69b_agente.codigo_contrato IS
'Identificador de contrato asociado a la coincidencia.';
COMMENT ON COLUMN clean.v_coincidencias_69b_agente.rfc_exacto IS
'Indica igualdad exacta del RFC entre contrato y listado, sujeta a validar la fuente.';
COMMENT ON COLUMN clean.v_coincidencias_69b_agente.nombre_normalizado_exacto IS
'Indica igualdad exacta de nombres normalizados; puede producir falsos positivos.';
COMMENT ON COLUMN clean.v_coincidencias_69b_agente.nivel_confianza IS
'Etiqueta heurística del método de coincidencia, no una probabilidad estadística.';
COMMENT ON COLUMN clean.v_coincidencias_69b_agente.requiere_revision_humana IS
'Señala coincidencias que requieren revisión; toda señal 69-B debe contextualizarse y verificarse.';
COMMENT ON COLUMN clean.v_coincidencias_69b_agente.proveedor IS
'Nombre del proveedor coincidente; puede identificar a una persona física.';
COMMENT ON COLUMN clean.v_coincidencias_69b_agente.rfc IS
'RFC coincidente, dato identificable que debe limitarse a su propósito autorizado.';
COMMENT ON COLUMN clean.v_coincidencias_69b_agente.nombre_del_contribuyente IS
'Nombre publicado en 69-B; la coincidencia no prueba por sí sola identidad jurídica.';
COMMENT ON COLUMN clean.v_coincidencias_69b_agente.created_at IS
'Momento de ejecución del cruce, no fecha de vigencia del registro SAT.';

GRANT SELECT ON clean.contratos, clean.contratos_excluidos, clean.config_calidad,
    clean.map_tipo_procedimiento, clean.v_cobertura_fuentes,
    clean.v_tipos_procedimiento_sin_regla, clean.v_contratos_agente,
    clean.v_coincidencias_69b_agente TO agent_ro;
