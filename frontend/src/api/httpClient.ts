import { config } from '../config';

export class ApiError extends Error {
  constructor(
    message: string,
    readonly status: number,
    readonly detail?: unknown,
  ) {
    super(message);
    this.name = 'ApiError';
  }
}

interface RequestOptions {
  method?: 'GET' | 'POST' | 'PUT' | 'DELETE';
  body?: unknown;
  signal?: AbortSignal;
}

/** Cliente JSON mínimo para el backend FastAPI. */
export async function apiRequest<T>(path: string, options: RequestOptions = {}): Promise<T> {
  const { method = 'GET', body, signal } = options;
  let response: Response;
  try {
    response = await fetch(`${config.apiBaseUrl}${path}`, {
      method,
      signal,
      headers: body !== undefined ? { 'Content-Type': 'application/json' } : undefined,
      body: body !== undefined ? JSON.stringify(body) : undefined,
    });
  } catch (err) {
    if ((err as Error).name === 'AbortError') throw err;
    throw new ApiError('No se pudo conectar con el servidor.', 0, err);
  }

  if (!response.ok) {
    let detail: unknown;
    try {
      detail = await response.json();
    } catch {
      detail = await response.text().catch(() => undefined);
    }
    // FastAPI devuelve los errores como { "detail": ... }
    const msg =
      typeof detail === 'object' && detail && 'detail' in detail && typeof detail.detail === 'string'
        ? detail.detail
        : `Error ${response.status} en ${path}`;
    throw new ApiError(msg, response.status, detail);
  }

  if (response.status === 204) return undefined as T;
  return (await response.json()) as T;
}
