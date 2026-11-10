import React, { useEffect, useState } from 'react';
import { useAuth } from '../auth/AuthContext';
import { Chip } from '../components/ui';
import { categoryPath, collectionPath, readPage } from './api.js';
import { canReadTeam, G } from './domain.js';
import { EventList, Feedback, Field, focusError, Pager, RefreshButton, useOperational } from './ui.jsx';

function CategoryDetail({ id, onBack }) {
  const { user } = useAuth(), api = useOperational();
  const [category, setCategory] = useState(null), [history, setHistory] = useState(null), [page, setPage] = useState(1);
  const [form, setForm] = useState(null), [errors, setErrors] = useState({});
  const base = categoryPath(id), admin = user.role === G;
  const read = () => { setCategory(null); return api.load('detail', base, setCategory); };
  const readHistory = () => api.load('history', collectionPath(`${base}historial/`, page), (data) => setHistory(readPage(data, `${base}historial/`)));
  useEffect(() => { void read(); }, [id]);
  useEffect(() => { if (admin) { setHistory(null); void readHistory(); } }, [id, page]);
  async function refresh() { const a = await read(); return admin ? (await readHistory()) && a : a; }
  async function submit(event) {
    event.preventDefault();
    if (!admin || api.busy || api.loading || api.locked) return;
    const invalid = {};
    if (form.type === 'renombrar' && (!form.nombre.trim() || form.nombre.trim().length > 100)) invalid.nombre = 'Ingresa un nombre de hasta 100 caracteres';
    if ((form.type !== 'renombrar' || form.nombre.trim() !== category.nombre) && !form.motivo.trim()) invalid.motivo = 'Campo obligatorio';
    if (form.motivo.trim().length > 2000) invalid.motivo = 'Máximo 2000 caracteres';
    setErrors(invalid); focusError(event, invalid); if (Object.keys(invalid).length) return;
    if (form.type === 'desactivar' && !window.confirm(`¿Desactivar la categoría ${category.nombre}?`)) return;
    await api.write(form.type === 'renombrar' ? base : `${base}${form.type}/`, form.type === 'renombrar' ? 'PATCH' : 'POST', { ...(form.type === 'renombrar' ? { nombre: form.nombre.trim() } : {}), motivo: form.motivo.trim() }, async () => {
      await api.requiredLoad('detail', base, setCategory);
      await api.requiredLoad('history', collectionPath(`${base}historial/`, page), (data) => { setHistory(readPage(data, `${base}historial/`)); setForm(null); });
    });
  }
  const blocked = api.busy || api.loading || api.locked;
  const open = (type) => { api.setError(null); setErrors({}); setForm({ type, nombre: category.nombre, motivo: '' }); };
  return <article className="card-fyag commercial-detail"><div className="commercial-section-head"><h2>{category?.nombre || `Categoría #${id}`}</h2><div className="commercial-row-actions"><RefreshButton busy={api.busy || api.loading} onClick={() => void api.reconcile(refresh)} /><button className="btn btn-outline-secondary btn-sm" disabled={api.busy} onClick={onBack}>Volver a categorías</button></div></div>
    <Feedback api={api} />
    {category && <><p>Categoría #{category.id} · <Chip cls={category.activo ? 'green' : 'gray'}>{category.activo ? 'Activa' : 'Inactiva'}</Chip></p>
      {admin && <div className="commercial-actions"><button className="btn btn-outline-secondary" disabled={blocked || !!form} onClick={() => open('renombrar')}>Renombrar categoría</button><button className={`btn ${category.activo ? 'btn-outline-danger' : 'btn-outline-success'}`} disabled={blocked || !!form} onClick={() => open(category.activo ? 'desactivar' : 'activar')}>{category.activo ? 'Desactivar categoría' : 'Activar categoría'}</button></div>}
      {form && admin && <form className="commercial-form obras-action-form" noValidate onSubmit={submit}><h2>{form.type === 'renombrar' ? 'Renombrar categoría' : form.type === 'activar' ? 'Activar categoría' : 'Desactivar categoría'}</h2>
        {form.type === 'renombrar' && <Field name="nombre" label="Nombre" value={form.nombre} onChange={(nombre) => setForm({ ...form, nombre })} error={errors.nombre} disabled={api.busy} maxLength={100} required />}
        <Field name="motivo" label="Motivo" value={form.motivo} onChange={(motivo) => setForm({ ...form, motivo })} type="textarea" error={errors.motivo} disabled={api.busy} maxLength={2000} />
        <div className="commercial-form-actions"><button className="btn btn-fyag-primary" type="submit" disabled={blocked}>Guardar categoría</button><button type="button" className="btn btn-outline-secondary" disabled={api.busy} onClick={() => setForm(null)}>Cancelar</button></div>
      </form>}
      {admin && <><EventList title="Historial de categoría" data={history} /><Pager label="Paginación del historial de categoría" data={history} page={page} setPage={setPage} disabled={blocked || !!form} /></>}
    </>}
  </article>;
}
export default function Categories({ onBack }) {
  const { user } = useAuth(), api = useOperational();
  const [data, setData] = useState(null), [query, setQuery] = useState({ page: 1, activo: '' }), [selected, setSelected] = useState(null);
  const [creating, setCreating] = useState(false), [name, setName] = useState(''), [errors, setErrors] = useState({});
  const read = () => { setData(null); return api.load('list', collectionPath(categoryPath(), query.page, { activo: query.activo }), (result) => setData(readPage(result, categoryPath()))); };
  useEffect(() => { setData(null); if (canReadTeam(user.role)) void read(); }, [query]);
  async function create(event) {
    event.preventDefault();
    if (user.role !== G || api.busy || api.locked) return;
    const invalid = !name.trim() || name.trim().length > 100 ? { nombre: 'Ingresa un nombre de hasta 100 caracteres' } : {};
    setErrors(invalid); focusError(event, invalid); if (Object.keys(invalid).length) return;
    await api.write(categoryPath(), 'POST', { nombre: name.trim() }, async (result) => {
      await api.requiredLoad('list', collectionPath(categoryPath(), query.page, { activo: query.activo }), (rows) => setData(readPage(rows, categoryPath())));
      await api.requiredLoad('created', categoryPath(result.id), (actual) => { setSelected(actual.id); setCreating(false); setName(''); });
    });
  }
  const blocked = api.busy || api.loading || api.locked;
  if (!canReadTeam(user.role)) return <p role="alert">No tienes acceso a categorías.</p>;
  if (selected) return <CategoryDetail key={`${user.id}:${user.role}:${selected}`} id={selected} onBack={() => { setSelected(null); void read(); }} />;
  return <section>
    <div className="commercial-section-head"><h2>Categorías de servicio</h2><button className="btn btn-outline-secondary" disabled={api.busy} onClick={onBack}>Volver a obras</button></div>
    <div className="budget-toolbar">{user.role === G && <button className="btn btn-fyag-primary" disabled={blocked || creating} onClick={() => { api.setError(null); setErrors({}); setCreating(true); }}>Nueva categoría</button>}
      <Field name="categorias_activo" label="Vigencia" options={[[ '', 'Todas' ], ['true', 'Activas'], ['false', 'Inactivas']]} value={query.activo} onChange={(activo) => setQuery({ page: 1, activo })} disabled={api.busy || creating} />
      <RefreshButton busy={api.busy || api.loading} onClick={() => void api.reconcile(read)} />
    </div>
    <Feedback api={api} />
    <div className="card-fyag commercial-table-card"><div className="table-responsive" role="region" aria-label="Catálogo de categorías" tabIndex={0}><table className="table table-hover align-middle commercial-table"><thead><tr><th scope="col">Nombre</th><th scope="col">Vigencia</th><th scope="col">Detalle</th></tr></thead><tbody>{data?.results.map((category) => <tr key={category.id}><td>{category.nombre} · #{category.id}</td><td><Chip cls={category.activo ? 'green' : 'gray'}>{category.activo ? 'Activa' : 'Inactiva'}</Chip></td><td><button className="btn btn-outline-secondary btn-sm" disabled={blocked || creating} onClick={() => setSelected(category.id)}>Ver categoría</button></td></tr>)}</tbody></table></div>
      {data && !data.count && <p className="commercial-empty">No hay categorías para este filtro.</p>}
      <Pager label="Paginación de categorías" data={data} page={query.page} setPage={(page) => setQuery({ ...query, page })} disabled={blocked || creating} />
      {api.error?.status === 404 && query.page !== 1 && <button className="btn btn-outline-secondary m-3" onClick={() => setQuery({ ...query, page: 1 })}>Volver a la primera página</button>}
    </div>
    {creating && user.role === G && <form className="card-fyag commercial-form" noValidate onSubmit={create}><h2>Nueva categoría</h2><Field name="nombre" label="Nombre" value={name} onChange={setName} disabled={api.busy} error={errors.nombre} required maxLength={100} /><div className="commercial-form-actions"><button className="btn btn-fyag-primary" disabled={blocked} type="submit">Crear categoría</button><button className="btn btn-outline-secondary" disabled={api.busy} type="button" onClick={() => setCreating(false)}>Cancelar</button></div></form>}
  </section>;
}
