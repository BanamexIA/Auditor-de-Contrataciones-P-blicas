-- T6: vistas con forma de estrella sobre clean. BORRADOR del Agente Consulta (2026-11-19).
--
-- No está en etl/sql/ a propósito: scripts/init_db.ps1 ejecuta todos los archivos de esa
-- carpeta. Cuando Backend lo apruebe, se mueve allá con el siguiente número.
-- Diseño, decisiones abiertas y consultas de verificación: docs/vistas_estrella.md.
--
-- Son vistas: no cambian clean ni el ETL. Todas las columnas llevan COMMENT para que
-- scripts/check_comentarios.sql siga sin filas.

-- Hecho: un registro de contrato de clean.contratos (mismo grano que v_contratos_agente).
CREATE OR REPLACE VIEW clean.v_hecho_contrato AS
SELECT
    c.codigo_contrato,
    c.fuente,
    c.proveedor_normalizado,
    c.clave_institucion,
    c.fecha_inicio,
    c.tipo_procedimiento_norm,
    c.importe,
    c.moneda,
    c.fecha_fin,
    c.fecha_inicio_estado,
    c.fecha_inicio_valida,
    c.fecha_inicio_futura,
    c.fecha_fin_antes_inicio,
    EXISTS (
        SELECT 1 FROM clean.coincidencias_69b AS m WHERE m.codigo_contrato = c.codigo_contrato
    ) AS tiene_coincidencia_69b
FROM clean.contratos AS c;

-- Dimensión proveedor: una fila por proveedor_normalizado. No expone el RFC.
CREATE OR REPLACE VIEW clean.v_dim_proveedor AS
SELECT
    c.proveedor_normalizado,
    MIN(c.proveedor) AS proveedor_publicado,
    COUNT(DISTINCT c.proveedor) AS nombres_publicados,
    STRING_AGG(DISTINCT c.fuente, ', ' ORDER BY c.fuente) AS fuentes,
    -- Los RFC genéricos (público en general y extranjeros) tienen 13 caracteres, pero no son personas.
    CASE
        WHEN BOOL_OR(LENGTH(TRIM(c.rfc)) = 13
                     AND UPPER(TRIM(c.rfc)) NOT IN ('XAXX010101000', 'XEXX010101000')) THEN 'fisica'
        WHEN BOOL_OR(LENGTH(TRIM(c.rfc)) = 12) THEN 'moral'
    END AS tipo_persona,
    MIN(c.fecha_inicio) FILTER (WHERE c.fecha_inicio_valida) AS primer_inicio,
    MAX(c.fecha_inicio) FILTER (WHERE c.fecha_inicio_valida) AS ultimo_inicio,
    BOOL_OR(m.codigo_contrato IS NOT NULL) AS en_listado_69b,
    CASE
        WHEN BOOL_OR(m.nivel_confianza = 'alta') THEN 'alta'
        WHEN BOOL_OR(m.nivel_confianza = 'media') THEN 'media'
    END AS nivel_confianza_69b,
    STRING_AGG(DISTINCT l.situacion_del_contribuyente, ', ' ORDER BY l.situacion_del_contribuyente)
        AS situacion_69b
FROM clean.contratos AS c
LEFT JOIN clean.coincidencias_69b AS m
    ON m.codigo_contrato = c.codigo_contrato
LEFT JOIN clean.listado_69b AS l
    ON l.rfc = m.rfc
WHERE c.proveedor_normalizado <> ''
GROUP BY c.proveedor_normalizado;

-- Dimensión institución: una fila por clave_institucion. Solo existe en ComprasMX.
CREATE OR REPLACE VIEW clean.v_dim_institucion AS
SELECT
    clave_institucion,
    MIN(institucion) AS institucion,
    COUNT(DISTINCT institucion) AS nombres_publicados,
    MIN(siglas_de_la_institucion) AS siglas_de_la_institucion,
    MIN(tipo_de_institucion) AS tipo_de_institucion,
    MIN(clave_ramo) AS clave_ramo,
    MIN(descripcion_ramo) AS descripcion_ramo
FROM clean.contratos
WHERE clave_institucion IS NOT NULL
GROUP BY clave_institucion;

-- Dimensión fecha: una fila por fecha de inicio válida que aparece en los contratos.
CREATE OR REPLACE VIEW clean.v_dim_fecha AS
SELECT
    fecha_inicio AS fecha,
    EXTRACT(YEAR FROM fecha_inicio)::integer AS anio,
    EXTRACT(QUARTER FROM fecha_inicio)::integer AS trimestre,
    EXTRACT(MONTH FROM fecha_inicio)::integer AS mes,
    TO_CHAR(fecha_inicio, 'YYYY-MM') AS anio_mes
