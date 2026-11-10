import React, { useEffect, useRef, useState } from 'react';
import { useAuth } from '../auth/AuthContext';
import { PageHead } from '../components/ui';
import { collectionPath, obraPath, readPage } from '../obras/api.js';
import { canReadObras, canReadTeam, emptyFilters, filterErrors, OBRA_STATES, orderingOptions, projectObra, S, shortDate, T } from '../obras/domain.js';
import Categories from '../obras/Categories.jsx';
import NewObra from '../obras/ObraForm.jsx';
import ObraDetail from '../obras/ObraDetail.jsx';
import { Feedback, Field, focusError, ObraStatus, Pager, PendingSection, RefreshButton, useOperational } from '../obras/ui.jsx';

export default function Obras() {
  const { user } = useAuth(), api = useOperational();
  const [query, setQuery] = useState({ filters: { ...emptyFilters }, page: 1 });
  const [draft, setDraft] = useState({ ...emptyFilters }), [errors, setErrors] = useState({});
  const [data, setData] = useState(null), [selected, setSelected] = useState(null), [creating, setCreating] = useState(false), [categories, setCategories] = useState(false), [expanded, setExpanded] = useState(false);
  const refreshFlight = useRef(false);
  const path = user.role === T ? `${obraPath()}mis-obras/` : obraPath();
  const read = () => { setData(null); return api.load('list', collectionPath(path, query.page, query.filters), (result) => {
    const page = readPage(result, path); setData({ ...page, results: page.results.map((row) => projectObra(row, user.role)) });
  }); };
  useEffect(() => { setData(null); if (canReadObras(user.role)) void read(); }, [query]);
  async function refresh() {
    if (refreshFlight.current || api.busy || api.loading) return;
    refreshFlight.current = true;
    try { await api.reconcile(read); } finally { refreshFlight.current = false; }
  }
  function apply(event) {
    event.preventDefault();
    const invalid = filterErrors(draft); setErrors(invalid); focusError(event, invalid);
    if (!Object.keys(invalid).length) { api.setError(null); setQuery({ filters: { ...draft }, page: 1 }); }
  }
  const blocked = api.busy || api.loading || api.locked;
  if (!canReadObras(user.role)) return <p role="alert">No tienes acceso a Obras.</p>;
  if (categories && canReadTeam(user.role)) return <section className="commercial-page obras-page"><Categories onBack={() => setCategories(false)} /></section>;
  if (selected) return <section className="commercial-page obras-page"><ObraDetail key={`${user.id}:${user.role}:${selected}`} id={selected} onBack={() => { setSelected(null); void read(); }} /></section>;
  return <section className="commercial-page obras-page">
    <PageHead title={user.role === T ? 'Mis obras' : 'Obras'} sub={user.role === T ? 'Consulta tus obras asignadas.' : 'Planificación y seguimiento operativo.'} />
    <div className="budget-toolbar">
      {user.role === S && <button className="btn btn-fyag-primary" disabled={blocked || creating} onClick={() => { setExpanded(false); setCreating(true); }}>Nueva obra</button>}
      {canReadTeam(user.role) && <button className="btn btn-outline-secondary" disabled={blocked || creating} onClick={() => setCategories(true)}>Categorías de servicio</button>}
      <div className="budget-toolbar-filters"><button className="btn btn-outline-secondary" type="button" aria-expanded={expanded} aria-controls="obras-filters" disabled={api.busy || creating} onClick={() => setExpanded(!expanded)}>Filtros</button><RefreshButton busy={api.busy || api.loading} onClick={refresh} /></div>
    </div>
    {expanded && <form id="obras-filters" className="card-fyag commercial-form" noValidate onSubmit={apply}>
      <div className="obras-form-grid">
        <Field name="estado" label="Estado" value={draft.estado} options={[[ '', 'Todos' ], ...Object.entries(OBRA_STATES).map(([key, [label]]) => [key, label])]} onChange={(estado) => setDraft({ ...draft, estado })} error={errors.estado} />
        {[[ 'cliente', 'Cliente (ID)' ], ['tecnico_responsable', 'Responsable (ID)'], ['categoria_servicio', 'Categoría (ID)']].map(([name, label]) => <Field key={name} name={name} label={label} value={draft[name]} onChange={(value) => setDraft({ ...draft, [name]: value })} error={errors[name]} />)}
        <Field name="fecha_programada_desde" label="Programada desde" type="date" value={draft.fecha_programada_desde} onChange={(value) => setDraft({ ...draft, fecha_programada_desde: value })} error={errors.fecha_programada_desde} />
        <Field name="fecha_programada_hasta" label="Programada hasta" type="date" value={draft.fecha_programada_hasta} onChange={(value) => setDraft({ ...draft, fecha_programada_hasta: value })} error={errors.fecha_programada_hasta} />
        <Field name="ordering" label="Ordenar por" value={draft.ordering} options={orderingOptions} onChange={(ordering) => setDraft({ ...draft, ordering })} error={errors.ordering} />
      </div><div className="commercial-form-actions"><button className="btn btn-fyag-primary" disabled={api.loading} type="submit">Aplicar filtros</button><button className="btn btn-outline-secondary" disabled={api.loading} type="button" onClick={() => { setDraft({ ...emptyFilters }); setErrors({}); api.setError(null); setQuery({ filters: { ...emptyFilters }, page: 1 }); }}>Limpiar filtros</button></div>
    </form>}
    <Feedback api={api} />
    <div className="card-fyag commercial-table-card"><div className="table-responsive" role="region" aria-label={user.role === T ? 'Mis obras asignadas' : 'Listado de obras'} tabIndex={0}><table className="table table-hover align-middle commercial-table"><thead><tr>{['Código', 'Cliente', 'Categoría', 'Responsable', 'Estado', 'Programación', 'Detalle'].map((label) => <th scope="col" key={label}>{label}</th>)}</tr></thead><tbody>
      {data?.results.map((obra) => <tr key={obra.id}><td className="commercial-code">{obra.codigo} · #{obra.id}</td><td className="commercial-description">{obra.cliente_nombre} · #{obra.cliente}</td><td>{obra.categoria_nombre} · #{obra.categoria_servicio}</td><td>{obra.tecnico_nombre || 'Sin asignar'}{obra.tecnico_responsable ? ` · #${obra.tecnico_responsable}` : ''}</td><td><ObraStatus state={obra.estado} /></td><td>{shortDate(obra.fecha_programada)}</td><td><button className="btn btn-outline-secondary btn-sm" disabled={blocked || creating} onClick={() => setSelected(obra.id)}>Ver obra</button></td></tr>)}
    </tbody></table></div>
      {data && !data.count && <div className="commercial-empty"><h2>No hay obras para esta consulta.</h2><p>Prueba con otros filtros.</p></div>}
      <Pager label="Paginación de obras" data={data} page={query.page} setPage={(page) => setQuery({ ...query, page })} disabled={blocked || creating} />
      {api.error?.status === 404 && query.page !== 1 && <button className="btn btn-outline-secondary m-3" onClick={() => setQuery({ ...query, page: 1 })}>Volver a la primera página</button>}
    </div>
    {creating && user.role === S && <NewObra onClose={() => setCreating(false)} onCreated={(id) => { setCreating(false); setSelected(id); }} />}
    {user.role === T && <PendingSection>Mis turnos: pendiente de integración frontend en 005C-2.</PendingSection>}
  </section>;
}
