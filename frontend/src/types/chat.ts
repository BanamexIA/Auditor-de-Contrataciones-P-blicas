export type ChatRole = 'user' | 'assistant';

/** Referencia a un informe PDF guardado en S3 (a través del backend). */
export interface ReportRef {
  documentId: string;
  title: string;
  fileName: string;
}

export interface ChatMessage {
  id: string;
  role: ChatRole;
  content: string;
  createdAt: string;
  /** Informe generado por el LLM a partir de esta respuesta, si lo hay. */
  report?: ReportRef;
  status?: 'pending' | 'error';
}

export interface ChatRequest {
  conversationId?: string;
  message: string;
  history: Array<Pick<ChatMessage, 'role' | 'content'>>;
  /** Documento abierto en el visor, para que el LLM lo use como contexto. */
  contextDocumentId?: string;
}

export interface ChatResponse {
  conversationId: string;
  message: ChatMessage;
  report?: ReportRef;
}
