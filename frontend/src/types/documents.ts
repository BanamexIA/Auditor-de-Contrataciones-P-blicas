export interface DocumentInfo {
  documentId: string;
  title: string;
  fileName: string;
  sizeBytes: number;
  /** Número de versión del PDF exportado más reciente (0 = solo el original). */
  version: number;
  createdAt: string;
  updatedAt: string;
}
