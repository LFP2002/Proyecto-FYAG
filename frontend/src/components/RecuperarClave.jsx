import React, { useLayoutEffect, useRef, useState } from 'react';
import { authClient } from '../auth/client.js';

const GENERICO = 'Si el correo electrónico corresponde a una cuenta habilitada para recuperación, recibirás las instrucciones para restablecer tu contraseña.';
const leerToken = () => new URLSearchParams(window.location.hash.slice(1)).get('token') || '';

export default function RecuperarClave() {
  const [token, setToken] = useState(leerToken);
  const [done, setDone] = useState(false);
  const [result, setResult] = useState('');
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  const pending = useRef(false);
  const title = useRef(null);
  const recoveryForm = useRef(null);

  useLayoutEffect(() => {
    if (window.location.hash) window.history.replaceState(null, '', window.location.pathname);
    title.current?.focus();
    const cambiarEnlace = () => {
      const next = leerToken();
      if (window.location.hash) window.history.replaceState(null, '', window.location.pathname);
      if (!next || pending.current) return;
      recoveryForm.current?.reset();
      setToken(next);
      setDone(false);
      setError('');
      setResult('');
      title.current?.focus();
    };
    window.addEventListener('hashchange', cambiarEnlace);
    return () => window.removeEventListener('hashchange', cambiarEnlace);
  }, []);

  async function submit(event) {
    event.preventDefault();
    if (pending.current) return;
    const form = event.currentTarget;
    const data = Object.fromEntries(new FormData(form));
    setError('');
    setResult('');
    if (token && data.nueva_clave !== data.confirmacion) {
      setError('Las contraseñas no coinciden.');
      return;
    }
    pending.current = true;
    setBusy(true);
    try {
      await authClient.submitPasswordRecovery(token ? 'confirmar' : 'solicitar', token ? { ...data, token } : data);
      form.reset();
      if (token) {
        setToken('');
        setDone(true);
      } else setResult(GENERICO);
    } catch (err) {
      if (err.status === 400 && token) {
        const message = err.fieldErrors?.nueva_clave?.[0];
        if (!message) setToken('');
        setError(message || 'El enlace de recuperación no es válido o ha vencido. Solicita uno nuevo.');
      } else if (err.status === 429) setError('Se alcanzó el límite de solicitudes. Espera antes de volver a intentar.');
      else setError('No se pudo completar la solicitud. Revisa tus datos o intenta más tarde.');
    } finally {
      if (token) form.reset();
      setBusy(false);
      pending.current = false;
    }
  }

  return <main className="login-page"><section className="login-card" aria-labelledby="recovery-title">
    <h1 id="recovery-title" className="login-title" ref={title} tabIndex={-1}>Restablecer contraseña</h1>
    {done ? <p role="status">Contraseña restablecida. Ya puedes iniciar sesión con tu nueva contraseña.</p> :
      <form key={token ? 'confirmar' : 'solicitar'} ref={recoveryForm} onSubmit={submit} aria-busy={busy}>
        {token ? <>
          <label htmlFor="recovery-password">Nueva contraseña</label>
          <input id="recovery-password" name="nueva_clave" className="form-control" type="password" autoComplete="new-password" required maxLength={4096} disabled={busy}/>
          <label htmlFor="recovery-confirm" className="mt-3">Confirmar contraseña</label>
          <input id="recovery-confirm" name="confirmacion" className="form-control" type="password" autoComplete="new-password" required maxLength={4096} disabled={busy}/>
        </> : <>
          <p className="login-sub">Introduce el correo verificado de tu cuenta.</p>
          <label htmlFor="recovery-email">Correo electrónico</label>
          <input id="recovery-email" name="email" className="form-control" type="email" autoComplete="email" required maxLength={254} disabled={busy}/>
        </>}
        {result && <p className="alert alert-info mt-3" role="status">{result}</p>}
        {error && <p className="alert alert-warning mt-3" role="alert">{error}</p>}
        <button className="btn btn-fyag-primary w-100 mt-3" type="submit" disabled={busy}>{busy ? 'Procesando…' : token ? 'Guardar nueva contraseña' : 'Solicitar enlace'}</button>
      </form>}
    <p className="login-foot"><a href="/">Volver al inicio de sesión</a></p>
  </section></main>;
}
