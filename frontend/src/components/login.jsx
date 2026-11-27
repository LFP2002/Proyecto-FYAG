import React, { useState } from 'react';
import { useAuth } from '../auth/AuthContext';
import { Icon } from './ui';

export default function Login({ setupCreated = false }) {
  const { login, logout, completeFirstPasswordChange, status, notice } = useAuth();
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [firstPassword, setFirstPassword] = useState('');
  const [firstPasswordAgain, setFirstPasswordAgain] = useState('');
  const [firstError, setFirstError] = useState('');
  const [firstBusy, setFirstBusy] = useState(false);
  const busy = status === 'authenticating' || status === 'logging-out';
  const changingFirstPassword = status === 'password-change-required';

  const handleSubmit = async (event) => {
    event.preventDefault();
    if (busy) return;
    try { await login({ email, password }); } catch { /* El contexto muestra el error seguro. */ }
    finally { setPassword(''); }
  };

  const handleFirstPassword = async (event) => {
    event.preventDefault();
    if (firstBusy) return;
    setFirstError('');
    if (firstPassword !== firstPasswordAgain) { setFirstError('Las contraseñas no coinciden.'); return; }
    setFirstBusy(true);
    try { await completeFirstPasswordChange(firstPassword); setFirstPassword(''); setFirstPasswordAgain(''); }
    catch (error) { setFirstError(error?.fieldErrors?.nueva_clave?.join(' ') || error.message); setFirstPassword(''); setFirstPasswordAgain(''); }
    finally { setFirstBusy(false); }
  };

  if (changingFirstPassword) return <main className="login-page"><form className="login-card" onSubmit={handleFirstPassword} aria-busy={firstBusy}>
    <Icon d="M12 2v20M4.2 7l15.6 10M4.2 17L19.8 7M9 3.5l3 2.5 3-2.5M9 20.5l3-2.5 3 2.5" className="logo-l" />
    <h1 className="login-title">Crear contraseña personal</h1>
    <p className="login-sub">La credencial temporal solo permite este cambio. Al confirmarlo, inicia sesión de nuevo con tu contraseña personal.</p>
    {notice && <div role="status" className="alert alert-info mt-3">{notice}</div>}
    <label htmlFor="first-password">Nueva contraseña</label>
    <input id="first-password" className="form-control" type="password" autoComplete="new-password" value={firstPassword} onChange={e=>setFirstPassword(e.target.value)} required disabled={firstBusy} maxLength={4096}/>
    <label htmlFor="first-password-confirm" className="mt-3">Confirmar contraseña</label>
    <input id="first-password-confirm" className="form-control" type="password" autoComplete="new-password" value={firstPasswordAgain} onChange={e=>setFirstPasswordAgain(e.target.value)} required disabled={firstBusy} maxLength={4096}/>
    {firstError && <div role="alert" className="alert alert-warning mt-3">{firstError}</div>}
    <button type="submit" disabled={firstBusy} className="btn btn-fyag-primary w-100 mt-3">{firstBusy ? 'Confirmando…' : 'Guardar contraseña personal'}</button>
  </form></main>;
  return (
    <main className="login-page">
      <form className="login-card" onSubmit={handleSubmit} aria-busy={busy}>
        <Icon d="M12 2v20M4.2 7l15.6 10M4.2 17L19.8 7M9 3.5l3 2.5 3-2.5M9 20.5l3-2.5 3 2.5" className="logo-l" />
        <h1 className="login-title">FYAG</h1>
        <p className="login-sub">Sistema de Gestión de Obras y Presupuestos</p>
        {setupCreated && status === 'anonymous' && !notice && <p role="status" className="alert alert-info mt-3">Cuenta TI creada. Ya puedes iniciar sesión. La verificación por correo es voluntaria.</p>}
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
        <p className="login-foot"><a href="/verificar-correo">Verificar mi correo electrónico</a></p>
        <p className="login-foot"><a href="/restablecer-clave">¿Olvidaste tu contraseña?</a></p>
      </form>
    </main>
  );
}
