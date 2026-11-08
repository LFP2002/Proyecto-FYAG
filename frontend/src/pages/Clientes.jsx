import React, { useEffect, useState } from 'react';
import { Chip, PageHead } from '../components/ui';
import { clientPath } from '../comercial/api.js';
import { clientPayload, emptyClient, validateClient } from '../comercial/domain.js';
import { Errors, Fields, useCommercial } from '../comercial/ui.jsx';

export default function Clientes() {
  const api = useCommercial();
  const [clients, setClients] = useState([]);
  const [selected, setSelected] = useState(null);
  const [form, setForm] = useState(null);
  const reload = () => api.load('list', clientPath(), setClients);
  useEffect(() => { void reload(); }, []);
  const detail = (id) => api.load('detail', clientPath(id), (data) => { setSelected(data); setForm(null); });
  const refresh = async () => {
    const ok = await reload();
    return selected ? (await api.load('detail', clientPath(selected.id), setSelected)) && ok : ok;
  };
  async function save(event) {
    event.preventDefault();
    const errors = validateClient(form);
    if (Object.keys(errors).length) { api.setError({ message: 'Revisa los datos.', fieldErrors: errors }); return; }
    await api.write(clientPath(selected?.id), selected ? 'PATCH' : 'POST', clientPayload(form, selected), async (data) => {
      await api.requiredLoad('list', clientPath(), (rows) => { setClients(rows); setSelected(data); setForm(null); });
    });
  }
  const disabled = api.busy || api.locked || api.loading;
  const fields = [
    ['tipo_cliente', 'Tipo de cliente', [['PERSONA', 'Persona'], ['EMPRESA', 'Empresa']]],
    ['tipo_identificacion', 'Identificación', [['RUT', 'RUT'], ['DOCUMENTO_EXTRANJERO', 'Documento extranjero'], ['SIN_IDENTIFICACION', 'Sin identificación']]],
    ...(form?.tipo_identificacion !== 'SIN_IDENTIFICACION' ? [['numero_identificacion', 'Número de identificación']] : []),
    ...(form?.tipo_identificacion === 'DOCUMENTO_EXTRANJERO' ? [['pais_identificacion', 'País (ISO, dos letras)'], ['tipo_documento_extranjero', 'Tipo de documento extranjero']] : []),
    ['nombre_legal', 'Nombre legal'], ['nombre_contacto', 'Contacto'], ['correo', 'Correo'], ['telefono', 'Teléfono'],
  ];
  const detailLabels = { tipo_cliente: 'Tipo de cliente', tipo_identificacion: 'Tipo de identificación', numero_identificacion: 'Número de identificación', pais_identificacion: 'País', tipo_documento_extranjero: 'Documento extranjero', nombre_legal: 'Nombre legal', nombre_contacto: 'Contacto', correo: 'Correo', telefono: 'Teléfono' };
  return <section className="commercial-page">
    <PageHead title="Clientes" sub="Clientes persistidos en Django.">
      <button className="btn btn-fyag-primary" disabled={disabled} onClick={() => { setSelected(null); setForm({ ...emptyClient }); api.setError(null); }}>Nuevo cliente</button>
    </PageHead>
    <Errors error={api.error} />
    <div className="commercial-toolbar">
      <p className="commercial-help mb-0">Consulta y administra los datos de tus clientes.</p>
      <button className="btn btn-outline-secondary" disabled={api.busy || api.loading} onClick={() => void api.reconcile(refresh)}>Reconsultar datos</button>
    </div>
    {api.locked && <p className="alert alert-warning" role="status">Resultado incierto o conflicto: reconsulta antes de realizar otra escritura. No se repetirá la operación.</p>}
    {api.loading && <p className="commercial-loading" role="status">Cargando clientes…</p>}
    <div className="card-fyag commercial-table-card">
      <div className="table-responsive" role="region" aria-label="Listado de clientes" tabIndex={0}><table className="table table-hover align-middle commercial-table"><thead><tr><th scope="col">ID</th><th scope="col">Nombre legal</th><th scope="col">Identificación</th><th scope="col">Estado</th><th scope="col">Detalle</th></tr></thead>
        <tbody>{clients.map((c) => <tr key={c.id}><td className="commercial-code">#{c.id}</td><td className="commercial-description"><strong>{c.nombre_legal}</strong></td><td className="commercial-description">{c.numero_identificacion || 'Sin identificación'}</td><td><Chip cls={c.activo ? 'green' : 'gray'}>{c.activo ? 'Activo' : 'Inactivo'}</Chip></td><td><button className="btn btn-outline-secondary btn-sm" disabled={disabled || !!form} onClick={() => void detail(c.id)}>Ver cliente</button></td></tr>)}</tbody></table></div>
      {!clients.length && !api.loading && !api.error && <div className="commercial-empty"><h2>No hay clientes.</h2><p>Crea un cliente para comenzar a preparar sus presupuestos.</p></div>}
    </div>
    {selected && <article className="card-fyag commercial-detail">
      <div className="commercial-section-head"><div><h2>{selected.nombre_legal} · #{selected.id}</h2><Chip cls={selected.activo ? 'green' : 'gray'}>{selected.activo ? 'Activo' : 'Inactivo'}</Chip></div>
        <button className="btn btn-outline-secondary btn-sm" disabled={api.busy || api.loading} onClick={() => { setSelected(null); setForm(null); }}>Volver al listado</button>
      </div>
      <dl className="commercial-facts">{Object.keys(emptyClient).map((key) => <div key={key}><dt>{detailLabels[key]}</dt><dd>{selected[key] || '—'}</dd></div>)}</dl>
      <div className="commercial-actions">
      <button className="btn btn-outline-secondary" disabled={disabled || !!form} onClick={() => setForm({ ...emptyClient, ...selected })}>Editar cliente</button>
      <button className={`btn ${selected.activo ? 'btn-outline-danger' : 'btn-outline-success'}`} disabled={disabled || !!form} onClick={() => {
        const action = selected.activo ? 'desactivar' : 'activar';
        if (window.confirm(`¿${action} cliente #${selected.id}?`)) void api.write(`${clientPath(selected.id)}${action}/`, 'POST', {}, async (data) => { await api.requiredLoad('list', clientPath(), (rows) => { setClients(rows); setSelected(data); }); });
      }}>{selected.activo ? 'Desactivar' : 'Activar'}</button>
      </div>
    </article>}
    {form && <form className="card-fyag commercial-form" onSubmit={save}><h2>{selected ? 'Editar cliente' : 'Nuevo cliente'}</h2>
      <Fields form={form} setForm={setForm} fields={fields} disabled={api.busy} />
      <div className="commercial-form-actions"><button className="btn btn-fyag-primary" type="submit" disabled={disabled}>Guardar cliente</button>
      <button className="btn btn-outline-secondary" type="button" disabled={api.busy} onClick={() => setForm(null)}>Cancelar</button></div>
    </form>}
  </section>;
}
