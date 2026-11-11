import React, { useEffect, useState } from 'react';
import { useAuth } from '../auth/AuthContext';
import { ROLES, MATRIX } from '../data/constants';
import { PageHead, Table } from '../components/ui';
import { Pager, useCommercial } from '../comercial/ui.jsx';
import { canManageUsers, userPath, usersPath, historyPath, readUser, readUsers, readHistory } from '../usuarios/api.js';

const roles = Object.entries(ROLES).map(([key, value]) => [key, value.short]);
const empty = { email: '', username: '', first_name: '', last_name: '', rol: 'TECNICO', password: '', motivo: '', nueva_clave: '', clave_actual: '' };
const conflicts = { ultima_ti: 'Debe permanecer una cuenta TI activa.', ultima_gerencia: 'Debe permanecer una Gerencia activa.', autooperacion_protegida: 'Esta acción no está permitida sobre su propia cuenta.', asignaciones_pendientes: 'Resuelva primero las asignaciones y turnos desde Obras.', sin_cambios: 'El rol ya está asignado.', version_agotada: 'La cuenta requiere revisión técnica.' };

function Feedback({ api }) {
  return <>
    {api.error && <div role="alert" className="alert alert-warning"><p>{conflicts[api.error.code] || api.error.message}</p>
      {Object.entries(api.error.fieldErrors || {}).map(([key, values]) => <p key={key}>{key}: {values.join(' ')}</p>)}
      {api.error.retryAfter && <p>Espere {api.error.retryAfter} antes de reintentar.</p>}</div>}
    {api.locked && <p role="status">Falta confirmar el estado. Pulse Actualizar antes de otra operación.</p>}
    {api.loading && <p role="status">Cargando usuarios…</p>}
  </>;
}

function Field({ name, label, form, setForm, disabled, type = 'text', options, required = true }) {
  const props = { id: `usuario-${name}`, value: form[name], disabled, required,
    onChange: (event) => setForm((prev) => ({ ...prev, [name]: event.target.value })) };
  return <div><label className="form-label" htmlFor={props.id}>{label}</label>
    {options ? <select {...props} className="form-select">{options.map(([key, text]) => <option key={key} value={key}>{text}</option>)}</select>
      : <input {...props} className="form-control" type={type} maxLength={['motivo'].includes(name) ? 2000 : type === 'password' ? 4096 : name === 'email' ? 254 : 150} autoComplete={type === 'password' ? name === 'clave_actual' ? 'current-password' : 'new-password' : 'off'} />}</div>;
}

function AccountForm({ mode, account, api, onSaved, onCancel }) {
  const { logout } = useAuth();
  const [form, setForm] = useState({ ...empty, ...(account || {}) });
  const busy = api.busy || api.loading || api.locked;
  const titles = { crear: 'Crear cuenta inactiva', editar: 'Editar perfil', activar: 'Activar cuenta', desactivar: 'Desactivar cuenta', rol: 'Cambiar rol', clave: 'Establecer contraseña ajena', propia: 'Cambiar mi contraseña' };
  async function submit(event) {
    event.preventDefault();
    if (busy) return;
    let path = userPath(account?.id), method = 'POST', body;
    const profile = Object.fromEntries(['email', 'username', 'first_name', 'last_name'].map((key) => [key, form[key]]));
    if (mode === 'crear') body = { ...profile, rol: form.rol, password: form.password };
    if (mode === 'editar') { method = 'PATCH'; body = profile; }
    if (mode === 'activar' || mode === 'desactivar') { path += `${mode}/`; body = { motivo: form.motivo }; }
    if (mode === 'rol') { path += 'cambiar-rol/'; body = { rol: form.rol, motivo: form.motivo }; }
    if (mode === 'clave') { path += 'establecer-clave/'; body = { nueva_clave: form.nueva_clave, motivo: form.motivo }; }
    if (mode === 'propia') { path = '/api/auth/cambiar-clave/'; body = { clave_actual: form.clave_actual, nueva_clave: form.nueva_clave }; }
    try {
      await api.write(path, method, body, async (result) => {
        if (mode === 'propia') { await logout(); return; }
        await onSaved(readUser(result));
      });
    } finally { setForm((prev) => ({ ...prev, password: '', nueva_clave: '', clave_actual: '' })); }
  }
  return <form aria-label={titles[mode]} onSubmit={submit} className="card-fyag p-3 mb-3">
    <h2>{titles[mode]}</h2>
    {mode === 'crear' && <p>La cuenta nace inactiva. Active expresamente tras entregar la contraseña por un canal seguro.</p>}
    <div className="fgrid commercial-fields">
      {['crear', 'editar'].includes(mode) && <>
        <Field name="email" label="Correo" type="email" {...{ form, setForm }} disabled={busy} />
        <Field name="username" label="Alias" {...{ form, setForm }} disabled={busy} />
        <Field name="first_name" label="Nombres" required={false} {...{ form, setForm }} disabled={busy} />
        <Field name="last_name" label="Apellidos" required={false} {...{ form, setForm }} disabled={busy} />
      </>}
      {['crear', 'rol'].includes(mode) && <Field name="rol" label="Rol" options={roles} {...{ form, setForm }} disabled={busy} />}
      {mode === 'crear' && <Field name="password" label="Contraseña inicial" type="password" {...{ form, setForm }} disabled={busy} />}
      {mode === 'propia' && <Field name="clave_actual" label="Contraseña actual" type="password" {...{ form, setForm }} disabled={busy} />}
      {['clave', 'propia'].includes(mode) && <Field name="nueva_clave" label="Nueva contraseña" type="password" {...{ form, setForm }} disabled={busy} />}
      {['activar', 'desactivar', 'rol', 'clave'].includes(mode) && <Field name="motivo" label="Motivo" {...{ form, setForm }} disabled={busy} />}
    </div>
    <div className="d-flex flex-wrap gap-2 mt-3"><button className="btn btn-fyag-primary" disabled={busy} type="submit">Confirmar {titles[mode].toLowerCase()}</button>
      <button className="btn btn-outline-secondary" type="button" disabled={api.busy} onClick={onCancel}>Cancelar</button></div>
  </form>;
}

