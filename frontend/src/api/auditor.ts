/** Llamadas al backend Flask. Contrato completo en docs/api.md (raíz del repo). */
import type {
  Caso,
  Decision,
  RespuestaAnalisis,
  RespuestaPregunta,
  Senal,
  Usuario,
} from '../types/auditor';
import type { CognitoPublico } from '../features/auth/cognito';
import { apiBytes, apiJson, session } from './client';

const enc = encodeURIComponent;

export const auth = {
  /** Estado de la autenticación del backend: si pide sesión y si acepta Cognito. */
  salud() {
    return apiJson<{ auth?: string; cognito?: CognitoPublico }>('/health');
  },

  /** Si el backend no tiene AUTH_SECRET (solo desarrollo), no pide sesión. */
  async requiereSesion(): Promise<boolean> {
    return (await auth.salud()).auth === 'activa';
  },

  async login(usuario: string, contrasena: string): Promise<Usuario> {
    const r = await apiJson<{ token: string; usuario: Usuario }>('/auth/login', {
      method: 'POST',
      body: { usuario, contrasena },
    });
    session.set(r.token);
    return r.usuario;
  },

  async yo(): Promise<Usuario> {
    return (await apiJson<{ usuario: Usuario }>('/auth/yo')).usuario;
  },

  logout() {
    session.set(null);
  },
};

export const auditor = {
  preguntar(pregunta: string, signal?: AbortSignal) {
    return apiJson<RespuestaPregunta>('/demo/preguntar', { method: 'POST', body: { pregunta }, signal });
  },

  analizar(casoId: string, narrativaLlm = false) {
    return apiJson<RespuestaAnalisis>(`/demo/casos/${enc(casoId)}/analizar`, {
      method: 'POST',
      body: { narrativa_llm: narrativaLlm },
    });
  },

  caso(casoId: string) {
    return apiJson<Caso>(`/casos/${enc(casoId)}`);
  },

  async senales(casoId: string): Promise<Senal[]> {
    return (await apiJson<{ senales: Senal[] }>(`/casos/${enc(casoId)}/senales`)).senales;
  },

  decidir(casoId: string, senalId: string, decision: Decision, comentario?: string) {
    return apiJson(`/casos/${enc(casoId)}/senales/${enc(senalId)}/decision`, {
      method: 'POST',
      body: { decision, comentario: comentario?.trim() || null },
    });
  },

  transitar(casoId: string, estado: string, motivo?: string) {
    return apiJson<Caso>(`/casos/${enc(casoId)}/transiciones`, {
      method: 'POST',
      body: motivo ? { estado, motivo } : { estado },
    });
  },

  /** Bytes del PDF vía backend (verificados con SHA-256); el navegador no lee S3 directo. */
  reportePdf(casoId: string, version: number, signal?: AbortSignal) {
    return apiBytes(`/casos/${enc(casoId)}/reportes/${version}/contenido`, signal);
  },
};
