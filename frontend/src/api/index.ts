import { config } from '../config';
import type { DocumentsApi, LlmApi } from './types';
import { httpLlmApi } from './http/httpLlmApi';
import { httpDocumentsApi } from './http/httpDocumentsApi';
import { mockLlmApi } from './mock/mockLlmApi';
import { mockDocumentsApi } from './mock/mockDocumentsApi';

/**
 * Punto único de acceso a los servicios. Para conectar FastAPI basta con
 * VITE_USE_MOCK=false; los componentes no cambian.
 */
export const llmApi: LlmApi = config.useMock ? mockLlmApi : httpLlmApi;
export const documentsApi: DocumentsApi = config.useMock ? mockDocumentsApi : httpDocumentsApi;

export type { DocumentsApi, LlmApi } from './types';
export { ApiError } from './httpClient';
