import { useState, type FormEvent } from 'react';
import { auth } from '../../api/auditor';
import type { Usuario } from '../../types/auditor';

interface LoginProps {
  onLogin: (u: Usuario) => void;
  aviso?: string | null;
  /** Solo si el backend tiene Cognito: redirige a la página de inicio de sesión de Cognito. */
  onEntrarCognito?: () => void;
  /** Cierra la sesión de Cognito para que el siguiente «Entrar» pida otra cuenta. */
  onCambiarCuenta?: () => void;
}

/** Inicio de sesión: cuenta del equipo (Cognito) si existe; usuario y contraseña locales como respaldo. */
export function Login({ onLogin, aviso, onEntrarCognito, onCambiarCuenta }: LoginProps) {
  const [usuario, setUsuario] = useState('');
  const [contrasena, setContrasena] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [enviando, setEnviando] = useState(false);
  const [local, setLocal] = useState(!onEntrarCognito);

  const enviar = async (e: FormEvent) => {
    e.preventDefault();
    setEnviando(true);
    setError(null);
    try {
      onLogin(await auth.login(usuario.trim().toLowerCase(), contrasena));
    } catch (err) {
      setError((err as Error).message);
      setContrasena('');
    } finally {
      setEnviando(false);
    }
  };

  return (
    <div className="login">
      <form className="login-card" onSubmit={enviar}>
        <div className="panel-title">
          <span className="brand-dot" />
          <h1>Auditor de contrataciones</h1>
        </div>
        {aviso && <p className="login-aviso">{aviso}</p>}

        {onEntrarCognito && (
          <>
            <p className="muted">Entra con la cuenta que te dio el equipo.</p>
            <button className="btn primary" type="button" onClick={onEntrarCognito}>
              Entrar con la cuenta del equipo
            </button>
            {onCambiarCuenta && (
              <button className="link" type="button" onClick={onCambiarCuenta} title="Cierra la sesión de Cognito en este navegador">
                Entrar con otra cuenta
              </button>
            )}
            {!local && (
              <button className="link" type="button" onClick={() => setLocal(true)}>
                Usar usuario y contraseña locales
              </button>
            )}
          </>
        )}

        {local && (
          <>
            {onEntrarCognito ? (
              <p className="muted login-separador">O con un usuario local del sistema:</p>
            ) : (
              <p className="muted">Inicia sesión con el usuario que te dio el administrador.</p>
            )}
            <label>
              Usuario
              <input value={usuario} onChange={(e) => setUsuario(e.target.value)} autoComplete="username" autoFocus={!onEntrarCognito} required />
            </label>
            <label>
              Contraseña
              <input
                type="password"
                value={contrasena}
                onChange={(e) => setContrasena(e.target.value)}
                autoComplete="current-password"
                required
              />
            </label>
            {error && <p className="login-error">{error}</p>}
            <button className={`btn ${onEntrarCognito ? 'ghost' : 'primary'}`} type="submit" disabled={enviando || !usuario.trim() || !contrasena}>
              {enviando ? 'Entrando…' : 'Entrar'}
            </button>
          </>
        )}
      </form>
    </div>
  );
}
