CREATE TABLE IF NOT EXISTS staging.contratos (
    codigo_contrato TEXT,
    codigo_expediente TEXT,
    rfc TEXT,
    proveedor TEXT,
    titulo_contrato TEXT,
    descripcion_contrato TEXT,
    contract_type TEXT,
    tipo_contratacion TEXT,
    tipo_expediente TEXT,
    importe NUMERIC,
    moneda TEXT,
    fecha_inicio DATE,
    fecha_fin DATE,
    fecha_inicio_estado TEXT,
    tipo_procedimiento TEXT,
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
    fuente TEXT,
    proveedor_normalizado TEXT,
    _source_file TEXT,
    _loaded_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

ALTER TABLE staging.contratos
    ADD COLUMN IF NOT EXISTS rfc TEXT,
    ADD COLUMN IF NOT EXISTS fecha_inicio_estado TEXT,
    ADD COLUMN IF NOT EXISTS tipo_procedimiento TEXT,
    ADD COLUMN IF NOT EXISTS ley TEXT,
    ADD COLUMN IF NOT EXISTS institucion TEXT,
    ADD COLUMN IF NOT EXISTS clave_institucion TEXT,
    ADD COLUMN IF NOT EXISTS siglas_de_la_institucion TEXT,
    ADD COLUMN IF NOT EXISTS tipo_de_institucion TEXT,
    ADD COLUMN IF NOT EXISTS clave_ramo TEXT,
    ADD COLUMN IF NOT EXISTS descripcion_ramo TEXT,
    ADD COLUMN IF NOT EXISTS clave_de_la_uc TEXT,
    ADD COLUMN IF NOT EXISTS nombre_de_la_uc TEXT,
    ADD COLUMN IF NOT EXISTS numero_de_procedimiento TEXT,
    ADD COLUMN IF NOT EXISTS caracter_del_procedimiento TEXT,
    ADD COLUMN IF NOT EXISTS articulo_de_excepcion TEXT,
    ADD COLUMN IF NOT EXISTS descripcion_excepcion TEXT,
    ADD COLUMN IF NOT EXISTS fuente TEXT;

CREATE TABLE IF NOT EXISTS staging.listado_69b (
    rfc TEXT,
    nombre_del_contribuyente TEXT,
    situacion_del_contribuyente TEXT,
    _source_file TEXT,
    _loaded_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS staging.rechazados (
    source_table TEXT,
    motivo TEXT,
    raw_payload JSONB,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_staging_contratos_proveedor ON staging.contratos (proveedor);
CREATE INDEX IF NOT EXISTS idx_staging_contratos_rfc ON staging.contratos (rfc);
CREATE INDEX IF NOT EXISTS idx_staging_contratos_fecha ON staging.contratos (fecha_inicio, fecha_fin);
CREATE INDEX IF NOT EXISTS idx_staging_69b_rfc ON staging.listado_69b (rfc);
