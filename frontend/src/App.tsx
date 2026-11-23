import { useCallback, useEffect, useState } from 'react';
import { useAuth } from 'react-oidc-context';
import { auth } from './api/auditor';
import { ApiError, session } from './api/client';
import { SplitPane } from './components/SplitPane';
import { urlSalidaCognito, type CognitoPublico } from './features/auth/cognito';
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

/** Acciones de Cognito que la app necesita (solo existen si el backend lo tiene configurado). */
interface AccionesCognito {
  entrar: () => void;
  /** Cierra la sesión en Cognito y vuelve al front. */
  salir: () => void;
  /** Olvida el token sin salir de Cognito (p. ej. si el backend lo rechazó). */
  olvidar: () => void;
  error: string | null;
}

export default function App({ cognito }: { cognito: CognitoPublico | null }) {
  return cognito ? <AppConCognito cognito={cognito} /> : <AppBase cognito={null} />;
}

/** Pasa el token de Cognito a la misma sesión que usa el login local.
 *  Es el ID token: trae el correo verificado con el que el backend encuentra al usuario
 *  (en un pool que entra con correo, el username de Cognito es un UUID ilegible). */
function AppConCognito({ cognito }: { cognito: CognitoPublico }) {
  const oidc = useAuth();
  const token = oidc.user?.id_token ?? null;

  // Antes de montar AppBase, para que su primera llamada ya lleve el token.
  if (token && session.token !== token) session.set(token);

  if (oidc.isLoading || oidc.activeNavigator) return <div className="viewer-status">Conectando con la cuenta del equipo…</div>;

  const acciones: AccionesCognito = {
    entrar: () => void oidc.signinRedirect(),
    salir: () => {
      const url = urlSalidaCognito(cognito);
      void oidc.removeUser().finally(() => {
        if (url) window.location.href = url;
      });
    },
    olvidar: () => void oidc.removeUser(),
    error: oidc.error ? `No se pudo iniciar sesión con la cuenta del equipo: ${oidc.error.message}` : null,
  };
  // key: al cambiar el token (entrar, renovar, salir) AppBase vuelve a comprobar la sesión.
  return <AppBase key={token ?? 'sin-token'} cognito={acciones} />;
}

function AppBase({ cognito }: { cognito: AccionesCognito | null }) {
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
      // 401: p. ej. una cuenta de Cognito que no está dada de alta en el sistema; el backend dice por qué.
      if (err instanceof ApiError && err.status === 401) setSesion({ estado: 'sin_sesion', aviso: err.message });
      else if (!session.token) setSesion({ estado: 'sin_sesion' });
      else setSesion({ estado: 'error', mensaje: (err as Error).message });
    }
  }, []);

  useEffect(() => {
    session.onUnauthorized(() => {
      cognito?.olvidar();
      setSesion({ estado: 'sin_sesion', aviso: 'Tu sesión terminó. Vuelve a entrar.' });
    });
    void iniciar();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [iniciar]);

  const abrirReporte = useCallback((r: ReporteRef) => {
    setReporte(r);
    setPestana('reporte');
  }, []);

  const salir = () => {
    auth.logout();
    setReporte(null);
    setSesion({ estado: 'sin_sesion' });
    cognito?.salir();
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
    return (
      <Login
        aviso={cognito?.error ?? sesion.aviso}
        onLogin={(usuario) => setSesion({ estado: 'lista', usuario })}
        onEntrarCognito={cognito?.entrar}
      />
    );

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
