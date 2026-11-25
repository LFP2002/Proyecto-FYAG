import React,{useEffect,useLayoutEffect,useRef,useState} from 'react';
import {ApiError} from '../auth/client.js';
import {PageHead} from '../components/ui';
import {PRE_E} from '../data/constants';
import {formatCompactCLP} from '../utils/format.js';
import {budgetPath,pagePath,validatePage} from './api.js';
import {BudgetStatus,Errors,Pager,useCommercial} from './ui.jsx';

const PATH='/api/presupuestos/seguimiento-comercial/';
const HISTORICAL={PENDIENTE_GERENCIA:'PENDIENTE_FINANZAS',APROBADO_GERENCIA:'APROBADO_FINANZAS',RECHAZADO_GERENCIA:'RECHAZADO_FINANZAS'};
const OPTIONS=Object.keys(PRE_E).filter(k=>!Object.hasOwn(HISTORICAL,k));
const METRICS=[['PENDIENTE_FINANZAS','Pendientes de revisión','amber'],['ENVIADO_CLIENTE','Enviados al cliente','blue'],['APROBADO_CLIENTE','Aceptados por el cliente','green'],['RECHAZADO_CLIENTE','Rechazados por el cliente','red']];
const INITIAL={page:1,estado:'',desde:'',hasta:'',buscar:'',sin_actualizar:''};
const count=n=>Number.isSafeInteger(n)&&n>=0;
const money=v=>typeof v==='string'&&/^\d+\.\d{2}$/.test(v);
const percent=v=>v===null||typeof v==='string'&&/^\d+\.\d$/.test(v)&&Number(v)<=100;
const when=v=>v?new Date(v).toLocaleDateString('es-CL'):'—';
function validate(data){
  const result=validatePage(data,PATH),s=data.resumen;
  if(!s||!['total','sin_actualizar','respuestas_cliente','dias_sin_actualizar'].every(k=>count(s[k]))||!percent(s.tasa_aceptacion)||!OPTIONS.every(k=>count(s.estados?.[k]?.cantidad)&&money(s.estados[k].monto_neto))||result.results.length>25)throw new ApiError(502,'No se pudieron confirmar los indicadores comerciales.');
  if(result.results.some(r=>!Number.isSafeInteger(r.id)||r.id<1||!OPTIONS.includes(r.estado)||!Object.hasOwn(PRE_E,r.estado_original)||!money(r.monto_neto)||typeof r.sin_actualizar!=='boolean'||typeof r.cliente_nombre!=='string'||typeof r.codigo!=='string'))throw new ApiError(502,'No se pudieron confirmar los presupuestos.');
  return result;
}
function label(state){return ({PENDIENTE_FINANZAS:'Pendiente de revisión',APROBADO_FINANZAS:'Aprobado internamente',RECHAZADO_FINANZAS:'Rechazado internamente'})[state]||PRE_E[state]?.[0]||'Estado no disponible';}
export default function SeguimientoComercial(){
  const api=useCommercial(),[query,setQuery]=useState(INITIAL),[draft,setDraft]=useState({desde:'',hasta:'',buscar:''}),[data,setData]=useState(null),[selected,setSelected]=useState(null),[invalid,setInvalid]=useState('');
  const scroll=useRef(null),trigger=useRef(null),flight=useRef(false);
  const path=PATH+'?'+new URLSearchParams(Object.entries(query).filter(([,v])=>v!=='')).toString();
  const read=()=>{setData(null);return api.load('panel',path,v=>setData(validate(v)));};
  useEffect(()=>{api.setError(null);void read();},[path]);
  useLayoutEffect(()=>{
    if(scroll.current===null)return;
    if(selected)globalThis.window?.scrollTo?.({top:0,behavior:'instant'});
    else{globalThis.document?.querySelector?.('[data-manager-budget="'+trigger.current+'"]')?.focus({preventScroll:true});globalThis.window?.scrollTo?.({top:scroll.current,behavior:'instant'});scroll.current=null;trigger.current=null;}
  },[selected]);
  async function refresh(){if(flight.current||api.loading)return;flight.current=true;try{await api.reconcile(read);}finally{flight.current=false;}}
  function filter(patch){setQuery(prev=>({...prev,...patch,page:1}));}
  function apply(event){event.preventDefault();if(draft.desde&&draft.hasta&&draft.desde>draft.hasta){setInvalid('La fecha final debe ser igual o posterior a la inicial.');return;}setInvalid('');filter({...draft,buscar:draft.buscar.trim()});}
  if(selected)return <BudgetDetail key={selected.id} row={selected} onBack={()=>setSelected(null)}/>;
  const s=data?.resumen,rate=s?.tasa_aceptacion;
  return <section className="commercial-page budgets-page manager-portfolio commercial-manager">
    <PageHead title="Seguimiento comercial" sub="Consulta el estado y valor de los presupuestos."><button className="btn btn-outline-secondary budget-refresh" type="button" aria-label="Actualizar datos" disabled={api.loading} onClick={refresh}><svg width="16" height="16" viewBox="0 0 16 16" fill="currentColor" aria-hidden="true"><path fillRule="evenodd" d="M8 3a5 5 0 1 1-4.546 2.914.5.5 0 0 0-.908-.417A6 6 0 1 0 8 2z"/><path d="M8 4.466V.534a.25.25 0 0 0-.41-.192L5.23 2.308a.25.25 0 0 0 0 .384l2.36 1.966A.25.25 0 0 0 8 4.466"/></svg>Actualizar</button></PageHead>
    <Errors error={api.error}/>{api.loading&&<p role="status" className="commercial-loading">Cargando presupuestos…</p>}
    <form className="card-fyag commercial-period" onSubmit={apply}>
      <div><label htmlFor="manager-budget-from">Creado desde</label><input type="date" id="manager-budget-from" className="form-control" value={draft.desde} onChange={e=>setDraft({...draft,desde:e.target.value})}/></div>
      <div><label htmlFor="manager-budget-to">Creado hasta</label><input type="date" id="manager-budget-to" className="form-control" value={draft.hasta} onChange={e=>setDraft({...draft,hasta:e.target.value})}/></div>
      <div className="commercial-search"><label htmlFor="manager-budget-search">Buscar presupuesto</label><input id="manager-budget-search" className="form-control" placeholder="Código, cliente o descripción" maxLength={100} value={draft.buscar} onChange={e=>setDraft({...draft,buscar:e.target.value})}/></div>
      <button className="btn btn-fyag-primary" type="submit">Aplicar filtros</button>
      <button className="btn btn-outline-secondary" type="button" onClick={()=>{setDraft({desde:'',hasta:'',buscar:''});setInvalid('');setQuery(INITIAL);}}>Limpiar filtros</button>
      {invalid&&<p role="alert">{invalid}</p>}
    </form>
    <div className="portfolio-kpis">{METRICS.map(([key,title,tone])=><button type="button" key={key} className={'portfolio-kpi portfolio-'+tone} aria-label={title} aria-pressed={query.estado===key} disabled={!s} onClick={()=>filter({estado:query.estado===key?'':key,sin_actualizar:''})}><span>{title}</span><strong>{s?.estados[key].cantidad??'—'}</strong><small>{s?formatCompactCLP(s.estados[key].monto_neto)+' CLP':'—'}</small></button>)}</div>
    <div className="commercial-insights">
      <section className="card-fyag commercial-acceptance">
        <h2>Resultados comerciales</h2>
        <div className="commercial-donut-layout">
          <div className="commercial-donut">
            <svg viewBox="0 0 180 180" aria-hidden="true" focusable="false">
              <circle cx="90" cy="90" r="74" stroke={s?.respuestas_cliente?'#E34D59':'#E7EDF3'} strokeWidth="20" fill="none"/>
              {rate!=null&&Number(rate)>0&&<circle cx="90" cy="90" r="74" stroke="#20AC73" strokeWidth="20" fill="none" pathLength="100" strokeDasharray={rate+' '+(100-Number(rate))} transform="rotate(-90 90 90)"/>}
            </svg>
            <div><strong>{rate==null?'—':Number(rate).toLocaleString('es-CL',{maximumFractionDigits:1})+'%'}</strong><span>Aceptación</span></div>
          </div>
          <div className="commercial-acceptance-legend">
            <div><span><i style={{background:'#20AC73'}}/>Aceptados</span><strong>{s?.estados.APROBADO_CLIENTE.cantidad??'—'}</strong></div>
            <div><span><i style={{background:'#E34D59'}}/>Rechazados</span><strong>{s?.estados.RECHAZADO_CLIENTE.cantidad??'—'}</strong></div>
            <small>{s?(s.respuestas_cliente===1?'1 presupuesto respondido':s.respuestas_cliente+' presupuestos respondidos'):'Sin datos disponibles'}</small>
          </div>
        </div>
      </section>
      <section className="card-fyag commercial-followup">
        <h2>Seguimiento pendiente</h2>
        <div className={'commercial-followup-body '+(!s?'followup-unknown':s.sin_actualizar?'followup-pending':'followup-clear')}>
          {s&&<svg width="34" height="34" viewBox="0 0 16 16" fill="currentColor" aria-hidden="true" focusable="false">
            <path d="M8 15A7 7 0 1 1 8 1a7 7 0 0 1 0 14m0 1A8 8 0 1 0 8 0a8 8 0 0 0 0 16"/>
            {s.sin_actualizar===0?<path d="M10.97 4.97a.75.75 0 0 1 1.08 1.04l-4 5a.75.75 0 0 1-1.08.02L4.324 8.384a.75.75 0 1 1 1.06-1.06l2.094 2.093 3.47-4.425z"/>:<path d="M7.002 11a1 1 0 1 1 2 0 1 1 0 0 1-2 0M7.1 4.995a.9.9 0 1 1 1.8 0l-.35 3.507a.55.55 0 0 1-1.1 0z"/>}
          </svg>}
          <strong className="commercial-followup-count">{s?.sin_actualizar??'—'}</strong>
          <div className="commercial-followup-label">{!s?'Sin datos disponibles':s.sin_actualizar===0?'Sin pendientes de seguimiento':s.sin_actualizar===1?'Presupuesto pendiente de seguimiento':'Presupuestos pendientes de seguimiento'}</div>
          <p title="Incluye presupuestos en revisión interna, aprobados internamente o enviados al cliente.">Sin actualización por {s?.dias_sin_actualizar??7} días o más.</p>
          {s&&(s.sin_actualizar>0||query.sin_actualizar==='true')&&<button type="button" className="btn btn-outline-secondary btn-sm" aria-pressed={query.sin_actualizar==='true'} onClick={()=>filter({sin_actualizar:query.sin_actualizar==='true'?'':'true',estado:''})}>{query.sin_actualizar?'Ver todos':'Ver pendientes sin actualizar'}</button>}
        </div>
      </section>
    </div>
    <section className="card-fyag portfolio-list"><div className="portfolio-list-head"><div><h2>Presupuestos</h2><span>{s?s.total+' registros del período · '+data.count+' coincidencias':'—'}</span></div><div><label htmlFor="budget-filter" className="form-label">Estado</label><select className="form-select" id="budget-filter" value={query.estado} onChange={e=>filter({estado:e.target.value,sin_actualizar:''})}><option value="">Todos</option>{OPTIONS.map(k=><option key={k} value={k}>{label(k)}</option>)}</select></div></div>
    <div className="portfolio-results">{data?.results.map(row=><article className={'portfolio-work '+(row.sin_actualizar?'portfolio-atencion':'portfolio-normal')} key={row.id}><div className="portfolio-row-head"><div><h3>{row.codigo} <BudgetStatus state={row.estado_original}/></h3><p>{row.cliente_nombre} · {when(row.creado_en)}</p></div><strong className="commercial-row-net">{formatCompactCLP(row.monto_neto)}</strong></div><div className="portfolio-context"><span>{row.sin_actualizar?'Sin actualización reciente':row.descripcion}</span><button className="btn btn-outline-secondary btn-sm" type="button" data-manager-budget={row.id} onClick={()=>{scroll.current=globalThis.window?.scrollY??0;trigger.current=row.id;setSelected(row);}}>Ver presupuesto</button></div></article>)}</div>
    {data&&!data.count&&<p className="commercial-empty">No hay presupuestos para estos filtros.</p>}
    {data&&(data.next||data.previous)&&<Pager label="Paginación de presupuestos" data={data} page={query.page} setPage={page=>setQuery(prev=>({...prev,page}))} disabled={api.loading}/>}
    {api.error?.status===404&&query.page!==1&&<button type="button" className="btn btn-outline-secondary" onClick={()=>filter({})}>Volver a la primera página</button>}
    </section><p className="commercial-help">Montos netos cotizados, no ingresos percibidos. Indicadores por presupuesto registrado (incluidas revisiones), según fecha de creación y estado actual.</p>
  </section>;
}
function BudgetDetail({row,onBack}){
  const api=useCommercial(),[budget,setBudget]=useState(null),[tab,setTab]=useState('items'),[history,setHistory]=useState(null),[page,setPage]=useState(1);
  const base=budgetPath(row.id);
  useEffect(()=>{void api.load('budget',base,b=>{if(b?.id!==row.id||!Array.isArray(b.items)||!money(b.monto_neto))throw new ApiError(502,'No se pudo confirmar el presupuesto.');setBudget(b);});},[row.id]);
  useEffect(()=>{if(tab==='history'){setHistory(null);void api.load('history',pagePath(base+'historial/',page),v=>setHistory(validatePage(v,base+'historial/')));}},[tab,page]);
  return <section className="commercial-page budgets-page"><button type="button" className="btn btn-outline-secondary budget-back" onClick={onBack}>Volver al listado</button><Errors error={api.error}/>{api.loading&&<p role="status">Cargando datos…</p>}
    {budget&&<article className="card-fyag commercial-detail"><div className="budget-detail-heading"><h2>{budget.codigo}</h2><BudgetStatus state={budget.estado}/></div><div className="commercial-summary"><div><strong>{row.cliente_nombre}</strong><p>{budget.descripcion}</p><small>Creado el {when(budget.creado_en)}</small></div><div className="commercial-total"><span>Total neto · CLP</span><strong>{formatCompactCLP(budget.monto_neto)}</strong></div></div>
    <div className="budget-tabs" role="group" aria-label="Secciones del presupuesto"><button type="button" aria-pressed={tab==='items'} onClick={()=>setTab('items')}>Ítems del presupuesto</button><button type="button" aria-pressed={tab==='history'} onClick={()=>setTab('history')}>Historial comercial</button></div>
    <div id="budget-items" hidden={tab!=='items'}><div className="table-responsive"><table className="table commercial-table"><thead><tr>{['Descripción','Cantidad','Unidad','Precio unitario CLP','Subtotal CLP'].map(x=><th key={x} scope="col">{x}</th>)}</tr></thead><tbody>{budget.items.map(i=><tr key={i.id}><td>{i.descripcion}</td><td>{i.cantidad}</td><td>{i.unidad}</td><td>{formatCompactCLP(i.precio_unitario)}</td><td>{formatCompactCLP(i.subtotal)}</td></tr>)}</tbody></table></div>{!budget.items.length&&<p>No hay ítems registrados.</p>}</div>
    <section id="budget-history" hidden={tab!=='history'}><ol className="commercial-timeline">{history?.results.map(e=><li key={e.id}><BudgetStatus state={e.estado_nuevo}/><p>{when(e.creado_en)}</p>{e.motivo&&<p>{e.motivo}</p>}</li>)}</ol>{history&&!history.count&&<p>No hay decisiones registradas.</p>}{history&&(history.next||history.previous)&&<Pager label="Paginación del historial" data={history} page={page} setPage={setPage} disabled={api.loading}/>}</section></article>}
  </section>;
}
