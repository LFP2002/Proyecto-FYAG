import React, { useEffect, useMemo, useState } from 'react';
import { useAuth } from '../auth/AuthContext.jsx';
import { PageHead } from '../components/ui';
import { useApi, readPage, strictObject, decimalString, positiveInteger } from '../integrations/useApi.js';
import { Pager } from '../comercial/ui.jsx';
import { civilRange, todayInSantiago } from '../integrations/dates.js';
export { todayInSantiago } from '../integrations/dates.js';

const STATES=['PLANIFICADA','EN_PROCESO','SUSPENDIDA','FINALIZADA','CANCELADA'];
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
 return <section className="commercial-page">
  <PageHead title="Dashboard gerencial" sub={summary?`Datos del servidor · corte ${new Date(summary.generado_en).toLocaleString('es-CL')} · America/Santiago`:'Indicadores reales de operación, cierres y cartera.'}><button className="btn btn-outline-secondary" disabled={disabled} onClick={()=>void refresh()}>Actualizar</button></PageHead>
  {api.error&&<div className="alert alert-warning" role="alert">{api.error.status===403?'Acceso denegado.':api.error.status===409?'El origen reporta una inconsistencia; no se muestran totales parciales.':api.error.message}</div>}
   <div className="d-flex flex-wrap gap-2 mb-3 align-items-end"><label className="form-label">Desde<input className="form-control" type="date" max={todayInSantiago()} value={dates.desde} onChange={(e)=>setDates({...dates,desde:e.target.value})}/></label><label className="form-label">Hasta<input className="form-control" type="date" max={todayInSantiago()} value={dates.hasta} onChange={(e)=>setDates({...dates,hasta:e.target.value})}/></label><label className="form-label">Meses finalizados<select className="form-select" value={months} onChange={(e)=>setMonths(e.target.value)}>{Array.from({length:12},(_,i)=>String(i+1)).map(m=><option key={m} value={m}>{m}</option>)}</select></label></div>
  {!rangeValid&&<p className="alert alert-warning" role="alert">Desde y Hasta deben indicarse juntos, con un máximo de 366 días y hasta hoy.</p>}
  {summary&&<><p className="commercial-help">Periodo aplicado a finalizaciones y rentabilidad: {summary.periodo.desde} a {summary.periodo.hasta}. Los conteos de estado y cobranza son actuales, sin filtro temporal.</p>
   <div className="kpis">{[['En proceso',summary.operacion.obras_por_estado_actual.EN_PROCESO],['Presupuestos pendientes de Finanzas',summary.operacion.presupuestos_pendientes_finanzas_actual],['Presupuestos pendientes de Gerencia (legado)',summary.operacion.presupuestos_pendientes_gerencia_actual],['Obras finalizadas en periodo',summary.operacion.obras_finalizadas_periodo],['Cierres reales',summary.rentabilidad_cerrada_periodo.obras_con_cierre],['Documentos vigentes',summary.cobranza_actual.documentos_vigentes],['Incidencias críticas activas',summary.incidencias.criticas_activas]].map(([label,value])=><div className="kpi" key={label}><div className="kpi-l">{label}</div><div className="kpi-v">{value}</div></div>)}</div>
   <div className="row g-3"><div className="col-lg-6"><div className="card-fyag"><h2>Estados actuales de Obras</h2>{STATES.map(s=><p key={s} className="d-flex justify-content-between"><span>{s.replaceAll('_',' ')}</span><strong>{summary.operacion.obras_por_estado_actual[s]}</strong></p>)}</div></div>
   <div className="col-lg-6"><div className="card-fyag"><h2>Rentabilidad cerrada del periodo · CLP neto</h2><dl>{[['Presupuesto neto',summary.rentabilidad_cerrada_periodo.presupuesto_neto],['Costo real neto',summary.rentabilidad_cerrada_periodo.costo_real_neto],['Margen real neto',summary.rentabilidad_cerrada_periodo.margen_real_neto]].map(([k,v])=><div key={k} className="d-flex justify-content-between"><dt>{k}</dt><dd>{v}</dd></div>)}</dl><p className="commercial-help">Margen de Obras finalizadas con cierre real. No es utilidad contable ni ingreso cobrado.</p></div></div>
   <div className="col-12"><div className="card-fyag"><h2>Incidencias activas</h2><p>Críticas activas: <strong>{summary.incidencias.criticas_activas}</strong></p><div className="d-flex flex-wrap gap-4">{Object.entries(summary.incidencias.pendientes_por_area).map(([area,count])=><p key={area}>Pendientes para {area==='ADMINISTRATIVO_FINANZAS'?'Finanzas':'Supervisión'}: <strong>{count}</strong></p>)}</div><p className="commercial-help">Sincronización de alertas: {summary.incidencias.sincronizacion.desactualizada?'desactualizada':'actualizada'}{summary.incidencias.sincronizacion.ultima_correcta_en?` · última correcta ${new Date(summary.incidencias.sincronizacion.ultima_correcta_en).toLocaleString('es-CL')}`:''}</p></div></div>
   <div className="col-12"><div className="card-fyag"><h2>Cobranza actual · CLP bruto</h2><div className="d-flex flex-wrap gap-4">{[['Documentado bruto',summary.cobranza_actual.monto_documentado_bruto],['Abonado',summary.cobranza_actual.abonado],['Saldo',summary.cobranza_actual.saldo],['Saldo vencido',summary.cobranza_actual.saldo_vencido]].map(([k,v])=><p key={k}>{k}: <strong>{v}</strong></p>)}</div><p className="commercial-help">Cartera vigente calculada por Finanzas; abonos no se suman como documentos.</p></div></div></div>
  </>}
  {series&&<section className="card-fyag"><h2>Obras finalizadas por mes</h2><div className="d-flex flex-wrap gap-3 mt-3" role="list">{series.puntos.map(p=><div className="card-fyag" role="listitem" key={p.mes}><strong>{p.mes}</strong><p className="mb-0">{p.cantidad} finalizadas</p></div>)}</div></section>}
  <section className="card-fyag flush"><div className="card-h"><h2>Obras en proceso</h2><span>{active?.count??0} registros</span></div><div className="table-responsive" role="region" aria-label="Obras en proceso" tabIndex={0}><table className="table table-hover commercial-table"><thead><tr>{['Código','Cliente','Categoría','Responsable','Programación','Presupuesto neto CLP'].map(k=><th key={k}>{k}</th>)}</tr></thead><tbody>{active?.results.map(o=><tr key={o.id}><td>{o.codigo}</td><td>{o.cliente_nombre} · #{o.cliente}</td><td>{o.categoria_nombre}</td><td>{o.tecnico_nombre||'Sin asignar'}</td><td>{o.fecha_programada||'Sin programar'}</td><td>{o.presupuesto_neto}</td></tr>)}</tbody></table></div><Pager data={active} page={page} setPage={setPage} disabled={disabled} label="Paginación de Obras en proceso"/></section>
 </section>;
}
