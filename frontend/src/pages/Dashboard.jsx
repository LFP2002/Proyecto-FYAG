import { formatCompactCLP, formatCivilDate } from '../utils/format.js';
import React, { useEffect, useMemo, useState } from 'react';
import { useAuth } from '../auth/AuthContext.jsx';
import { PageHead } from '../components/ui';
import { useApi, readPage, strictObject, decimalString, positiveInteger } from '../integrations/useApi.js';
import { Pager } from '../comercial/ui.jsx';
import { civilRange, todayInSantiago } from '../integrations/dates.js';
export { todayInSantiago } from '../integrations/dates.js';

const STATES=['PLANIFICADA','EN_PROCESO','SUSPENDIDA','FINALIZADA','CANCELADA'];
const STATE_LABELS={PLANIFICADA:'Planificadas',EN_PROCESO:'En ejecución',SUSPENDIDA:'Suspendidas',FINALIZADA:'Finalizadas',CANCELADA:'Canceladas'};
const STATE_TONES={PLANIFICADA:'pending',EN_PROCESO:'active',SUSPENDIDA:'danger',FINALIZADA:'good',CANCELADA:'neutral'};
const isNegative=(value)=>typeof value==='string'&&value.startsWith('-')&&/[1-9]/.test(value);
const hasAmount=(value)=>typeof value==='string'&&/[1-9]/.test(value);
function Kpi({label,value,tone}) {return <article className={`dash-kpi dash-${tone}`}><div className="dash-kpi-label">{label}</div><strong className="dash-kpi-value">{value.toLocaleString('es-CL')}</strong></article>;}
function MoneyStat({label,value,tone='neutral'}) {return <div className={`dash-money dash-${tone}`}><dt>{label}</dt><dd>{formatCompactCLP(value)}</dd></div>;}
function WorkStates({counts}) {
  const total=STATES.reduce((sum,state)=>sum+counts[state],0);
  let offset=0;
  const segments=STATES.filter(state=>counts[state]>0).map(state=>{
    const share=counts[state]/total*100;
    const segment={state,share,offset};
    offset+=share;
    return segment;
  });
  return <div className="dash-donut-layout">
    <div className="dash-donut">
      <svg viewBox="0 0 160 160" aria-hidden="true" focusable="false">
        <circle className="dash-donut-track" cx="80" cy="80" r="62" fill="none" strokeWidth="26"/>
        {segments.map(({state,share,offset})=><circle key={state} className={`dash-donut-segment dash-${STATE_TONES[state]}`} cx="80" cy="80" r="62" fill="none" strokeWidth="26" pathLength="100" strokeDasharray={`${share} ${100-share}`} strokeDashoffset={-offset} transform="rotate(-90 80 80)"/>)}
      </svg>
      <div className="dash-donut-center"><strong>{total.toLocaleString('es-CL')}</strong><span>{total===1?'obra':'obras'}</span></div>
    </div>
    <ul className="dash-donut-legend" aria-label="Distribución de obras por estado">
      {STATES.map(state=><li key={state} className={`dash-${STATE_TONES[state]}`}><span className="dash-donut-dot" aria-hidden="true"/><span className="dash-donut-label">{STATE_LABELS[state]}</span><strong>{counts[state].toLocaleString('es-CL')}</strong></li>)}
    </ul>
  </div>;
}
function MonthlyChart({points}) {const max=Math.max(1,...points.map(p=>p.cantidad));return <div className="dash-month-scroll" role="region" aria-label="Gráfico de obras finalizadas por mes" tabIndex={0}><div className="dash-month-chart" style={{gridTemplateColumns:`repeat(${points.length},minmax(54px,1fr))`}}>{points.map(p=><div className="dash-month" key={p.mes}><div className="dash-month-plot"><strong>{p.cantidad.toLocaleString('es-CL')}</strong><div className="dash-month-bar" style={{height:`${p.cantidad/max*100}%`}} /></div><span>{new Date(`${p.mes}-01T12:00:00Z`).toLocaleDateString('es-CL',{month:'short',year:'2-digit',timeZone:'UTC'})}</span></div>)}</div></div>;}
const SUMMARY='/api/dashboard/resumen/'; const SERIES='/api/dashboard/serie-obras/'; const ACTIVE='/api/dashboard/obras-activas/';
const moneyKeys=['presupuesto_neto','costo_real_neto','margen_real_neto','monto_documentado_bruto','abonado','saldo','saldo_vencido'];
function validateSummary(v){
  strictObject(v,['generado_en','zona_horaria','moneda','periodo','operacion','rentabilidad_cerrada_periodo','cobranza_actual','incidencias']);
  strictObject(v.periodo,['desde','hasta']); strictObject(v.operacion,['obras_por_estado_actual','presupuestos_pendientes_gerencia_actual','presupuestos_pendientes_finanzas_actual','obras_finalizadas_periodo']);
  strictObject(v.operacion.obras_por_estado_actual,STATES); strictObject(v.rentabilidad_cerrada_periodo,['obras_con_cierre','presupuesto_neto','costo_real_neto','margen_real_neto']);
  strictObject(v.cobranza_actual,['documentos_vigentes','monto_documentado_bruto','abonado','saldo','saldo_vencido']);
  strictObject(v.incidencias,['criticas_activas','pendientes_por_area','por_estado','sincronizacion']);
  strictObject(v.incidencias.pendientes_por_area,['ADMINISTRATIVO_FINANZAS','SUPERVISOR_OBRAS']);
  strictObject(v.incidencias.por_estado,['PENDIENTE','ATENDIDA','RESUELTA']);
  strictObject(v.incidencias.sincronizacion,['ultima_correcta_en','desactualizada']);
  if(v.zona_horaria!=='America/Santiago'||v.moneda!=='CLP'||Object.values(v.operacion.obras_por_estado_actual).some(n=>!Number.isSafeInteger(n)||n<0)
    ||['presupuestos_pendientes_gerencia_actual','presupuestos_pendientes_finanzas_actual','obras_finalizadas_periodo','obras_con_cierre','documentos_vigentes','criticas_activas'].some(k=>!Number.isSafeInteger(v.operacion[k]??v.rentabilidad_cerrada_periodo[k]??v.cobranza_actual[k]??v.incidencias[k]) || (v.operacion[k]??v.rentabilidad_cerrada_periodo[k]??v.cobranza_actual[k]??v.incidencias[k])<0)
    ||Object.values(v.incidencias.pendientes_por_area).some(n=>!Number.isSafeInteger(n)||n<0)
    ||Object.values(v.incidencias.por_estado).some(n=>!Number.isSafeInteger(n)||n<0)
    ||typeof v.incidencias.sincronizacion.desactualizada!=='boolean'
    ||(v.incidencias.sincronizacion.ultima_correcta_en!==null&&typeof v.incidencias.sincronizacion.ultima_correcta_en!=='string')
    ||moneyKeys.some(k=>!decimalString(v.rentabilidad_cerrada_periodo[k]??v.cobranza_actual[k],k==='margen_real_neto'))) throw new Error('Respuesta de Dashboard inválida.');
  return v;
}
function validateSeries(v,months){strictObject(v,['metrica','zona_horaria','puntos']);if(v.metrica!=='OBRAS_FINALIZADAS'||v.zona_horaria!=='America/Santiago'||!Array.isArray(v.puntos)||v.puntos.length!==months)throw new Error('Serie del Dashboard inválida.');let prev='';for(const p of v.puntos){strictObject(p,['mes','cantidad']);if(!/^\d{4}-(0[1-9]|1[0-2])$/.test(p.mes)||p.mes<=prev||!Number.isSafeInteger(p.cantidad)||p.cantidad<0)throw new Error('Punto de serie inválido.');prev=p.mes;}return v;}
function validateActivePage(v){readPage(v,ACTIVE);for(const x of v.results){strictObject(x,['id','codigo','cliente','cliente_nombre','categoria_nombre','estado','tecnico_responsable','tecnico_nombre','fecha_programada','presupuesto_neto']);if(!positiveInteger(x.id)||!positiveInteger(x.cliente)||x.estado!=='EN_PROCESO'||typeof x.codigo!=='string'||typeof x.cliente_nombre!=='string'||typeof x.categoria_nombre!=='string'||!decimalString(x.presupuesto_neto))throw new Error('Obra activa inválida.');}return v;}
function asURL(path,params){const q=new URLSearchParams();Object.entries(params).forEach(([k,v])=>{if(v!=='')q.set(k,v);});return path+(q.size?`?${q}`:'');}
export function validDashboardRange(dates,today=todayInSantiago()){if(!!dates.desde!==!!dates.hasta)return false;if(!dates.desde)return true;return civilRange(dates.desde,dates.hasta)&&dates.hasta<=today;}
export default function Dashboard(){
 const {user}=useAuth();
 if(user.role!=='GERENCIA')return <section><PageHead title="Dashboard"/><p role="alert">No tienes permiso para el Dashboard.</p></section>;
 return <DashboardScreen key={`${user.id}:${user.role}`}/>;
}
function DashboardScreen(){
 const api=useApi(); const [summaryResult,setSummary]=useState(null),[seriesResult,setSeries]=useState(null),[activeResult,setActive]=useState(null),[months,setMonths]=useState('6'),[page,setPage]=useState(1),[dates,setDates]=useState({desde:'',hasta:''});
 const summaryUrl=useMemo(()=>asURL(SUMMARY,dates),[dates]); const seriesUrl=useMemo(()=>`${SERIES}?meses=${months}`,[months]); const activeUrl=useMemo(()=>`${ACTIVE}${page>1?`?page=${page}`:''}`,[page]);
 const rangeValid=validDashboardRange(dates);
 const summary=rangeValid&&summaryResult?.path===summaryUrl?summaryResult.value:null,series=seriesResult?.path===seriesUrl?seriesResult.value:null,active=activeResult?.path===activeUrl?activeResult.value:null;
 const loadSummary=()=>{api.cancelRead('summary');setSummary(null);return rangeValid?api.load('summary',summaryUrl,(v)=>setSummary({path:summaryUrl,value:validateSummary(v)})):Promise.resolve(false);};
 const loadSeries=()=>{setSeries(null);return api.load('series',seriesUrl,(v)=>setSeries({path:seriesUrl,value:validateSeries(v,Number(months))}));};
 const loadActive=()=>{setActive(null);return api.load('active',activeUrl,(v)=>setActive({path:activeUrl,value:validateActivePage(v)}));};
  useEffect(()=>{setPage(1);void loadSummary();},[summaryUrl,rangeValid]); useEffect(()=>{void loadSeries();},[seriesUrl]); useEffect(()=>{void loadActive();},[activeUrl]);
 async function refresh(){const r=await Promise.all([loadSummary(),loadSeries(),loadActive()]);if(r.every(Boolean))api.reconcile(async()=>true);}
 const disabled=api.loading||api.busy;
 const rent=summary?.rentabilidad_cerrada_periodo, collection=summary?.cobranza_actual, incidents=summary?.incidencias;
 const updated=summary?new Intl.DateTimeFormat('es-CL',{timeZone:'America/Santiago',dateStyle:'short',timeStyle:'short'}).format(new Date(summary.generado_en)):null;
 return <section className="commercial-page dashboard-page">
  <PageHead title="Dashboard gerencial" sub="Consulta el estado operativo y financiero de tu empresa.">
    <button type="button" className="btn btn-outline-secondary dash-refresh" disabled={disabled} onClick={()=>void refresh()}><svg width="16" height="16" viewBox="0 0 16 16" fill="currentColor" className="bi bi-arrow-counterclockwise" aria-hidden="true"><path fillRule="evenodd" d="M8 3a5 5 0 1 1-4.546 2.914.5.5 0 0 0-.908-.417A6 6 0 1 0 8 2z"/><path d="M8 4.466V.534a.25.25 0 0 0-.41-.192L5.23 2.308a.25.25 0 0 0 0 .384l2.36 1.966A.25.25 0 0 0 8 4.466"/></svg>Actualizar</button>
  </PageHead>
  {api.error&&<div className="alert alert-warning" role="alert">{api.error.status===403?'Acceso denegado.':api.error.status===409?'No fue posible confirmar las cifras. Actualiza la información.':api.error.message}</div>}
  <div className="dash-filterbar">
    <div className="dash-period-fields"><label className="form-label">Desde<input className="form-control" type="date" max={todayInSantiago()} value={dates.desde} onChange={e=>setDates({...dates,desde:e.target.value})}/></label><label className="form-label">Hasta<input className="form-control" type="date" max={todayInSantiago()} value={dates.hasta} onChange={e=>setDates({...dates,hasta:e.target.value})}/></label></div>
    <div className="dash-period-note">{summary&&<span>Período de finalización y rentabilidad: <strong>{formatCivilDate(summary.periodo.desde)} – {formatCivilDate(summary.periodo.hasta)}</strong></span>}{updated&&<span>Actualizado: {updated}</span>}</div>
  </div>
  {!rangeValid&&<p className="alert alert-warning" role="alert">Desde y Hasta deben indicarse juntos, con un máximo de 366 días y hasta hoy.</p>}
  {summary&&<div className="dash-kpi-grid">
    <Kpi label="Obras en ejecución" value={summary.operacion.obras_por_estado_actual.EN_PROCESO} tone="active"/>
    <Kpi label="Presupuestos pendientes de Finanzas" value={summary.operacion.presupuestos_pendientes_finanzas_actual} tone="pending"/>
    <Kpi label="Obras finalizadas en el período" value={summary.operacion.obras_finalizadas_periodo} tone="good"/>
    <Kpi label="Incidencias críticas activas" value={incidents.criticas_activas} tone={incidents.criticas_activas?'danger':'good'}/>
  </div>}
  {(summary||series)&&<div className="dash-panels dash-operation">
    {summary&&<section className="card-fyag dash-panel"><div className="dash-panel-head"><h2>Estado actual de obras</h2></div><WorkStates counts={summary.operacion.obras_por_estado_actual}/></section>}
    {series&&<section className="card-fyag dash-panel"><div className="dash-panel-head"><h2>Obras finalizadas por mes</h2><label className="dash-series-control">Meses<select className="form-select form-select-sm" value={months} onChange={e=>setMonths(e.target.value)}>{Array.from({length:12},(_,i)=>String(i+1)).map(m=><option key={m} value={m}>{m}</option>)}</select></label></div><MonthlyChart points={series.puntos}/></section>}
    {!series&&<section className="card-fyag dash-panel"><div className="dash-panel-head"><h2>Obras finalizadas por mes</h2><label className="dash-series-control">Meses<select className="form-select form-select-sm" value={months} onChange={e=>setMonths(e.target.value)}>{Array.from({length:12},(_,i)=>String(i+1)).map(m=><option key={m} value={m}>{m}</option>)}</select></label></div><p className="commercial-help">{api.loading?'Cargando…':'No se pudo consultar la información.'}</p></section>}
  </div>}
  {!summary&&!series&&<label className="dash-series-control">Meses<select className="form-select form-select-sm" value={months} onChange={e=>setMonths(e.target.value)}>{Array.from({length:12},(_,i)=>String(i+1)).map(m=><option key={m} value={m}>{m}</option>)}</select></label>}
  {summary&&<div className="dash-panels dash-finance-grid">
    <section className="card-fyag dash-panel"><div className="dash-panel-head"><h2>Rentabilidad del período</h2><span>CLP · neto</span></div><p className="dash-panel-sub">{rent.obras_con_cierre} {rent.obras_con_cierre===1?'obra finalizada con cierre económico':'obras finalizadas con cierre económico'}</p><dl className="dash-financial dash-profit"><MoneyStat label="Presupuesto neto" value={rent.presupuesto_neto}/><MoneyStat label="Costo real neto" value={rent.costo_real_neto}/><MoneyStat label="Margen real neto" value={rent.margen_real_neto} tone={isNegative(rent.margen_real_neto)?'danger':'good'}/></dl></section>
    <section className="card-fyag dash-panel"><div className="dash-panel-head"><h2>Cobranza actual</h2><span>CLP · bruto</span></div><p className="dash-panel-sub">{collection.documentos_vigentes} documentos vigentes</p><dl className="dash-financial"><MoneyStat label="Documentado" value={collection.monto_documentado_bruto}/><MoneyStat label="Abonado" value={collection.abonado} tone="good"/><MoneyStat label="Saldo por cobrar" value={collection.saldo} tone={hasAmount(collection.saldo)?'pending':'neutral'}/><MoneyStat label="Saldo vencido" value={collection.saldo_vencido} tone={hasAmount(collection.saldo_vencido)?'danger':'neutral'}/></dl></section>
    <section className="card-fyag dash-panel"><div className="dash-panel-head"><h2>Incidencias activas</h2></div><div className={`dash-incidence ${incidents.criticas_activas?'dash-danger':'dash-good'}`}><strong>{incidents.criticas_activas}</strong><span>{incidents.criticas_activas?'Incidencias críticas':'Sin incidencias críticas'}</span></div><dl className="dash-state-list">{Object.entries(incidents.pendientes_por_area).map(([area,count])=><div className="dash-state-label" key={area}><dt>{area==='ADMINISTRATIVO_FINANZAS'?'Pendientes de Finanzas':'Pendientes de Supervisión'}</dt><dd>{count}</dd></div>)}</dl>{summary.operacion.presupuestos_pendientes_gerencia_actual>0&&<p className="dash-user-warning">Presupuestos pendientes de Gerencia: {summary.operacion.presupuestos_pendientes_gerencia_actual}</p>}{incidents.sincronizacion.desactualizada&&<p role="alert" className="dash-user-warning">Las alertas pueden estar desactualizadas. Intenta actualizar.</p>}</section>
  </div>}
  <section className="card-fyag flush dash-works"><div className="card-h"><h2>Obras en proceso</h2><span>{active?`${active.count} registros`:api.loading?'Cargando…':'No disponible'}</span></div><div className="table-responsive" role="region" aria-label="Obras en proceso" tabIndex={0}><table className="table table-hover commercial-table"><thead><tr>{['Código','Cliente','Categoría','Responsable','Programación','Presupuesto neto CLP'].map(k=><th scope="col" key={k}>{k}</th>)}</tr></thead><tbody>{active?.results.map(o=><tr key={o.id}><td>{o.codigo}</td><td>{o.cliente_nombre}</td><td>{o.categoria_nombre}</td><td>{o.tecnico_nombre||'Sin asignar'}</td><td>{o.fecha_programada?formatCivilDate(o.fecha_programada):'Sin programar'}</td><td className="dash-table-amount">{formatCompactCLP(o.presupuesto_neto)}</td></tr>)}{active&&active.count===0&&<tr><td colSpan={6} className="text-center py-4">No hay obras en ejecución.</td></tr>}</tbody></table></div>{active&&(active.next||active.previous)&&<Pager data={active} page={page} setPage={setPage} disabled={disabled} label="Paginación de Obras en proceso"/>}</section>
 </section>;
}