FROM (
    SELECT DISTINCT fecha_inicio
    FROM clean.contratos
    WHERE fecha_inicio_valida
) AS fechas;

-- Dimensión procedimiento: los cinco valores de tipo_procedimiento_norm (capa semántica, M3).
CREATE OR REPLACE VIEW clean.v_dim_procedimiento AS
SELECT tipo_procedimiento_norm, nombre, es_competitivo
FROM (VALUES
    ('adjudicacion_directa', 'Adjudicación directa', false),
    ('invitacion_tres_personas', 'Invitación a cuando menos tres personas', false),
    ('licitacion_publica', 'Licitación pública', true),
    ('otro', 'Otro', NULL),
    ('sin_dato', 'Sin dato', NULL)
) AS procedimientos (tipo_procedimiento_norm, nombre, es_competitivo);

COMMENT ON VIEW clean.v_hecho_contrato IS
'Hecho de la estrella (T6): un registro de contrato de una fuente, con las llaves de las dimensiones de proveedor, institución, fecha y procedimiento. Mismo grano que v_contratos_agente; codigo_contrato no es una llave única garantizada.';
COMMENT ON COLUMN clean.v_hecho_contrato.codigo_contrato IS
'Identificador de contrato de la fuente. Puede faltar o repetirse; para contar contratos únicos usar COUNT(DISTINCT).';
COMMENT ON COLUMN clean.v_hecho_contrato.fuente IS
'Fuente de origen: comprasmx (ComprasMX 2026) o historico (CompraNet 2010-2024).';
COMMENT ON COLUMN clean.v_hecho_contrato.proveedor_normalizado IS
'Llave hacia v_dim_proveedor. Clave textual normalizada, no identificador legal; vacía cuando la fuente no trae proveedor.';
COMMENT ON COLUMN clean.v_hecho_contrato.clave_institucion IS
'Llave hacia v_dim_institucion. Solo existe en ComprasMX; nula en el histórico, lo que no significa falta de actividad.';
COMMENT ON COLUMN clean.v_hecho_contrato.fecha_inicio IS
'Llave hacia v_dim_fecha cuando fecha_inicio_valida es verdadero. Es la fecha de referencia para los periodos.';
COMMENT ON COLUMN clean.v_hecho_contrato.tipo_procedimiento_norm IS
'Llave hacia v_dim_procedimiento. Clasificación preliminar del tipo de procedimiento.';
COMMENT ON COLUMN clean.v_hecho_contrato.importe IS
'Importe registrado en la fuente; no es gasto pagado ni ejercido. Se suma por fuente y por moneda.';
COMMENT ON COLUMN clean.v_hecho_contrato.moneda IS
'Moneda del importe registrado. Nunca se suman importes de monedas distintas.';
COMMENT ON COLUMN clean.v_hecho_contrato.fecha_fin IS
'Fecha de fin publicada; no define periodos.';
COMMENT ON COLUMN clean.v_hecho_contrato.fecha_inicio_estado IS
'Estado de la fecha de inicio: valida, nula, fuera_de_rango o no_parseable.';
COMMENT ON COLUMN clean.v_hecho_contrato.fecha_inicio_valida IS
'Verdadero si la fecha de inicio existe y cae entre 2010-01-01 y 2026-12-31; solo esas filas entran en análisis por periodo.';
COMMENT ON COLUMN clean.v_hecho_contrato.fecha_inicio_futura IS
'Bandera informativa: inicio posterior a la fecha de descarga. No excluye el registro.';
COMMENT ON COLUMN clean.v_hecho_contrato.fecha_fin_antes_inicio IS
'Bandera de calidad de datos: fecha de fin anterior a la de inicio. No es una cancelación ni una irregularidad.';
COMMENT ON COLUMN clean.v_hecho_contrato.tiene_coincidencia_69b IS
'Verdadero si el contrato tiene una coincidencia en clean.coincidencias_69b. Es una señal para revisión humana, no una determinación.';

