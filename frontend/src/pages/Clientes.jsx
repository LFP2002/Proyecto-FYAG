import React, { useEffect, useState } from 'react';
import { useAuth } from '../auth/AuthContext.jsx';
import { useApp } from '../context/AppContext.jsx';
import { AF, clientPayload, emptyClient, validateClient } from '../comercial/domain.js';
import { Chip, PageHead } from '../components/ui';
import { clientPath } from '../comercial/api.js';
import { Errors, useCommercial } from '../comercial/ui.jsx';
import TecIcon from '../obras/TecIcon.jsx';

const TYPES = [['PERSONA', 'Persona'], ['EMPRESA', 'Empresa']];
const IDS = [['RUT', 'RUT'], ['DOCUMENTO_EXTRANJERO', 'Documento extranjero'], ['SIN_IDENTIFICACION', 'Sin identificación']];
const typeLabel = (value) => Object.fromEntries(TYPES)[value] || '—';
const idLabel = (value) => Object.fromEntries(IDS)[value] || '—';
const normalize = (value) => String(value ?? '').normalize('NFD').replace(/[\u0300-\u036f]/g, '').toLowerCase();
const compactId = (value) => normalize(value).replace(/[.\s-]/g, '');
const initialFilters = { search: '', state: '', type: '' };

function Button({ icon, children, primary, variant, ...props }) {
  return <button type="button" className={'btn clientes-button ' + (variant || (primary ? 'btn-fyag-primary' : 'btn-outline-secondary'))} {...props}>{icon && <TecIcon name={icon}/>}<span>{children}</span></button>;
}
function Heading({ title, sub, children }) {
  return <header className="clientes-heading"><div><h1>{title}</h1>{sub && <p>{sub}</p>}</div><div className="clientes-actions">{children}</div></header>;
}
function Status({ row }) { return <Chip cls={row.activo ? 'green' : 'gray'}>{row.activo ? 'Activo' : 'Inactivo'}</Chip>; }
function Fact({ label, value }) { return <div><dt>{label}</dt><dd>{value || <span className="clientes-unrecorded">No registrado</span>}</dd></div>; }
function SectionTitle({ icon, children }) { return <h2 className="clientes-section-title"><TecIcon name={icon}/>{children}</h2>; }
const FIELD_HINTS = {
  nombre_legal: 'Nombre completo o razón social', nombre_contacto: 'Nombre de la persona de contacto',
  correo: 'correo@empresa.cl', telefono: '+56 9 1234 5678', pais_identificacion: 'Ej.: AR',
  tipo_documento_extranjero: 'Ej.: Pasaporte',
};
const FULL_FIELDS = new Set(['numero_identificacion', 'nombre_legal', 'nombre_contacto']);
function ClientFields({ form, setForm, fields, disabled }) {
  return <div className="fgrid commercial-fields">{fields.map(([name, label, options]) => {
    const required = ['nombre_legal', 'numero_identificacion', 'pais_identificacion', 'tipo_documento_extranjero'].includes(name);
    const change = e => setForm(previous => ({ ...previous, [name]: e.target.value }));
    const id = 'com-' + name;
    const hint = name === 'numero_identificacion' ? (form.tipo_identificacion === 'RUT' ? '12.345.678-5' : 'Número del documento') : FIELD_HINTS[name];
    return <div key={name} className={FULL_FIELDS.has(name) ? 'clientes-field-full' : undefined}>
      <label className="form-label" htmlFor={id}>{label}{required && <span className="clientes-required" aria-hidden="true"> *</span>}</label>
      {options ? <select id={id} className="form-select" disabled={disabled} value={form[name] ?? ''} onChange={change}>{options.map(([key, value]) => <option key={key} value={key}>{value}</option>)}</select>
      : <input id={id} className="form-control" disabled={disabled} value={form[name] ?? ''} onChange={change} placeholder={hint} aria-required={required || undefined} type={name === 'telefono' ? 'tel' : 'text'} inputMode={name === 'correo' ? 'email' : undefined} autoComplete={name === 'correo' ? 'email' : name === 'telefono' ? 'tel' : undefined}/>}
    </div>;
  })}</div>;
}

