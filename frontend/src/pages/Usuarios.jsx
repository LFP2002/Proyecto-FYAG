import React, { useEffect, useState } from 'react';
import { useAuth } from '../auth/AuthContext';
import { ROLES, ROLE_NOTE } from '../data/constants';
import { PageHead, Table } from '../components/ui';
import { Pager, useCommercial } from '../comercial/ui.jsx';
import { canManageUsers, userPath, usersPath, historyPath, readUser, readUsers, readHistory } from '../usuarios/api.js';
import { permissionRoles, permissionRows, permissionLevels } from '../usuarios/permissionMatrix.js';

// Bootstrap Icons v1.13.1 (MIT), twbs/icons; SVG originales incorporados localmente.
const tiIcons={
"eye": [
    {
      "d": "M16 8s-3-5.5-8-5.5S0 8 0 8s3 5.5 8 5.5S16 8 16 8M1.173 8a13 13 0 0 1 1.66-2.043C4.12 4.668 5.88 3.5 8 3.5s3.879 1.168 5.168 2.457A13 13 0 0 1 14.828 8q-.086.13-.195.288c-.335.48-.83 1.12-1.465 1.755C11.879 11.332 10.119 12.5 8 12.5s-3.879-1.168-5.168-2.457A13 13 0 0 1 1.172 8z"
    },
    {
      "d": "M8 5.5a2.5 2.5 0 1 0 0 5 2.5 2.5 0 0 0 0-5M4.5 8a3.5 3.5 0 1 1 7 0 3.5 3.5 0 0 1-7 0"
    }
  ],
  "none": [
    {
      "d": "M2 8a.5.5 0 0 1 .5-.5h11a.5.5 0 0 1 0 1h-11A.5.5 0 0 1 2 8",
      "rule": "evenodd"
    }
  ],
  "people": [
    {
      "d": "M15 14s1 0 1-1-1-4-5-4-5 3-5 4 1 1 1 1zm-7.978-1L7 12.996c.001-.264.167-1.03.76-1.72C8.312 10.629 9.282 10 11 10c1.717 0 2.687.63 3.24 1.276.593.69.758 1.457.76 1.72l-.008.002-.014.002zM11 7a2 2 0 1 0 0-4 2 2 0 0 0 0 4m3-2a3 3 0 1 1-6 0 3 3 0 0 1 6 0M6.936 9.28a6 6 0 0 0-1.23-.247A7 7 0 0 0 5 9c-4 0-5 3-5 4q0 1 1 1h4.216A2.24 2.24 0 0 1 5 13c0-1.01.377-2.042 1.09-2.904.243-.294.526-.569.846-.816M4.92 10A5.5 5.5 0 0 0 4 13H1c0-.26.164-1.03.76-1.724.545-.636 1.492-1.256 3.16-1.275ZM1.5 5.5a3 3 0 1 1 6 0 3 3 0 0 1-6 0m3-2a2 2 0 1 0 0 4 2 2 0 0 0 0-4"
    }
  ],
  "manage": [
    {
      "d": "M8 15A7 7 0 1 1 8 1a7 7 0 0 1 0 14m0 1A8 8 0 1 0 8 0a8 8 0 0 0 0 16"
    },
    {
      "d": "m10.97 4.97-.02.022-3.473 4.425-2.093-2.094a.75.75 0 0 0-1.06 1.06L6.97 11.03a.75.75 0 0 0 1.079-.02l3.992-4.99a.75.75 0 0 0-1.071-1.05"
    }
  ],
  "back": [
    {
      "d": "M15 8a.5.5 0 0 0-.5-.5H2.707l3.147-3.146a.5.5 0 1 0-.708-.708l-4 4a.5.5 0 0 0 0 .708l4 4a.5.5 0 0 0 .708-.708L2.707 8.5H14.5A.5.5 0 0 0 15 8",
      "rule": "evenodd"
    }
  ],
  "refresh": [
    {
      "d": "M8 3a5 5 0 1 0 4.546 2.914.5.5 0 0 1 .908-.417A6 6 0 1 1 8 2z",
      "rule": "evenodd"
    },
    {
      "d": "M8 4.466V.534a.25.25 0 0 1 .41-.192l2.36 1.966c.12.1.12.284 0 .384L8.41 4.658A.25.25 0 0 1 8 4.466"
    }
  ],
  "plus": [
    {
      "d": "M8 2a.5.5 0 0 1 .5.5v5h5a.5.5 0 0 1 0 1h-5v5a.5.5 0 0 1-1 0v-5h-5a.5.5 0 0 1 0-1h5v-5A.5.5 0 0 1 8 2",
      "rule": "evenodd"
    }
  ],
  "chevron": [
    {
      "d": "M4.646 1.646a.5.5 0 0 1 .708 0l6 6a.5.5 0 0 1 0 .708l-6 6a.5.5 0 0 1-.708-.708L10.293 8 4.646 2.354a.5.5 0 0 1 0-.708",
      "rule": "evenodd"
    }
  ],
  "filter": [
    {
      "d": "M6 10.5a.5.5 0 0 1 .5-.5h3a.5.5 0 0 1 0 1h-3a.5.5 0 0 1-.5-.5m-2-3a.5.5 0 0 1 .5-.5h7a.5.5 0 0 1 0 1h-7a.5.5 0 0 1-.5-.5m-2-3a.5.5 0 0 1 .5-.5h11a.5.5 0 0 1 0 1h-11a.5.5 0 0 1-.5-.5"
    }
  ],
  "search": [
    {
      "d": "M11.742 10.344a6.5 6.5 0 1 0-1.397 1.398h-.001q.044.06.098.115l3.85 3.85a1 1 0 0 0 1.415-1.414l-3.85-3.85a1 1 0 0 0-.115-.1zM12 6.5a5.5 5.5 0 1 1-11 0 5.5 5.5 0 0 1 11 0"
    }
  ],
  "person": [
    {
      "d": "M8 8a3 3 0 1 0 0-6 3 3 0 0 0 0 6m2-3a2 2 0 1 1-4 0 2 2 0 0 1 4 0m4 8c0 1-1 1-1 1H3s-1 0-1-1 1-4 6-4 6 3 6 4m-1-.004c-.001-.246-.154-.986-.832-1.664C11.516 10.68 10.289 10 8 10s-3.516.68-4.168 1.332c-.678.678-.83 1.418-.832 1.664z"
    }
  ],
  "check": [
    {
      "d": "M12.5 16a3.5 3.5 0 1 0 0-7 3.5 3.5 0 0 0 0 7m1.679-4.493-1.335 2.226a.75.75 0 0 1-1.174.144l-.774-.773a.5.5 0 0 1 .708-.708l.547.548 1.17-1.951a.5.5 0 1 1 .858.514M11 5a3 3 0 1 1-6 0 3 3 0 0 1 6 0M8 7a2 2 0 1 0 0-4 2 2 0 0 0 0 4"
    },
    {
      "d": "M8.256 14a4.5 4.5 0 0 1-.229-1.004H3c.001-.246.154-.986.832-1.664C4.484 10.68 5.711 10 8 10q.39 0 .74.025c.226-.341.496-.65.804-.918Q8.844 9.002 8 9c-5 0-6 3-6 4s1 1 1 1z"
    }
  ],
  "dash": [
    {
      "d": "M12.5 16a3.5 3.5 0 1 0 0-7 3.5 3.5 0 0 0 0 7M11 12h3a.5.5 0 0 1 0 1h-3a.5.5 0 0 1 0-1m0-7a3 3 0 1 1-6 0 3 3 0 0 1 6 0M8 7a2 2 0 1 0 0-4 2 2 0 0 0 0 4"
    },
    {
      "d": "M8.256 14a4.5 4.5 0 0 1-.229-1.004H3c.001-.246.154-.986.832-1.664C4.484 10.68 5.711 10 8 10q.39 0 .74.025c.226-.341.496-.65.804-.918Q8.844 9.002 8 9c-5 0-6 3-6 4s1 1 1 1z"
    }
  ],
  "key": [
    {
      "d": "M0 8a4 4 0 0 1 7.465-2H14a.5.5 0 0 1 .354.146l1.5 1.5a.5.5 0 0 1 0 .708l-1.5 1.5a.5.5 0 0 1-.708 0L13 9.207l-.646.647a.5.5 0 0 1-.708 0L11 9.207l-.646.647a.5.5 0 0 1-.708 0L9 9.207l-.646.647A.5.5 0 0 1 8 10h-.535A4 4 0 0 1 0 8m4-3a3 3 0 1 0 2.712 4.285A.5.5 0 0 1 7.163 9h.63l.853-.854a.5.5 0 0 1 .708 0l.646.647.646-.647a.5.5 0 0 1 .708 0l.646.647.646-.647a.5.5 0 0 1 .708 0l.646.647.793-.793-1-1h-6.63a.5.5 0 0 1-.451-.285A3 3 0 0 0 4 5"
    },
    {
      "d": "M4 8a1 1 0 1 1-2 0 1 1 0 0 1 2 0"
    }
  ],
  "shield": [
    {
      "d": "M5.338 1.59a61 61 0 0 0-2.837.856.48.48 0 0 0-.328.39c-.554 4.157.726 7.19 2.253 9.188a10.7 10.7 0 0 0 2.287 2.233c.346.244.652.42.893.533q.18.085.293.118a1 1 0 0 0 .101.025 1 1 0 0 0 .1-.025q.114-.034.294-.118c.24-.113.547-.29.893-.533a10.7 10.7 0 0 0 2.287-2.233c1.527-1.997 2.807-5.031 2.253-9.188a.48.48 0 0 0-.328-.39c-.651-.213-1.75-.56-2.837-.855C9.552 1.29 8.531 1.067 8 1.067c-.53 0-1.552.223-2.662.524zM5.072.56C6.157.265 7.31 0 8 0s1.843.265 2.928.56c1.11.3 2.229.655 2.887.87a1.54 1.54 0 0 1 1.044 1.262c.596 4.477-.787 7.795-2.465 9.99a11.8 11.8 0 0 1-2.517 2.453 7 7 0 0 1-1.048.625c-.28.132-.581.24-.829.24s-.548-.108-.829-.24a7 7 0 0 1-1.048-.625 11.8 11.8 0 0 1-2.517-2.453C1.928 10.487.545 7.169 1.141 2.692A1.54 1.54 0 0 1 2.185 1.43 63 63 0 0 1 5.072.56"
    },
    {
      "d": "M10.854 5.146a.5.5 0 0 1 0 .708l-3 3a.5.5 0 0 1-.708 0l-1.5-1.5a.5.5 0 1 1 .708-.708L7.5 7.793l2.646-2.647a.5.5 0 0 1 .708 0"
    }
  ],
  "info": [
    {
      "d": "M8 15A7 7 0 1 1 8 1a7 7 0 0 1 0 14m0 1A8 8 0 1 0 8 0a8 8 0 0 0 0 16"
    },
    {
      "d": "m8.93 6.588-2.29.287-.082.38.45.083c.294.07.352.176.288.469l-.738 3.468c-.194.897.105 1.319.808 1.319.545 0 1.178-.252 1.465-.598l.088-.416c-.2.176-.492.246-.686.246-.275 0-.375-.193-.304-.533zM9 4.5a1 1 0 1 1-2 0 1 1 0 0 1 2 0"
    }
  ]
};
function TiIcon({name}){return <svg className="ti-icon" width="16" height="16" viewBox="0 0 16 16" fill="currentColor" aria-hidden="true">{tiIcons[name].map((path,i)=><path key={i} fillRule={path.rule} d={path.d}/>)}</svg>;}

