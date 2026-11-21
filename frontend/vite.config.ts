import { defineConfig, loadEnv } from 'vite';
import react from '@vitejs/plugin-react';

// En desarrollo, /api se redirige al backend Flask (sin el prefijo /api, que las rutas
// del backend no llevan). El navegador habla con un solo origen: no hace falta CORS.
//   Local:  BACKEND_URL=http://localhost:5000
//   EC2:    BACKEND_URL=http://localhost:15000  (con el túnel SSH abierto)
export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, '.', '');
  const proxy = {
    target: env.BACKEND_URL || 'http://localhost:5000',
    changeOrigin: true,
    rewrite: (path: string) => path.replace(/^\/api/, ''),
    // El Agente Consulta corre en una laptop: una respuesta puede tardar minutos.
    timeout: 600_000,
    proxyTimeout: 600_000,
  };
  return {
    plugins: [react()],
    server: { port: 5173, proxy: { '/api': proxy } },
    preview: { port: 4173, proxy: { '/api': proxy } },
  };
});
