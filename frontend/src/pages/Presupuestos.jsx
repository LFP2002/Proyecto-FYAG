import React, { useEffect, useRef, useState } from 'react';
import { useAuth } from '../auth/AuthContext';
import { PageHead } from '../components/ui';
import { PRE_E } from '../data/constants';
import { budgetPath, clientPath, itemPath, pagePath, validatePage } from '../comercial/api.js';
import { AF, actionsFor, dateLabel, emptyItem, itemPayload, labels, money, needsReason } from '../comercial/domain.js';
import { actionButtonClass, BudgetStatus, Errors, Fields, Pager, useCommercial } from '../comercial/ui.jsx';
import ItemEditRow, { itemRowErrors } from '../comercial/ItemEditRow.jsx';

export default function Presupuestos() {
  const { user } = useAuth();
  const api = useCommercial();
  const [clients, setClients] = useState([]);
  const [list, setList] = useState(null);
  const [page, setPage] = useState(1);
  const [selected, setSelected] = useState(null);
  const [history, setHistory] = useState(null);
  const [historyPage, setHistoryPage] = useState(1);
  const [header, setHeader] = useState(null);
  const [line, setLine] = useState(null);
  const addItemButton = useRef(null);
  const wasEditing = useRef(false);
  useEffect(() => {
    if (line) wasEditing.current = true;
    else if (wasEditing.current && !api.busy && !api.loading) {
      addItemButton.current?.focus(); wasEditing.current = false;
    }
  }, [!!line, api.busy, api.loading]);
  const [action, setAction] = useState(null);
  const [reason, setReason] = useState('');
  const [filter, setFilter] = useState('');
  const refreshFlight = useRef(false);
  const reload = () => api.load('list', pagePath(budgetPath(), page), (data) => setList(validatePage(data, budgetPath())));
  const loadClients = () => api.load('clients', clientPath(), setClients);
  const loadHistory = (pk, p = 1) => api.load('history', pagePath(`${budgetPath(pk)}historial/`, p), (data) => setHistory(validatePage(data, `${budgetPath(pk)}historial/`)));
  useEffect(() => { setList(null); void reload(); }, [page]);
  useEffect(() => { void loadClients(); }, []);
  useEffect(() => { if (selected) { setHistory(null); void loadHistory(selected.id, historyPage); } }, [selected?.id, historyPage]);
  async function detail(pk) {
    setSelected(null); setHistory(null); setHeader(null); setLine(null); setAction(null); setHistoryPage(1);
    await api.load('detail', budgetPath(pk), setSelected);
  }
  async function refresh() {
    const a = await reload(), b = await loadClients();
    if (!selected) return a && b;
    const c = await api.load('detail', budgetPath(selected.id), setSelected);
    const d = await loadHistory(selected.id, historyPage);
    return a && b && c && d;
  }
  async function refreshFromToolbar() {
    if (refreshFlight.current || api.busy || api.loading) return;
    refreshFlight.current = true;
    try { await api.reconcile(refresh); }
    finally { refreshFlight.current = false; }
  }
  async function refreshedDetail(pk) {
    // Después de cualquier línea, leer de nuevo neto/subtotales del backend.
    await api.requiredLoad('detail', budgetPath(pk), setSelected);
    await api.requiredLoad('list', pagePath(budgetPath(), page), (data) => setList(validatePage(data, budgetPath())));
    await api.requiredLoad('history', pagePath(`${budgetPath(pk)}historial/`, historyPage), (data) => setHistory(validatePage(data, `${budgetPath(pk)}historial/`)));
  }
  const disabled = api.busy || api.locked || api.loading;
  const editable = user.role === AF && selected?.estado === 'BORRADOR';
  const clientOptions = [['', 'Selecciona cliente activo'], ...clients.filter((c) => c.activo || c.id === selected?.cliente).map((c) => [String(c.id), `${c.nombre_legal} · #${c.id}${c.activo ? '' : ' (inactivo, solo conservar)'}`])];
  const clientLabel = (pk) => clients.find((c) => c.id === pk)?.nombre_legal || `Cliente #${pk}`;
  async function saveHeader(event) {
    event.preventDefault();
    if (selected && !editable) return;
    const cliente = Number(header.cliente);
    if (!Number.isSafeInteger(cliente) || cliente <= 0 || !header.descripcion.trim()) { api.setError({ message: 'Selecciona un cliente e ingresa descripción.' }); return; }
    const data = { ...(selected && cliente === selected.cliente ? {} : { cliente }), ...(selected && header.descripcion === selected.descripcion ? {} : { descripcion: header.descripcion.trim() }) };
    if (data.cliente && !clients.some((c) => c.id === cliente && c.activo)) { api.setError({ message: 'El cliente debe estar activo.' }); return; }
    await api.write(budgetPath(selected?.id), selected ? 'PATCH' : 'POST', data, async (result) => {
      await refreshedDetail(result.id); setHeader(null); setHistoryPage(1);
    });
  }
  async function saveLine(event) {
    event.preventDefault();
    if (!editable || disabled || !line) return;
    const errors = itemRowErrors(line.form, selected.items, line.original);
    if (Object.keys(errors).length) return;
    await api.write(itemPath(selected.id, line.original?.id), line.original ? 'PATCH' : 'POST', itemPayload(line.form, line.original), async () => { await refreshedDetail(selected.id); setLine(null); });
  }
  async function execute(event) {
    event.preventDefault();
    if (!actionsFor(user.role, selected.estado).includes(action)) return;
    if (needsReason(action) && !reason.trim()) { api.setError({ message: 'El motivo es obligatorio.' }); return; }
    if (!window.confirm(`¿${labels[action]} para ${selected.codigo}?`)) return;
    await api.write(`${budgetPath(selected.id)}${action}/`, 'POST', action === 'crear-revision' ? {} : { motivo: reason.trim() }, async (data) => {
      await refreshedDetail(data.id); setAction(null); setReason(''); setHistoryPage(1);
    });
  }
  return <section className="commercial-page">
    <PageHead title="Presupuestos" sub="Consulta y gestiona tus presupuestos." />
    {!line && <Errors error={api.error} />}
    <div className="budget-toolbar" role="group" aria-label="Herramientas de presupuestos">
      {user.role === AF && <button type="button" className="btn btn-fyag-primary" aria-label="Nuevo borrador" disabled={disabled} onClick={() => { setSelected(null); setHistory(null); setLine(null); setAction(null); setHeader({ cliente: '', descripcion: '' }); }}><span aria-hidden="true">+ </span>Nuevo borrador</button>}
      <div className="budget-toolbar-filters">
        <label className="form-label" htmlFor="budget-filter">Filtrar por</label>
        <select className="form-select" id="budget-filter" value={filter} onChange={(e) => setFilter(e.target.value)}><option value="">Todos</option>{Object.entries(PRE_E).map(([k, [v]]) => <option key={k} value={k}>{v}</option>)}</select>
        <button type="button" className="btn btn-outline-secondary budget-refresh" aria-label="Actualizar datos" title="Actualizar datos" aria-busy={api.loading} disabled={api.busy || api.loading} onClick={refreshFromToolbar}>
          {api.loading ? <span className="spinner-border spinner-border-sm" aria-hidden="true" /> : <svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" fill="currentColor" className="bi bi-arrow-counterclockwise" viewBox="0 0 16 16" aria-hidden="true" focusable="false">
            <path fillRule="evenodd" d="M8 3a5 5 0 1 1-4.546 2.914.5.5 0 0 0-.908-.417A6 6 0 1 0 8 2z" />
            <path d="M8 4.466V.534a.25.25 0 0 0-.41-.192L5.23 2.308a.25.25 0 0 0 0 .384l2.36 1.966A.25.25 0 0 0 8 4.466" />
          </svg>}
        </button>
      </div>
    </div>
    {api.locked && <p className="alert alert-warning" role="status">Resultado incierto o conflicto. Reconsulta los datos; no se repetirá la escritura. Conserva y revisa tu formulario antes de continuar.</p>}
    {api.loading && <p className="commercial-loading" role="status">Cargando presupuestos…</p>}
    <div className="card-fyag commercial-table-card">
      <div className="table-responsive" role="region" aria-label="Listado de presupuestos" tabIndex={0}><table className="table table-hover align-middle commercial-table"><thead><tr><th scope="col">Código</th><th scope="col">Cliente</th><th scope="col">Descripción</th><th scope="col">Estado</th><th scope="col" className="text-end">Neto</th><th scope="col">Detalle</th></tr></thead><tbody>
        {(list?.results || []).filter((b) => !filter || b.estado === filter).map((b) => <tr key={b.id}><td className="commercial-code">{b.codigo}<span className="commercial-help d-block">#{b.id}</span></td><td className="commercial-description">{clientLabel(b.cliente)}</td><td className="commercial-description">{b.descripcion}</td><td><BudgetStatus state={b.estado} /></td><td className="commercial-money">{money(b.monto_neto)}</td><td><button className="btn btn-outline-secondary btn-sm" disabled={disabled || !!header || !!line || !!action} onClick={() => void detail(b.id)}>Ver presupuesto</button></td></tr>)}
      </tbody></table></div>
      {list && !api.loading && !api.error && !list.results.filter((b) => !filter || b.estado === filter).length && <div className="commercial-empty"><h2>{list.results.length ? 'No hay coincidencias en esta página.' : 'No hay presupuestos.'}</h2><p>{list.results.length ? 'Prueba con otro estado o consulta otra página.' : 'Los presupuestos aparecerán aquí cuando se creen borradores.'}</p></div>}
      <Pager data={list} page={page} setPage={setPage} disabled={disabled || !!header || !!line || !!action} />
    </div>
    {selected && <article className="card-fyag commercial-detail">
      <div className="commercial-section-head"><div><h2>{selected.codigo} · #{selected.id}</h2><BudgetStatus state={selected.estado} /></div>
        <button className="btn btn-outline-secondary btn-sm" disabled={api.busy || api.loading} onClick={() => { setSelected(null); setHistory(null); setHeader(null); setLine(null); setAction(null); }}>Volver al listado</button>
      </div>
      <div className="commercial-summary"><div><p className="commercial-code">{clientLabel(selected.cliente)}</p><p className="commercial-long-text mb-0">{selected.descripcion}</p></div><div className="commercial-total"><span>Neto</span><strong>{money(selected.monto_neto)}</strong></div></div>
      <p className="commercial-help">Origen: {selected.presupuesto_origen ? <button className="btn btn-outline-secondary btn-sm" disabled={disabled || !!header || !!line || !!action} onClick={() => void detail(selected.presupuesto_origen)}>Ver origen #{selected.presupuesto_origen}</button> : 'Original'} · Creado por #{selected.creado_por} · {dateLabel(selected.creado_en)}</p>
      {editable && <div className="commercial-actions"><button className="btn btn-outline-secondary" disabled={disabled || !!header || !!line || !!action} onClick={() => setHeader({ cliente: String(selected.cliente), descripcion: selected.descripcion })}>Editar cabecera</button></div>}
      <div className="commercial-table-frame"><div className="table-responsive" role="region" aria-label="Ítems del presupuesto" tabIndex={0}><table className="table table-hover align-middle commercial-table commercial-items-table"><thead><tr><th scope="col">Descripción</th><th scope="col" className="text-end">Cantidad</th><th scope="col">Unidad</th><th scope="col" className="text-end">Precio unitario</th><th scope="col">Orden</th><th scope="col" className="text-end">Subtotal</th><th scope="col">Acciones</th></tr></thead><tbody>
        {selected.items.map((i) => line?.original?.id === i.id ? <ItemEditRow key={i.id} line={line} items={selected.items} onChange={(form) => setLine({ ...line, form })} onSave={saveLine} onCancel={() => setLine(null)} disabled={disabled} busy={api.busy} editable={editable} error={api.error} /> : <tr key={i.id} className="commercial-item-read"><td data-label="Descripción" className="commercial-description">{i.descripcion}</td><td data-label="Cantidad" className="text-end">{i.cantidad}</td><td data-label="Unidad">{i.unidad}</td><td data-label="Precio unitario" className="commercial-money">{money(i.precio_unitario)}</td><td data-label="Orden">{i.orden}</td><td data-label="Subtotal" className="commercial-money">{money(i.subtotal)}</td><td data-label="Acciones">{editable && <div className="commercial-row-actions"><button className="btn btn-outline-secondary btn-sm" disabled={disabled || !!line || !!header || !!action} onClick={() => { api.setError(null); setLine({ form: { ...i }, original: i }); }}>Editar ítem</button><button className="btn btn-outline-danger btn-sm" disabled={disabled || !!line || !!header || !!action} onClick={() => {
          if (window.confirm(`¿Eliminar ítem #${i.id}?`)) void api.write(itemPath(selected.id, i.id), 'DELETE', undefined, () => refreshedDetail(selected.id));
        }}>Eliminar ítem</button></div>}</td></tr>)}
        {line && (!line.original || !selected.items.some((item) => item.id === line.original.id)) && <ItemEditRow line={line} items={selected.items} onChange={(form) => setLine({ ...line, form })} onSave={saveLine} onCancel={() => setLine(null)} disabled={disabled || !!line.original} busy={api.busy} editable={editable && !line.original} error={api.error} />}
        {editable && !line && <tr className="commercial-ghost-row"><td colSpan={7}><button ref={addItemButton} type="button" className="btn btn-sm commercial-add-item" disabled={disabled || !!header || !!action} onClick={() => { api.setError(null); setLine({ form: { ...emptyItem }, original: null }); }}>+ Agregar nuevo ítem</button></td></tr>}
      </tbody></table></div>{!selected.items.length && !line && <div className="commercial-empty"><p className="mb-0">Sin ítems.</p></div>}</div>
      <div className="commercial-actions">{actionsFor(user.role, selected.estado).map((a) => <button className={actionButtonClass(a)} key={a} disabled={disabled || !!header || !!line || !!action} onClick={() => { setAction(a); setReason(''); }}>{labels[a]}</button>)}</div>
      <section className="commercial-history" aria-labelledby="budget-history-title"><h3 id="budget-history-title">Historial comercial</h3>
        {!history && <p className="commercial-loading" role="status">Cargando historial…</p>}
        {history && !history.results.length && <p className="commercial-help">No hay decisiones registradas.</p>}
        <ol className="commercial-timeline">{history?.results.map((e) => <li key={e.id}><div className="commercial-history-states">{e.estado_anterior ? <BudgetStatus state={e.estado_anterior} /> : <span className="commercial-help">Creación</span>}<span aria-label="cambia a">→</span><BudgetStatus state={e.estado_nuevo} /></div><p className="commercial-help"><time dateTime={e.creado_en}>{dateLabel(e.creado_en)}</time> · Usuario #{e.registrado_por}</p><p className="commercial-long-text mb-0">{e.motivo || 'Sin motivo'}</p></li>)}</ol>
        <Pager label="Paginación del historial" data={history} page={historyPage} setPage={setHistoryPage} disabled={disabled} />
      </section>
    </article>}
    {header && <form className="card-fyag commercial-form" onSubmit={saveHeader}><h2>{selected ? 'Editar cabecera' : 'Nuevo borrador'}</h2>
      <Fields form={header} setForm={setHeader} fields={[[ 'cliente', 'Cliente', clientOptions ], ['descripcion', 'Descripción (máximo 2000 caracteres)']]} disabled={api.busy || (selected && !editable)} />
      {selected && !editable && <p>El presupuesto ya no es BORRADOR. El formulario se conserva solo para consulta; cancélalo para continuar.</p>}
      <div className="commercial-form-actions"><button className="btn btn-fyag-primary" disabled={disabled || (selected && !editable)} type="submit">Guardar cabecera</button><button className="btn btn-outline-secondary" type="button" disabled={api.busy} onClick={() => setHeader(null)}>Cancelar</button></div>
    </form>}
    {action && <form className="card-fyag commercial-form" onSubmit={execute}><h2>{labels[action]}</h2>
      {action !== 'crear-revision' && <><label className="form-label" htmlFor="budget-reason">Motivo {needsReason(action) ? '(obligatorio)' : '(opcional)'}</label><textarea id="budget-reason" className="form-control" rows={4} maxLength={2000} required={needsReason(action)} disabled={api.busy} value={reason} onChange={(e) => setReason(e.target.value)} /></>}
      {!actionsFor(user.role, selected.estado).includes(action) && <p>El estado actual ya no permite esta acción. Cancela y toma una nueva decisión.</p>}
      <div className="commercial-form-actions"><button className={actionButtonClass(action)} disabled={disabled || !actionsFor(user.role, selected.estado).includes(action)} type="submit">Confirmar {labels[action]}</button><button className="btn btn-outline-secondary" type="button" disabled={api.busy} onClick={() => setAction(null)}>Cancelar</button></div>
    </form>}
  </section>;
}