const roles = Object.entries(ROLES).map(([key, value]) => [key, value.short]);
const empty = { email: '', username: '', first_name: '', last_name: '', rol: 'TECNICO', motivo: '', nueva_clave: '', clave_actual: '' };
const conflicts = { ultima_ti: 'Debe permanecer una cuenta TI activa.', ultima_gerencia: 'Debe permanecer una Gerencia activa.', autooperacion_protegida: 'Esta acción no está permitida sobre su propia cuenta.', asignaciones_pendientes: 'Resuelva primero las asignaciones y turnos desde Obras.', sin_cambios: 'El rol ya está asignado.', version_agotada: 'La cuenta requiere revisión técnica.' };

const credentialLabel={PERSONAL:'Personal',INICIAL:'Primer cambio pendiente',RECUPERACION:'Recuperación pendiente',NO_DISPONIBLE:'No disponible'};
const nameOf=a=>[a.first_name,a.last_name].map(s=>s.trim()).filter(Boolean).join(' ')||a.username;
const initials=a=>nameOf(a).split(/\s+/).slice(0,2).map(s=>s.charAt(0).toUpperCase()).join('');
const timestamp=v=>typeof v==='string'&&Number.isFinite(Date.parse(v))?new Intl.DateTimeFormat('es-CL',{timeZone:'America/Santiago',dateStyle:'short',timeStyle:'short',hour12:false}).format(new Date(v)):'—';
const roleTone = { ADMINISTRADOR_TI: 'ti', GERENCIA: 'gerencia', ADMINISTRATIVO_FINANZAS: 'finanzas', SUPERVISOR_OBRAS: 'supervisor', TECNICO: 'tecnico' };
const HIDDEN_ACCOUNT_CREATION_REASON = 'Aprovisionamiento manual inicial de TI mediante comando Django';
// Textos del historial de la cuenta, en lenguaje simple (solo presentación).
const eventLabel = { CREACION: 'Cuenta creada', EDICION: 'Perfil editado', ACTIVACION: 'Cuenta activada', DESACTIVACION: 'Cuenta desactivada', CAMBIO_ROL: 'Rol cambiado', ESTABLECER_CLAVE: 'Contraseña restablecida', CAMBIO_CLAVE_PROPIA: 'Contraseña cambiada', CREACION_CREDENCIAL_TEMPORAL: 'Credencial temporal emitida', REEMISION: 'Credencial temporal reemitida', CAMBIO_INICIAL: 'Contraseña personal establecida' };
const fieldLabel = { username: 'Usuario', email: 'Correo', rol: 'Rol', is_active: 'Estado', first_name: 'Nombres', last_name: 'Apellidos' };
const showValue = (key, value) => (key === 'rol' ? ROLES[value]?.short ?? String(value) : key === 'is_active' ? (value ? 'Activa' : 'Inactiva') : value === '' ? 'sin dato' : String(value));
const hasValue = (value) => value !== undefined && value !== null && value !== '';
const changeRows = (event) => Object.keys(fieldLabel).filter((key) => key in event.datos_nuevos && (hasValue(event.datos_nuevos[key]) || hasValue(event.datos_anteriores[key])))
  .map((key) => [key, hasValue(event.datos_anteriores[key]) ? `${showValue(key, event.datos_anteriores[key])} → ${showValue(key, event.datos_nuevos[key])}` : showValue(key, event.datos_nuevos[key])]);

