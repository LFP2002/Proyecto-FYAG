import React,{useEffect,useLayoutEffect,useRef,useState} from 'react';
import {PageHead} from '../components/ui';
import {Pager,Errors} from '../comercial/ui.jsx';
import {useApi,readPage,decimalString,positiveInteger} from './useApi.js';
import {financialDocument,financialEvent,financialPayment,financialPage} from './finance.js';
import {civilRange} from './dates.js';
import {formatCompactCLP,formatCivilDate} from '../utils/format.js';
import Adjuntos from './Adjuntos.jsx';

const PATH='/api/finanzas/cobranzas/supervision-gerencial/';
const INITIAL={vista:'atencion',desde:'',hasta:'',buscar:'',page:1};
const LABELS={VENCIDA:'Vencida',PARCIAL:'Pago parcial',PENDIENTE:'Pendiente',PAGADA:'Pagada',REVERTIDO:'Revertido'};
const EVENTS={DOCUMENTO_REGISTRADO:'Documento registrado',DOCUMENTO_REVERTIDO:'Documento revertido',PAGO_REGISTRADO:'Pago registrado',PAGO_ANULADO:'Pago anulado'};
const fmt=formatCompactCLP;
const count=n=>Number.isSafeInteger(n)&&n>=0;
const cents=v=>BigInt(v.replace('.',''));
const ratio=(v,total)=>total===0n?0:Number((v*100000n+total/2n)/total)/1000;
const date=v=>typeof v==='string'&&/^\d{4}-\d{2}-\d{2}$/.test(v);
function validate(v,filters){
 const data=readPage(v,PATH,25,filters),s=data.resumen;
 if(!s||s.moneda!=='CLP'||!count(s.documentos)||!count(s.clientes_vencidos)||!date(s.fecha_corte)||!['total','cobrado','saldo','vencido','no_vencido'].every(k=>decimalString(s[k]))||cents(s.total)!==cents(s.cobrado)+cents(s.saldo)||cents(s.saldo)!==cents(s.vencido)+cents(s.no_vencido))throw Error('No se pudo confirmar el resumen de cobranzas.');
 for(const row of data.results){
  if(!positiveInteger(row.id)||!Object.hasOwn(LABELS,row.estado)||!['folio','cliente','obra'].every(k=>typeof row[k]==='string')||!date(row.emision)||!date(row.vencimiento)||!decimalString(row.total)||!count(row.dias_atraso)||(row.estado==='REVERTIDO'?(row.cobrado!==null||row.saldo!==null):(!decimalString(row.cobrado)||!decimalString(row.saldo)||cents(row.total)!==cents(row.cobrado)+cents(row.saldo))))throw Error('No se pudo confirmar el documento.');
 }
 return data;
}
function Refresh({onClick,disabled}){return <button type="button" className="btn btn-outline-secondary cobranzas-refresh" aria-label="Actualizar datos" disabled={disabled} onClick={onClick}><svg width="16" height="16" viewBox="0 0 16 16" fill="currentColor" aria-hidden="true"><path fillRule="evenodd" d="M8 3a5 5 0 1 1-4.546 2.914.5.5 0 0 0-.908-.417A6 6 0 1 0 8 2z"/><path d="M8 4.466V.534a.25.25 0 0 0-.41-.192L5.23 2.308a.25.25 0 0 0 0 .384l2.36 1.966A.25.25 0 0 0 8 4.466"/></svg>Actualizar</button>;}
function Donut({summary}){
 const parts=[['Cobrado','cobrado','#20AC73'],['Pendiente no vencido','no_vencido','#ECA321'],['Vencido','vencido','#E34D59']];
 const total=summary?cents(summary.total):0n;
 let offset=0;
 const segments=parts.map(([label,key,color])=>{const n=summary?ratio(cents(summary[key]),total):0;const result={label,key,color,n,offset};offset+=n;return result;});
 const pct=summary&&total>0n?ratio(cents(summary.cobrado),total):null;
 return <section className="card-fyag commercial-acceptance"><h2>Estado de cobranzas</h2><div className="commercial-donut-layout">
  <div className="commercial-donut"><svg viewBox="0 0 180 180" aria-hidden="true" focusable="false"><circle cx="90" cy="90" r="74" fill="none" stroke="#E7EDF3" strokeWidth="20"/>{segments.filter(x=>x.n>0).map(x=><circle key={x.key} cx="90" cy="90" r="74" fill="none" stroke={x.color} strokeWidth="20" pathLength="100" strokeDasharray={x.n+' '+(100-x.n)} strokeDashoffset={-x.offset} transform="rotate(-90 90 90)"/>)}</svg><div><strong>{pct===null?'—':pct.toLocaleString('es-CL',{maximumFractionDigits:1})+'%'}</strong><span>Cobrado</span></div></div>
  <div className="commercial-acceptance-legend">{parts.map(([label,key,color])=><div key={key}><span><i style={{background:color}}/>{label}</span><strong>{fmt(summary?.[key])}</strong></div>)}<small>{summary?summary.documentos+' documentos vigentes':'Sin datos disponibles'}</small></div>
 </div></section>;
}
export default function GerenciaCobranzas(){
 const api=useApi(),[query,setQuery]=useState(INITIAL),[draft,setDraft]=useState({desde:'',hasta:'',buscar:''}),[snapshot,setSnapshot]=useState(null),[selected,setSelected]=useState(null),[invalid,setInvalid]=useState('');
 const pos=useRef(null),trigger=useRef(null);
 const {page,...filters}=query;
 const path=PATH+'?'+new URLSearchParams(Object.entries(query).filter(([,v])=>v!=='')).toString();
 const read=()=>{setSnapshot(null);return api.load('portfolio',path,v=>setSnapshot({path,data:validate(v,filters)}));};
 useEffect(()=>{api.setError(null);void read();},[path]);
 useLayoutEffect(()=>{if(pos.current===null)return;if(selected)globalThis.window?.scrollTo?.({top:0,behavior:'instant'});else{globalThis.document?.querySelector?.('[data-cobranza="'+trigger.current+'"]')?.focus({preventScroll:true});globalThis.window?.scrollTo?.({top:pos.current,behavior:'instant'});pos.current=null;trigger.current=null;}},[selected]);
 const data=snapshot?.path===path?snapshot.data:null,s=data?.resumen;
 function change(patch){setQuery(prev=>({...prev,...patch,page:1}));}
 function apply(e){e.preventDefault();if((draft.desde||draft.hasta)&&!civilRange(draft.desde,draft.hasta)){setInvalid('Completa un período de emisión válido.');return;}setInvalid('');change({...draft,buscar:draft.buscar.trim()});}
 if(selected)return <GerenciaDocumento key={selected.id} row={selected} onBack={()=>setSelected(null)}/>;
 return <section className="commercial-page manager-portfolio cobranzas-page manager-cobranzas">
  <PageHead title="Cobranzas" sub="Supervisa los cobros y compromisos pendientes."><Refresh disabled={api.loading} onClick={()=>void api.reconcile(read)}/></PageHead>
  <Errors error={api.error}/>{api.loading&&<p role="status">Cargando cobranzas…</p>}
  <form className="card-fyag commercial-period" onSubmit={apply}>
    <div><label htmlFor="cob-desde">Emisión desde</label><input id="cob-desde" type="date" className="form-control" value={draft.desde} onChange={e=>setDraft({...draft,desde:e.target.value})}/></div>
    <div><label htmlFor="cob-hasta">Emisión hasta</label><input id="cob-hasta" type="date" className="form-control" value={draft.hasta} onChange={e=>setDraft({...draft,hasta:e.target.value})}/></div>
    <div className="commercial-search"><label htmlFor="cob-buscar">Buscar documentos</label><input id="cob-buscar" className="form-control" placeholder="Cliente, código de obra o folio" maxLength={100} value={draft.buscar} onChange={e=>setDraft({...draft,buscar:e.target.value})}/></div>
    <button type="submit" className="btn btn-fyag-primary">Aplicar filtros</button><button type="button" className="btn btn-outline-secondary" onClick={()=>{setDraft({desde:'',hasta:'',buscar:''});setInvalid('');setQuery(INITIAL);}}>Limpiar filtros</button>{invalid&&<p role="alert">{invalid}</p>}
  </form>
  <div className="portfolio-kpis">{[['Total documentado','total','blue'],['Total cobrado','cobrado','green'],['Saldo por cobrar','saldo','amber'],['Saldo vencido','vencido','red']].map(([label,key,tone])=><div key={key} className={'portfolio-kpi portfolio-'+tone}><span>{label}</span><strong>{fmt(s?.[key])}</strong><small>CLP · bruto</small></div>)}</div>
  <div className="commercial-insights"><Donut summary={s}/><section className="card-fyag commercial-followup"><h2>Clientes con deuda vencida</h2><div className={'commercial-followup-body '+(s?s.clientes_vencidos?'followup-pending':'followup-clear':'followup-unknown')}>
  {s&&<svg width="34" height="34" viewBox="0 0 16 16" fill="currentColor" aria-hidden="true"><path d="M8 15A7 7 0 1 1 8 1a7 7 0 0 1 0 14m0 1A8 8 0 1 0 8 0a8 8 0 0 0 0 16"/>{s.clientes_vencidos?<path d="M7.1 4.995a.9.9 0 1 1 1.8 0l-.35 3.507a.55.55 0 0 1-1.1 0zM8 10a1 1 0 1 0 0 2 1 1 0 0 0 0-2"/>:<path d="M10.97 4.97a.75.75 0 0 1 1.08 1.04l-4 5a.75.75 0 0 1-1.08.02L4.324 8.384a.75.75 0 1 1 1.06-1.06l2.094 2.093 3.47-4.425z"/>}</svg>}
  <strong className="commercial-followup-count">{s?.clientes_vencidos??'—'}</strong><div className="commercial-followup-label">{!s?'Sin datos disponibles':s.clientes_vencidos?'Requieren atención':'Sin clientes con deuda vencida'}</div>{s?.clientes_vencidos>0&&<button type="button" className="btn btn-outline-secondary btn-sm" onClick={()=>change({vista:'atencion'})}>Ver vencidos</button>}</div></section></div>
  <section className="card-fyag portfolio-list"><div className="portfolio-list-head"><div><h2>Seguimiento de cobranzas</h2><span>{data?data.count+' registros':'—'}</span></div></div>
  <div className="manager-work-tabs" role="group" aria-label="Vistas de cobranzas">{[['atencion','Requieren atención'],['vigentes','Vigentes'],['documentos','Documentos']].map(([key,label])=><button key={key} type="button" aria-pressed={query.vista===key} onClick={()=>change({vista:key})}>{label}</button>)}</div>
  <div className="portfolio-results">{data?.results.map(row=><article key={row.id} className={'portfolio-work '+(row.estado==='VENCIDA'?'portfolio-critica':'portfolio-normal')}><div className="portfolio-row-head"><div><h3>{row.cliente} <span className="cobranzas-estado" data-estado={row.estado}>{LABELS[row.estado]}</span></h3><p>{row.obra} · Folio {row.folio}</p></div><div className="manager-cob-amount"><small>{row.estado==='REVERTIDO'?'Total documento':'Saldo pendiente'}</small><strong>{fmt(row.estado==='REVERTIDO'?row.total:row.saldo)}</strong></div></div><div className="portfolio-context"><span>{row.estado==='VENCIDA'?row.dias_atraso+' '+(row.dias_atraso===1?'día':'días')+' de atraso':'Vencimiento: '+formatCivilDate(row.vencimiento)}</span><button type="button" className="btn btn-outline-secondary btn-sm" data-cobranza={row.id} onClick={()=>{pos.current=globalThis.window?.scrollY??0;trigger.current=row.id;setSelected(row);}}>Ver detalle</button></div></article>)}</div>
  {data&&!data.count&&<p className="commercial-empty">{query.vista==='atencion'?'No hay cobranzas vencidas para estos filtros.':'No hay documentos para estos filtros.'}</p>}
  {data&&(data.next||data.previous)&&<Pager data={data} page={page} setPage={p=>setQuery(prev=>({...prev,page:p}))} disabled={api.loading} label="Paginación de cobranzas"/>}
  {api.error?.status===404&&page!==1&&<button type="button" className="btn btn-outline-secondary" onClick={()=>change({})}>Volver a la primera página</button>}
  </section><p className="commercial-help">Documentos vigentes emitidos en el período y sus pagos registrados activos a la fecha de consulta. Los revertidos solo aparecen en Documentos.</p>
 </section>;
}
function GerenciaDocumento({row,onBack}){
 const api=useApi(),[detail,setDetail]=useState(null),[tab,setTab]=useState(row.estado==='REVERTIDO'?'history':'payments'),[page,setPage]=useState(1),[data,setData]=useState(null);
 const base='/api/finanzas/documentos/'+row.id+'/',path=tab==='payments'?base+'pagos/':tab==='history'?base+'historial/':base+'pagos/historial/';
 function loadDetail(){setDetail(null);return api.load('detail',base,v=>{const d=financialDocument(v);if(d.id!==row.id)throw Error('Documento inesperado.');setDetail(d);});}
 function loadTab(){setData(null);if(tab==='files')return Promise.resolve(true);return api.load('tab',path+'?page='+page,v=>{const result=financialPage(v,path,tab==='payments'?financialPayment:financialEvent);if(tab==='payments'&&result.results.some(p=>p.documento!==row.id))throw Error('Pago inesperado.');setData(result);});}
 useEffect(()=>{void loadDetail();},[row.id]);
 useEffect(()=>{void loadTab();return ()=>api.cancelRead('tab');},[tab,page]);
 return <section className="commercial-page manager-portfolio cobranzas-page manager-cobranzas"><div className="manager-work-toolbar"><button type="button" className="manager-budget-back" onClick={onBack}><svg width="18" height="18" viewBox="0 0 16 16" fill="currentColor" aria-hidden="true"><path fillRule="evenodd" d="M15 8a.5.5 0 0 0-.5-.5H2.707l3.647-3.646a.5.5 0 1 0-.708-.708l-4.5 4.5a.5.5 0 0 0 0 .708l4.5 4.5a.5.5 0 0 0 .708-.708L2.707 8.5H14.5A.5.5 0 0 0 15 8"/></svg>Volver al listado</button><Refresh disabled={api.loading} onClick={()=>void api.reconcile(async()=>{const r=await Promise.all([loadDetail(),loadTab()]);return r.every(Boolean);})}/></div>
 <Errors error={api.error}/>{api.loading&&<p role="status">Cargando documento…</p>}
 {detail&&<><div className="manager-work-heading"><div><h1>Folio {detail.folio_externo}</h1><p>{detail.origen.cliente.nombre_legal} · {detail.origen.codigo_obra}</p></div><span className="cobranzas-estado" data-estado={detail.cobranza?.estado||detail.estado}>{LABELS[detail.cobranza?.estado||detail.estado]}</span></div>
 <div className="portfolio-kpis">{[['Total documento',detail.monto_total],['Cobrado',detail.cobranza?.abonado],['Saldo pendiente',detail.cobranza?.saldo],['Vencimiento',null]].map(([label,value])=><div className="portfolio-kpi" key={label}><span>{label}</span><strong>{label==='Vencimiento'?formatCivilDate(detail.fecha_vencimiento):fmt(value)}</strong></div>)}</div>
 <section className="card-fyag manager-work-panel"><dl className="manager-facts"><div><dt>Emisión</dt><dd>{formatCivilDate(detail.fecha_emision)}</dd></div><div><dt>Neto CLP</dt><dd>{fmt(detail.monto_neto)}</dd></div><div><dt>Impuesto CLP</dt><dd>{fmt(detail.monto_impuesto)}</dd></div></dl>{detail.estado==='REVERTIDO'&&<p className="commercial-help">Documento revertido; no forma parte de los saldos vigentes.</p>}</section>
 <nav className="manager-work-tabs" aria-label="Secciones del documento">{[['payments','Pagos'],['history','Historial del documento'],['payhistory','Historial de pagos'],['files','Respaldos']].map(([key,label])=><button key={key} type="button" aria-pressed={tab===key} onClick={()=>{setData(null);setPage(1);setTab(key);}} disabled={tab===key}>{label}</button>)}</nav>
 {tab==='files'?<Adjuntos embedded type="RESPALDO_FACTURA" destinationId={row.id} canUpload={false} readOnly/>:<section className="card-fyag manager-work-panel">
 {data&&!data.count&&<p>No hay registros.</p>}
 {tab==='payments'?<ul className="finance-payments">{data?.results.map(p=><li key={p.id}><div><strong>{fmt(p.monto)}</strong><span>{formatCivilDate(p.fecha_pago)} · {({TRANSFERENCIA:'Transferencia',EFECTIVO:'Efectivo',TARJETA:'Tarjeta',OTRO:'Otro'})[p.medio]}</span></div><span className="cobranzas-estado" data-estado={p.activo?'PAGADA':'REVERTIDO'}>{p.activo?'Activo':'Anulado'}</span></li>)}</ul>:<ol className="finance-timeline">{data?.results.map(e=><li key={e.id} data-type={e.tipo}><strong>{EVENTS[e.tipo]||'Movimiento financiero'}</strong><div className="finance-event-meta">{new Date(e.creado_en).toLocaleString('es-CL',{timeZone:'America/Santiago'})}</div>{e.motivo&&<p>{e.motivo}</p>}</li>)}</ol>}
 {data&&(data.next||data.previous)&&<Pager data={data} page={page} setPage={setPage} disabled={api.loading} label={'Paginación de '+(tab==='payments'?'pagos':'historial')}/>}
 </section>}</>}
 </section>;
}
