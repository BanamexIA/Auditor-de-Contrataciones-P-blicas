import { useState, type FormEvent } from 'react';
import { auth } from '../../api/auditor';
import type { Usuario } from '../../types/auditor';

/** Inicio de sesión sencillo: usuario y contraseña contra /auth/login del backend. */
export function Login({ onLogin, aviso }: { onLogin: (u: Usuario) => void; aviso?: string | null }) {
  const [usuario, setUsuario] = useState('');
  const [contrasena, setContrasena] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [enviando, setEnviando] = useState(false);

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
        <p className="muted">Inicia sesión con el usuario que te dio el administrador.</p>
        {aviso && <p className="login-aviso">{aviso}</p>}
        <label>
          Usuario
          <input value={usuario} onChange={(e) => setUsuario(e.target.value)} autoComplete="username" autoFocus required />
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
        <button className="btn primary" type="submit" disabled={enviando || !usuario.trim() || !contrasena}>
          {enviando ? 'Entrando…' : 'Entrar'}
        </button>
      </form>
    </div>
  );
}