function Detail({ id, onBack }) {
  const { user } = useAuth();
  const api = useCommercial();
  const [account, setAccount] = useState(null), [history, setHistory] = useState(null), [page, setPage] = useState(1), [mode, setMode] = useState(null);
  const load = () => api.load('cuenta', userPath(id), (data) => setAccount(readUser(data)));
  const loadHistory = () => api.load('historial', historyPath(id, page), (data) => setHistory(readHistory(data, id)));
  useEffect(() => { void load(); }, [id]);
  useEffect(() => { setHistory(null); void loadHistory(); }, [id, page]);
  const refresh = () => api.reconcile(async () => { const ok = await load(); return await loadHistory() && ok; });
  const onSaved = async () => {
    await api.requiredLoad('cuenta', userPath(id), (data) => setAccount(readUser(data)));
    await api.requiredLoad('historial', historyPath(id, page), (data) => setHistory(readHistory(data, id)));
    setMode(null);
  };
  const own = user.id === id, disabled = api.busy || api.loading || api.locked;
  return <section className="commercial-page">
    <button className="btn btn-outline-secondary" disabled={api.busy} onClick={onBack}>Volver a usuarios</button>
    <button className="btn btn-outline-secondary ms-2" disabled={api.busy || api.loading} onClick={refresh}>Actualizar</button>
    <Feedback api={api} />
    {account && <>
      <h2 className="commercial-long-text">{account.username} · #{account.id}</h2><p className="commercial-long-text">{account.email} · {ROLES[account.rol].short} · {account.is_active ? 'Activa' : 'Inactiva'}</p>
      <p className="commercial-long-text">{account.first_name} {account.last_name}</p>
      <div className="d-flex flex-wrap gap-2 mb-3">
        {['editar', account.is_active ? 'desactivar' : 'activar', 'rol', own ? 'propia' : 'clave'].map((action) => <button key={action} className="btn btn-outline-secondary" disabled={disabled || (own && ['desactivar', 'rol'].includes(action))} onClick={() => setMode(action)}>
          {{ editar: 'Editar perfil', activar: 'Activar', desactivar: 'Desactivar', rol: 'Cambiar rol', clave: 'Establecer contraseña', propia: 'Mi contraseña' }[action]}</button>)}
      </div>
      {own && <p>Auto-baja y cambio de rol propio protegidos. Cambiar correo o contraseña exige nuevo inicio de sesión.</p>}
      {mode && <AccountForm key={`${account.id}:${mode}`} {...{ mode, account, api, onSaved }} onCancel={() => setMode(null)} />}
    </>}
    <section className="card-fyag p-3"><h2>Auditoría administrativa</h2>
      {history && !history.count && <p>No hay eventos registrados.</p>}
      <ol>{history?.results.map((event) => <li key={event.id} className="mb-3"><strong>{event.tipo.replaceAll('_', ' ')}</strong><p>Actor #{event.actor} · {new Date(event.creado_en).toLocaleString('es-CL')}</p><p className="commercial-long-text">{event.motivo}</p>
        <dl>{Object.entries(event.datos_nuevos).map(([key, value]) => <div key={key}><dt>{key}</dt><dd className="commercial-long-text">{String(event.datos_anteriores[key] ?? '—')} → {String(value)}</dd></div>)}</dl>
      </li>)}</ol>
      {history && <Pager data={history} {...{ page, setPage }} disabled={api.busy || api.loading} label="Páginas de auditoría" />}
    </section>
  </section>;
}

