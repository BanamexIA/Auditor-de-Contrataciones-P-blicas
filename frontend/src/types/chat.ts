import type { Fila, ReporteRef } from './auditor';

export type ChatRole = 'user' | 'assistant';

/** Resultado del Agente Consulta asociado a una respuesta. */
export interface ResultadoConsulta {
  casoId: string;
  sql: string;
  supuestos: string[];
  totalFilas: number;
  filas: Fila[];
  modelo: string;
  equipo: string;
}

export interface ChatMessage {
  id: string;
  role: ChatRole;
  content: string;
  createdAt: string;
  status?: 'pending' | 'error' | 'aviso';
  /** Caso creado por la pregunta (también cuando quedó bloqueado). */
  casoId?: string;
  consulta?: ResultadoConsulta;
  /** Estado del análisis (Calidad, Detección, Normativo y Reportes) de ese caso. */
  analisis?: { estado: 'corriendo' } | { estado: 'listo'; reporte: ReporteRef; resumen: string } | { estado: 'error'; mensaje: string };
}