COMMENT ON VIEW clean.v_dim_proveedor IS
'Dimensión proveedor (T6): una fila por proveedor_normalizado con contratos. No incluye el RFC; agrega la información del listado 69-B de todos sus contratos.';
COMMENT ON COLUMN clean.v_dim_proveedor.proveedor_normalizado IS
'Llave de la dimensión: clave textual normalizada (sin acentos, puntuación ni sufijos societarios). Puede unir entidades distintas o separar variantes de la misma.';
COMMENT ON COLUMN clean.v_dim_proveedor.proveedor_publicado IS
'Uno de los nombres publicados por la fuente para esta clave. Puede identificar a una persona física: mostrar solo cuando la pregunta lo necesite.';
COMMENT ON COLUMN clean.v_dim_proveedor.nombres_publicados IS
'Cuántos nombres publicados distintos comparten la clave; más de uno indica variantes de escritura o entidades distintas.';
COMMENT ON COLUMN clean.v_dim_proveedor.fuentes IS
'Fuentes en las que aparece el proveedor: comprasmx, historico o ambas.';
COMMENT ON COLUMN clean.v_dim_proveedor.tipo_persona IS
'fisica (RFC de 13 caracteres, sin contar los genéricos) o moral (12), deducido del RFC de ComprasMX; si la clave tiene ambos, gana fisica. Nulo si no hay RFC, como en el histórico. Provisional: sirve para no mostrar nombres de personas físicas sin criterio.';
COMMENT ON COLUMN clean.v_dim_proveedor.primer_inicio IS
'Fecha de inicio válida más antigua entre sus contratos.';
COMMENT ON COLUMN clean.v_dim_proveedor.ultimo_inicio IS
'Fecha de inicio válida más reciente entre sus contratos.';
COMMENT ON COLUMN clean.v_dim_proveedor.en_listado_69b IS
'Verdadero si al menos un contrato del proveedor tiene coincidencia con el listado 69-B. Señal para revisión humana, no determinación.';
COMMENT ON COLUMN clean.v_dim_proveedor.nivel_confianza_69b IS
'alta si alguna coincidencia es por RFC exacto, media si solo hay coincidencias por nombre; nulo sin coincidencias. Etiqueta heurística, no probabilidad.';
COMMENT ON COLUMN clean.v_dim_proveedor.situacion_69b IS
'Situaciones publicadas en el listado 69-B para los registros que coinciden. Sin fecha de publicación: no afirmar la situación vigente.';

COMMENT ON VIEW clean.v_dim_institucion IS
'Dimensión institución (T6): una fila por clave_institucion. Solo ComprasMX trae institución; el histórico no tiene filas aquí.';
COMMENT ON COLUMN clean.v_dim_institucion.clave_institucion IS
'Llave de la dimensión: clave de la institución publicada por ComprasMX.';
COMMENT ON COLUMN clean.v_dim_institucion.institucion IS
'Nombre de la institución. Si la clave tiene varios nombres, se muestra uno (ver nombres_publicados).';
COMMENT ON COLUMN clean.v_dim_institucion.nombres_publicados IS
'Cuántos nombres distintos tiene la clave; más de uno es una inconsistencia de la fuente por revisar.';
COMMENT ON COLUMN clean.v_dim_institucion.siglas_de_la_institucion IS
'Siglas publicadas de la institución.';
COMMENT ON COLUMN clean.v_dim_institucion.tipo_de_institucion IS
'Tipo de institución publicado por ComprasMX.';
COMMENT ON COLUMN clean.v_dim_institucion.clave_ramo IS
'Clave del ramo presupuestario publicada por ComprasMX.';
COMMENT ON COLUMN clean.v_dim_institucion.descripcion_ramo IS
'Descripción del ramo presupuestario publicada por ComprasMX.';

COMMENT ON VIEW clean.v_dim_fecha IS
'Dimensión fecha (T6): una fila por fecha de inicio válida presente en los contratos. Los años 2010, 2023 y 2024 del histórico están incompletos y no hay 2025.';
COMMENT ON COLUMN clean.v_dim_fecha.fecha IS
'Llave de la dimensión: fecha de inicio del contrato.';
COMMENT ON COLUMN clean.v_dim_fecha.anio IS
'Año calendario de la fecha de inicio.';
COMMENT ON COLUMN clean.v_dim_fecha.trimestre IS
'Trimestre calendario, de 1 a 4.';
COMMENT ON COLUMN clean.v_dim_fecha.mes IS
'Mes calendario, de 1 a 12.';
COMMENT ON COLUMN clean.v_dim_fecha.anio_mes IS
'Año y mes en formato AAAA-MM, para agrupar por mes.';

COMMENT ON VIEW clean.v_dim_procedimiento IS
'Dimensión procedimiento (T6): los valores de tipo_procedimiento_norm. La clasificación es preliminar: todas las reglas del seed están pendientes.';
COMMENT ON COLUMN clean.v_dim_procedimiento.tipo_procedimiento_norm IS
'Llave de la dimensión: valor normalizado del tipo de procedimiento.';
COMMENT ON COLUMN clean.v_dim_procedimiento.nombre IS
'Nombre legible del tipo de procedimiento.';
COMMENT ON COLUMN clean.v_dim_procedimiento.es_competitivo IS
'Verdadero para la licitación pública, falso para adjudicación directa e invitación, nulo para otro y sin dato. Provisional.';

GRANT SELECT ON clean.v_hecho_contrato, clean.v_dim_proveedor, clean.v_dim_institucion,
    clean.v_dim_fecha, clean.v_dim_procedimiento TO agent_ro;