export default function Clientes() {
  const { user } = useAuth();
  if (user?.role !== AF) return <section><PageHead title="Clientes" /><p role="alert">Este módulo está reservado a Finanzas.</p></section>;
  return <ClientesScreen key={user.id} />;
}

function ClientesScreen() {
  const api = useCommercial(), app = useApp();
  const [clients, setClients] = useState(null);
  const [selected, setSelected] = useState(null);
  const [form, setForm] = useState(null);
  const [filters, setFilters] = useState(initialFilters);
  const [message, setMessage] = useState('');
  const disabled = api.busy || api.locked || api.loading;
  const locked = api.busy || api.locked;
  const reload = () => api.load('list', clientPath(), rows => {
    if (!Array.isArray(rows)) throw new Error('Listado de clientes inesperado.');
    setClients(rows);
  });
  useEffect(() => { void reload(); }, []);
  useEffect(() => {
    app?.setNavigationBlocked?.(locked);
    return () => app?.setNavigationBlocked?.(false);
  }, [locked, app?.setNavigationBlocked]);

  const detail = (id) => {
    api.setError(null); setMessage('');
    return api.load('detail', clientPath(id), data => { setSelected(data); setForm(null); });
  };
  const refresh = async () => {
    const ok = await reload();
    if (!ok) return false;
    return selected ? api.load('detail', clientPath(selected.id), setSelected) : true;
  };
  function back() {
    if (locked) return;
    api.setError(null); setMessage('');
    if (form) setForm(null);
    else setSelected(null);
  }
  function start() {
    if (disabled) return;
    setSelected(null); setForm({ ...emptyClient }); setMessage(''); api.setError(null);
  }
  async function save(event) {
    event.preventDefault();
    if (disabled || !form) return;
    const errors = validateClient(form);
    if (Object.keys(errors).length) { api.setError({ message: 'Revisa los datos.', fieldErrors: errors }); return; }
    const editing = !!selected;
    await api.write(clientPath(selected?.id), editing ? 'PATCH' : 'POST', clientPayload(form, selected), async data => {
      await api.requiredLoad('list', clientPath(), rows => {
        if (!Array.isArray(rows)) throw new Error('Listado de clientes inesperado.');
        setClients(rows); setSelected(data); setForm(null); setMessage(editing ? 'Cliente actualizado.' : 'Cliente registrado.');
      });
    });
  }
  async function toggle() {
    if (disabled || !selected) return;
    const action = selected.activo ? 'desactivar' : 'activar';
    if (!window.confirm(`¿${action === 'activar' ? 'Activar' : 'Desactivar'} a ${selected.nombre_legal}?`)) return;
    await api.write(`${clientPath(selected.id)}${action}/`, 'POST', {}, async data => {
      await api.requiredLoad('list', clientPath(), rows => {
        if (!Array.isArray(rows)) throw new Error('Listado de clientes inesperado.');
        setClients(rows); setSelected(data); setMessage(data.activo ? 'Cliente activado.' : 'Cliente desactivado.');
      });
    });
  }
  const refreshButton = <Button icon="refresh" disabled={api.busy || api.loading} onClick={() => void api.reconcile(refresh)}>Actualizar</Button>;
  const feedback = <><Errors error={api.error}/>{api.locked && <div className="alert alert-warning" role="status">Resultado incierto o conflicto. Actualiza los datos antes de realizar otra escritura. No se repetirá la operación.</div>}{message && <p className="alert alert-info" role="status">{message}</p>}{api.loading && <p className="commercial-loading" role="status">Cargando clientes…</p>}</>;

  if (form) {
    const identityFields = [
      ['tipo_cliente', 'Tipo de cliente', TYPES],
      ['tipo_identificacion', 'Tipo de identificación', IDS],
      ...(form.tipo_identificacion !== 'SIN_IDENTIFICACION' ? [['numero_identificacion', form.tipo_identificacion === 'RUT' ? 'RUT' : 'Número de identificación']] : []),
      ...(form.tipo_identificacion === 'DOCUMENTO_EXTRANJERO' ? [['pais_identificacion', 'País (ISO, dos letras)'], ['tipo_documento_extranjero', 'Tipo de documento extranjero']] : []),
      ['nombre_legal', 'Nombre legal'],
    ];
    return <section className="commercial-page clientes-page clientes-compact">
      <div className="clientes-back"><Button icon="back" disabled={disabled} onClick={back}>{selected ? 'Volver al detalle' : 'Volver a clientes'}</Button></div>
      <Heading title={selected ? 'Editar cliente' : 'Nuevo cliente'} sub={selected ? 'Actualiza los datos del cliente.' : 'Completa los datos de identificación y contacto.'}>{api.locked && refreshButton}</Heading>
      {feedback}
      <form className="clientes-form" onSubmit={save}>
        <section className="card-fyag clientes-panel"><SectionTitle icon="work">Identificación</SectionTitle><ClientFields form={form} setForm={setForm} fields={identityFields} disabled={locked}/></section>
        <section className="card-fyag clientes-panel"><SectionTitle icon="person">Información de contacto</SectionTitle><ClientFields form={form} setForm={setForm} fields={ [['nombre_contacto', 'Nombre de contacto'], ['correo', 'Correo electrónico'], ['telefono', 'Teléfono']] } disabled={locked}/><p className="commercial-help clientes-contact-note">Ingresa al menos un correo electrónico o teléfono.</p></section>
        <div className="clientes-actions clientes-end"><small className="clientes-required-note">* Campos obligatorios</small><Button disabled={disabled} onClick={back}>Cancelar</Button><button className="btn btn-fyag-primary clientes-button" type="submit" disabled={disabled}><TecIcon name="check"/><span>Guardar cliente</span></button></div>
      </form>
    </section>;
  }
  if (selected) return <section className="commercial-page clientes-page clientes-compact">
    <div className="clientes-back"><Button icon="back" disabled={disabled} onClick={back}>Volver a clientes</Button></div>
    {feedback}
    <section className="card-fyag clientes-panel clientes-profile">
      <div className="clientes-profile-head">
        <div className="clientes-profile-identity"><div className="clientes-avatar"><TecIcon name={selected.tipo_cliente === 'EMPRESA' ? 'work' : 'person'}/></div>
          <div><h1>{selected.nombre_legal}</h1><p>{selected.tipo_cliente === 'EMPRESA' ? 'Cliente empresarial' : 'Cliente particular'} · #{selected.id}</p></div>
        </div><Status row={selected}/>
      </div>
      <div className="clientes-actions clientes-profile-actions">{refreshButton}<Button disabled={disabled} onClick={() => { setForm({ ...emptyClient, ...selected }); setMessage(''); api.setError(null); }}>Editar cliente</Button><Button variant={selected.activo ? 'btn-outline-danger' : 'btn-outline-success'} disabled={disabled} onClick={() => void toggle()}>{selected.activo ? 'Desactivar' : 'Activar'}</Button></div>
    </section>
    <div className="clientes-detail-grid">
      <section className="card-fyag clientes-panel"><SectionTitle icon="work">Identificación</SectionTitle><dl className="commercial-facts">
        <Fact label="Tipo de cliente" value={typeLabel(selected.tipo_cliente)}/><Fact label="Tipo de identificación" value={idLabel(selected.tipo_identificacion)}/>
        {selected.tipo_identificacion !== 'SIN_IDENTIFICACION' && <Fact label="Número de identificación" value={selected.numero_identificacion}/>}
        {selected.tipo_identificacion === 'DOCUMENTO_EXTRANJERO' && <><Fact label="País" value={selected.pais_identificacion}/><Fact label="Documento extranjero" value={selected.tipo_documento_extranjero}/></>}
        <Fact label="Nombre legal" value={selected.nombre_legal}/>
      </dl></section>
      <section className="card-fyag clientes-panel"><SectionTitle icon="person">Información de contacto</SectionTitle><dl className="commercial-facts"><Fact label="Contacto" value={selected.nombre_contacto}/><Fact label="Correo electrónico" value={selected.correo}/><Fact label="Teléfono" value={selected.telefono}/></dl></section>
    </div>
  </section>;

  const term = normalize(filters.search.trim()), idTerm = compactId(term);
  const visible = [...(clients || [])].sort((a, b) => a.id - b.id).filter(c =>
    (!term || [c.nombre_legal, c.numero_identificacion, c.nombre_contacto, c.correo, c.telefono].some(v => normalize(v).includes(term)) || (idTerm && compactId(c.numero_identificacion).includes(idTerm)))
    && (!filters.state || String(c.activo) === filters.state)
    && (!filters.type || c.tipo_cliente === filters.type));
  const filtered = !!(term || filters.state || filters.type);
  const filter = (key, value) => setFilters(previous => ({ ...previous, [key]: value }));
  return <section className="commercial-page clientes-page">
    <Heading title="Clientes" sub="Gestiona la información de tus clientes.">{refreshButton}<Button icon="plus" primary disabled={disabled} onClick={start}>Nuevo cliente</Button></Heading>
    {feedback}
    <section className="card-fyag clientes-panel clientes-list">
      <div className="clientes-filters">
        <div className="clientes-search"><label className="form-label" htmlFor="clientes-search">Buscar cliente</label><div><TecIcon name="search"/><input id="clientes-search" className="form-control" placeholder="Nombre, RUT o contacto" value={filters.search} onChange={e => filter('search', e.target.value)} /></div></div>
        <div><label className="form-label" htmlFor="clientes-state">Estado</label><select id="clientes-state" className="form-select" value={filters.state} onChange={e => filter('state', e.target.value)}><option value="">Todos los estados</option><option value="true">Activos</option><option value="false">Inactivos</option></select></div>
        <div><label className="form-label" htmlFor="clientes-type">Tipo de cliente</label><select id="clientes-type" className="form-select" value={filters.type} onChange={e => filter('type', e.target.value)}><option value="">Todos los tipos</option>{TYPES.map(([k,v]) => <option value={k} key={k}>{v}</option>)}</select></div>
        {filtered && <Button onClick={() => setFilters(initialFilters)}>Limpiar filtros</Button>}
      </div>
      {clients && !api.loading && !api.error && <>
        <div className="clientes-table-frame"><div className="table-responsive" role="region" aria-label="Listado de clientes" tabIndex={0}><table className="table table-hover align-middle commercial-table"><thead><tr><th scope="col">Cliente</th><th scope="col">Identificación</th><th scope="col">Contacto</th><th scope="col">Estado</th><th scope="col">Detalle</th></tr></thead><tbody>
          {visible.map(c => <tr key={c.id}><td className="commercial-description"><strong>{c.nombre_legal}</strong><small className="clientes-secondary">{typeLabel(c.tipo_cliente)}</small></td><td>{c.numero_identificacion || idLabel(c.tipo_identificacion)}{c.tipo_identificacion === 'DOCUMENTO_EXTRANJERO' && <small className="clientes-secondary">{[c.pais_identificacion, c.tipo_documento_extranjero].filter(Boolean).join(' · ')}</small>}</td><td className="commercial-description">{c.nombre_contacto || '—'}{c.correo && <small className="clientes-secondary">{c.correo}</small>}{!c.correo && c.telefono && <small className="clientes-secondary">{c.telefono}</small>}</td><td><Status row={c}/></td><td><Button icon="chevron" disabled={disabled} onClick={() => void detail(c.id)}>Ver detalle</Button></td></tr>)}
        </tbody></table></div>{!visible.length && <div className="commercial-empty"><TecIcon name="inbox"/><h2>{filtered ? 'No se encontraron clientes.' : 'No hay clientes.'}</h2><p>{filtered ? 'Prueba otra búsqueda o limpia los filtros.' : 'Crea un cliente para comenzar a preparar sus presupuestos.'}</p></div>}</div>
        <p className="clientes-count" role="status">{visible.length} de {clients.length} clientes</p>
      </>}
    </section>
  </section>;
}
