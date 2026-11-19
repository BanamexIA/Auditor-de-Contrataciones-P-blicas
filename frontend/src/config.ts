export const config = {
  useMock: (import.meta.env.VITE_USE_MOCK ?? 'true') !== 'false',
  apiBaseUrl: (import.meta.env.VITE_API_BASE_URL ?? '/api').replace(/\/$/, ''),
  /** Espera antes de guardar automáticamente las anotaciones. */
  autosaveDelayMs: 1200,
} as const;
