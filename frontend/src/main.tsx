import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';
import { AuthProvider } from 'react-oidc-context';
import App from './App';
import { auth } from './api/auditor';
import { configuracionOidc, type CognitoPublico } from './features/auth/cognito';
import './styles/base.css';
import './styles/chat.css';
import './styles/viewer.css';
import './styles/auditor.css';

const root = createRoot(document.getElementById('root')!);

// El backend dice en /health si hay Cognito; así el mismo front sirve con o sin él.
async function arrancar() {
  let cognito: CognitoPublico | null = null;
  try {
    cognito = (await auth.salud()).cognito ?? null;
  } catch {
    // Sin /health no se sabe si hay Cognito: mostrar el login local aquí confundiría.
    // Recargar vuelve a leer la configuración cuando el backend (o el túnel) regrese.
    root.render(
      <div className="login">
        <div className="login-card">
          <h1>Auditor de contrataciones</h1>
          <p className="login-error">
            No hay conexión con el backend. Revisa que el túnel SSH siga abierto (o que BACKEND_URL apunte al puerto
            correcto) y que el backend esté encendido.
          </p>
          <button className="btn primary" onClick={() => window.location.reload()}>
            Reintentar
          </button>
        </div>
      </div>,
    );
    return;
  }
  root.render(
    <StrictMode>
      {cognito ? (
        <AuthProvider {...configuracionOidc(cognito)}>
          <App cognito={cognito} />
        </AuthProvider>
      ) : (
        <App cognito={null} />
      )}
    </StrictMode>,
  );
}

void arrancar();