function Feedback({ api }) {
  return <>
    {api.error && <div role="alert" className="alert alert-warning"><p>{conflicts[api.error.code] || api.error.message}</p>
      {Object.entries(api.error.fieldErrors || {}).map(([key, values]) => <p key={key}>{key}: {values.join(' ')}</p>)}
      {api.error.retryAfter && <p>Espere {api.error.retryAfter} antes de reintentar.</p>}</div>}
    {api.locked && <p role="status">Falta confirmar el estado. Pulse Actualizar antes de otra operación.</p>}
    {api.loading && <p role="status">Cargando usuarios…</p>}
  </>;
}

function Field({ name, label, form, setForm, disabled, type = 'text', options, required = true, placeholder }) {
  const props = { id: `usuario-${name}`, value: form[name], disabled, required,
    onChange: (event) => setForm((prev) => ({ ...prev, [name]: event.target.value })) };
  return <div><label className="form-label" htmlFor={props.id}>{label}</label>
    {options ? <select {...props} className="form-select">{options.map(([key, text]) => <option key={key} value={key}>{text}</option>)}</select>
      : name==='motivo'?<textarea {...props} className="form-control" rows={3} maxLength={2000}/>: <input {...props} className="form-control" type={type} placeholder={placeholder} maxLength={['motivo'].includes(name) ? 2000 : type === 'password' ? 4096 : name === 'email' ? 254 : 150} autoComplete={type === 'password' ? name === 'clave_actual' ? 'current-password' : 'new-password' : 'off'} />}</div>;
}

