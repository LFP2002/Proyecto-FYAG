import React,{useEffect,useLayoutEffect,useRef,useState} from 'react';
import {ApiError} from '../auth/client.js';
import {formatCompactCLP,formatCivilDate} from '../utils/format.js';
import {PageHead} from '../components/ui';
import {readPage} from './api.js';
import {OBRA_STATES} from './domain.js';
import {Feedback,ObraStatus,Pager,useOperational} from './ui.jsx';
import GerenciaObra from './GerenciaObra.jsx';
import {economicDifference} from './managerEconomy.js';
import '../styles/pages/obras-gerencia.css';

const PATH='/api/obras/supervision-gerencial/';
const INITIAL={estado:'',atencion:'todas',buscar:'',prioridad:'',page:1};
const ALERTS={PRESUPUESTO_SUPERADO:'Presupuesto superado',SUSPENDIDA:'Suspendida',SIN_PROGRAMAR:'Sin programar',SIN_RESPONSABLE:'Sin responsable',CIERRE_NO_DISPONIBLE:'Cierre no disponible'};
const METRICS=[['en_ejecucion','En ejecución','blue','estado','EN_PROCESO'],['sin_programar','Sin programar','amber','prioridad','sin_programar'],['presupuesto_superado','Presupuesto superado','red','prioridad','presupuesto_superado'],['suspendidas','Suspendidas','gray','prioridad','suspendidas']];
const amount=v=>typeof v==='string'&&/^-?\d+(?:\.\d{1,2})?$/.test(v);
function project(data){
  const result=readPage(data,PATH);
  const keys=['total','en_ejecucion','sin_programar','presupuesto_superado','suspendidas','requieren_atencion'];
  if(!keys.every(k=>Number.isSafeInteger(data.resumen?.[k])&&data.resumen[k]>=0&&data.resumen[k]<=data.resumen.total))throw new ApiError(502,'No se pudieron confirmar los indicadores.');
  const fields=['id','codigo','cliente_nombre','categoria_nombre','tecnico_nombre','estado','fecha_programada','presupuesto_neto','costo_total','diferencia_neta','porcentaje_utilizado','costos_provisionales','sin_cobro','alertas','nivel'];
  const results=result.results.map(row=>{
    if(!Number.isSafeInteger(row.id)||row.id<1||!OBRA_STATES[row.estado]||!['critica','atencion','normal'].includes(row.nivel)||!['presupuesto_neto','costo_total','diferencia_neta'].every(k=>amount(row[k]))||!(row.porcentaje_utilizado===null||typeof row.porcentaje_utilizado==='string'&&/^\d+\.\d$/.test(row.porcentaje_utilizado))||!Array.isArray(row.alertas)||!row.alertas.every(a=>Object.hasOwn(ALERTS,a))||typeof row.costos_provisionales!=='boolean'||typeof row.sin_cobro!=='boolean')throw new ApiError(502,'No se pudo confirmar la información de las obras.');
    return Object.fromEntries(fields.map(k=>[k,row[k]]));
  });
  return {...result,results,resumen:Object.fromEntries(keys.map(k=>[k,data.resumen[k]]))};
}
export default function GerenciaPanel(){
  const api=useOperational(),[query,setQuery]=useState(INITIAL),[draft,setDraft]=useState({buscar:'',estado:''}),[filtersOpen,setFiltersOpen]=useState(false),[data,setData]=useState(null),[selected,setSelected]=useState(null);
  const position=useRef(null);
  const path=PATH+'?'+new URLSearchParams(Object.entries(query).filter(([k,v])=>v!==''&&(k!=='atencion'||v!=='todas'))).toString();
  function read(){setData(null);return api.load('portfolio',path,value=>setData(project(value)));}
  useEffect(()=>{api.setError(null);void read();},[path]);
  useLayoutEffect(()=>{
    if(position.current===null)return;
    if(selected)globalThis.window?.scrollTo?.({top:0,behavior:'instant'});
    else{globalThis.window?.scrollTo?.({top:position.current,behavior:'instant'});position.current=null;}
  },[selected]);
  function filter(patch){setQuery(prev=>({...prev,...patch,page:1}));if(Object.hasOwn(patch,'estado'))setDraft(prev=>({...prev,estado:patch.estado}));}
  function clear(){setDraft({buscar:'',estado:''});setQuery(INITIAL);}
  function open(id){position.current=globalThis.window?.scrollY??0;setSelected(id);}
  if(selected)return <section className="commercial-page obras-page"><GerenciaObra key={selected} id={selected} onBack={()=>setSelected(null)}/></section>;
  return <section className="commercial-page obras-page manager-portfolio manager-obras-list">
    <PageHead title="Supervisión de obras" sub="Consulta el estado y desempeño económico de tus obras."><button type="button" className="btn btn-outline-secondary" disabled={api.loading} aria-label="Actualizar datos" onClick={()=>void api.reconcile(read)}><svg width="16" height="16" viewBox="0 0 16 16" fill="currentColor" className="bi bi-arrow-counterclockwise" aria-hidden="true"><path fillRule="evenodd" d="M8 3a5 5 0 1 1-4.546 2.914.5.5 0 0 0-.908-.417A6 6 0 1 0 8 2z"/><path d="M8 4.466V.534a.25.25 0 0 0-.41-.192L5.23 2.308a.25.25 0 0 0 0 .384l2.36 1.966A.25.25 0 0 0 8 4.466"/></svg> Actualizar</button></PageHead>
    <Feedback api={api}/>
    <div className="portfolio-kpis">{METRICS.map(([key,label,tone,field,value])=><button type="button" key={key} className={'portfolio-kpi portfolio-'+tone} aria-pressed={query[field]===value} disabled={!data} onClick={()=>filter({estado:'',prioridad:'',atencion:'todas',[field]:query[field]===value?'':value})}><span>{label}</span><strong>{data?.resumen[key]??'—'}</strong></button>)}</div>
    <div className="card-fyag portfolio-list">
      <div className="portfolio-list-head"><div><h2>Obras</h2><span>{data?data.resumen.total+' obras · '+data.resumen.requieren_atencion+' requieren atención':'—'}</span></div><button type="button" className="btn btn-outline-secondary btn-sm manager-obras-icon" aria-expanded={filtersOpen} aria-controls="manager-obra-filters" onClick={()=>setFiltersOpen(x=>!x)}><svg width="16" height="16" viewBox="0 0 16 16" fill="currentColor" aria-hidden="true"><path d="M6 11.5a.5.5 0 0 1 .5-.5h3a.5.5 0 0 1 0 1h-3a.5.5 0 0 1-.5-.5m-2-4a.5.5 0 0 1 .5-.5h7a.5.5 0 0 1 0 1h-7a.5.5 0 0 1-.5-.5m-2-4a.5.5 0 0 1 .5-.5h11a.5.5 0 0 1 0 1h-11a.5.5 0 0 1-.5-.5"/></svg>Filtros</button></div>
      <form id="manager-obra-filters" className="manager-obras-filters" hidden={!filtersOpen} onSubmit={e=>{e.preventDefault();filter({buscar:draft.buscar.trim(),estado:draft.estado,prioridad:''});setFiltersOpen(false);}}><div><label htmlFor="manager-obra-search">Buscar obra</label><input id="manager-obra-search" className="form-control" placeholder="Código, cliente o responsable" maxLength={100} value={draft.buscar} onChange={e=>setDraft(prev=>({...prev,buscar:e.target.value}))}/></div><div><label htmlFor="manager-obra-state">Estado de obra</label><select id="manager-obra-state" className="form-select" value={draft.estado} onChange={e=>setDraft(prev=>({...prev,estado:e.target.value}))}><option value="">Todos los estados</option>{Object.entries(OBRA_STATES).map(([key,[label]])=><option key={key} value={key}>{label}</option>)}</select></div><button type="submit" className="btn btn-fyag-primary">Aplicar filtros</button></form>
      {(query.estado||query.prioridad||query.buscar||query.atencion!=='todas')&&<div className="manager-obras-applied"><span>{[query.buscar,OBRA_STATES[query.estado]?.[0],METRICS.find(m=>m[3]==='prioridad'&&m[4]===query.prioridad)?.[1],query.atencion==='requiere'?'Requieren atención':query.atencion==='sin_alertas'?'Sin alertas':''].filter(Boolean).join(' · ')}</span><button type="button" className="btn btn-outline-secondary btn-sm" onClick={clear}>Limpiar filtros</button></div>}
      <div className="manager-work-tabs" role="group" aria-label="Atención requerida">{[['todas','Todas'],['requiere','Requieren atención'],['sin_alertas','Sin alertas de supervisión']].map(([key,label])=><button type="button" key={key} aria-pressed={query.atencion===key} onClick={()=>filter({atencion:key,prioridad:'',estado:''})}>{label}</button>)}</div>
      {data&&<div className="portfolio-results">{data.results.map(row=>{const diff=economicDifference(row.presupuesto_neto,row.costo_total,row.estado==='FINALIZADA'&&!row.costos_provisionales&&!row.sin_cobro);return <article className={'portfolio-work portfolio-'+row.nivel} key={row.id}>
        <div className="portfolio-row-head"><div><h3>{row.codigo} <ObraStatus state={row.estado}/></h3><p>{row.cliente_nombre} · {row.categoria_nombre}</p></div><div className="portfolio-alerts">{row.alertas.length?row.alertas.map(a=><span key={a} className={a==='PRESUPUESTO_SUPERADO'||a==='CIERRE_NO_DISPONIBLE'?'portfolio-alert-critical':'portfolio-alert-warning'}>{ALERTS[a]}</span>):<span className="portfolio-alert-good">Sin alertas de supervisión</span>}</div></div>
        <div className="portfolio-work-body"><div className="portfolio-amounts"><div><span>Presupuesto neto</span><strong>{formatCompactCLP(row.presupuesto_neto)}</strong></div><div><span>Costo acumulado neto</span><strong>{formatCompactCLP(row.costo_total)}</strong><small>{row.costos_provisionales?'Provisional':'Validado'}{row.sin_cobro?' · Sin cobro':''}</small></div><div><span>{diff?.label||'Diferencia presupuestaria'}</span><strong className={'manager-difference '+(diff?.tone||'neutral')}>{diff?.value||'—'}</strong><small>{diff?.detail||'No disponible'}</small></div></div>
        <div className="manager-obras-footer"><div className="portfolio-context"><span>{row.tecnico_nombre||'Sin responsable'} · {row.fecha_programada?formatCivilDate(row.fecha_programada):'Sin programar'}</span><button type="button" className="btn btn-outline-secondary btn-sm" onClick={()=>open(row.id)}>Ver obra</button></div></div></div>
      </article>;})}{!data.count&&<p className="commercial-empty">No hay obras para estos filtros.</p>}</div>}
      {data&&(data.next||data.previous)&&<Pager label="Paginación de obras" data={data} page={query.page} setPage={page=>setQuery(prev=>({...prev,page}))} disabled={api.loading}/>}
      {api.error?.status===404&&query.page!==1&&<button type="button" className="btn btn-outline-secondary" onClick={()=>filter({})}>Volver a la primera página</button>}
    </div>
  </section>;
}
