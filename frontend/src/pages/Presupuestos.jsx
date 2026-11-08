import React, { useEffect, useState } from 'react';
import { useAuth } from '../auth/AuthContext';
import { PageHead } from '../components/ui';
import { PRE_E } from '../data/constants';
import { budgetPath, clientPath, itemPath, pagePath, validatePage } from '../comercial/api.js';
import { AF, actionsFor, dateLabel, emptyItem, itemPayload, labels, money, needsReason, validateItem } from '../comercial/domain.js';
import { Errors, Fields, Pager, useCommercial } from '../comercial/ui.jsx';

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
  const [action, setAction] = useState(null);
  const [reason, setReason] = useState('');
  const [filter, setFilter] = useState('');
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
    if (!editable) return;
    const errors = validateItem(line.form);
    if (Object.keys(errors).length) { api.setError({ message: 'Revisa el ítem.', fieldErrors: errors }); return; }
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
  return <section>
    <PageHead title="Presupuestos" sub="Todo presupuesto requiere aprobación de Gerencia; neto calculado en Django.">
      {user.role === AF && <button className="btn btn-fyag-primary" disabled={disabled} onClick={() => { setSelected(null); setHistory(null); setLine(null); setAction(null); setHeader({ cliente: '', descripcion: '' }); }}>Nuevo borrador</button>}
    </PageHead>
    <Errors error={api.error} />
    <button disabled={api.busy || api.loading} onClick={() => void api.reconcile(refresh)}>Reconsultar datos</button>
    {api.locked && <p role="status">Resultado incierto o conflicto. Reconsulta los datos; no se repetirá la escritura. Conserva y revisa tu formulario antes de continuar.</p>}
    {api.loading && <p role="status">Cargando presupuestos…</p>}
    <label htmlFor="budget-filter">Estado (solo esta página)</label><select id="budget-filter" value={filter} onChange={(e) => setFilter(e.target.value)}><option value="">Todos</option>{Object.entries(PRE_E).map(([k, [v]]) => <option key={k} value={k}>{v}</option>)}</select>
    <div className="table-responsive"><table className="table"><thead><tr><th>Código</th><th>Cliente</th><th>Descripción</th><th>Estado</th><th>Neto</th><th>Detalle</th></tr></thead><tbody>
      {(list?.results || []).filter((b) => !filter || b.estado === filter).map((b) => <tr key={b.id}><td>{b.codigo} · #{b.id}</td><td>{clientLabel(b.cliente)}</td><td>{b.descripcion}</td><td>{PRE_E[b.estado]?.[0] || b.estado}</td><td>{money(b.monto_neto)}</td><td><button disabled={disabled || !!header || !!line || !!action} onClick={() => void detail(b.id)}>Ver presupuesto</button></td></tr>)}
    </tbody></table></div>
    {list && !list.results.length && <p>No hay presupuestos.</p>}
    <Pager data={list} page={page} setPage={setPage} disabled={disabled || !!header || !!line || !!action} />
    {selected && <article className="card-fyag"><h2>{selected.codigo} · #{selected.id}</h2>
      <button disabled={api.busy || api.loading} onClick={() => { setSelected(null); setHistory(null); setHeader(null); setLine(null); setAction(null); }}>Volver al listado</button>
      <p>{clientLabel(selected.cliente)} · {PRE_E[selected.estado]?.[0]}</p><p>{selected.descripcion}</p>
      <p>Neto: <strong>{money(selected.monto_neto)}</strong></p><p>Origen: {selected.presupuesto_origen ? <button disabled={disabled || !!header || !!line || !!action} onClick={() => void detail(selected.presupuesto_origen)}>Ver origen #{selected.presupuesto_origen}</button> : 'Original'} · Creado por #{selected.creado_por} · {dateLabel(selected.creado_en)}</p>
      {editable && <><button disabled={disabled || !!header || !!line || !!action} onClick={() => setHeader({ cliente: String(selected.cliente), descripcion: selected.descripcion })}>Editar cabecera</button>{' '}
        <button disabled={disabled || !!header || !!line || !!action} onClick={() => setLine({ form: { ...emptyItem }, original: null })}>Agregar ítem</button></>}
      <div className="table-responsive"><table className="table"><thead><tr><th>Orden</th><th>Descripción</th><th>Cantidad</th><th>Unidad</th><th>Precio unitario</th><th>Subtotal</th><th>Acciones</th></tr></thead><tbody>
        {selected.items.map((i) => <tr key={i.id}><td>{i.orden}</td><td>{i.descripcion}</td><td>{i.cantidad}</td><td>{i.unidad}</td><td>{money(i.precio_unitario)}</td><td>{money(i.subtotal)}</td><td>{editable && <><button disabled={disabled || !!line || !!header || !!action} onClick={() => setLine({ form: { ...i }, original: i })}>Editar ítem</button>{' '}<button disabled={disabled || !!line || !!header || !!action} onClick={() => {
          if (window.confirm(`¿Eliminar ítem #${i.id}?`)) void api.write(itemPath(selected.id, i.id), 'DELETE', undefined, () => refreshedDetail(selected.id));
        }}>Eliminar ítem</button></>}</td></tr>)}
      </tbody></table></div>{!selected.items.length && <p>Sin ítems.</p>}
      <div className="d-flex flex-wrap gap-2">{actionsFor(user.role, selected.estado).map((a) => <button key={a} disabled={disabled || !!header || !!line || !!action} onClick={() => { setAction(a); setReason(''); }}>{labels[a]}</button>)}</div>
      <p>La anulación puede ser rechazada por Django si el presupuesto está utilizado por una Obra.</p>
      <h3>Historial comercial</h3>
      {!history && <p>Cargando historial…</p>}
      {history?.results.map((e) => <div key={e.id}><strong>{e.estado_anterior || 'Creación'} → {e.estado_nuevo}</strong><p>{dateLabel(e.creado_en)} · Usuario #{e.registrado_por} · {e.motivo || 'Sin motivo'}</p></div>)}
      <Pager data={history} page={historyPage} setPage={setHistoryPage} disabled={disabled} />
    </article>}
    {header && <form className="card-fyag" onSubmit={saveHeader}><h2>{selected ? 'Editar cabecera' : 'Nuevo borrador'}</h2>
      <Fields form={header} setForm={setHeader} fields={[[ 'cliente', 'Cliente', clientOptions ], ['descripcion', 'Descripción (máximo 2000 caracteres)']]} disabled={api.busy || (selected && !editable)} />
      {selected && !editable && <p>El presupuesto ya no es BORRADOR. El formulario se conserva solo para consulta; cancélalo para continuar.</p>}
      <button disabled={disabled || (selected && !editable)} type="submit">Guardar cabecera</button>{' '}<button type="button" disabled={api.busy} onClick={() => setHeader(null)}>Cancelar</button>
    </form>}
    {line && <form className="card-fyag" onSubmit={saveLine}><h2>{line.original ? 'Editar ítem' : 'Nuevo ítem'}</h2>
      <Fields form={line.form} setForm={(form) => setLine({ ...line, form })} fields={[[ 'descripcion', 'Descripción' ], ['cantidad', 'Cantidad (decimal)'], ['unidad', 'Unidad'], ['precio_unitario', 'Precio unitario (decimal CLP)'], ['orden', 'Orden']]} disabled={api.busy || !editable} />
      <p>Subtotal y neto se consultarán al servidor después de guardar.</p>{!editable && <p>El presupuesto ya no es BORRADOR. Cancela este formulario para continuar.</p>}<button disabled={disabled || !editable} type="submit">Guardar ítem</button>{' '}<button type="button" disabled={api.busy} onClick={() => setLine(null)}>Cancelar</button>
    </form>}
    {action && <form className="card-fyag" onSubmit={execute}><h2>{labels[action]}</h2>
      {action !== 'crear-revision' && <><label htmlFor="budget-reason">Motivo {needsReason(action) ? '(obligatorio)' : '(opcional)'}</label><textarea id="budget-reason" className="form-control" maxLength={2000} required={needsReason(action)} disabled={api.busy} value={reason} onChange={(e) => setReason(e.target.value)} /></>}
      {!actionsFor(user.role, selected.estado).includes(action) && <p>El estado actual ya no permite esta acción. Cancela y toma una nueva decisión.</p>}
      <button disabled={disabled || !actionsFor(user.role, selected.estado).includes(action)} type="submit">Confirmar {labels[action]}</button>{' '}<button type="button" disabled={api.busy} onClick={() => setAction(null)}>Cancelar</button>
    </form>}
  </section>;
}
