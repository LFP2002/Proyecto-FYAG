import React,{useEffect,useLayoutEffect,useRef,useState} from 'react';
import {PageHead} from '../components/ui/index.js';
import {Errors,Pager} from '../comercial/ui.jsx';
import {useApi,readPage,strictObject,positiveInteger,decimalString} from './useApi.js';
import {civilRange,isoDate,todayInSantiago} from './dates.js';
import {formatCompactCLP as fmt,formatCivilDate as date} from '../utils/format.js';
import '../styles/pages/egresos-gerencia.css';

const BASE='/api/finanzas/egresos/',PATH=BASE+'supervision-gerencial/',FLOW='/api/finanzas/flujo-dinero/resumen/';
const CATS={MATERIALES:'Materiales',TRANSPORTE:'Transporte',SERVICIOS:'Servicios',ARRIENDO:'Arriendo',OTROS:'Otros'};
const MEANS={TRANSFERENCIA:'Transferencia',EFECTIVO:'Efectivo',TARJETA:'Tarjeta',OTRO:'Otro'};
const COLORS=['#3478DC','#20AC73','#ECA321','#8B75C9','#8492A6'];
const EMPTY={buscar:'',categoria:'',medio:''};
const month=()=>{const hasta=todayInSantiago();return {desde:hasta.slice(0,7)+'-01',hasta};};
const units=v=>BigInt(v.replace('.',''));
const pct=(v,total)=>total===0n?0:Number((v*10000n+total/2n)/total)/100;
const percent=n=>n.toLocaleString('es-CL',{maximumFractionDigits:1})+'%';
const count=n=>Number.isSafeInteger(n)&&n>=0;
const string=v=>typeof v==='string';
const invalid=()=>{throw Error('No se pudieron confirmar los datos de egresos.');};
const timestamp=v=>new Intl.DateTimeFormat('es-CL',{timeZone:'America/Santiago',dateStyle:'short',timeStyle:'short'}).format(new Date(v));
const code=id=>id===null?'Sin obra asociada':'OB-'+String(id).padStart(6,'0');
const stamp=v=>string(v)&&Number.isFinite(Date.parse(v));
function expense(d){
 strictObject(d,['id','naturaleza','moneda','monto','fecha_pago','categoria','concepto','beneficiario','medio','referencia_respaldo','observacion','obra','registrado_por','registrado_en','activo','anulado_por','anulado_en','motivo_anulacion','referencia_correccion']);
 if(!positiveInteger(d.id)||d.moneda!=='CLP'||d.naturaleza!=='REGISTRO_ADMINISTRATIVO_DINERO_PAGADO'||!decimalString(d.monto)||units(d.monto)<=0n||!isoDate(d.fecha_pago)||!Object.hasOwn(CATS,d.categoria)||!Object.hasOwn(MEANS,d.medio)||!['concepto','beneficiario','referencia_respaldo','observacion'].every(k=>string(d[k]))||(d.obra!==null&&!positiveInteger(d.obra))||!positiveInteger(d.registrado_por)||!stamp(d.registrado_en)||typeof d.activo!=='boolean'||(!d.activo&&(!positiveInteger(d.anulado_por)||!stamp(d.anulado_en)||!string(d.motivo_anulacion)||!string(d.referencia_correccion))))invalid();
 return d;
}
function summary(s,filters){
 if(!s||s.moneda!=='CLP'||s.desde!==filters.desde||s.hasta!==filters.hasta||!decimalString(s.total)||!decimalString(s.mayor)||!count(s.pagos)||!count(s.beneficiarios)||s.beneficiarios>s.pagos||units(s.mayor)>units(s.total)||!Array.isArray(s.categorias)||s.categorias.length!==5||!Array.isArray(s.ranking)||s.ranking.length!==Math.min(3,s.beneficiarios))invalid();
 if(!s.categorias.every(x=>Object.hasOwn(CATS,x.categoria)&&decimalString(x.monto))||new Set(s.categorias.map(x=>x.categoria)).size!==5||s.categorias.reduce((a,x)=>a+units(x.monto),0n)!==units(s.total))invalid();
 if(!s.ranking.every(x=>string(x.beneficiario)&&decimalString(x.monto)&&positiveInteger(x.pagos))||new Set(s.ranking.map(x=>x.beneficiario)).size!==s.ranking.length||s.ranking.reduce((a,x)=>a+units(x.monto),0n)>units(s.total)||s.ranking.reduce((a,x)=>a+x.pagos,0)>s.pagos)invalid();
 return s;
}
function flow(v,p){
 if(!v||v.moneda!=='CLP'||v.periodo?.desde!==p.desde||v.periodo?.hasta!==p.hasta||v.naturaleza!=='REGISTROS_ADMINISTRATIVOS_NO_CONCILIADOS'||!decimalString(v.ingresos_recibidos)||!decimalString(v.egresos_pagados)||!decimalString(v.flujo_neto_registrado,true)||units(v.ingresos_recibidos)-units(v.egresos_pagados)!==units(v.flujo_neto_registrado))invalid();
 return v;
}
function Refresh({onClick,disabled}){return <button type="button" className="btn btn-outline-secondary cobranzas-refresh" aria-label="Actualizar datos" onClick={onClick} disabled={disabled}><svg width="16" height="16" viewBox="0 0 16 16" fill="currentColor" aria-hidden="true"><path fillRule="evenodd" d="M8 3a5 5 0 1 1-4.546 2.914.5.5 0 0 0-.908-.417A6 6 0 1 0 8 2z"/><path d="M8 4.466V.534a.25.25 0 0 0-.41-.192L5.23 2.308a.25.25 0 0 0 0 .384l2.36 1.966A.25.25 0 0 0 8 4.466"/></svg>Actualizar</button>;}
function Kpis({items}){return <div className="portfolio-kpis">{items.map(([label,value,tone])=><div className={'portfolio-kpi portfolio-'+tone} key={label}><span>{label}</span><strong>{value}</strong></div>)}</div>;}
function Status({row}){return <span className="cobranzas-estado" data-estado={row.activo?'PAGADA':'REVERTIDO'}>{row.activo?'Activo':'Anulado'}</span>;}
function Columns({s}){
 const data=Object.keys(CATS).map((c,i)=>({c,i,m:s?.categorias.find(x=>x.categoria===c)?.monto}));
 const max=s?data.reduce((a,x)=>units(x.m)>a?units(x.m):a,0n):0n;
 const best=max>0n?data.find(x=>units(x.m)===max):null;
 // Escala común de 0 a 100% del total; los importes se conservan exactos en la leyenda.
 const top=units(s?.total??'0.00')||1n;
 return <section className="card-fyag manager-eg-chart"><h2>Distribución de egresos</h2>{!s?<p className="commercial-empty">Sin datos disponibles.</p>:<>
 <svg viewBox="0 0 480 210" className="manager-eg-columns" role="img" aria-label="Distribución de egresos por categoría">
 {Array.from({length:5},(_,i)=>{const y=170-i*36;return <g key={i}><line x1="43" x2="468" y1={y} y2={y} stroke="#d9e2ec" strokeDasharray={i?'3 3':undefined}/><text x="37" y={y+4} textAnchor="end" fill="#526578" fontSize="11">{i*25}%</text></g>;})}
 {data.map(({c,i,m})=>{const x=86+i*84,h=Number(units(m)*144000n/top)/1000;return <g key={c}><rect x={x-22} y={170-h} width="44" height={h} rx="3" fill={COLORS[i]}><title>{CATS[c]}: {fmt(m)}</title></rect><text x={x} y="190" textAnchor="middle" fill="#526578" fontSize="12">{CATS[c]}</text><text x={x} y={Math.max(15,162-h)} textAnchor="middle" fill="#16324D" fontSize="12" fontWeight="600">{percent(pct(units(m),units(s.total)))}</text></g>;})}
 </svg><div className="manager-eg-category-values">{data.map(({c,i,m})=><div key={c}><span><i style={{background:COLORS[i]}}/>{CATS[c]}</span><strong>{fmt(m)}</strong></div>)}</div>
 <div className="manager-eg-chart-foot"><span>Categoría con mayor gasto</span><strong>{best?CATS[best.c]+' · '+percent(pct(max,units(s.total))):'Sin egresos'}</strong></div></>}</section>;
}
function Ranking({s}){
 return <section className="card-fyag manager-eg-chart"><h2>Principales beneficiarios</h2>{!s?<p className="commercial-empty">Sin datos disponibles.</p>:!s.ranking.length?<p className="commercial-empty">No hay egresos activos en el período.</p>:<>
 <ol className="manager-eg-ranking">{s.ranking.map((r,i)=><li key={r.beneficiario}><span className="manager-eg-rank">{i+1}</span><div><strong>{r.beneficiario}</strong><small>{r.pagos} {r.pagos===1?'pago':'pagos'} · {percent(pct(units(r.monto),units(s.total)))} del total</small></div><strong>{fmt(r.monto)}</strong></li>)}</ol>
 <div className="manager-eg-chart-foot"><span>Concentración en los principales beneficiarios</span><strong>{percent(pct(s.ranking.reduce((a,r)=>a+units(r.monto),0n),units(s.total)))}</strong></div></>}</section>;
}
export default function GerenciaEgresos(){
 const api=useApi(),flowApi=useApi(),[query,setQuery]=useState(()=>({...month(),...EMPTY,vista:'activos',page:1})),[period,setPeriod]=useState(()=>month()),[draft,setDraft]=useState(EMPTY),[open,setOpen]=useState(false),[snap,setSnap]=useState(null),[selected,setSelected]=useState(null),[error,setError]=useState(''),[flowOpen,setFlowOpen]=useState(false),[flowSnap,setFlowSnap]=useState(null);
 const pos=useRef(null),trigger=useRef(null),{page,...filters}=query;
 const path=PATH+'?'+new URLSearchParams(Object.entries(query).filter(([,v])=>v!==''));
 const fp={desde:query.desde,hasta:query.hasta},flowPath=FLOW+'?'+new URLSearchParams(fp);
 function read(){setSnap(null);return api.load('list',path,v=>{const data=readPage(v,PATH,25,filters);data.results.forEach(expense);summary(data.resumen,filters);setSnap({path,data});});}
 function readFlow(){setFlowSnap(null);return flowApi.load('flow',flowPath,v=>setFlowSnap({path:flowPath,data:flow(v,fp)}));}
 useEffect(()=>{api.setError(null);void read();},[path]);
 useEffect(()=>{flowApi.setError(null);if(flowOpen)void readFlow();else{flowApi.cancelRead('flow');setFlowSnap(null);}},[flowPath,flowOpen]);
 useLayoutEffect(()=>{if(pos.current===null)return;if(selected)globalThis.window?.scrollTo?.({top:0,behavior:'instant'});else{globalThis.document?.querySelector?.('[data-egreso="'+trigger.current+'"]')?.focus({preventScroll:true});globalThis.window?.scrollTo?.({top:pos.current,behavior:'instant'});pos.current=null;trigger.current=null;}},[selected]);
 const data=snap?.path===path?snap.data:null,s=data?.resumen,f=flowSnap?.path===flowPath?flowSnap.data:null;
 const change=patch=>setQuery(prev=>({...prev,...patch,page:1}));
 function applyPeriod(e){e.preventDefault();if(!civilRange(period.desde,period.hasta)||period.hasta>todayInSantiago()){setError('Selecciona un período válido de hasta 366 días, sin fechas futuras.');return;}setError('');change(period);}
 function refresh(){void api.reconcile(read);if(flowOpen)void flowApi.reconcile(readFlow);}
 if(selected)return <Detail key={selected.id} row={selected} onBack={()=>setSelected(null)}/>;
 return <section className="commercial-page manager-portfolio cobranzas-page manager-cobranzas manager-egresos">
 <PageHead title="Egresos" sub="Supervisa los desembolsos de la empresa."><Refresh onClick={refresh} disabled={api.loading||flowApi.loading}/></PageHead>
 <Errors error={api.error}/>{api.loading&&<p role="status">Cargando egresos…</p>}
 <form className="card-fyag commercial-period manager-eg-period" onSubmit={applyPeriod}><div><label htmlFor="eg-from">Pagado desde</label><input id="eg-from" className="form-control" type="date" value={period.desde} onChange={e=>setPeriod({...period,desde:e.target.value})}/></div><div><label htmlFor="eg-to">Pagado hasta</label><input id="eg-to" className="form-control" type="date" value={period.hasta} onChange={e=>setPeriod({...period,hasta:e.target.value})}/></div><button type="submit" className="btn btn-fyag-primary">Aplicar período</button><button type="button" className="btn btn-outline-secondary" onClick={()=>{const p=month();setPeriod(p);setError('');change(p);}}>Este mes</button>{error&&<p role="alert">{error}</p>}</form>
 <Kpis items={[[ 'Total egresos pagados',fmt(s?.total),'red'],['Pagos realizados',s?.pagos??'—','blue'],['Beneficiarios',s?.beneficiarios??'—','blue'],['Mayor egreso',fmt(s?.mayor),'amber']]}/>
 <div className="commercial-insights"><Columns s={s}/><Ranking s={s}/></div>
 <section className="card-fyag manager-eg-flow"><div className="portfolio-list-head"><div><h2>Flujo de dinero registrado</h2><span>Ingresos y egresos del período</span></div><button type="button" className="btn btn-outline-secondary btn-sm" aria-expanded={flowOpen} aria-controls="eg-flow" onClick={()=>setFlowOpen(x=>!x)}>{flowOpen?'Ocultar flujo':'Ver flujo'}</button></div>
 {flowOpen&&<div id="eg-flow"><Errors error={flowApi.error}/>{flowApi.loading&&<p role="status">Cargando flujo…</p>}<Kpis items={[[ 'Ingresos recibidos',fmt(f?.ingresos_recibidos),'green'],['Egresos pagados',fmt(f?.egresos_pagados),'red'],['Flujo neto registrado',fmt(f?.flujo_neto_registrado),f?units(f.flujo_neto_registrado)<0n?'red':'green':'gray']]}/><p className="commercial-help">Corresponde a cobros y pagos registrados, no al saldo bancario.</p></div>}</section>
 <section className="card-fyag portfolio-list"><div className="portfolio-list-head"><div><h2>Registro de egresos</h2><span>{data?data.count+' registros':'—'}</span></div><button type="button" className="btn btn-outline-secondary btn-sm manager-cob-filter-toggle" aria-controls="eg-filters" aria-expanded={open} onClick={()=>setOpen(x=>!x)}><svg width="16" height="16" viewBox="0 0 16 16" fill="currentColor" aria-hidden="true"><path d="M6 11.5a.5.5 0 0 1 .5-.5h3a.5.5 0 0 1 0 1h-3a.5.5 0 0 1-.5-.5m-2-4a.5.5 0 0 1 .5-.5h7a.5.5 0 0 1 0 1h-7a.5.5 0 0 1-.5-.5m-2-4a.5.5 0 0 1 .5-.5h11a.5.5 0 0 1 0 1h-11a.5.5 0 0 1-.5-.5"/></svg>Filtros</button></div>
 <form id="eg-filters" hidden={!open} className="commercial-period manager-cob-filter-form" onSubmit={e=>{e.preventDefault();change({...draft,buscar:draft.buscar.trim()});}}><div className="commercial-search"><label htmlFor="eg-search">Buscar</label><input id="eg-search" className="form-control" maxLength={100} placeholder="Concepto, beneficiario o código de obra" value={draft.buscar} onChange={e=>setDraft({...draft,buscar:e.target.value})}/></div>{[['categoria','Categoría',CATS],['medio','Medio de pago',MEANS]].map(([k,label,options])=><div key={k}><label htmlFor={'eg-'+k}>{label}</label><select id={'eg-'+k} className="form-select" value={draft[k]} onChange={e=>setDraft({...draft,[k]:e.target.value})}><option value="">Todos</option>{Object.entries(options).map(([v,l])=><option key={v} value={v}>{l}</option>)}</select></div>)}<button type="submit" className="btn btn-fyag-primary">Aplicar filtros</button><button type="button" className="btn btn-outline-secondary" onClick={()=>{setDraft(EMPTY);change(EMPTY);}}>Limpiar filtros</button></form>
 {(query.buscar||query.categoria||query.medio)&&<p className="commercial-help">{[query.buscar&&'Búsqueda: '+query.buscar,CATS[query.categoria],MEANS[query.medio]].filter(Boolean).join(' · ')}</p>}
 <div className="manager-work-tabs" role="group" aria-label="Vistas de egresos">{[['activos','Activos'],['anulados','Anulados'],['todos','Todos']].map(([k,label])=><button key={k} type="button" aria-pressed={query.vista===k} onClick={()=>change({vista:k})}>{label}</button>)}</div>
 {data?.results.length>0&&<table className="manager-cob-table manager-eg-table" aria-label="Registro de egresos"><thead><tr><th scope="col">Concepto / Beneficiario</th><th scope="col">Fecha / Categoría</th><th scope="col" className="manager-cob-num">Monto CLP</th><th scope="col"><span className="visually-hidden">Detalle</span></th></tr></thead><tbody>{data.results.map(r=><tr key={r.id}><td><div className="manager-cob-client"><strong>{r.concepto}</strong><Status row={r}/></div><div className="manager-cob-meta">{r.beneficiario}</div></td><td><strong>{date(r.fecha_pago)}</strong><div className="manager-cob-meta">{CATS[r.categoria]}</div></td><td className="manager-cob-num"><strong>{fmt(r.monto)}</strong></td><td className="manager-cob-action"><button type="button" data-egreso={r.id} aria-label={'Ver detalle del egreso '+r.id} className="manager-cob-detail" onClick={()=>{pos.current=globalThis.window?.scrollY??0;trigger.current=r.id;setSelected(r);}}><svg width="16" height="16" viewBox="0 0 16 16" fill="currentColor" aria-hidden="true"><path fillRule="evenodd" d="M4.646 1.646a.5.5 0 0 1 .708 0l6 6a.5.5 0 0 1 0 .708l-6 6a.5.5 0 0 1-.708-.708L10.293 8 4.646 2.354a.5.5 0 0 1 0-.708"/></svg></button></td></tr>)}</tbody></table>}
 {data&&!data.count&&<p className="commercial-empty">No hay egresos para estos filtros.</p>}{data&&(data.next||data.previous)&&<Pager data={data} page={page} setPage={p=>setQuery(prev=>({...prev,page:p}))} disabled={api.loading} label="Paginación de egresos"/>}
 {api.error?.status===404&&page>1&&<button type="button" className="btn btn-outline-secondary" onClick={()=>change({})}>Volver a la primera página</button>}</section>
 <p className="commercial-help">Los indicadores incluyen únicamente egresos activos del período. Los filtros de búsqueda se aplican al listado.</p>
 </section>;
}
function Detail({row,onBack}){
 const api=useApi(),[d,setD]=useState(null),[tab,setTab]=useState('info'),[page,setPage]=useState(1),[history,setHistory]=useState(null);
 const path=BASE+row.id+'/',hp=path+'historial/';
 function read(){setD(null);return api.load('detail',path,v=>{const data=expense(v);if(data.id!==row.id)invalid();setD(data);});}
 function readHistory(){setHistory(null);return api.load('history',hp+'?page='+page,v=>{const data=readPage(v,hp);for(const e of data.results){if(!positiveInteger(e.id)||e.egreso!==row.id||!positiveInteger(e.actor)||!['CREACION','ANULACION'].includes(e.tipo)||!string(e.motivo)||!stamp(e.creado_en))invalid();}setHistory(data);});}
 useEffect(()=>{void read();},[row.id]);
 useEffect(()=>{if(tab==='history')void readHistory();return ()=>api.cancelRead('history');},[tab,page]);
 return <section className="commercial-page manager-portfolio cobranzas-page manager-cobranzas manager-egresos"><div className="manager-work-toolbar"><button type="button" className="manager-budget-back" onClick={onBack}><svg width="18" height="18" viewBox="0 0 16 16" fill="currentColor" aria-hidden="true"><path fillRule="evenodd" d="M15 8a.5.5 0 0 0-.5-.5H2.707l3.647-3.646a.5.5 0 1 0-.708-.708l-4.5 4.5a.5.5 0 0 0 0 .708l4.5 4.5a.5.5 0 0 0 .708-.708L2.707 8.5H14.5A.5.5 0 0 0 15 8"/></svg>Volver al listado</button><Refresh disabled={api.loading} onClick={()=>void api.reconcile(async()=>{const result=await Promise.all([read(),tab==='history'?readHistory():true]);return result.every(Boolean);})}/></div>
 <Errors error={api.error}/>{api.loading&&<p role="status">Cargando egreso…</p>}
 {d&&<><div className="manager-work-heading"><div><div className="manager-cob-title"><h1>Egreso #{d.id}</h1><Status row={d}/></div><h2 className="manager-eg-concept">{d.concepto}</h2><p>{d.beneficiario}</p></div></div>
 <Kpis items={[[d.activo?'Monto pagado':'Monto anulado',fmt(d.monto),d.activo?'red':'gray'],['Fecha de pago',date(d.fecha_pago),'blue'],['Categoría',CATS[d.categoria],'blue'],['Medio de pago',MEANS[d.medio],'blue']]}/>
 <nav className="manager-work-tabs" aria-label="Secciones del egreso">{[['info','Información general'],['history','Historial']].map(([k,label])=><button key={k} type="button" aria-pressed={tab===k} onClick={()=>{setPage(1);setHistory(null);setTab(k);}} disabled={tab===k}>{label}</button>)}</nav>
 {tab==='info'?<section className="card-fyag manager-work-panel"><h2>Información del egreso</h2><dl className="manager-facts">{[['Referencia de respaldo',d.referencia_respaldo],['Obra asociada',code(d.obra)],['Registrado por','Usuario #'+d.registrado_por],['Fecha de registro',timestamp(d.registrado_en)],...(d.observacion?[['Observación',d.observacion]]:[]),...(!d.activo?[['Anulado por','Usuario #'+d.anulado_por],['Fecha de anulación',timestamp(d.anulado_en)],['Motivo de anulación',d.motivo_anulacion],['Referencia de corrección',d.referencia_correccion]]:[])].map(([label,value])=><div key={label}><dt>{label}</dt><dd>{value}</dd></div>)}</dl></section>:<section className="card-fyag manager-work-panel"><div className="finance-history-head"><h2>Actividad del egreso</h2><span>{history?history.count+' registros':'—'}</span></div><ol className="finance-timeline">{history?.results.map(e=><li key={e.id} data-type={e.tipo==='ANULACION'?'PAGO_ANULADO':'CREACION'}><strong>{e.tipo==='CREACION'?'Egreso registrado':'Egreso anulado'}</strong><div className="finance-event-meta"><time dateTime={e.creado_en}>{timestamp(e.creado_en)}</time> · Usuario #{e.actor}</div>{e.motivo&&<div className="finance-event-reason"><strong>Motivo</strong><p>{e.motivo}</p></div>}</li>)}</ol>{history&&!history.count&&<p className="commercial-empty">No hay registros.</p>}{history&&(history.next||history.previous)&&<Pager data={history} page={page} setPage={setPage} disabled={api.loading} label="Paginación del historial"/>}</section>}</>}
 </section>;
}
