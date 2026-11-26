import React, { useEffect, useState } from 'react';
import { useAuth } from '../auth/AuthContext';
import { ROLES, ROLE_NOTE } from '../data/constants';
import { PageHead, Table, Icon } from '../components/ui';
import { Pager, useCommercial } from '../comercial/ui.jsx';
import { canManageUsers, userPath, usersPath, historyPath, readUser, readUsers, readHistory } from '../usuarios/api.js';

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

function Field({ name, label, form, setForm, disabled, type = 'text', options, required = true }) {
  const props = { id: `usuario-${name}`, value: form[name], disabled, required,
    onChange: (event) => setForm((prev) => ({ ...prev, [name]: event.target.value })) };
  return <div><label className="form-label" htmlFor={props.id}>{label}</label>
    {options ? <select {...props} className="form-select">{options.map(([key, text]) => <option key={key} value={key}>{text}</option>)}</select>
      : name==='motivo'?<textarea {...props} className="form-control" rows={3} maxLength={2000}/>: <input {...props} className="form-control" type={type} maxLength={['motivo'].includes(name) ? 2000 : type === 'password' ? 4096 : name === 'email' ? 254 : 150} autoComplete={type === 'password' ? name === 'clave_actual' ? 'current-password' : 'new-password' : 'off'} />}</div>;
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
  return <form aria-label={titles[mode]} onSubmit={submit} className={`card-fyag p-3 mb-3${mode === 'crear' ? ' usuario-crear-form' : ''}`}>
    <h2>{titles[mode]}</h2>
    {mode==='crear'&&<p className="detalle-aviso">La cuenta se creará inactiva. El servidor emitirá una credencial temporal de una sola exhibición. La activación es independiente.</p>}
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
      <button className="ti-back" disabled={api.busy||api.locked} onClick={()=>{setIssuedCredential(null);onHideTemporaryCredential?.();onBack();}}><Icon d="M19 12H5M12 5l-7 7 7 7"/>Volver a usuarios</button>
      <button className="btn btn-outline-secondary" disabled={api.busy || api.loading} onClick={refresh}><Icon d="M20 11a8 8 0 1 1-2-5M20 4v7h-7"/>Actualizar</button>
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
        <p className="detalle-evento-meta">{timestamp(event.creado_en) · Hecho por la cuenta #{event.actor}</p>
        {event.motivo && event.motivo !== HIDDEN_ACCOUNT_CREATION_REASON && <p className="commercial-long-text">{event.motivo}</p>}
        <dl className="detalle-cambios">{changeRows(event).map(([key, value]) => <div key={key}><dt>{fieldLabel[key]}</dt><dd className="commercial-long-text">{value}</dd></div>)}</dl>
      </li>)}</ol>
      {history && (history.next||history.previous) && <Pager data={history} {...{ page, setPage }} disabled={api.busy || api.loading} label="Páginas del historial" />}
    </section>}
  </section>;
}

