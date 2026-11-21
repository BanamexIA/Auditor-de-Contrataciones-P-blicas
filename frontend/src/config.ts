export const config = {
  /** Prefijo de la API. En desarrollo, Vite redirige /api al backend Flask (ver vite.config.ts). */
  apiBaseUrl: (import.meta.env.VITE_API_BASE_URL ?? '/api').replace(/\/$/, ''),
  /** Espera antes de guardar automáticamente las notas del auditor. */
  autosaveDelayMs: 800,
} as const;
