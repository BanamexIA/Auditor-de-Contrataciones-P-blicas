import type { Annotation } from '../types/annotations';
import type { ChatRequest, ChatResponse } from '../types/chat';
import type { DocumentInfo } from '../types/documents';

/** Conversación con el LLM. La implementación real llama a FastAPI. */
export interface LlmApi {
  sendMessage(request: ChatRequest, signal?: AbortSignal): Promise<ChatResponse>;
}

/**
 * Documentos PDF guardados en S3. El backend firma las URLs y el navegador
 * sube/descarga directamente contra S3.
 */
export interface DocumentsApi {
  getDocument(documentId: string): Promise<DocumentInfo>;
  /** Descarga el PDF original (sin anotaciones aplanadas). */
  downloadPdf(documentId: string): Promise<Uint8Array>;
  /** Sube un PDF nuevo (p. ej. uno abierto desde el equipo). */
  createDocument(file: Blob, title: string, fileName: string): Promise<DocumentInfo>;
  /** Sube una versión exportada (con anotaciones aplanadas) del documento. */
  uploadVersion(documentId: string, file: Blob, fileName: string): Promise<DocumentInfo>;
  getAnnotations(documentId: string): Promise<Annotation[]>;
  saveAnnotations(documentId: string, annotations: Annotation[]): Promise<void>;
}
