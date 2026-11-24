import type { AuthProviderProps } from 'react-oidc-context';

/** Lo que publica el backend en GET /health cuando Cognito está configurado (datos públicos). */
export interface CognitoPublico {
  authority: string;
  client_id: string;
  dominio: string | null;
}

/** Sin callbacks en la URL: Cognito redirige a la raíz del front. Debe estar en las
 *  "Allowed callback URLs" y "Allowed sign-out URLs" del app client. */
const raiz = () => `${window.location.origin}/`;

export function configuracionOidc(c: CognitoPublico): AuthProviderProps {
  return {
    authority: c.authority,
    client_id: c.client_id,
    redirect_uri: raiz(),
    post_logout_redirect_uri: raiz(),
    response_type: 'code', // Authorization Code + PKCE: el navegador no guarda ningún secreto
    scope: 'openid email',
    automaticSilentRenew: true,
    // Quita ?code=…&state=… de la barra de direcciones después de entrar.
    onSigninCallback: () => window.history.replaceState({}, document.title, window.location.pathname),
  };
}

/** Cierra la sesión también en Cognito (si no, el siguiente "Entrar" no pide contraseña). */
export function urlSalidaCognito(c: CognitoPublico): string | null {
  if (!c.dominio) return null;
  const q = new URLSearchParams({ client_id: c.client_id, logout_uri: raiz() });
  return `${c.dominio}/logout?${q.toString()}`;
}
