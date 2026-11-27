import React, { useLayoutEffect, useRef, useState } from 'react';
import { authClient } from '../auth/client.js';

export default function VerificacionCorreo() {
  const [token, setToken] = useState(() => new URLSearchParams(window.location.hash.slice(1)).get('token') || '');
  const [email, setEmail] = useState('');
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState('');
  const [error, setError] = useState('');
  const pending = useRef(false);
  const heading = useRef(null);
  useLayoutEffect(() => {
    if (window.location.hash) window.history.replaceState(null, '', window.location.pathname);
    heading.current?.focus();
  }, []);

  async function submit(event) {
    event.preventDefault();
    if (pending.current) return;
    pending.current = true;
    setBusy(true);
    setError('');
    setResult('');
    try {
      if (token) {
        await authClient.submitEmailVerification('confirmar', token);
        setToken('');
        setResult('Correo confirmado. Si cambiaste tu dirección, vuelve a iniciar sesión con el correo nuevo.');
      } else {
        await authClient.submitEmailVerification('enviar', email.trim());
        setResult('Si corresponde verificar esa dirección, recibirás las instrucciones por correo.');
      }
    } catch (err) {
      if (err.status === 400 && token) {
        setToken('');
        setError('El enlace de verificación no es válido o ha vencido. Solicita otro enlace para el correo actual, o pide a TI el reenvío de un cambio pendiente.');
      } else if (err.status === 429) setError('Se alcanzó el límite de solicitudes. Espera antes de volver a intentar.');
      else setError('No se pudo completar la solicitud. Intenta más tarde.');
    } finally {
      pending.current = false;
      setBusy(false);
    }
  }

  return <main className="login-page"><form className="login-card" onSubmit={submit} aria-busy={busy}>
    <h1 className="login-title" tabIndex={-1} ref={heading}>Verificar correo</h1>
    {token ? <p className="login-sub">Confirma la titularidad de la dirección asociada al enlace. Esto no inicia una sesión.</p> : <>
      <p className="login-sub">Solicita un enlace para verificar tu dirección de acceso actual.</p>
      <label htmlFor="verification-email">Correo electrónico</label>
      <input id="verification-email" className="form-control" type="email" autoComplete="email" required maxLength={254}
        value={email} onChange={event => setEmail(event.target.value)} disabled={busy}/>
    </>}
    {result && <p role="status" className="alert alert-info mt-3">{result}</p>}
    {error && <p role="alert" className="alert alert-warning mt-3">{error}</p>}
    <button className="btn btn-fyag-primary w-100 mt-3" type="submit" disabled={busy}>
      {busy ? 'Procesando…' : token ? 'Confirmar correo' : 'Solicitar enlace'}
    </button>
    <p className="login-foot"><a href="/">Volver a FYAG</a></p>
  </form></main>;
}
