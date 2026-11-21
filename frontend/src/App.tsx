import { useCallback, useEffect, useState } from 'react';
import { auth } from './api/auditor';
import { session } from './api/client';
import { SplitPane } from './components/SplitPane';
import { Login } from './features/auth/Login';
import { ChatPanel } from './features/chat/ChatPanel';
import { PdfWorkspace } from './features/pdf/PdfWorkspace';
import { SenalesPanel } from './features/senales/SenalesPanel';
import type { ReporteRef, Usuario } from './types/auditor';

type Sesion =
  | { estado: 'cargando' }
  | { estado: 'sin_sesion'; aviso?: string }
  | { estado: 'lista'; usuario: Usuario | null }
  | { estado: 'error'; mensaje: string };

type Pestana = 'reporte' | 'senales';

export default function App() {
  const [sesion, setSesion] = useState<Sesion>({ estado: 'cargando' });
  const [reporte, setReporte] = useState<ReporteRef | null>(null);
  const [pestana, setPestana] = useState<Pestana>('reporte');

  const iniciar = useCallback(async () => {
    setSesion({ estado: 'cargando' });
    try {
      if (!(await auth.requiereSesion())) {
        setSesion({ estado: 'lista', usuario: null }); // backend de desarrollo sin AUTH_SECRET
        return;
      }
      if (!session.token) {
        setSesion({ estado: 'sin_sesion' });
        return;
      }
      setSesion({ estado: 'lista', usuario: await auth.yo() });
    } catch (err) {
      if (!session.token) setSesion({ estado: 'sin_sesion' });
      else setSesion({ estado: 'error', mensaje: (err as Error).message });
    }
  }, []);

  useEffect(() => {
    session.onUnauthorized(() => setSesion({ estado: 'sin_sesion', aviso: 'Tu sesión terminó. Vuelve a entrar.' }));
    void iniciar();
  }, [iniciar]);

  const abrirReporte = useCallback((r: ReporteRef) => {
    setReporte(r);
    setPestana('reporte');
  }, []);

  const salir = () => {
    auth.logout();
    setReporte(null);
    setSesion({ estado: 'sin_sesion' });
  };

  if (sesion.estado === 'cargando') return <div className="viewer-status">Conectando con el backend…</div>;
  if (sesion.estado === 'error')
    return (
      <div className="login">
        <div className="login-card">
          <p className="login-error">{sesion.mensaje}</p>
          <button className="btn primary" onClick={() => void iniciar()}>
            Reintentar
          </button>
        </div>
      </div>
    );
  if (sesion.estado === 'sin_sesion')
    return <Login aviso={sesion.aviso} onLogin={(usuario) => setSesion({ estado: 'lista', usuario })} />;

  return (
    <div className="app">
      <SplitPane
        left={
          <ChatPanel
            usuario={sesion.usuario}
            reporteActivo={reporte}
            onOpenReporte={abrirReporte}
            onLogout={sesion.usuario ? salir : undefined}
          />
        }
        right={
          <div className="derecha">
            <nav className="pestanas" role="tablist">
              <button role="tab" aria-selected={pestana === 'reporte'} className={pestana === 'reporte' ? 'active' : ''} onClick={() => setPestana('reporte')}>
                Reporte
              </button>
              <button role="tab" aria-selected={pestana === 'senales'} className={pestana === 'senales' ? 'active' : ''} onClick={() => setPestana('senales')}>
                Señales y decisión
              </button>
            </nav>
            {/* El visor se mantiene montado para no recargar el PDF al cambiar de pestaña. */}
            <div className="pestana" hidden={pestana !== 'reporte'}>
              <PdfWorkspace reporte={reporte} />
            </div>
            <div className="pestana" hidden={pestana !== 'senales'}>
              <SenalesPanel casoId={reporte?.casoId ?? null} />
            </div>
          </div>
        }
      />
    </div>
  );
}
