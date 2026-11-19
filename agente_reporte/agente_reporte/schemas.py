"""Contratos de datos del Agente de Reporte.

- EntradaReporte: lo que entregan los agentes de Consulta, Detección y Normativo.
- NarrativaSenal / ResumenEjecutivoLLM: lo ÚNICO que se le pide al LLM (se valida con estos esquemas).
- Reporte: la salida final (JSON) que se entrega al backend.
"""
from __future__ import annotations

from typing import Any, Literal, Optional

from pydantic import BaseModel, Field


# --------------------------------------------------------------------------- ENTRADA
class Contrato(BaseModel):
    id: str
    proveedor: Optional[str] = None
    rfc: Optional[str] = None
    monto: Optional[float] = None
    moneda: str = "MXN"
    dependencia: Optional[str] = None
    tipo_procedimiento: Optional[str] = None
    fecha: Optional[str] = None
    fuente: Optional[str] = None


class Senal(BaseModel):
    codigo: str
    nombre: str
    criterio: str
    umbral: str
    valores_calculados: dict[str, Any] = Field(default_factory=dict)
    contratos_ids: list[str] = Field(default_factory=list)
    confianza: Literal["alta", "media", "baja"] = "alta"
    estado: Literal["activa", "no_evaluable"] = "activa"
    campos_faltantes: list[str] = Field(default_factory=list)


class FragmentoNorma(BaseModel):
    fragmento_id: str
    senal_codigo: Optional[str] = None  # señal a la que el agente Normativo asoció el fragmento
    norma: str
    articulo: str
    version: str
    vigencia: Optional[str] = None
    texto: str


class Excluido(BaseModel):
    contrato_id: str
    motivo: str


class Contradiccion(BaseModel):
    contrato_id: str
    campo: str
    valor_a: str
    fuente_a: str
    valor_b: str
    fuente_b: str


class ConcentracionProveedor(BaseModel):
    rfc: Optional[str] = None
    proveedor: str
    num_contratos: int
    monto_total: float
    porcentaje_monto: float  # 0-100
    porcentaje_adjudicaciones_directas: Optional[float] = None  # 0-100


class EntradaReporte(BaseModel):
    consulta_id: str
    version_reglas: str = "sin-version"
    contratos: list[Contrato] = Field(default_factory=list)
    senales: list[Senal] = Field(default_factory=list)
    normas_recuperadas: list[FragmentoNorma] = Field(default_factory=list)
    excluidos: list[Excluido] = Field(default_factory=list)
    contradicciones: list[Contradiccion] = Field(default_factory=list)
    concentracion: list[ConcentracionProveedor] = Field(default_factory=list)
    patrones_adjudicacion: dict[str, Any] = Field(default_factory=dict)


# --------------------------------------------------------------------------- SALIDA DEL LLM
class NarrativaSenal(BaseModel):
    narrativa: str = Field(min_length=20, max_length=1500)
    fragmento_ids: list[str] = Field(default_factory=list)


class ResumenEjecutivoLLM(BaseModel):
    texto: str = Field(min_length=20, max_length=2500)


# --------------------------------------------------------------------------- REPORTE FINAL
class Cita(BaseModel):
    fragmento_id: str
    norma: str
    articulo: str
    version: str


class SeccionSenal(BaseModel):
    codigo: str
    nombre: str
    estado: Literal["activa", "no_evaluable"]
    criterio: str
    umbral: str
    valores_calculados: dict[str, Any] = Field(default_factory=dict)
    contratos_ids: list[str] = Field(default_factory=list)
    confianza: Literal["alta", "media", "baja"]
    campos_faltantes: list[str] = Field(default_factory=list)
    narrativa: str
    narrativa_generada_por_llm: bool
    citas: list[Cita] = Field(default_factory=list)


class Limitacion(BaseModel):
    tipo: Literal[
        "registro_excluido",
        "dato_contradictorio",
        "senal_no_evaluable",
        "confianza_baja",
        "sin_norma_aplicable",
        "sin_senales",
        "verificacion",
    ]
    descripcion: str
    referencia: Optional[str] = None


class ResumenEjecutivo(BaseModel):
    texto: str = ""
    generado_por_llm: bool = False
    concentracion: list[ConcentracionProveedor] = Field(default_factory=list)
    patrones_adjudicacion: dict[str, Any] = Field(default_factory=dict)
    num_excluidos: int = 0
    num_senales_confianza_baja: int = 0


class Verificacion(BaseModel):
    total_citas: int
    citas_correctas: int
    tasa_citas_correctas: float
    citas_invalidas: list[str] = Field(default_factory=list)
    articulos_no_respaldados: list[str] = Field(default_factory=list)
    terminos_prohibidos: list[str] = Field(default_factory=list)
    numeros_no_respaldados: list[str] = Field(default_factory=list)  # advertencia, no bloquea
    aprobado: bool


class Reporte(BaseModel):
    consulta_id: str
    generado_en: str
    version_plantilla: str
    version_reglas: str
    modelo: str
    aviso: str
    contratos: list[Contrato] = Field(default_factory=list)
    contradicciones: list[Contradiccion] = Field(default_factory=list)
    senales: list[SeccionSenal] = Field(default_factory=list)
    limitaciones: list[Limitacion] = Field(default_factory=list)
    resumen_ejecutivo: Optional[ResumenEjecutivo] = None
    verificacion: Optional[Verificacion] = None
    trazabilidad: list[dict[str, Any]] = Field(default_factory=list)