function AccountForm({ mode, account, api, onSaved, onCancel }) {
  const { user: authenticatedUser, logout, sessionInvalidatedByEmailChange } = useAuth();
  const [form, setForm] = useState({ ...empty, ...(account || {}) });
  const busy = api.busy || api.loading || api.locked;
  const titles = { crear: 'Crear cuenta inactiva', editar: 'Editar perfil', activar: 'Activar cuenta', desactivar: 'Desactivar cuenta', rol: 'Cambiar rol', clave: 'Restablecer acceso ajeno', propia: 'Cambiar mi contraseña' };
  async function submit(event) {
    event.preventDefault();
    if (busy) return;
    if (mode === 'clave') {
      await api.writeResult(`${userPath(account.id)}restablecer-clave/`, 'POST', { motivo: form.motivo.trim() }, async (result) => {
        const credential = typeof result?.credencial_temporal === 'string' && result.credencial_temporal.length === 43 && typeof result?.credencial_vence_en === 'string'
          ? { value: result.credencial_temporal, expiresAt: result.credencial_vence_en, userId: account.id }
          : null;
        if (!credential) { throw new Error('El servidor no devolvió una credencial temporal válida. No puede recuperarse desde el historial.'); }
        await onSaved(null,credential);
      });
      return;
    }
    let path = userPath(account?.id), method = 'POST', body;
    const profile = Object.fromEntries(['email', 'username', 'first_name', 'last_name'].map((key) => [key, form[key]]));
    if (mode === 'crear') body = { ...profile, rol: form.rol };
    if (mode === 'editar') { method = 'PATCH'; body = profile; }
    if (mode === 'activar' || mode === 'desactivar') { path += `${mode}/`; body = { motivo: form.motivo }; }
    if (mode === 'rol') { path += 'cambiar-rol/'; body = { rol: form.rol, motivo: form.motivo }; }

    if (mode === 'propia') { path = '/api/auth/cambiar-clave/'; body = { clave_actual: form.clave_actual, nueva_clave: form.nueva_clave }; }
    try {
      await api.write(path, method, body, async (result) => {
        if (mode === 'propia') { await logout(); return; }
        const saved = readUser(result);
        if (mode === 'editar' && account?.id === authenticatedUser?.id && saved.email !== account.email) {
          // La API confirmó la nueva identidad: el token ya no es válido.
          // Mostrar el login con aviso explícito, sin provocar refresh ni relecturas 401.
          sessionInvalidatedByEmailChange();
          return;
        }
        const temporaryCredential = mode === 'crear'
          && typeof result?.credencial_temporal === 'string'
          && result.credencial_temporal.length === 43
          && typeof result?.credencial_vence_en === 'string'
          ? { value: result.credencial_temporal, expiresAt: result.credencial_vence_en }
          : null;
        if(mode==='crear'&&!temporaryCredential)throw new Error('Cuenta creada, pero falta confirmar la credencial temporal. Reconsulta antes de continuar.');
        await onSaved(saved, temporaryCredential);
      });
    } finally { setForm((prev) => ({ ...prev, nueva_clave: '', clave_actual: '' })); }
  }
  if(mode==='crear')return <form aria-label={titles[mode]} onSubmit={submit} className="ti-create-form">
    <div className="ti-create-grid">
      <section className="card-fyag ti-panel"><h2 className="ti-section-title"><TiIcon name="person"/>Información personal</h2>
        <div className="ti-create-fields">
          <Field name="first_name" label="Nombres" placeholder="Ej. Camila" required={false} {...{form,setForm}} disabled={busy}/>
          <Field name="last_name" label="Apellidos" placeholder="Ej. Hernández" required={false} {...{form,setForm}} disabled={busy}/>
          <Field name="username" label="Nombre de usuario" placeholder="Ej. chernandez" {...{form,setForm}} disabled={busy}/>
          <Field name="email" label="Correo electrónico" placeholder="usuario@fyag.cl" type="email" {...{form,setForm}} disabled={busy}/>
        </div>
      </section>
      <section className="card-fyag ti-panel"><h2 className="ti-section-title"><TiIcon name="shield"/>Rol y permisos</h2>
        <Field name="rol" label="Rol asignado" options={roles} {...{form,setForm}} disabled={busy}/>
        <div className="ti-role-description"><strong>Funciones del rol</strong><p>{ROLE_NOTE[form.rol]}</p></div>
      </section>
    </div>
    <section className="card-fyag ti-panel ti-activation"><TiIcon name="info"/><div><h2>Activación de la cuenta</h2><p>La cuenta se creará inactiva. El servidor emitirá una credencial temporal de una sola exhibición. La activación se realiza posteriormente.</p></div></section>
    <div className="ti-create-actions"><button className="btn btn-outline-secondary" type="button" disabled={api.busy||api.locked} onClick={onCancel}>Cancelar</button><button className="btn btn-fyag-primary ti-button" disabled={busy} type="submit"><TiIcon name="plus"/>Crear cuenta</button></div>
  </form>;
  return <form aria-label={titles[mode]} onSubmit={submit} className={`card-fyag p-3 mb-3${mode === 'crear' ? ' usuario-crear-form' : ''}`}>
    <h2>{titles[mode]}</h2>
    
    {['activar','desactivar','rol','clave'].includes(mode)&&<p className="detalle-aviso">{({activar:'Habilita la cuenta; se mantienen las reglas de primer acceso.',desactivar:'Impide el acceso y revoca las sesiones. El historial se conserva.',rol:'Cambia los permisos y revoca las sesiones existentes.',clave:'Emite una credencial temporal y revoca las sesiones existentes.'})[mode]} Cuenta: <strong>{nameOf(account)} ({account.username})</strong>.</p>}
    <div className="fgrid commercial-fields">
      {['crear', 'editar'].includes(mode) && <>
        <Field name="email" label="Correo" type="email" {...{ form, setForm }} disabled={busy} />
        <Field name="username" label="Alias" {...{ form, setForm }} disabled={busy} />
        <Field name="first_name" label="Nombres" required={false} {...{ form, setForm }} disabled={busy} />
        <Field name="last_name" label="Apellidos" required={false} {...{ form, setForm }} disabled={busy} />
      </>}
      {['crear', 'rol'].includes(mode) && <Field name="rol" label="Rol" options={roles} {...{ form, setForm }} disabled={busy} />}

      {mode === 'propia' && <Field name="clave_actual" label="Contraseña actual" type="password" {...{ form, setForm }} disabled={busy} />}
      {mode === 'propia' && <Field name="nueva_clave" label="Nueva contraseña" type="password" {...{ form, setForm }} disabled={busy} />}
      {['activar', 'desactivar', 'rol', 'clave'].includes(mode) && <Field name="motivo" label="Motivo" {...{ form, setForm }} disabled={busy} />}
    </div>
    <div className="d-flex flex-wrap gap-2 mt-3"><button className={mode==='desactivar'?'btn btn-danger':'btn btn-fyag-primary'} disabled={busy} type="submit">{mode==='crear'?'Crear cuenta':'Confirmar '+titles[mode].toLowerCase()}</button>
      <button className="btn btn-outline-secondary" type="button" disabled={api.busy||api.locked} onClick={onCancel}>Cancelar</button></div>
  </form>;
}

