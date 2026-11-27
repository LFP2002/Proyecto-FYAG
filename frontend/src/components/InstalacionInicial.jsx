import React, { useEffect, useRef, useState } from 'react';

const fields = [
  ['first_name', 'Nombre', 'text', 'given-name', 150],
  ['last_name', 'Apellidos', 'text', 'family-name', 150],
  ['username', 'Nombre de usuario', 'text', 'username', 150],
  ['email', 'Correo electrónico', 'email', 'email', 254],
  ['password', 'Contraseña', 'password', 'new-password', 4096],
  ['password_confirm', 'Confirmar contraseña', 'password', 'new-password', 4096],
  ['clave_instalacion', 'Clave de instalación', 'password', 'off', 43],
];

export default function InstalacionInicial({ client, onCreated }) {
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  const inFlight = useRef(false);
  const intro = useRef(null);
  const alert = useRef(null);

  useEffect(() => { intro.current?.focus(); }, []);
  useEffect(() => { if (error) alert.current?.focus(); }, [error]);

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
      await client.submitInitialSetup(data);
      form.reset();
    } catch (err) {
      const passwordMessage = err.fieldErrors?.password?.[0];
      setError(err.status === 409 ? 'No se autorizó el aprovisionamiento. Confirma que la instalación esté pendiente y solicita una clave vigente.'
        : err.status === 429 ? 'Se alcanzó el límite de solicitudes. Espera antes de volver a intentar.'
          : err.status === 400 ? passwordMessage || 'Revisa el nombre, apellidos, usuario, correo y contraseña.'
             : 'No se pudo completar la solicitud. Comprueba el estado al volver a abrir el asistente.');
      return;
    } finally {
      for (const name of ['password', 'password_confirm', 'clave_instalacion']) {
        const field = form.elements.namedItem(name);
        if (field) field.value = '';
      }
      inFlight.current = false;
      setBusy(false);
    }
    onCreated();
  }

  return <form onSubmit={submit} aria-busy={busy}>
      <p ref={intro} tabIndex={-1} className="login-sub">Crea la primera cuenta de Administración TI con la clave entregada por el operador de infraestructura.</p>
      {fields.map(([name, label, type, autoComplete, maxLength]) => <div className="mb-2" key={name}>
        <label htmlFor={`setup-${name}`}>{label}</label>
        <input id={`setup-${name}`} name={name} className="form-control" type={type} autoComplete={autoComplete}
          maxLength={maxLength} minLength={name === 'clave_instalacion' ? 43 : undefined} required disabled={busy} />
      </div>)}
      {error && <p ref={alert} tabIndex={-1} role="alert" className="alert alert-warning mt-3">{error}</p>}
      <button className="btn btn-fyag-primary w-100 mt-3" type="submit" disabled={busy}>{busy ? 'Creando cuenta…' : 'Crear cuenta TI'}</button>
  </form>;
}
