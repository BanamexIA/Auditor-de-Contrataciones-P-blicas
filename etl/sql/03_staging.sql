CREATE SCHEMA IF NOT EXISTS staging;

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
    proveedor_normalizado TEXT,
    _source_file TEXT,
    _loaded_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

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