function Detail({ id, onBack, temporaryCredential, onHideTemporaryCredential }) {
  const { user } = useAuth();
  const api = useCommercial();
  const [account, setAccount] = useState(null), [history, setHistory] = useState(null), [page, setPage] = useState(1), [mode, setMode] = useState(null), [issuedCredential, setIssuedCredential] = useState(null), [tab,setTab]=useState('Perfil');
  const load = () => api.load('cuenta', userPath(id), (data) => setAccount(readUser(data)));
  const loadHistory = () => api.load('historial', historyPath(id, page), (data) => setHistory(readHistory(data, id)));
  useEffect(() => { void load(); }, [id]);
  useEffect(() => { setHistory(null); void loadHistory(); }, [id, page]);
  const refresh = () => api.reconcile(async () => { const ok = await load(); return await loadHistory() && ok; });
  const onSaved = async (saved,credential=null) => {
    if(credential)setIssuedCredential(credential);
    await api.requiredLoad('cuenta', userPath(id), (data) => setAccount(readUser(data)));
    await api.requiredLoad('historial', historyPath(id, page), (data) => setHistory(readHistory(data, id)));
    setMode(null);
  };
  const own = user.id === id, disabled = api.busy || api.loading || api.locked;
  return <section className="commercial-page usuarios-page usuarios-detalle">
    <div className="usuarios-toolbar ti-detail-toolbar">
      <button className="ti-back" disabled={api.busy||api.locked} onClick={()=>{setIssuedCredential(null);onHideTemporaryCredential?.();onBack();}}><TiIcon name="back"/>Volver a usuarios</button>
      <button className="btn btn-outline-secondary ti-button" disabled={api.busy || api.loading} onClick={refresh}><TiIcon name="refresh"/>Actualizar</button>
    </div>
    <Feedback api={api} />
    {account&&<>
      <section className="card-fyag detalle-perfil">
        <div className="detalle-cabecera"><span className="usuarios-avatar" aria-hidden="true">{initials(account)}</span><div className="detalle-titulo"><h2 className="commercial-long-text">{nameOf(account)}</h2><div className="detalle-datos"><span>{account.username}</span><span className="usuarios-pill" data-tone={roleTone[account.rol]}>{ROLES[account.rol].short}</span><span className="usuarios-state" data-active={String(account.is_active)}>{account.is_active?'Activa':'Inactiva'}</span></div></div></div>
      </section>
            {(issuedCredential || temporaryCredential)?.userId === id && <div className="alert alert-warning mt-3" role="alert" aria-label="Credencial temporal de una sola exhibición"><h3>Credencial temporal generada</h3><p>El servidor la entrega una sola vez. Compártela con el titular por un canal privado; no la envíes por correo ni la guardes en el navegador.</p><p><strong>Vence:</strong> {new Date((issuedCredential || temporaryCredential).expiresAt).toLocaleString('es-CL')}</p><p><strong>Credencial temporal:</strong> <code className="user-select-all">{(issuedCredential || temporaryCredential).value}</code></p><button type="button" className="btn btn-outline-secondary" onClick={() => { setIssuedCredential(null); onHideTemporaryCredential?.(); }}>Ocultar credencial</button></div>}

      <div className="ti-tabs" role="group" aria-label="Secciones de la cuenta">{['Perfil','Acceso y seguridad','Historial'].map(item=><button key={item} type="button" aria-pressed={tab===item} disabled={api.busy||api.locked||!!mode} onClick={()=>setTab(item)}>{item}</button>)}</div>
      {own&&<p className="detalle-aviso">Por seguridad, no puedes desactivar tu propia cuenta ni cambiar tu propio rol. Si cambias tu correo o tu contraseña, tendrás que iniciar sesión de nuevo.</p>}
      {tab==='Perfil'&&<><section className="card-fyag ti-panel"><div className="ti-head"><h2>Información personal</h2><button className="btn btn-outline-secondary" disabled={disabled||!!mode} onClick={()=>setMode('editar')}>Editar perfil</button></div><dl className="ti-facts">{[['Nombres',account.first_name],['Apellidos',account.last_name],['Nombre de usuario',account.username],['Correo electrónico',account.email],['Identificador',account.id],['Fecha de creación',timestamp(account.date_joined)]].map(([label,value])=><div key={label}><dt>{label}</dt><dd>{value||'Sin registrar'}</dd></div>)}</dl></section><section className="card-fyag ti-panel"><div className="ti-head"><h2>Rol y permisos</h2><button className="btn btn-outline-secondary" disabled={disabled||own||!!mode} onClick={()=>setMode('rol')}>Cambiar rol</button></div><strong>{ROLES[account.rol].short}</strong><p>{ROLE_NOTE[account.rol]}</p></section></>}
      {tab==='Acceso y seguridad'&&<section className="card-fyag ti-panel"><h2>Estado del acceso</h2><dl className="ti-facts"><div><dt>Estado de la cuenta</dt><dd>{account.is_active?'Activa':'Inactiva'}</dd></div><div><dt>Credencial</dt><dd>{credentialLabel[account.estado_credencial]||'No disponible'}</dd></div>{account.estado_acceso&&<div><dt>Estado de acceso</dt><dd>{({NORMAL:'Normal',BLOQUEO_TEMPORAL:'Bloqueo temporal',REQUIERE_TI:'Requiere intervención de TI',NO_DISPONIBLE:'No disponible'})[account.estado_acceso]||account.estado_acceso}{account.bloqueado_hasta&&' · Hasta '+timestamp(account.bloqueado_hasta)}</dd></div>}</dl>
      <div className="ti-action"><div><strong>{own?'Cambiar mi contraseña':'Restablecer acceso'}</strong><p>{own?'Actualiza tu contraseña personal.':'Emite una credencial temporal de recuperación.'}</p></div><button className="btn btn-outline-secondary" disabled={disabled||!!mode} onClick={()=>setMode(own?'propia':'clave')}>{own?'Mi contraseña':'Restablecer acceso'}</button></div>
      <div className="ti-action"><div><strong>{account.is_active?'Desactivar cuenta':'Activar cuenta'}</strong><p>{account.is_active?'Impide el acceso sin eliminar el historial.':'Habilita la cuenta siguiendo las reglas de acceso.'}</p></div><button className={account.is_active?'btn btn-outline-danger':'btn btn-outline-secondary'} disabled={disabled||!!mode||(own&&account.is_active)} onClick={()=>setMode(account.is_active?'desactivar':'activar')}>{account.is_active?'Desactivar':'Activar'}</button></div></section>}
      {mode&&<AccountForm key={account.id+':'+mode} {...{mode,account,api,onSaved}} onCancel={()=>setMode(null)}/>}
    </>}
    {tab==='Historial'&&<section className="card-fyag detalle-historial"><h2>Historial de cambios</h2>
      <p className="detalle-sub">Cambios administrativos registrados en esta cuenta.</p>
      {history && !history.count && <p>Todavía no hay cambios registrados.</p>}
      <ol className="detalle-eventos">{history?.results.map((event) => <li key={event.id}><strong>{eventLabel[event.tipo] || event.tipo}</strong>
        <p className="detalle-evento-meta">{timestamp(event.creado_en)} · Hecho por la cuenta #{event.actor}</p>
        {event.motivo && event.motivo !== HIDDEN_ACCOUNT_CREATION_REASON && <p className="commercial-long-text">{event.motivo}</p>}
        <dl className="detalle-cambios">{changeRows(event).map(([key, value]) => <div key={key}><dt>{fieldLabel[key]}</dt><dd className="commercial-long-text">{value}</dd></div>)}</dl>
      </li>)}</ol>
      {history && (history.next||history.previous) && <Pager data={history} {...{ page, setPage }} disabled={api.busy || api.loading} label="Páginas del historial" />}
    </section>}
  </section>;
}