function UsuariosTI() {
  const api = useCommercial();
  const [data, setData] = useState(null), [page, setPage] = useState(1), [filters, setFilters] = useState({ rol: '', activo: '' }), [selected, setSelected] = useState(null), [creating, setCreating] = useState(false);
  const load = () => api.load('usuarios', usersPath(page, filters), (result) => setData(readUsers(result)));
  useEffect(() => { if (!selected) { setData(null); void load(); } }, [page, filters.rol, filters.activo, selected]);
  const disabled = api.busy || api.loading || api.locked;
  if (selected) return <Detail key={selected} id={selected} onBack={() => setSelected(null)} />;
  return <section className="commercial-page">
    <PageHead title="Usuarios y roles" sub="Administración exclusiva de TI. Los cambios se confirman en PostgreSQL con auditoría." />
    <div className="d-flex flex-wrap gap-2 mb-3">
      <button className="btn btn-fyag-primary" disabled={disabled} onClick={() => setCreating(true)}>Nueva cuenta</button>
      <button className="btn btn-outline-secondary" disabled={api.busy || api.loading} onClick={() => api.reconcile(load)}>Actualizar</button>
      <label>Rol <select aria-label="Filtrar rol" className="form-select" value={filters.rol} disabled={api.busy} onChange={(e) => { setPage(1); setFilters({ ...filters, rol: e.target.value }); }}><option value="">Todos</option>{roles.map(([key, text]) => <option key={key} value={key}>{text}</option>)}</select></label>
      <label>Estado <select aria-label="Filtrar estado" className="form-select" value={filters.activo} disabled={api.busy} onChange={(e) => { setPage(1); setFilters({ ...filters, activo: e.target.value }); }}><option value="">Todos</option><option value="true">Activas</option><option value="false">Inactivas</option></select></label>
    </div>
    <Feedback api={api} />
    {api.error?.status === 404 && page > 1 && <button className="btn btn-outline-secondary" onClick={() => setPage(1)}>Primera página</button>}
    {creating && <AccountForm mode="crear" api={api} onCancel={() => setCreating(false)} onSaved={async (account) => { await api.requiredLoad('usuarios', usersPath(page, filters), (result) => setData(readUsers(result))); setCreating(false); setSelected(account.id); }} />}
    <div className="card-fyag flush mb-3"><Table label="Cuentas de usuario" min="780px" columns="1fr 1.4fr 1.3fr 100px 110px" head={['Alias', 'Correo', 'Rol', 'Estado', 'Detalle']}>
      {data?.results.map((account) => <div key={account.id} className="trow" role="row"><div role="cell">{account.username}</div><div role="cell">{account.email}</div><div role="cell">{ROLES[account.rol].short}</div><div role="cell">{account.is_active ? 'Activa' : 'Inactiva'}</div><div role="cell"><button className="btn btn-outline-secondary btn-sm" disabled={api.busy} onClick={() => setSelected(account.id)}>Ver cuenta #{account.id}</button></div></div>)}
    </Table></div>
    {data && !data.count && <p>No hay cuentas para estos filtros.</p>}
    {data && <Pager {...{ data, page, setPage }} disabled={api.busy || api.loading} label="Páginas de usuarios" />}
    <section className="card-fyag p-3"><h2>Matriz de permisos</h2><Table label="Matriz de cinco roles" min="900px" columns="1.4fr repeat(5, 1fr)" head={['Módulo', 'Gerencia', 'Finanzas', 'Supervisor', 'Técnico', 'TI']}>
      {MATRIX.map((row) => <div className="trow" role="row" key={row[0]}>{row.map((value, index) => <div role="cell" key={index}>{value}</div>)}</div>)}
    </Table></section>
  </section>;
}

export default function Usuarios() {
  const { user } = useAuth();
  return canManageUsers(user?.role) ? <UsuariosTI key={`${user.id}:${user.role}`} /> : <p role="alert">No tiene permiso para administrar cuentas.</p>;
}