function UsuariosTI() {
  const api=useCommercial();
  const [data,setData]=useState(null),[page,setPage]=useState(1),[filters,setFilters]=useState({rol:'',activo:'',buscar:''}),[draft,setDraft]=useState(filters),[selected,setSelected]=useState(null),[creating,setCreating]=useState(false),[temporaryCredential,setTemporaryCredential]=useState(null),[filterOpen,setFilterOpen]=useState(false),[matrixOpen,setMatrixOpen]=useState(false);
  const [summary,setSummary]=useState(null);
  const path=usersPath(page,{...filters,resumen:true});
  const accept=result=>{const next=readUsers(result);setData(next);setSummary(next.resumen||null);};
  const load=()=>api.load('usuarios',path,accept);
  useEffect(()=>{if(!selected&&!creating){setData(null);void load();}},[path,selected,creating]);
  const disabled=api.busy||api.loading||api.locked;
  function apply(e){e.preventDefault();setPage(1);setFilters({...draft,buscar:draft.buscar.trim()});setFilterOpen(false);}
  function clear(){const empty={rol:'',activo:'',buscar:''};setDraft(empty);setFilters(empty);setPage(1);}
  if(selected)return <Detail key={selected} id={selected} onBack={()=>{setTemporaryCredential(null);setSelected(null);}} temporaryCredential={temporaryCredential} onHideTemporaryCredential={()=>setTemporaryCredential(null)}/>;
  if(creating)return <section className="commercial-page usuarios-page usuarios-lista"><div className="usuarios-toolbar ti-detail-toolbar"><button className="ti-back" disabled={api.busy||api.locked} onClick={()=>setCreating(false)}><Icon d="M19 12H5M12 5l-7 7 7 7"/>Volver a usuarios</button><button className="btn btn-outline-secondary" disabled={api.busy||api.loading} onClick={()=>api.reconcile(load)}>Actualizar</button></div><PageHead title="Nueva cuenta" sub="Registra una cuenta y asigna su rol."/><Feedback api={api}/><AccountForm mode="crear" api={api} onCancel={()=>setCreating(false)} onSaved={async(account,credential)=>{if(credential)setTemporaryCredential({...credential,userId:account.id});setCreating(false);setSelected(account.id);}}/></section>;
  return <section className="commercial-page usuarios-page usuarios-lista">
    <PageHead title="Usuarios y roles" sub="Administración de cuentas y accesos"><button className="btn btn-outline-secondary" disabled={api.busy||api.loading} onClick={()=>api.reconcile(load)}><Icon d="M20 11a8 8 0 1 1-2-5M20 4v7h-7"/>Actualizar</button><button className="btn btn-fyag-primary" disabled={disabled} onClick={()=>setCreating(true)}><Icon d="M12 5v14M5 12h14"/>Nueva cuenta</button></PageHead>
    <div className="ti-kpis">{[['total','Total de cuentas'],['activas','Cuentas activas'],['inactivas','Cuentas inactivas'],['temporales','Cambio de clave pendiente']].map(([key,label])=><div key={key} className="card-fyag ti-kpi"><span>{label}</span><strong>{summary?summary[key].toLocaleString('es-CL'):'—'}</strong>{key==='temporales'&&<small>Incluye credenciales vencidas</small>}</div>)}</div>
    <Feedback api={api}/>
    {api.error?.status===404&&page>1&&<button className="btn btn-outline-secondary" onClick={()=>setPage(1)}>Primera página</button>}
    <section className="card-fyag ti-panel"><div className="ti-head"><div><h2>Cuentas registradas</h2><small>{data?data.count+' cuentas coincidentes':'—'}</small></div><button type="button" className="btn btn-outline-secondary" aria-expanded={filterOpen} aria-controls="ti-filters" onClick={()=>setFilterOpen(x=>!x)}>Filtros</button></div>
    <form className="ti-search" onSubmit={apply}><label htmlFor="ti-search" className="visually-hidden">Buscar usuarios</label><input id="ti-search" className="form-control" maxLength={150} placeholder="Buscar por nombre, alias o correo" value={draft.buscar} disabled={disabled} onChange={e=>setDraft(old=>({...old,buscar:e.target.value}))}/><button className="btn btn-fyag-primary" disabled={disabled}>Buscar</button></form>
    <form id="ti-filters" className="ti-filter-form" hidden={!filterOpen} onSubmit={apply}><label>Rol<select aria-label="Filtrar rol" className="form-select" value={draft.rol} disabled={disabled} onChange={e=>setDraft(old=>({...old,rol:e.target.value}))}><option value="">Todos</option>{roles.map(([key,label])=><option key={key} value={key}>{label}</option>)}</select></label><label>Estado<select aria-label="Filtrar estado" className="form-select" value={draft.activo} disabled={disabled} onChange={e=>setDraft(old=>({...old,activo:e.target.value}))}><option value="">Todos</option><option value="true">Activas</option><option value="false">Inactivas</option></select></label><button className="btn btn-fyag-primary" disabled={disabled}>Aplicar filtros</button></form>
    {(filters.rol||filters.activo||filters.buscar)&&<div className="ti-head"><small>{[filters.buscar,ROLES[filters.rol]?.short,filters.activo==='true'?'Activas':filters.activo==='false'?'Inactivas':''].filter(Boolean).join(' · ')}</small><button className="btn btn-outline-secondary btn-sm" disabled={disabled} onClick={clear}>Limpiar filtros</button></div>}
    {data?.results.length>0?<div className="usuarios-table-region" role="region" aria-label="Desplazamiento de cuentas de usuario" tabIndex={0}><Table label="Cuentas de usuario" min="850px" columns="minmax(0,1.4fr) minmax(0,1.4fr) minmax(0,1.1fr) minmax(0,1fr) 100px" head={['Usuario','Correo','Rol','Estado','Detalle']}>{data.results.map(account=><div key={account.id} className="trow" role="row"><div role="cell" className="ti-person"><span className="usuarios-avatar ti-avatar-small" aria-hidden="true">{initials(account)}</span><div><strong>{nameOf(account)}</strong>{nameOf(account)!==account.username&&<small>{account.username}</small>}</div></div><div role="cell">{account.email}</div><div role="cell"><span className="usuarios-pill" data-tone={roleTone[account.rol]}>{ROLES[account.rol].short}</span></div><div role="cell"><span className="usuarios-state" data-active={String(account.is_active)}>{account.is_active?'Activa':'Inactiva'}</span>{account.estado_credencial&&account.estado_credencial!=='PERSONAL'&&<small className="ti-credential">{credentialLabel[account.estado_credencial]}</small>}</div><div role="cell" className="usuarios-detail"><button className="btn btn-link btn-sm" aria-label={'Ver cuenta #'+account.id} disabled={disabled} onClick={()=>setSelected(account.id)}>Ver cuenta <Icon d="M9 5l7 7-7 7"/></button></div></div>)}</Table></div>:data&&<p className="ti-empty">No hay cuentas para estos filtros.</p>}
    {data&&(data.next||data.previous)&&<Pager {...{data,page,setPage}} disabled={disabled} label="Páginas de usuarios"/>}</section>
    <section className="card-fyag ti-panel"><div className="ti-head"><h2>Funciones de los roles</h2><button className="btn btn-outline-secondary" aria-expanded={matrixOpen} onClick={()=>setMatrixOpen(x=>!x)}>{matrixOpen?'Ocultar':'Ver roles'}</button></div>{matrixOpen&&<dl className="ti-role-list">{roles.map(([key,label])=><div key={key}><dt>{label}</dt><dd>{ROLE_NOTE[key]}</dd></div>)}</dl>}</section>
  </section>;
}

export default function Usuarios() {
  const { user } = useAuth();
  return canManageUsers(user?.role) ? <UsuariosTI key={`${user.id}:${user.role}`} /> : <p role="alert">No tiene permiso para administrar cuentas.</p>;
}