function PermissionMatrix(){
  const glyph={manage:'manage',read:'eye',limited:'shield',none:'none'};
  return <section className="card-fyag ti-panel ti-permissions" aria-label="Permisos por rol">
    <div className="ti-head"><div><h2>Matriz de permisos</h2><small>Consulta de atribuciones de los seis roles del sistema.</small></div></div>
    <div className="ti-permissions-legend">{Object.entries(permissionLevels).map(([level,label])=><span key={level} className={'ti-permission '+level}><TiIcon name={glyph[level]}/>{label}</span>)}</div>
    <div className="ti-permissions-scroll" role="region" aria-label="Desplazamiento de matriz de permisos" tabIndex={0}>
      <table className="ti-permission-table"><thead><tr><th scope="col">Módulo / función</th>{permissionRoles.map(([role,label])=><th key={role} scope="col" title={ROLES[role].short}>{label}</th>)}</tr></thead>
      <tbody>{permissionRows.map(({label,access})=><tr key={label}><th scope="row">{label}</th>{permissionRoles.map(([role])=>{const [level,detail]=access[role]||['none',''];return <td key={role}><span className={'ti-permission '+level} title={permissionLevels[level]}><TiIcon name={glyph[level]}/><span className={level==='none'?'visually-hidden':undefined}>{permissionLevels[level]}</span></span>{detail&&<small>{detail}</small>}</td>;})}</tr>)}</tbody></table>
    </div>
    <p className="ti-permission-note"><TiIcon name="info"/> Consulta informativa, no editable. Las operaciones dependen también del estado del recurso, la sesión y las reglas de alcance. Los permisos se validan en el servidor.</p>
  </section>;
}

