import React, { useEffect, useState } from 'react';
import { PageHead } from '../components/ui';
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
  return <section>
    <PageHead title="Clientes" sub="Clientes persistidos en Django.">
      <button className="btn btn-fyag-primary" disabled={disabled} onClick={() => { setSelected(null); setForm({ ...emptyClient }); api.setError(null); }}>Nuevo cliente</button>
    </PageHead>
    <Errors error={api.error} />
    <button disabled={api.busy || api.loading} onClick={() => void api.reconcile(refresh)}>Reconsultar datos</button>
    {api.locked && <p role="status">Resultado incierto o conflicto: reconsulta antes de realizar otra escritura. No se repetirá la operación.</p>}
    {api.loading && <p role="status">Cargando clientes…</p>}
    {!clients.length && !api.loading && !api.error && <p>No hay clientes.</p>}
    <div className="table-responsive"><table className="table"><thead><tr><th>ID</th><th>Nombre legal</th><th>Identificación</th><th>Estado</th><th>Detalle</th></tr></thead>
      <tbody>{clients.map((c) => <tr key={c.id}><td>{c.id}</td><td>{c.nombre_legal}</td><td>{c.numero_identificacion || 'Sin identificación'}</td><td>{c.activo ? 'Activo' : 'Inactivo'}</td><td><button disabled={disabled || !!form} onClick={() => void detail(c.id)}>Ver cliente</button></td></tr>)}</tbody></table></div>
    {selected && <article className="card-fyag"><h2>{selected.nombre_legal} · #{selected.id}</h2>
      <button disabled={api.busy || api.loading} onClick={() => { setSelected(null); setForm(null); }}>Volver al listado</button>
      <dl>{Object.keys(emptyClient).map((key) => <React.Fragment key={key}><dt>{key}</dt><dd>{selected[key] || '—'}</dd></React.Fragment>)}</dl>
      <p>{selected.activo ? 'Activo' : 'Inactivo'}</p>
      <button disabled={disabled || !!form} onClick={() => setForm({ ...emptyClient, ...selected })}>Editar cliente</button>{' '}
      <button disabled={disabled || !!form} onClick={() => {
        const action = selected.activo ? 'desactivar' : 'activar';
        if (window.confirm(`¿${action} cliente #${selected.id}?`)) void api.write(`${clientPath(selected.id)}${action}/`, 'POST', {}, async (data) => { await api.requiredLoad('list', clientPath(), (rows) => { setClients(rows); setSelected(data); }); });
      }}>{selected.activo ? 'Desactivar' : 'Activar'}</button>
    </article>}
    {form && <form className="card-fyag" onSubmit={save}><h2>{selected ? 'Editar cliente' : 'Nuevo cliente'}</h2>
      <Fields form={form} setForm={setForm} fields={fields} disabled={api.busy} />
      <button type="submit" disabled={disabled}>Guardar cliente</button>{' '}
      <button type="button" disabled={api.busy} onClick={() => setForm(null)}>Cancelar</button>
    </form>}
  </section>;
}
