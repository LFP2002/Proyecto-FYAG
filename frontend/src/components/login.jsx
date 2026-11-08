import React, { useState } from 'react';
import { useAuth } from '../auth/AuthContext';
import { Icon } from './ui';

export default function Login() {
  const { login, logout, status, notice } = useAuth();
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const busy = status === 'authenticating' || status === 'logging-out';

  const handleSubmit = async (event) => {
    event.preventDefault();
    if (busy) return;
    try { await login({ email, password }); } catch { /* El contexto muestra el error seguro. */ }
    finally { setPassword(''); }
  };

  return (
    <main className="login-page">
      <form className="login-card" onSubmit={handleSubmit} aria-busy={busy}>
        <Icon d="M12 2v20M4.2 7l15.6 10M4.2 17L19.8 7M9 3.5l3 2.5 3-2.5M9 20.5l3-2.5 3 2.5" className="logo-l" />
        <h1 className="login-title">FYAG</h1>
        <p className="login-sub">Sistema de Gestión de Obras y Presupuestos</p>
        <label htmlFor="f-email">Correo electrónico</label>
        <input id="f-email" name="email" className="form-control" type="email" autoComplete="username"
          value={email} onChange={(e) => setEmail(e.target.value)} required disabled={busy} />
        <label htmlFor="f-pass">Contraseña</label>
        <input id="f-pass" name="password" className="form-control" type="password" autoComplete="current-password"
          value={password} onChange={(e) => setPassword(e.target.value)} required disabled={busy} />
        {notice && <div role="alert" className="alert alert-warning mt-3">{notice}</div>}
        <button type="submit" disabled={busy} className="btn btn-fyag-primary w-100 mt-3">
          {status === 'authenticating' ? 'Ingresando…' : status === 'logging-out' ? 'Cerrando sesión…' : 'Ingresar'}
        </button>
        {notice?.includes('revocación remota') && !busy && (
          <button type="button" className="btn btn-outline-secondary w-100 mt-2" onClick={() => void logout()}>Reintentar cierre de sesión</button>
        )}
        <p className="login-foot">Acceso con cuenta institucional</p>
      </form>
    </main>
  );
}