function UsuariosTI() {
  const api=useCommercial();
  const [data,setData]=useState(null),[page,setPage]=useState(1),[filters,setFilters]=useState({rol:'',activo:'',buscar:''}),[draft,setDraft]=useState(filters),[selected,setSelected]=useState(null),[creating,setCreating]=useState(false),[temporaryCredential,setTemporaryCredential]=useState(null),[filterOpen,setFilterOpen]=useState(false),[section,setSection]=useState('usuarios');
  const [summary,setSummary]=useState(null);
  const path=usersPath(page,{...filters,resumen:true});
  const accept=result=>{const next=readUsers(result);setData(next);setSummary(next.resumen||null);};
  const load=()=>api.load('usuarios',path,accept);
  useEffect(()=>{if(!selected&&!creating){setData(null);void load();}},[path,selected,creating]);
  const disabled=api.busy||api.loading||api.locked;
  function apply(e){e.preventDefault();setPage(1);setFilters({...draft,buscar:draft.buscar.trim()});setFilterOpen(false);}
  function clear(){const empty={rol:'',activo:'',buscar:''};setDraft(empty);setFilters(empty);setPage(1);}
  if(selected)return <Detail key={selected} id={selected} onBack={()=>{setTemporaryCredential(null);setSelected(null);}} temporaryCredential={temporaryCredential} onHideTemporaryCredential={()=>setTemporaryCredential(null)}/>;
  if(creating)return <section className="commercial-page usuarios-page usuarios-lista"><div className="usuarios-toolbar ti-detail-toolbar"><button className="ti-back" disabled={api.busy||api.locked} onClick={()=>setCreating(false)}><TiIcon name="back"/>Volver a usuarios</button>{api.locked&&<button className="btn btn-outline-secondary ti-button" disabled={api.busy||api.loading} onClick={()=>api.reconcile(load)}><TiIcon name="refresh"/>Actualizar</button>}</div><PageHead title="Nueva cuenta" sub="Registra una cuenta y asigna su rol."/><Feedback api={api}/><AccountForm mode="crear" api={api} onCancel={()=>setCreating(false)} onSaved={async(account,credential)=>{if(credential)setTemporaryCredential({...credential,userId:account.id});setCreating(false);setSelected(account.id);}}/></section>;
  return <section className="commercial-page usuarios-page usuarios-lista">
    <div className="ti-page-heading"><div><h1>Usuarios y roles</h1><p>Administración de cuentas y accesos</p></div>{section==='usuarios'&&<div className="ti-heading-actions"><button className="btn btn-outline-secondary ti-icon-button" aria-label="Actualizar" title="Actualizar" disabled={api.busy||api.loading} onClick={()=>api.reconcile(load)}><TiIcon name="refresh"/></button><button className="btn btn-fyag-primary ti-button" disabled={disabled} onClick={()=>setCreating(true)}><TiIcon name="plus"/>Nueva cuenta</button></div>}</div>
    <div className="ti-tabs ti-module-tabs" role="group" aria-label="Secciones de Usuarios y roles"><button type="button" aria-pressed={section==='usuarios'} disabled={api.busy||api.locked} onClick={()=>setSection('usuarios')}><TiIcon name="people"/>Usuarios</button><button type="button" aria-pressed={section==='permisos'} disabled={api.busy||api.locked} onClick={()=>setSection('permisos')}><TiIcon name="shield"/>Permisos por rol</button></div>
    {section==='permisos'?<PermissionMatrix/>:<>
    <div className="ti-kpis">{[['total','Total de cuentas','person'],['activas','Cuentas activas','check'],['inactivas','Cuentas inactivas','dash'],['temporales','Cambio de clave pendiente','key']].map(([key,label,icon])=><div key={key} className="card-fyag ti-kpi"><div className="ti-kpi-heading"><span>{label}</span><TiIcon name={icon}/></div><strong>{summary?summary[key].toLocaleString('es-CL'):'—'}</strong>{key==='temporales'&&<small>Incluye credenciales vencidas</small>}</div>)}</div>
    <Feedback api={api}/>
    {api.error?.status===404&&page>1&&<button className="btn btn-outline-secondary" onClick={()=>setPage(1)}>Primera página</button>}
    <section className="card-fyag ti-panel"><div className="ti-head"><div><h2>Cuentas registradas</h2><small>{data?data.count+' cuentas coincidentes':'—'}</small></div><button type="button" className="btn btn-outline-secondary ti-button" aria-expanded={filterOpen} aria-controls="ti-filters" onClick={()=>setFilterOpen(x=>!x)}><TiIcon name="filter"/>Filtros</button></div>
    <form className="ti-search" onSubmit={apply}><label htmlFor="ti-search" className="visually-hidden">Buscar usuarios</label><div className="ti-search-field"><TiIcon name="search"/><input id="ti-search" className="form-control" maxLength={150} placeholder="Buscar por nombre, alias o correo" value={draft.buscar} disabled={disabled} onChange={e=>setDraft(old=>({...old,buscar:e.target.value}))}/></div><button className="btn btn-outline-secondary" disabled={disabled}>Buscar</button></form>
    <form id="ti-filters" className="ti-filter-form" hidden={!filterOpen} onSubmit={apply}><label>Rol<select aria-label="Filtrar rol" className="form-select" value={draft.rol} disabled={disabled} onChange={e=>setDraft(old=>({...old,rol:e.target.value}))}><option value="">Todos</option>{roles.map(([key,label])=><option key={key} value={key}>{label}</option>)}</select></label><label>Estado<select aria-label="Filtrar estado" className="form-select" value={draft.activo} disabled={disabled} onChange={e=>setDraft(old=>({...old,activo:e.target.value}))}><option value="">Todos</option><option value="true">Activas</option><option value="false">Inactivas</option></select></label><button className="btn btn-fyag-primary" disabled={disabled}>Aplicar filtros</button></form>
    {(filters.rol||filters.activo||filters.buscar)&&<div className="ti-head"><small>{[filters.buscar,ROLES[filters.rol]?.short,filters.activo==='true'?'Activas':filters.activo==='false'?'Inactivas':''].filter(Boolean).join(' · ')}</small><button className="btn btn-outline-secondary btn-sm" disabled={disabled} onClick={clear}>Limpiar filtros</button></div>}
    {data?.results.length>0?<div className="usuarios-table-region" role="region" aria-label="Desplazamiento de cuentas de usuario" tabIndex={0}><Table label="Cuentas de usuario" min="780px" columns="minmax(0,1.3fr) minmax(0,1.5fr) minmax(0,1.1fr) minmax(0,0.85fr) 64px" head={['Usuario','Correo','Rol','Estado','Detalle']}>{data.results.map(account=><div key={account.id} className="trow" role="row"><div role="cell" className="ti-person"><span className="usuarios-avatar ti-avatar-small" aria-hidden="true">{initials(account)}</span><div><strong>{nameOf(account)}</strong>{nameOf(account)!==account.username&&<small>{account.username}</small>}</div></div><div role="cell">{account.email}</div><div role="cell"><span className="usuarios-pill" data-tone={roleTone[account.rol]}>{ROLES[account.rol].short}</span></div><div role="cell"><span className="usuarios-state" data-active={String(account.is_active)}>{account.is_active?'Activa':'Inactiva'}</span>{account.estado_credencial&&account.estado_credencial!=='PERSONAL'&&<small className="ti-credential">{credentialLabel[account.estado_credencial]}</small>}</div><div role="cell" className="usuarios-detail"><button className="btn btn-link ti-row-open" aria-label={'Ver cuenta #'+account.id} title={'Ver cuenta de '+nameOf(account)} disabled={disabled} onClick={()=>setSelected(account.id)}><TiIcon name="chevron"/></button></div></div>)}</Table></div>:data&&<p className="ti-empty">No hay cuentas para estos filtros.</p>}
    {data&&(data.next||data.previous)&&<Pager {...{data,page,setPage}} disabled={disabled} label="Páginas de usuarios"/>}</section>
    </>}

  </section>;
}

export default function Usuarios() {
  const { user } = useAuth();
  return canManageUsers(user?.role) ? <UsuariosTI key={`${user.id}:${user.role}`} /> : <p role="alert">No tiene permiso para administrar cuentas.</p>;
}
