import type { EstadoCaso, Fila, ReporteRef } from './auditor';

export type ChatRole = 'user' | 'assistant';

/** Resultado del Agente Consulta asociado a una respuesta. */
export interface ResultadoConsulta {
  casoId: string;
  /** Solo llega para el rol admin; para los demás es null. */
  sql: string | null;
  supuestos: string[];
  totalFilas: number;
  filas: Fila[];
  modelo: string | null;
  equipo: string | null;
}

/** Avance del orquestador sobre el caso (se actualiza mientras corre). */
export interface Progreso {
  estado: EstadoCaso;
  segundos: number;
  /** Resumen de lo que ya se sabe, p. ej. "13 señales · 0 fragmentos de norma". */
  resumen?: string;
}

export interface ChatMessage {
  id: string;
  role: ChatRole;
  content: string;
  createdAt: string;
  status?: 'pending' | 'error' | 'aviso';
  /** Caso creado por la pregunta (también cuando quedó bloqueado). */
  casoId?: string;
  progreso?: Progreso;
  consulta?: ResultadoConsulta;
  reporte?: { ref: ReporteRef; resumen: string };
}
