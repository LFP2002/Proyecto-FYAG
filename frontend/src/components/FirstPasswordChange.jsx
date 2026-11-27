import React, { useState } from 'react';
import { useAuth } from '../auth/AuthContext.jsx';
import { Icon } from './ui';

export default function FirstPasswordChange() {
  const { completeFirstPasswordChange, notice, status } = useAuth();
  const [password, setPassword] = useState('');
  const [confirmation, setConfirmation] = useState('');
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);

  async function submit(event) {
    event.preventDefault();
    if (busy) return;
    setError('');
    if (password !== confirmation) { setError('Las contraseñas no coinciden.'); return; }
    if (!password || password.length > 4096) { setError('Ingresa una contraseña válida.'); return; }
    setBusy(true);
    try {
      await completeFirstPasswordChange(password);
      setPassword(''); setConfirmation('');
    } catch (cause) {
      setPassword(''); setConfirmation('');
      setError(cause?.fieldErrors?.nueva_clave?.join(' ') || cause.message || 'No se pudo confirmar el cambio.');
    } finally { setBusy(false); }
  }

  return <main className="login-page">
    <form className="login-card" onSubmit={submit} aria-busy={busy}>
      <Icon d="M12 2v20M4.2 7l15.6 10M4.2 17L19.8 7M9 3.5l3 2.5 3-2.5M9 20.5l3-2.5 3 2.5" className="logo-l" />
      <h1 className="login-title">Crear contraseña personal</h1>
      <p className="login-sub">El primer acceso con credencial temporal requiere una contraseña personal. Después tendrás que iniciar sesión nuevamente.</p>
      {notice && <div role="status" className="alert alert-info mt-3">{notice}</div>}
      <label htmlFor="first-password">Nueva contraseña</label>
      <input id="first-password" name="nueva_clave" className="form-control" type="password" autoComplete="new-password" value={password} onChange={e => setPassword(e.target.value)} required disabled={busy} maxLength={4096} />
      <label htmlFor="first-password-confirm" className="mt-3">Confirmar contraseña</label>
      <input id="first-password-confirm" name="confirmar_clave" className="form-control" type="password" autoComplete="new-password" value={confirmation} onChange={e => setConfirmation(e.target.value)} required disabled={busy} maxLength={4096} />
      {(error || status === 'password-change-required') && <div role="alert" className="alert alert-warning mt-3">{error || 'La credencial temporal no abre una sesión de trabajo. Define una contraseña personal para continuar.'}</div>}
      <button type="submit" disabled={busy} className="btn btn-fyag-primary w-100 mt-3">{busy ? 'Confirmando…' : 'Guardar contraseña personal'}</button>
      <p className="login-foot">La contraseña temporal se consume al confirmar el cambio.</p>
    </form>
  </main>;
}
