import { ApiError, apiRequest } from '../httpClient';
import {
  toDocumentInfo,
  type AnnotationsDTO,
  type ConfirmUploadRequestDTO,
  type CreateDocumentRequestDTO,
  type CreateDocumentResponseDTO,
  type DocumentDTO,
  type PresignedUrlDTO,
  type UploadUrlRequestDTO,
} from '../contracts';
import type { DocumentsApi } from '../types';
import type { Annotation } from '../../types/annotations';

const enc = encodeURIComponent;

/** Sube el archivo directamente a S3 con la URL prefirmada que dio el backend. */
async function putToS3(target: PresignedUrlDTO, file: Blob): Promise<void> {
  const res = await fetch(target.url, {
    method: target.method,
    headers: { 'Content-Type': 'application/pdf', ...target.headers },
    body: file,
  });
  if (!res.ok) throw new ApiError(`S3 rechazó la subida (${res.status}).`, res.status);
}

export const httpDocumentsApi: DocumentsApi = {
  async getDocument(documentId) {
    return toDocumentInfo(await apiRequest<DocumentDTO>(`/documents/${enc(documentId)}`));
  },

  async downloadPdf(documentId) {
    const target = await apiRequest<PresignedUrlDTO>(`/documents/${enc(documentId)}/download-url`);
    const res = await fetch(target.url, { headers: target.headers });
    if (!res.ok) throw new ApiError(`No se pudo descargar el PDF de S3 (${res.status}).`, res.status);
    return new Uint8Array(await res.arrayBuffer());
  },

  async createDocument(file, title, fileName) {
    const body: CreateDocumentRequestDTO = {
      title,
      file_name: fileName,
      content_type: 'application/pdf',
      size_bytes: file.size,
    };
    const created = await apiRequest<CreateDocumentResponseDTO>('/documents', { method: 'POST', body });
    await putToS3(created.upload, file);
    const confirm: ConfirmUploadRequestDTO = { s3_key: created.upload.s3_key, size_bytes: file.size };
    const doc = await apiRequest<DocumentDTO>(
      `/documents/${enc(created.document.document_id)}/original`,
      { method: 'POST', body: confirm },
    );
    return toDocumentInfo(doc);
  },

  async uploadVersion(documentId, file, fileName) {
    const req: UploadUrlRequestDTO = { file_name: fileName, content_type: 'application/pdf', size_bytes: file.size };
    const target = await apiRequest<PresignedUrlDTO>(`/documents/${enc(documentId)}/upload-url`, {
      method: 'POST',
      body: req,
    });
    await putToS3(target, file);
    const confirm: ConfirmUploadRequestDTO = { s3_key: target.s3_key, size_bytes: file.size };
    const doc = await apiRequest<DocumentDTO>(`/documents/${enc(documentId)}/versions`, {
      method: 'POST',
      body: confirm,
    });
    return toDocumentInfo(doc);
  },

  async getAnnotations(documentId) {
    const dto = await apiRequest<AnnotationsDTO>(`/documents/${enc(documentId)}/annotations`);
    return dto.annotations as Annotation[];
  },

  async saveAnnotations(documentId, annotations) {
    const body: AnnotationsDTO = { annotations };
    await apiRequest<AnnotationsDTO>(`/documents/${enc(documentId)}/annotations`, { method: 'PUT', body });
  },
};
