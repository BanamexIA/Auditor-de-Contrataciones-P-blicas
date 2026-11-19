/**
 * Contrato con el backend FastAPI (JSON en snake_case, como los modelos Pydantic).
 * Los mapeadores convierten a los tipos del front (camelCase).
 * La especificación completa de los endpoints está en docs/API_CONTRACT.md.
 */
import type { ChatMessage, ChatResponse, ReportRef } from '../types/chat';
import type { DocumentInfo } from '../types/documents';

export interface ChatRequestDTO {
  conversation_id?: string;
  message: string;
  history: Array<{ role: 'user' | 'assistant'; content: string }>;
  context_document_id?: string;
}

export interface ChatMessageDTO {
  id: string;
  role: 'user' | 'assistant';
  content: string;
  created_at: string;
}

export interface ReportRefDTO {
  document_id: string;
  title: string;
  file_name: string;
}

export interface ChatResponseDTO {
  conversation_id: string;
  message: ChatMessageDTO;
  report?: ReportRefDTO | null;
}

export interface DocumentDTO {
  document_id: string;
  title: string;
  file_name: string;
  size_bytes: number;
  version: number;
  created_at: string;
  updated_at: string;
}

/** URL prefirmada de S3 que entrega el backend (el front nunca ve credenciales). */
export interface PresignedUrlDTO {
  url: string;
  method: 'GET' | 'PUT';
  headers?: Record<string, string>;
  s3_key: string;
  expires_in: number;
}

export interface CreateDocumentRequestDTO {
  title: string;
  file_name: string;
  content_type: 'application/pdf';
  size_bytes: number;
}

export interface CreateDocumentResponseDTO {
  document: DocumentDTO;
  upload: PresignedUrlDTO;
}

export interface UploadUrlRequestDTO {
  file_name: string;
  content_type: 'application/pdf';
  size_bytes: number;
}

export interface ConfirmUploadRequestDTO {
  s3_key: string;
  size_bytes: number;
}

export interface AnnotationsDTO {
  /** Las anotaciones viajan tal cual (ver src/types/annotations.ts). */
  annotations: unknown[];
  updated_at?: string;
}

export const toReportRef = (dto: ReportRefDTO): ReportRef => ({
  documentId: dto.document_id,
  title: dto.title,
  fileName: dto.file_name,
});

export const toChatMessage = (dto: ChatMessageDTO, report?: ReportRef): ChatMessage => ({
  id: dto.id,
  role: dto.role,
  content: dto.content,
  createdAt: dto.created_at,
  report,
});

export const toChatResponse = (dto: ChatResponseDTO): ChatResponse => {
  const report = dto.report ? toReportRef(dto.report) : undefined;
  return {
    conversationId: dto.conversation_id,
    message: toChatMessage(dto.message, report),
    report,
  };
};

export const toDocumentInfo = (dto: DocumentDTO): DocumentInfo => ({
  documentId: dto.document_id,
  title: dto.title,
  fileName: dto.file_name,
  sizeBytes: dto.size_bytes,
  version: dto.version,
  createdAt: dto.created_at,
  updatedAt: dto.updated_at,
});
