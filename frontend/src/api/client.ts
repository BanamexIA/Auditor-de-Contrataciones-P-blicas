import { config } from '../config';

/** Error de la API con el formato del backend: {"error": {"codigo", "mensaje"}}. */
export class ApiError extends Error {
  constructor(
    message: string,
    readonly status: number,
    readonly codigo?: string,
  ) {
    super(message);
    this.name = 'ApiError';
  }
}

const TOKEN_KEY = 'auditor.token';
let token: string | null = (() => {
  try {
    return sessionStorage.getItem(TOKEN_KEY);
  } catch {
    return null;
  }
})();

/** Se llama cuando el backend responde 401: la sesión venció o el usuario fue dado de baja. */
let onUnauthorized: () => void = () => undefined;

export const session = {
  get token() {
    return token;
  },
  set(value: string | null) {
    token = value;
    try {
      if (value) sessionStorage.setItem(TOKEN_KEY, value);
      else sessionStorage.removeItem(TOKEN_KEY);
    } catch {
      /* almacenamiento no disponible: la sesión dura lo que la pestaña */
    }
  },
  onUnauthorized(handler: () => void) {
    onUnauthorized = handler;
  },
};

interface RequestOptions {
  method?: 'GET' | 'POST';
  body?: unknown;
  signal?: AbortSignal;
}

async function send(path: string, { method = 'GET', body, signal }: RequestOptions): Promise<Response> {
  const headers: Record<string, string> = {};
  if (body !== undefined) headers['Content-Type'] = 'application/json';
  if (token) headers.Authorization = `Bearer ${token}`;
  let response: Response;
  try {
    response = await fetch(`${config.apiBaseUrl}${path}`, {
      method,
      signal,
      headers,
      body: body !== undefined ? JSON.stringify(body) : undefined,
    });
  } catch (err) {
    if ((err as Error).name === 'AbortError') throw err;
    throw new ApiError('No se pudo conectar con el servidor. Revisa el túnel o que el backend esté encendido.', 0);
  }
  if (response.status === 401 && path !== '/auth/login') {
    session.set(null);
    onUnauthorized();
  }
  if (!response.ok) {
    let codigo: string | undefined;
    let mensaje = `Error ${response.status} en ${path}`;
    try {
      const data = await response.json();
      codigo = data?.error?.codigo;
      if (typeof data?.error?.mensaje === 'string') mensaje = data.error.mensaje;
      else if (typeof data?.motivo === 'string') mensaje = data.motivo;
    } catch {
      /* respuesta sin JSON */
    }
    throw new ApiError(mensaje, response.status, codigo);
  }
  return response;
}

/** Petición JSON. */
export async function apiJson<T>(path: string, options: RequestOptions = {}): Promise<T> {
  const response = await send(path, options);
  return (await response.json()) as T;
}

/** Petición binaria (PDF). */
export async function apiBytes(path: string, signal?: AbortSignal): Promise<Uint8Array> {
  const response = await send(path, { signal });
  return new Uint8Array(await response.arrayBuffer());
}
