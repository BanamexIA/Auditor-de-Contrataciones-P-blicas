CREATE SCHEMA IF NOT EXISTS clean;

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

CREATE INDEX IF NOT EXISTS idx_clean_contratos_proveedor ON clean.contratos (proveedor_normalizado, fecha_inicio);
CREATE INDEX IF NOT EXISTS idx_clean_contratos_importe ON clean.contratos (importe);
CREATE INDEX IF NOT EXISTS idx_clean_contratos_tipo ON clean.contratos (tipo_contratacion, fecha_inicio);
CREATE INDEX IF NOT EXISTS idx_clean_69b_rfc ON clean.listado_69b (rfc);
CREATE INDEX IF NOT EXISTS idx_clean_69b_nombre ON clean.listado_69b (nombre_del_contribuyente);
