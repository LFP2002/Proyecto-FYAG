import React, { useEffect, useLayoutEffect, useRef, useState } from 'react';
import { useAuth } from '../auth/AuthContext';
import { PageHead } from '../components/ui';
import { PRE_E } from '../data/constants';
import { budgetPath, clientPath, eligibleClientPath, itemPath, pagePath, validatePage } from '../comercial/api.js';
import { AF, actionsFor, dateLabel, emptyItem, itemPayload, labels, money, needsReason, nextItemOrder } from '../comercial/domain.js';
import { actionButtonClass, BudgetStatus, Errors, Pager, useCommercial } from '../comercial/ui.jsx';
import ItemEditRow, { itemRowErrors } from '../comercial/ItemEditRow.jsx';
import SeguimientoComercial from '../comercial/SeguimientoComercial.jsx';
import TecIcon from '../obras/TecIcon.jsx';
import { useApp } from '../context/AppContext.jsx';

// Agrupación exclusivamente visual; los estados originales conservan sus permisos e historial.
const HISTORICAL_FILTERS = { PENDIENTE_GERENCIA:'PENDIENTE_FINANZAS', APROBADO_GERENCIA:'APROBADO_FINANZAS', RECHAZADO_GERENCIA:'RECHAZADO_FINANZAS' };
const filterState = state => HISTORICAL_FILTERS[state] ?? state;
const FILTER_OPTIONS = Object.entries(PRE_E).filter(([state])=>!Object.hasOwn(HISTORICAL_FILTERS,state));
const ACTION_LABELS = { ...labels, 'enviar-finanzas': 'Enviar a revisión de Finanzas', 'enviar-cliente': 'Registrar envío al cliente', 'registrar-aprobacion-cliente': 'Registrar aceptación del cliente', anular: 'Anular presupuesto' };
const quantityLabel = value => String(value ?? '').replace(/(\.\d*?)0+$/, '$1').replace(/\.$/, '').replace('.', ',');
const budgetListPath = (page, filter, search) => pagePath(budgetPath(), page) + (filter ? '&estado='+encodeURIComponent(filter) : '') + (search ? '&buscar='+encodeURIComponent(search) : '');
const STEPS = ['Borrador', 'Revisión interna', 'Aprobado', 'Enviado al cliente', 'Aceptado'];
const STAGE = { BORRADOR:0, PENDIENTE_FINANZAS:1, APROBADO_FINANZAS:2, ENVIADO_CLIENTE:3, APROBADO_CLIENTE:4 };
function BudgetProgress({ budget, role }) {
  const state = filterState(budget.estado), stage = STAGE[state];
  const hint = ({ BORRADOR: 'Agrega los materiales y servicios necesarios. Cuando el presupuesto esté completo, envíalo a revisión.', PENDIENTE_FINANZAS: role === AF ? 'Revisa los ítems y el importe antes de aprobar o rechazar el presupuesto.' : 'Finanzas revisará el presupuesto. Consulta aquí el resultado.', APROBADO_FINANZAS: role === AF ? 'Registra el envío cuando hayas enviado el presupuesto al cliente por el canal correspondiente.' : 'Finanzas registrará el envío al cliente.', ENVIADO_CLIENTE: role === AF ? 'Registra la respuesta del cliente cuando esté disponible.' : 'Se espera la respuesta del cliente.', APROBADO_CLIENTE: 'El cliente aceptó el presupuesto.', RECHAZADO_FINANZAS: 'La revisión interna fue rechazada. Consulta el motivo en el historial.', RECHAZADO_CLIENTE: 'El cliente rechazó el presupuesto. Consulta el historial.', ANULADO: 'El presupuesto fue anulado. Consulta el historial.' })[state];
  return <><div className="budget-progress" aria-label="Etapas del presupuesto">{stage !== undefined && STEPS.map((step,i)=><div key={step} className={'budget-step '+(i===stage?'current':i<stage?'done':'')} aria-current={i===stage?'step':undefined}><span className="budget-step-dot">{i<stage?<TecIcon name="check"/>:i+1}</span><span>{step}</span></div>)}</div><div className="budget-next"><strong>{stage!==undefined&&stage<4?'Próximo paso':'Situación actual'}</strong><p>{hint}</p></div></>;
}

