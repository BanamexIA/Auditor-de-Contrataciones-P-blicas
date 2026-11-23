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
    /* backend caído: App muestra el error y permite reintentar */
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
