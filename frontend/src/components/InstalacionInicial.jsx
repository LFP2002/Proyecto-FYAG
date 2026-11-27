import React, { useEffect, useRef, useState } from 'react';
import { authClient } from '../auth/client.js';

const fields = [
  ['first_name', 'Nombre', 'text', 'given-name', 150],
  ['last_name', 'Apellidos', 'text', 'family-name', 150],
  ['username', 'Nombre de usuario', 'text', 'username', 150],
  ['email', 'Correo electrónico', 'email', 'email', 254],
  ['password', 'Contraseña', 'password', 'new-password', 4096],
  ['password_confirm', 'Confirmar contraseña', 'password', 'new-password', 4096],
  ['clave_instalacion', 'Clave de instalación', 'password', 'off', 43],
];

export default function InstalacionInicial() {
  const [phase, setPhase] = useState('loading');
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  const [dark, setDark] = useState(() => globalThis.matchMedia?.('(prefers-color-scheme: dark)').matches ?? false);
  const inFlight = useRef(false);
  const heading = useRef(null);
  const alert = useRef(null);

  useEffect(() => {
    let active = true;
    authClient.initialSetupStatus().then(data => {
      if (active) setPhase(data?.pendiente === true ? 'ready' : data?.pendiente === false ? 'closed' : 'unavailable');
    }).catch(() => { if (active) setPhase('unavailable'); });
    return () => { active = false; };
  }, []);
  useEffect(() => { heading.current?.focus(); }, [phase]);
  useEffect(() => { if (error) alert.current?.focus(); }, [error]);
  useEffect(() => {
    const root = document.documentElement;
    root.dataset.fyagTheme = dark ? 'dark' : 'light';
    return () => { delete root.dataset.fyagTheme; };
  }, [dark]);

  async function submit(event) {
    event.preventDefault();
    if (inFlight.current) return;
    const form = event.currentTarget;
    const data = Object.fromEntries(new FormData(form));
    if (data.password !== data.password_confirm) {
      setError('Las contraseñas no coinciden.');
      return;
    }
    inFlight.current = true;
    setBusy(true);
    setError('');
    try {
      await authClient.submitInitialSetup(data);
      form.reset();
      setPhase('done');
    } catch (err) {
      const passwordMessage = err.fieldErrors?.password?.[0];
      setError(err.status === 409 ? 'No se autorizó el aprovisionamiento. Confirma que la instalación esté pendiente y solicita una clave vigente.'
        : err.status === 429 ? 'Se alcanzó el límite de solicitudes. Espera antes de volver a intentar.'
          : err.status === 400 ? passwordMessage || 'Revisa el nombre, apellidos, usuario, correo y contraseña.'
            : 'No se pudo completar la solicitud. Comprueba el estado al volver a abrir el asistente.');
    } finally {
      for (const name of ['password', 'password_confirm', 'clave_instalacion']) {
        const field = form.elements.namedItem(name);
        if (field) field.value = '';
      }
      inFlight.current = false;
      setBusy(false);
    }
  }

  return <main className="login-page"><section className="login-card" aria-labelledby="setup-title">
    <h1 id="setup-title" className="login-title" ref={heading} tabIndex={-1}>Configuración inicial de FYAG</h1>
    {phase === 'loading' && <p role="status">Comprobando el estado de la instalación…</p>}
    {phase === 'closed' && <p role="status">La configuración inicial no está disponible.</p>}
    {phase === 'unavailable' && <p role="alert">No se pudo consultar la instalación. Vuelve a cargar la página más tarde.</p>}
    {phase === 'done' && <p role="status">Cuenta TI creada. Ya puedes iniciar sesión. Si recibes un correo de verificación, sigue el enlace; verificar es voluntario.</p>}
    {phase === 'ready' && <form onSubmit={submit} aria-busy={busy}>
      <p className="login-sub">Crea la primera cuenta de Administración TI con la clave entregada por el operador de infraestructura.</p>
      {fields.map(([name, label, type, autoComplete, maxLength]) => <div className="mb-2" key={name}>
        <label htmlFor={`setup-${name}`}>{label}</label>
        <input id={`setup-${name}`} name={name} className="form-control" type={type} autoComplete={autoComplete}
          maxLength={maxLength} minLength={name === 'clave_instalacion' ? 43 : undefined} required disabled={busy} />
      </div>)}
      {error && <p ref={alert} tabIndex={-1} role="alert" className="alert alert-warning mt-3">{error}</p>}
      <button className="btn btn-fyag-primary w-100 mt-3" type="submit" disabled={busy}>{busy ? 'Creando cuenta…' : 'Crear cuenta TI'}</button>
    </form>}
    <p className="login-foot"><a href="/">Ir al inicio de sesión</a></p>
    <button type="button" className="btn btn-outline-secondary" aria-pressed={dark} onClick={() => setDark(value => !value)}>Tema oscuro</button>
  </section></main>;
}
