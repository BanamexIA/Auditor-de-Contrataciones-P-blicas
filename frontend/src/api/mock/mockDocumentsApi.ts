import type { DocumentsApi } from '../types';
import type { Annotation } from '../../types/annotations';
import type { DocumentInfo } from '../../types/documents';
import { ApiError } from '../httpClient';
import { newId, nowIso } from '../../lib/id';

/**
 * Simula el backend + S3 en memoria del navegador. Se pierde al recargar.
 * Mantiene la misma interfaz que la implementación HTTP.
 */
interface StoredDocument {
  info: DocumentInfo;
  original: Uint8Array;
  versions: Uint8Array[];
  annotations: Annotation[];
}

const store = new Map<string, StoredDocument>();
const latency = (ms = 150) => new Promise((r) => setTimeout(r, ms));

function get(documentId: string): StoredDocument {
  const doc = store.get(documentId);
  if (!doc) throw new ApiError('Documento no encontrado.', 404);
  return doc;
}

async function blobBytes(file: Blob): Promise<Uint8Array> {
  return new Uint8Array(await file.arrayBuffer());
}

/** Usado por el LLM simulado para "guardar en S3" el informe que genera. */
export function mockStorePdf(bytes: Uint8Array, title: string, fileName: string): DocumentInfo {
  const now = nowIso();
  const info: DocumentInfo = {
    documentId: newId('doc'),
    title,
    fileName,
    sizeBytes: bytes.byteLength,
    version: 0,
    createdAt: now,
    updatedAt: now,
  };
  store.set(info.documentId, { info, original: bytes, versions: [], annotations: [] });
  return info;
}

export const mockDocumentsApi: DocumentsApi = {
  async getDocument(documentId) {
    await latency();
    return { ...get(documentId).info };
  },

  async downloadPdf(documentId) {
    await latency(250);
    // Copia: pdf.js se queda con el buffer que recibe.
    return get(documentId).original.slice();
  },

  async createDocument(file, title, fileName) {
    await latency(300);
    return mockStorePdf(await blobBytes(file), title, fileName);
  },

  async uploadVersion(documentId, file) {
    await latency(400);
    const doc = get(documentId);
    doc.versions.push(await blobBytes(file));
    doc.info = { ...doc.info, version: doc.versions.length, updatedAt: nowIso() };
    return { ...doc.info };
  },

  async getAnnotations(documentId) {
    await latency();
    return structuredClone(get(documentId).annotations);
  },

  async saveAnnotations(documentId, annotations) {
    await latency(200);
    const doc = get(documentId);
    doc.annotations = structuredClone(annotations);
    doc.info = { ...doc.info, updatedAt: nowIso() };
  },
};
