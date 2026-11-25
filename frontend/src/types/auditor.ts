/** Tipos de la API del backend (Flask). Referencia: docs/api.md en la raíz del repo. */

export interface Usuario {
  usuario: string;
  rol: 'auditor' | 'admin';
  nombre?: string | null;
}

export type EstadoCaso =
  | 'recibido'
  | 'consultado'
  | 'detectado'
  | 'normado'
  | 'reportado'
  | 'en_revision'
  | 'cerrado'
  | 'bloqueado';

export interface Caso {
  id: string;
  solicitud: string;
  estado: EstadoCaso;
  estado_previo: EstadoCaso | null;
  motivo_bloqueo: string | null;
  creado_por: string | null;
  created_at?: string;
  updated_at?: string;
}

export type Fila = Record<string, unknown>;

/** Evento de GET /casos/<id>/bitacora (contrato 5). */
export interface EventoBitacora {
  id: number;
  etapa: EstadoCaso;
  evento: string;
  detalle: Record<string, unknown>;
  modelo: string | null;
  equipo: string | null;
  created_at: string;
}

/** Respuesta de POST /demo/preguntar. */
export type RespuestaPregunta =
  | {
      tipo: 'sql';
      caso_id: string;
      sql: string;
      supuestos: string[];
      equipo: string;
      modelo: string;
      total_filas: number;
      filas: Fila[];
    }
  | { tipo: 'bloqueado'; caso_id: string; motivo: string; codigo: string };

/** Respuesta de POST /demo/casos/<id>/analizar. */
export type RespuestaAnalisis =
  | {
      caso_id: string;
      estado: 'en_revision';
      senales: number;
      evaluadas: number;
      no_evaluables: number;
      normas: number;
      narrativa_llm: boolean;
      rag: boolean;
      reporte: { version: number; formato: string; tamano_bytes: number; sha256: string };
    }
  | { caso_id: string; estado: 'bloqueado'; motivo: string; codigo: string };

export type Decision = 'relevante' | 'descartada' | 'pendiente';

/** Señal tal como la guarda Detección en audit.senales.datos. */
export interface DatosSenal {
  senal_id?: string;
  codigo?: string;
  nombre?: string;
  criterio?: string;
  umbral?: unknown;
  estado?: 'evaluada' | 'no_evaluable';
  nivel?: 'alto' | 'medio' | 'bajo' | null;
  confianza?: 'alta' | 'media' | 'baja' | null;
  valores_calculados?: Record<string, unknown>;
  contratos_ids?: string[];
  campos_faltantes?: string[];
  motivo?: string | null;
  [k: string]: unknown;
}

export interface Senal {
  id: string;
  tipo: string;
  datos: DatosSenal;
  created_at: string;
  decision: {
    decision: Decision;
    comentario: string | null;
    decidido_por: string | null;
    created_at: string;
  } | null;
}

/** Reporte abierto en el visor. */
export interface ReporteRef {
  casoId: string;
  version: number;
  titulo: string;
}