export default function Presupuestos() {
  const {user}=useAuth();
  return user.role==='GERENCIA'?<SeguimientoComercial key={user.id}/>:<PresupuestosOperativos key={user.id+':'+user.role}/>;
}
function PresupuestosOperativos() {
  const { user } = useAuth();
  const api = useCommercial();
  const target = useApp()?.navigationTarget;
  const initialBudget = useRef(target?.module==='presupuestos' && Number.isSafeInteger(target.presupuesto) && target.presupuesto>0 ? target.presupuesto : null);
  const [clients, setClients] = useState([]);
  const [clientPage, setClientPage] = useState(1);
  const [clientPageInfo, setClientPageInfo] = useState(null);
  const [clientQuery,setClientQuery] = useState('');
  const [clientSearch,setClientSearch] = useState('');
  const [chosenClient,setChosenClient] = useState(null);
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
  const [query,setQuery] = useState('');
  const [search,setSearch] = useState('');
  const [opening,setOpening]=useState(false);
  const [tab,setTab]=useState('items');
  const listPosition=useRef(null), listTrigger=useRef(null), viewHeading=useRef(null);
  const inDetail=opening||!!selected||!!header;
  function rememberList(event){
    listPosition.current=globalThis.window?.scrollY??0;
    listTrigger.current=event?.currentTarget?.dataset?.budgetId??null;
  }
  useLayoutEffect(()=>{
    const win=globalThis.window;
    if(inDetail){
      viewHeading.current?.focus({preventScroll:true});
      win?.scrollTo?.({top:0,behavior:'instant'});
    }else if(listPosition.current!==null){
      const trigger=listTrigger.current;
      if(trigger)globalThis.document?.querySelector?.(`[data-budget-id="${trigger}"]`)?.focus({preventScroll:true});
      win?.scrollTo?.({top:listPosition.current,behavior:'instant'});
      listPosition.current=null;listTrigger.current=null;
    }
  },[inDetail]);
  const refreshFlight = useRef(false);
  const reload = () => api.load('list', budgetListPath(page, filter, search), (data) => setList(validatePage(data, budgetPath())));
  const loadClients = () => user.role === 'SUPERVISOR_OBRAS'
    ? api.load('clients', eligibleClientPath(clientPage, clientSearch), (data) => {
      const valid = validatePage(data, '/api/presupuestos/clientes-elegibles/');
      setClients(valid.results);
      setClientPageInfo(valid);
    })
    : api.load('clients', clientPath(), (data) => { setClients(data); setClientPageInfo(null); });
  const loadHistory = (pk, p = 1) => api.load('history', pagePath(`${budgetPath(pk)}historial/`, p), (data) => setHistory(validatePage(data, `${budgetPath(pk)}historial/`)));
  useEffect(() => { setList(null); void reload(); }, [page, filter, search]);
  useEffect(()=>{const id=initialBudget.current;if(!id)return;initialBudget.current=null;setOpening(true);void api.load('detail',budgetPath(id),setSelected).finally(()=>setOpening(false));},[]);
  useEffect(() => { void loadClients(); }, [user.id, user.role, clientPage, clientSearch]);
  useEffect(() => { if (selected) { setHistory(null); void loadHistory(selected.id, historyPage); } }, [selected?.id, historyPage]);
  async function detail(pk,event) {
    if(disabled)return;
    rememberList(event);setOpening(true);setTab('items');api.setError(null);
    setSelected(null); setHistory(null); setHeader(null); setLine(null); setAction(null); setHistoryPage(1);
    try{await api.load('detail', budgetPath(pk), setSelected);}
    finally{setOpening(false);}
  }
  function backToList(){
    if(api.busy||api.loading||api.locked||line||header||action)return;
    setSelected(null);setHistory(null);setTab('items');api.setError(null);
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
    await api.requiredLoad('list', budgetListPath(1, filter, search), (data) => setList(validatePage(data, budgetPath())));
    setPage(1);
    await api.requiredLoad('history', pagePath(`${budgetPath(pk)}historial/`, historyPage), (data) => setHistory(validatePage(data, `${budgetPath(pk)}historial/`)));
  }
  const disabled = api.busy || api.locked || api.loading;
  const compactMoney=value=>money(value).replace(/,00 CLP$/, '').replace(/ CLP$/, '');
  const canCreate=[AF,'SUPERVISOR_OBRAS'].includes(user.role);
  const editable = [AF, 'SUPERVISOR_OBRAS'].includes(user.role) && selected?.estado === 'BORRADOR';
  const historical = selected ? {id:selected.cliente,nombre_legal:selected.cliente_nombre || clients.find(c=>c.id===selected.cliente)?.nombre_legal || 'Cliente #'+selected.cliente, historical:true} : null;
  const currentChoices = clients.filter(c=>user.role==='SUPERVISOR_OBRAS'||c.activo||c.id===selected?.cliente).filter(c=>user.role==='SUPERVISOR_OBRAS'||!clientSearch||c.nombre_legal.toLocaleLowerCase('es-CL').includes(clientSearch.toLocaleLowerCase('es-CL')));
  const retained = [chosenClient,historical].filter(c=>c&&String(c.id)===header?.cliente&&!currentChoices.some(x=>x.id===c.id));
  const clientOptions = [...currentChoices,...retained.filter((c,i,a)=>a.findIndex(x=>x.id===c.id)===i)];
  const clientLabel = b => b.cliente_nombre || clients.find(c=>c.id===b.cliente)?.nombre_legal || 'Cliente #'+b.cliente;
  function openHeader(value) {
    setClientQuery('');setClientSearch('');setClientPage(1);setChosenClient(null);setHeader(value);api.setError(null);
  }
  function pickClient(value) {
    setChosenClient(clientOptions.find(c=>String(c.id)===value)||null);
    setHeader(previous=>({...previous,cliente:value}));
  }
  function applyFilters(nextFilter, nextSearch) {
    api.setError(null);setPage(1);setFilter(nextFilter);setSearch(nextSearch);
  }
  function startLine(mode) {
    api.setError(null);setLine({ form:{...emptyItem,orden:nextItemOrder(selected.items)},original:null,mode });
  }
  async function saveHeader(event) {
    event.preventDefault();
    if (disabled || !header || (selected && !editable)) return;
    const cliente = Number(header.cliente);
    if (!Number.isSafeInteger(cliente) || cliente <= 0 || !header.descripcion.trim() || header.descripcion.trim().length > 2000) { api.setError({ message: 'Selecciona un cliente e ingresa descripción.' }); return; }
    const data = { ...(selected && cliente === selected.cliente ? {} : { cliente }), ...(selected && header.descripcion === selected.descripcion ? {} : { descripcion: header.descripcion.trim() }) };
    if (data.cliente && !(user.role === 'SUPERVISOR_OBRAS' ? [...clients,chosenClient].some(c=>c?.id===cliente&&!c.historical) : clients.some(c=>c.id===cliente&&c.activo))) { api.setError({ message: 'El cliente debe estar activo y disponible.' }); return; }
    await api.write(budgetPath(selected?.id), selected ? 'PATCH' : 'POST', data, async (result) => {
      await refreshedDetail(result.id); setHeader(null); setHistoryPage(1);
    });
  }
  async function saveLine(event) {
    event.preventDefault();
    if (!editable || disabled || !line) return;
    const form = { ...line.form, orden: line.original ? line.original.orden : nextItemOrder(selected.items) };
    const errors = itemRowErrors(form, selected.items, line.original);
    if (Object.keys(errors).length) return;
    await api.write(itemPath(selected.id, line.original?.id), line.original ? 'PATCH' : 'POST', itemPayload(form, line.original), async () => { await refreshedDetail(selected.id); setLine(null); });
  }
  async function execute(event) {
    event.preventDefault();
    if (disabled || !actionsFor(user.role, selected.estado).includes(action)) return;
    if (needsReason(action) && !reason.trim()) { api.setError({ message: 'El motivo es obligatorio.' }); return; }
    if (!window.confirm(`¿${ACTION_LABELS[action]} para ${selected.codigo}?`)) return;
    await api.write(`${budgetPath(selected.id)}${action}/`, 'POST', action === 'crear-revision' ? {} : { motivo: reason.trim() }, async (data) => {
      await refreshedDetail(data.id); setAction(null); setReason(''); setHistoryPage(1);
    });
  }
  const headerForm = header && <div className="budget-header-view">
    <button type="button" className="btn btn-outline-secondary btn-sm budget-back" disabled={api.busy||api.locked||api.loading} onClick={()=>{setHeader(null);api.setError(null);}}><TecIcon name="back"/>{selected?'Volver al detalle':'Volver a presupuestos'}</button>
    <h2>{selected ? 'Editar datos generales' : 'Nuevo presupuesto'}</h2><p className="commercial-help">{selected?'Actualiza el cliente o la descripción.':'Primero registra los datos generales. Luego podrás agregar materiales y servicios.'}</p>
    <form className="card-fyag commercial-form budget-header-form" onSubmit={saveHeader}>
      <h3>Datos generales</h3>
      <label className="form-label" htmlFor="budget-client-search">Buscar cliente por nombre</label>
      <div className="budget-search-row"><input id="budget-client-search" className="form-control" value={clientQuery} maxLength={200} disabled={disabled} onChange={e=>setClientQuery(e.target.value)} onKeyDown={e=>{if(e.key==='Enter'){e.preventDefault();setClientPage(1);setClientSearch(clientQuery.trim());}}} placeholder="Nombre o razón social"/><button type="button" className="btn btn-outline-secondary" disabled={disabled} onClick={()=>{setClientPage(1);setClientSearch(clientQuery.trim());}}><TecIcon name="search"/> Buscar</button></div>
      <label className="form-label" htmlFor="com-cliente">Cliente *</label>
      <select id="com-cliente" className="form-select" value={header.cliente} disabled={disabled||(selected&&!editable)} onChange={e=>pickClient(e.target.value)}><option value="">Selecciona cliente activo</option>{clientOptions.map(c=><option key={c.id} value={String(c.id)}>{c.nombre_legal}{c.activo===false?' (inactivo, solo conservar)':''}</option>)}</select>
      {!clientOptions.length&&!api.loading&&<p className="commercial-help">No hay clientes disponibles para esta búsqueda.</p>}
      {user.role==='SUPERVISOR_OBRAS'&&clientPageInfo&&(clientPageInfo.previous||clientPageInfo.next)&&<nav className="commercial-pager" aria-label="Clientes elegibles"><button type="button" className="btn btn-outline-secondary btn-sm" disabled={!clientPageInfo.previous||disabled} onClick={()=>setClientPage(p=>p-1)}>Clientes anteriores</button><span>Página {clientPage} · {clientPageInfo.count} clientes elegibles</span><button type="button" className="btn btn-outline-secondary btn-sm" disabled={!clientPageInfo.next||disabled} onClick={()=>setClientPage(p=>p+1)}>Clientes siguientes</button></nav>}
      <label className="form-label mt-3" htmlFor="com-descripcion">Descripción del trabajo *</label><textarea className="form-control" id="com-descripcion" rows={4} maxLength={2000} placeholder="Describe el trabajo, instalación o servicio solicitado" value={header.descripcion} disabled={disabled||(selected&&!editable)} onChange={e=>setHeader(previous=>({...previous,descripcion:e.target.value}))}/>
      <p className="commercial-help mt-2">{header.descripcion.length}/2000 caracteres</p>
      {selected&&!editable&&<p>El presupuesto ya no está en borrador. Cancela para continuar.</p>}
      <div className="commercial-form-actions"><button className="btn btn-outline-secondary" type="button" disabled={api.busy||api.locked} onClick={()=>{setHeader(null);api.setError(null);}}>Cancelar</button><button className="btn btn-fyag-primary" disabled={disabled||(selected&&!editable)} type="submit">{selected?'Guardar cambios':'Crear presupuesto'}</button></div>
    </form></div>;
  return <section className="commercial-page budgets-page budgets-operational">
    <PageHead title="Presupuestos" sub="Consulta y gestiona tus presupuestos."><button type="button" className="btn btn-outline-secondary budget-refresh" aria-label="Actualizar datos" title="Actualizar datos" aria-busy={api.loading} disabled={api.busy || api.loading} onClick={refreshFromToolbar}>
          {api.loading ? <span className="spinner-border spinner-border-sm" aria-hidden="true" /> : <svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" fill="currentColor" className="bi bi-arrow-counterclockwise" viewBox="0 0 16 16" aria-hidden="true" focusable="false">
            <path fillRule="evenodd" d="M8 3a5 5 0 1 1-4.546 2.914.5.5 0 0 0-.908-.417A6 6 0 1 0 8 2z" />
            <path d="M8 4.466V.534a.25.25 0 0 0-.41-.192L5.23 2.308a.25.25 0 0 0 0 .384l2.36 1.966A.25.25 0 0 0 8 4.466" />
          </svg>}
        <span>Actualizar</span></button></PageHead>
    {!line && <Errors error={api.error} />}
    {api.locked && <p className="alert alert-warning" role="status">Resultado incierto o conflicto. Reconsulta los datos; no se repetirá la escritura. Conserva y revisa tu formulario antes de continuar.</p>}
    {api.loading && <p className="commercial-loading" role="status">Cargando presupuestos…</p>}
    {!inDetail&&<>
    <div className="budget-toolbar" role="group" aria-label="Herramientas de presupuestos">
      {canCreate && <button type="button" className="btn btn-fyag-primary" aria-label="Nuevo presupuesto" disabled={disabled} onClick={event=>{rememberList(event);setTab('items');api.setError(null);setSelected(null);setHistory(null);setLine(null);setAction(null);openHeader({cliente:'',descripcion:''});}}><span aria-hidden="true">+ </span>Nuevo presupuesto</button>}
      <div className="budget-toolbar-filters">
        <div className="budget-search-row"><input id="budget-search" aria-label="Buscar presupuesto" className="form-control" maxLength={200} placeholder="Código completo, cliente o descripción" value={query} disabled={disabled} onChange={e=>setQuery(e.target.value)} onKeyDown={e=>{if(e.key==='Enter')applyFilters(filter,query.trim());}}/><button type="button" className="btn btn-outline-secondary" disabled={disabled} onClick={()=>applyFilters(filter,query.trim())}><TecIcon name="search"/> Buscar</button></div><label className="form-label" htmlFor="budget-filter">Estado</label>
        <select className="form-select" id="budget-filter" value={filter} disabled={disabled} onChange={e=>applyFilters(e.target.value,search)}><option value="">Todos</option>{FILTER_OPTIONS.map(([k,[v]])=><option key={k} value={k}>{v}</option>)}</select>{(filter||search)&&<button type="button" className="btn btn-outline-secondary" disabled={disabled} onClick={()=>{setQuery('');applyFilters('','');}}>Limpiar filtros</button>}
      </div>
    </div>
    <div className="card-fyag commercial-table-card budget-list-card">
      <div className="table-responsive" role="region" aria-label="Listado de presupuestos" tabIndex={0}><table className="table table-hover align-middle commercial-table"><thead><tr><th scope="col">Código</th><th scope="col">Cliente</th><th scope="col">Descripción</th><th scope="col">Estado</th><th scope="col" className="text-end">Neto CLP</th><th scope="col">Detalle</th></tr></thead><tbody>
        {(list?.results || []).map((b) => <tr key={b.id}><td className="commercial-code">{b.codigo}</td><td className="commercial-description">{clientLabel(b)}</td><td className="commercial-description">{b.descripcion}</td><td><BudgetStatus state={b.estado} /></td><td className="commercial-money">{compactMoney(b.monto_neto)}</td><td><button className="btn btn-outline-secondary btn-sm" disabled={disabled || !!header || !!line || !!action} data-budget-id={b.id} onClick={event => void detail(b.id,event)}>Ver presupuesto</button></td></tr>)}
      </tbody></table></div>
      {list && !api.loading && !api.error && !list.results.length && <div className="commercial-empty"><h2>{filter||search ? 'No se encontraron presupuestos.' : 'No hay presupuestos.'}</h2><p>{filter||search ? 'Prueba otra búsqueda o limpia los filtros.' : 'Los presupuestos aparecerán aquí cuando se creen.'}</p></div>}
      {list&&<p className="budget-count" role="status">{list.count} presupuestos encontrados</p>}
      {list&&(list.previous||list.next)&&<Pager data={list} page={page} setPage={setPage} disabled={disabled} />}
    </div>
    </>}
    {inDetail&&<div className="budget-detail-view" ref={viewHeading} tabIndex={-1}>
      {selected&&!header&&<button className="btn btn-outline-secondary btn-sm budget-back" type="button" disabled={disabled||!!header||!!line||!!action} onClick={backToList}><svg width="16" height="16" viewBox="0 0 16 16" fill="currentColor" className="bi bi-arrow-left" aria-hidden="true"><path fillRule="evenodd" d="M15 8a.5.5 0 0 0-.5-.5H2.707l3.647-3.646a.5.5 0 1 0-.708-.708l-4.5 4.5a.5.5 0 0 0 0 .708l4.5 4.5a.5.5 0 0 0 .708-.708L2.707 8.5H14.5A.5.5 0 0 0 15 8"/></svg>Volver al listado</button>}
      {opening&&!selected&&<p className="commercial-loading" role="status">Cargando presupuesto…</p>}
    {selected && !header && <article className="card-fyag commercial-detail">
      <div className="budget-detail-heading"><h2>{selected.codigo}</h2><BudgetStatus state={selected.estado} /></div>
      <div className="commercial-summary"><div><span className="commercial-help">Cliente</span><p className="commercial-code">{clientLabel(selected)}</p><p className="commercial-long-text mb-0">{selected.descripcion}</p></div><div className="commercial-total"><span>Total neto · CLP</span><strong>{compactMoney(selected.monto_neto)}</strong></div></div>
      <p className="commercial-help">Creado por {selected.creador_nombre || `Usuario #${selected.creado_por}`} · {new Date(selected.creado_en).toLocaleString('es-CL', { day: '2-digit', month: '2-digit', year: 'numeric', hour: '2-digit', minute: '2-digit' })}</p>
      {editable && <div className="commercial-actions"><button className="btn btn-outline-secondary" disabled={disabled || !!header || !!line || !!action} onClick={() => {setTab('items');openHeader({ cliente: String(selected.cliente), descripcion: selected.descripcion });}}>Editar datos generales</button></div>}
      <BudgetProgress budget={selected} role={user.role}/>
      <div className="budget-tabs" role="group" aria-label="Secciones del presupuesto">
        <button type="button" aria-pressed={tab==='items'} aria-controls="budget-items" onClick={()=>setTab('items')}>Materiales y servicios</button>
        <button type="button" aria-pressed={tab==='history'} aria-controls="budget-history" disabled={!!line||!!header||!!action||api.busy||api.locked} onClick={()=>setTab('history')}>Historial comercial</button>
      </div>
      <div id="budget-items" hidden={tab!=='items'}>
      <div className="commercial-table-frame"><div className="table-responsive" role="region" aria-label="Ítems del presupuesto" tabIndex={0}><table className="table table-hover align-middle commercial-table commercial-items-table"><thead><tr><th scope="col">Descripción</th><th scope="col" className="text-end">Cantidad</th><th scope="col">Unidad</th><th scope="col" className="text-end">Precio de venta CLP</th><th scope="col" className="text-end">Subtotal CLP</th>{editable&&<th scope="col">Acciones</th>}</tr></thead><tbody>
        {selected.items.map((i) => line?.original?.id === i.id ? <ItemEditRow key={i.id} line={line} items={selected.items} onChange={(form) => setLine(previous => previous ? { ...previous, form } : previous)} onSave={saveLine} onCancel={() => setLine(null)} disabled={disabled} busy={api.busy} editable={editable} error={api.error} /> : <tr key={i.id} className="commercial-item-read"><td data-label="Descripción" className="commercial-description">{i.descripcion}{i.articulo!=null&&<span className="commercial-help d-block">Material de catálogo · {i.codigo_articulo}</span>}</td><td data-label="Cantidad" className="text-end">{quantityLabel(i.cantidad)}</td><td data-label="Unidad">{i.unidad}</td><td data-label="Precio unitario" className="commercial-money">{compactMoney(i.precio_unitario)}</td><td data-label="Subtotal" className="commercial-money">{compactMoney(i.subtotal)}</td>{editable && <td data-label="Acciones"><div className="commercial-row-actions"><button className="btn btn-outline-secondary btn-sm" disabled={disabled || !!line || !!header || !!action} onClick={() => { api.setError(null); setLine({ form: { ...i }, original: i }); }}>Editar ítem</button><button className="btn btn-outline-danger btn-sm" disabled={disabled || !!line || !!header || !!action} onClick={() => {
          if (window.confirm(`¿Eliminar ítem #${i.id}?`)) void api.write(itemPath(selected.id, i.id), 'DELETE', undefined, () => refreshedDetail(selected.id));
        }}>Eliminar ítem</button></div></td>}</tr>)}
        {line && (!line.original || !selected.items.some((item) => item.id === line.original.id)) && <ItemEditRow line={line} items={selected.items} onChange={(form) => setLine(previous => previous ? { ...previous, form } : previous)} onSave={saveLine} onCancel={() => setLine(null)} disabled={disabled || !!line.original} busy={api.busy} editable={editable && !line.original} error={api.error} />}
        {editable && !line && <tr className="commercial-ghost-row"><td colSpan={6}><div className="budget-add-options"><button type="button" className="btn btn-outline-secondary" disabled={disabled||!!header||!!action} onClick={()=>startLine('material')}><TecIcon name="plus"/> Agregar material de bodega</button><button ref={addItemButton} type="button" className="btn btn-outline-secondary" disabled={disabled||!!header||!!action} onClick={()=>startLine('manual')}><TecIcon name="plus"/> Agregar ítem manual</button></div></td></tr>}
      </tbody></table></div>{!selected.items.length && !line && <div className="commercial-empty"><p className="mb-0">{editable?'Agrega materiales de Bodega o servicios personalizados.':'Este presupuesto no tiene ítems.'}</p></div>}</div>
      </div>
      <section id="budget-history" hidden={tab!=='history'} className="commercial-history" aria-labelledby="budget-history-title"><h3 id="budget-history-title">Historial comercial</h3>
        {!history && <p className="commercial-loading" role="status">Cargando historial…</p>}
        {history && !history.results.length && <p className="commercial-help">No hay decisiones registradas.</p>}
        <ol className="commercial-timeline">{history?.results.map(e=><li key={e.id}><div className="commercial-history-states">{e.estado_anterior?<BudgetStatus state={e.estado_anterior}/>:<span className="commercial-help">Creación</span>}<span aria-label="cambia a">→</span><BudgetStatus state={e.estado_nuevo}/></div><p className="commercial-help"><time dateTime={e.creado_en}>{dateLabel(e.creado_en)}</time> · Usuario #{e.registrado_por}</p>{e.motivo&&<p className="commercial-long-text mb-0">{e.motivo}</p>}</li>)}</ol>
        {history&&(history.next||history.previous)&&<Pager label="Paginación del historial" data={history} page={historyPage} setPage={setHistoryPage} disabled={disabled}/>}
      </section>
      {actionsFor(user.role,selected.estado).length>0&&<section className="budget-commercial-actions"><h3>Acciones comerciales</h3><div className="commercial-actions">{actionsFor(user.role, selected.estado).map((a) => <button className={actionButtonClass(a)} key={a} disabled={disabled || !!header || !!line || !!action} onClick={() => { setAction(a); setReason(''); }}>{ACTION_LABELS[a]}</button>)}</div></section>}
    {action && <form className="card-fyag commercial-form" onSubmit={execute}><h2>{ACTION_LABELS[action]}</h2>
      {action !== 'crear-revision' && <><label className="form-label" htmlFor="budget-reason">Motivo {needsReason(action) ? '(obligatorio)' : '(opcional)'}</label><textarea id="budget-reason" className="form-control" rows={4} maxLength={2000} required={needsReason(action)} disabled={api.busy} value={reason} onChange={(e) => setReason(e.target.value)} /></>}
      {!actionsFor(user.role, selected.estado).includes(action) && <p>El estado actual ya no permite esta acción. Cancela y toma una nueva decisión.</p>}
      <div className="commercial-form-actions"><button className={actionButtonClass(action)} disabled={disabled || !actionsFor(user.role, selected.estado).includes(action)} type="submit">Confirmar {ACTION_LABELS[action]}</button><button className="btn btn-outline-secondary" type="button" disabled={api.busy} onClick={() => setAction(null)}>Cancelar</button></div>
    </form>}
    </article>}

      {headerForm}
    </div>}
  </section>;
}
