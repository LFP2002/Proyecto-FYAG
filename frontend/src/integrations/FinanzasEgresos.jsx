import React,{useEffect,useRef,useState} from 'react';
import {PageHead} from '../components/ui/index.js';
import {useApp} from '../context/AppContext.jsx';
import {Errors,Pager} from '../comercial/ui.jsx';
import {useApi,readPage,strictObject,positiveInteger,decimalString} from './useApi.js';
import {civilRange,isoDate,todayInSantiago} from './dates.js';
import {expense,flow} from './GerenciaEgresos.jsx';
import {formatCompactCLP as money,formatCivilDate as date} from '../utils/format.js';
import TecIcon from '../obras/TecIcon.jsx';
import '../styles/pages/egresos-finanzas.css';

const BASE='/api/finanzas/egresos/',WORK='/api/finanzas/obras-resumen/',FLOW='/api/finanzas/flujo-dinero/resumen/';
const CATS={MATERIALES:'Materiales',TRANSPORTE:'Transporte',SERVICIOS:'Servicios',ARRIENDO:'Arriendo',OTROS:'Otros'};
const MEANS={TRANSFERENCIA:'Transferencia',EFECTIVO:'Efectivo',TARJETA:'Tarjeta',OTRO:'Otro'};
const FILTERS={buscar:'',categoria:'',medio:'',activo:'',desde:'',hasta:''};
const EMPTY={monto:'',fecha_pago:'',categoria:'MATERIALES',concepto:'',beneficiario:'',medio:'TRANSFERENCIA',referencia_respaldo:'',observacion:'',obra:null};
const query=(path,params)=>path+'?'+new URLSearchParams(Object.entries(params).filter(([,v])=>v!==''&&v!==null));
const code=id=>id===null?'Sin obra asociada':'OB-'+String(id).padStart(6,'0');
const stamp=v=>new Intl.DateTimeFormat('es-CL',{timeZone:'America/Santiago',dateStyle:'short',timeStyle:'short'}).format(new Date(v));
const month=()=>{const hasta=todayInSantiago();return {desde:hasta.slice(0,7)+'-01',hasta};};
const bad=()=>{throw Error('El servidor devolvió datos de egresos inesperados.');};
const validMoney=v=>/^(?:0|[1-9][0-9]{0,35})(?:\.[0-9]{1,2})?$/.test(v)&&BigInt(v.replace('.',''))>0n;
function Status({row}){return <span className="cobranzas-estado" data-estado={row.activo?'PAGADA':'REVERTIDO'}>{row.activo?'Activo':'Anulado'}</span>;}
function Btn({icon,children,...props}){return <button type="button" className="btn btn-outline-secondary" {...props}>{icon&&<TecIcon name={icon}/>} {children}</button>;}
function Metric({label,value}){return <div className="portfolio-kpi"><span>{label}</span><strong>{value}</strong></div>;}
 
// Los importes permanecen como centavos enteros; solo las coordenadas SVG se aproximan.
const flowUnits=v=>{const negative=v.startsWith('-');const [whole,fraction='']= (negative?v.slice(1):v).split('.');return BigInt(whole+fraction.padEnd(2,'0'))*(negative?-1n:1n);};
const flowTick=v=>money((v<0n?'-':'')+(String(v<0n?-v:v).padStart(3,'0').slice(0,-2))+'.'+String(v<0n?-v:v).padStart(3,'0').slice(-2));
const axisTick=v=>{
  const a=v<0n?-v:v;
  for(const [scale,suffix] of [[100000000000000n,' bill.'],[100000000n,' M'],[100000n,' mil']]){
    if(a>=scale){
      const tenths=a*10n/scale;
      if(tenths>999999n)return (v<0n?'-':'')+'
function Fact({label,value}){return <div><dt>{label}</dt><dd>{value||'—'}</dd></div>;}
function Choice({label,value,onChange,options,all=false,disabled=false,id}){return <label className="form-label" htmlFor={id}>{label}<select id={id} className="form-select" value={value} disabled={disabled} onChange={e=>onChange(e.target.value)}>{all&&<option value="">Todos</option>}{Object.entries(options).map(([k,l])=><option key={k} value={k}>{l}</option>)}</select></label>;}
function WorkPicker({value,onChange,disabled}){
 const api=useApi(),[open,setOpen]=useState(false),[draft,setDraft]=useState(''),[search,setSearch]=useState(''),[page,setPage]=useState(1),[data,setData]=useState(null),[name,setName]=useState('');
 const params={buscar:search};
 const path=query(WORK,{page,...params});
 useEffect(()=>{if(!open)return;setData(null);api.setError(null);void api.load('works',path,v=>{const p=readPage(v,WORK,25,params);for(const r of p.results)if(!positiveInteger(r.id)||typeof r.codigo!=='string'||typeof r.cliente_nombre!=='string')bad();setData(p);});return ()=>api.cancelRead('works');},[open,path]);
 return <div className="eg-work"><label className="form-label">Obra asociada (opcional)</label><div className="eg-toolbar"><span>{value?name||code(value):'Sin obra asociada'}</span><Btn disabled={disabled} onClick={()=>setOpen(v=>!v)} aria-expanded={open}>{open?'Cerrar búsqueda':value?'Cambiar obra':'Seleccionar obra'}</Btn>{value&&<Btn disabled={disabled} onClick={()=>{onChange(null);setName('');setOpen(false);}}>Quitar</Btn>}</div>
 {open&&<div className="eg-work-picker"><div className="eg-toolbar"><input className="form-control" aria-label="Buscar obra" placeholder="Código de obra o cliente" maxLength={150} value={draft} disabled={disabled} onChange={e=>setDraft(e.target.value)} onKeyDown={e=>{if(e.key==='Enter'){e.preventDefault();setPage(1);setSearch(draft.trim());}}}/><Btn disabled={disabled||api.loading} onClick={()=>{setPage(1);setSearch(draft.trim());}}>Buscar</Btn></div><Errors error={api.error}/>{api.loading&&<p role="status">Cargando obras…</p>}
 <div className="eg-work-results">{data?.results.map(r=><div key={r.id}><span><strong>{r.codigo}</strong> · {r.cliente_nombre}</span><Btn disabled={disabled} onClick={()=>{onChange(r.id);setName(r.codigo+' · '+r.cliente_nombre);setOpen(false);}}>Seleccionar</Btn></div>)}</div>{data&&!data.count&&<p>No se encontraron obras.</p>}{data&&(data.next||data.previous)&&<Pager data={data} page={page} setPage={setPage} disabled={disabled||api.loading} label="Paginación de obras"/>}</div>}
 </div>;
}
export default function FinanzasEgresos(){
 const api=useApi(),app=useApp(),inFlight=useRef(false);
 const [view,setView]=useState('list'),[draft,setDraft]=useState(FILTERS),[filters,setFilters]=useState(FILTERS),[expanded,setExpanded]=useState(false),[page,setPage]=useState(1),[snapshot,setSnapshot]=useState(null);
 const [form,setForm]=useState(null),[selected,setSelected]=useState(null),[detail,setDetail]=useState(null),[history,setHistory]=useState(null),[historyPage,setHistoryPage]=useState(1),[correction,setCorrection]=useState(null),[message,setMessage]=useState('');
 const [period,setPeriod]=useState(month),[appliedPeriod,setAppliedPeriod]=useState(null),[flowData,setFlowData]=useState(null);
 const listFilters={...filters,resumen:'true'},path=query(BASE,{page,...listFilters});
 const data=snapshot?.path===path?snapshot.data:null;
 const blocked=api.busy||api.locked,disabled=blocked||api.loading;
 const nav=app?.setNavigationBlocked;
 useEffect(()=>{nav?.(blocked);return ()=>nav?.(false);},[blocked,nav]);
 function readList(){setSnapshot(null);return api.load('list',path,v=>{
   const p=readPage(v,BASE,25,listFilters);p.results.forEach(expense);
   const s=strictObject(p.resumen,['moneda','total','pagos']);
   if(s.moneda!=='CLP'||!decimalString(s.total)||!Number.isSafeInteger(s.pagos)||s.pagos<0||s.pagos>p.count)bad();
   setSnapshot({path,data:p});
 });}
 function readDetail(id=selected){return api.load('detail',BASE+id+'/',v=>{const d=expense(v);if(d.id!==id)bad();setDetail(d);if(!d.activo)setCorrection(null);});}
 function readHistory(id=selected,p=historyPage){setHistory(null);return api.load('history',BASE+id+'/historial/?page='+p,v=>{const h=readPage(v,BASE+id+'/historial/');for(const e of h.results)if(!positiveInteger(e.id)||e.egreso!==id||!positiveInteger(e.actor)||!['CREACION','ANULACION'].includes(e.tipo)||typeof e.motivo!=='string'||!Number.isFinite(Date.parse(e.creado_en)))bad();setHistory(h);});}
 function readFlow(p=appliedPeriod){if(!p)return Promise.resolve(true);setFlowData(null);return api.load('flow',query(FLOW,p),v=>setFlowData(flow(v,p)));}
 useEffect(()=>{api.setError(null);setMessage('');if(view==='list')void readList();return ()=>api.cancelRead('list');},[view,path]);
 useEffect(()=>{if(view==='detail'&&selected){void readDetail();void readHistory();}return ()=>{api.cancelRead('detail');api.cancelRead('history');};},[view,selected,historyPage]);
 useEffect(()=>{if(view==='flow'&&appliedPeriod)void readFlow();return ()=>api.cancelRead('flow');},[view,appliedPeriod]);
 function navigate(next){if(blocked)return;api.setError(null);setMessage('');setCorrection(null);setView(next);}
 function inspect(r){setSelected(r.id);setDetail(null);setHistory(null);setHistoryPage(1);navigate('detail');}
 function begin(){setForm({...EMPTY,clave:crypto.randomUUID()});navigate('create');}
 function apply(e){e.preventDefault();if((draft.desde||draft.hasta)&&!civilRange(draft.desde,draft.hasta)){setMessage('Selecciona ambas fechas y un período de hasta 366 días.');return;}setMessage('');setPage(1);setFilters({...draft,buscar:draft.buscar.trim()});}
 async function refresh(){setMessage('');await api.reconcile(async()=>{if(view==='list')return readList();if(view==='detail'){const r=await Promise.all([readDetail(),readHistory()]);return r.every(Boolean);}if(view==='flow')return readFlow();return false;});}
 const change=(k,v)=>setForm(p=>({...p,[k]:v}));
 async function save(e,retry=false){
   e?.preventDefault();if(inFlight.current||api.busy||(!retry&&api.locked)||!form)return;
   const {clave,...values}=form;
   const body={...values,monto:values.monto.trim(),concepto:values.concepto.trim(),beneficiario:values.beneficiario.trim(),referencia_respaldo:values.referencia_respaldo.trim(),observacion:values.observacion.trim()};
   if(!validMoney(body.monto)||!isoDate(body.fecha_pago)||body.fecha_pago>todayInSantiago()||!body.concepto||!body.beneficiario||!body.referencia_respaldo){setMessage('Completa los datos obligatorios con un monto positivo y una fecha válida.');return;}
   inFlight.current=true;setMessage('');
   try{
     // Un resultado incierto solo admite repetir el mismo payload con la misma UUID.
     if(retry&&!await api.reconcile(()=>Promise.resolve(true)))return;
     await api.write(BASE,'POST',body,async v=>{
       const created=expense(v);if(!created.activo)bad();
       let current;
       await api.requiredLoad('confirm-create',BASE+created.id+'/',x=>{current=expense(x);if(current.id!==created.id)bad();});
       setDetail(current);setSelected(current.id);setHistoryPage(1);setHistory(null);setForm(null);setView('detail');
     },{headers:{'Idempotency-Key':clave}});
   }finally{inFlight.current=false;}
 }
 async function annul(e){
   e.preventDefault();if(inFlight.current||disabled||!detail?.activo||!correction?.motivo.trim()||!correction?.referencia_correccion.trim())return;
   if(!globalThis.confirm('¿Anular este registro de egreso? Esta acción no devuelve dinero.'))return;
   inFlight.current=true;setMessage('');
   try{await api.write(BASE+selected+'/anular/','POST',{motivo:correction.motivo.trim(),referencia_correccion:correction.referencia_correccion.trim()},async v=>{
     const d=expense(v);if(d.id!==selected||d.activo)bad();
     if(!(await Promise.all([readDetail(),readHistory()])).every(Boolean))throw Error('No se pudo confirmar el estado. Actualiza antes de continuar.');
     setCorrection(null);
   });}finally{inFlight.current=false;}
 }
 const notice=<><Errors error={api.error}/>{message&&<p role="alert" className="alert alert-warning">{message}</p>}{api.loading&&<p role="status">Cargando datos…</p>}</>;
 return <section className="commercial-page manager-portfolio cobranzas-page manager-cobranzas manager-egresos finance-egresos">
 <PageHead title="Egresos" sub="Consulta y registra pagos ya realizados. No representa cuentas por pagar ni saldo bancario.">{view!=='create'&&<Btn icon="refresh" disabled={api.busy||api.loading} onClick={()=>void refresh()}>Actualizar</Btn>}{view==='list'&&<button type="button" className="btn btn-fyag-primary" disabled={disabled} onClick={begin}>+ Registrar egreso</button>}</PageHead>
 {(view==='list'||view==='flow')&&<nav className="manager-work-tabs" aria-label="Secciones de egresos"><button type="button" aria-pressed={view==='list'} onClick={()=>navigate('list')}>Registro de egresos</button><button type="button" aria-pressed={view==='flow'} onClick={()=>navigate('flow')}>Flujo de dinero</button></nav>}
 {notice}
 {view==='list'&&<>
 <div className="portfolio-kpis eg-kpis"><Metric label="Total de egresos activos" value={money(data?.resumen.total)}/><Metric label="Pagos activos registrados" value={data?.resumen.pagos??'—'}/></div>
 <p className="commercial-help">Indicadores del conjunto filtrado, excluyen registros anulados.</p>
 <section className="card-fyag portfolio-list eg-list"><div className="portfolio-list-head"><div><h2>Registro de egresos</h2><span>{data?data.count+' registros · CLP':'—'}</span></div><Btn icon="filter" aria-expanded={expanded} onClick={()=>setExpanded(v=>!v)}>Filtros</Btn></div>
 <form className="eg-filters" onSubmit={apply} aria-label="Filtros de egresos"><div className="eg-toolbar"><label className="form-label eg-search">Buscar egreso<input className="form-control" maxLength={100} value={draft.buscar} placeholder="Concepto, beneficiario o código de obra" onChange={e=>setDraft({...draft,buscar:e.target.value})}/></label><Choice label="Estado" value={draft.activo} onChange={v=>setDraft({...draft,activo:v})} options={{true:'Activos',false:'Anulados'}} all/><button className="btn btn-fyag-primary" disabled={disabled}>Buscar</button>{(Object.values(filters).some(Boolean)||Object.values(draft).some(Boolean))&&<Btn disabled={disabled} onClick={()=>{setDraft(FILTERS);setFilters(FILTERS);setPage(1);setMessage('');}}>Limpiar filtros</Btn>}</div>
 {expanded&&<div className="eg-fields"><Choice label="Categoría" value={draft.categoria} onChange={v=>setDraft({...draft,categoria:v})} options={CATS} all/><Choice label="Medio de pago" value={draft.medio} onChange={v=>setDraft({...draft,medio:v})} options={MEANS} all/>{[['desde','Pagado desde'],['hasta','Pagado hasta']].map(([k,l])=><label key={k} className="form-label">{l}<input className="form-control" type="date" value={draft[k]} onChange={e=>setDraft({...draft,[k]:e.target.value})}/></label>)}</div>}</form>
 {data&&<><div className="table-responsive" role="region" aria-label="Listado de egresos" tabIndex={0}><table className="table commercial-table eg-table"><thead><tr>{['Concepto / Beneficiario','Fecha de pago','Categoría','Medio de pago','Monto CLP','Estado','Detalle'].map(l=><th scope="col" key={l}>{l}</th>)}</tr></thead><tbody>{data.results.map(r=><tr key={r.id}><td><strong>{r.concepto}</strong><span className="eg-client">{r.beneficiario}</span></td><td>{date(r.fecha_pago)}</td><td>{CATS[r.categoria]}</td><td>{MEANS[r.medio]}</td><td>{money(r.monto)}</td><td><Status row={r}/></td><td><Btn disabled={disabled} onClick={()=>inspect(r)}>Ver detalle</Btn></td></tr>)}</tbody></table></div>{!data.count&&<p className="commercial-empty">No se encontraron egresos.</p>}{(data.next||data.previous)&&<Pager data={data} page={page} setPage={setPage} disabled={disabled} label="Paginación de egresos"/>}</>}{api.error?.status===404&&page>1&&<Btn onClick={()=>setPage(1)}>Volver a primera página</Btn>}</section></>}
 {view==='flow'&&<section className="card-fyag eg-panel"><h2>Flujo de dinero registrado</h2><p className="commercial-help">Ingresos recibidos menos egresos activos del período. No es saldo bancario ni conciliación.</p><form className="eg-toolbar" onSubmit={e=>{e.preventDefault();if(!civilRange(period.desde,period.hasta)){setMessage('Selecciona un período válido de hasta 366 días.');return;}setMessage('');setAppliedPeriod({...period});}}>{[['desde','Desde'],['hasta','Hasta']].map(([k,l])=><label className="form-label" key={k}>{l}<input className="form-control" type="date" value={period[k]} onChange={e=>setPeriod({...period,[k]:e.target.value})}/></label>)}<button className="btn btn-fyag-primary" disabled={disabled}>Consultar</button></form>{!appliedPeriod&&<div className="eg-flow-empty" role="status"><TecIcon name="calendar"/><strong>Selecciona un período</strong><p>Indica las fechas y pulsa Consultar para visualizar los ingresos y egresos registrados.</p></div>}{flowData&&flowData.periodo.desde===appliedPeriod?.desde&&flowData.periodo.hasta===appliedPeriod?.hasta&&<><p className="commercial-help">{date(appliedPeriod.desde)} – {date(appliedPeriod.hasta)} · CLP</p><div className="portfolio-kpis eg-flow-kpis"><Metric label="Ingresos recibidos" value={money(flowData.ingresos_recibidos)}/><Metric label="Egresos pagados" value={money(flowData.egresos_pagados)}/><Metric label="Flujo neto registrado" value={money(flowData.flujo_neto_registrado)}/></div><FlowCharts data={flowData}/></>}</section>}
 {view==='create'&&form&&<><Btn className="btn btn-outline-secondary eg-back" icon="back" disabled={blocked} onClick={()=>{setForm(null);navigate('list');}}>Volver a egresos</Btn><section className="card-fyag eg-panel"><h2>Registrar egreso</h2><p className="commercial-help">Ingresa los datos de un pago ya realizado.</p><form onSubmit={save} aria-label="Registro de egreso">
 <h3>Datos del pago</h3><div className="eg-fields">
 {[[ 'monto','Monto pagado (CLP)'],['fecha_pago','Fecha de pago']].map(([k,l])=><label className="form-label" key={k}>{l}<input className="form-control" required type={k==='fecha_pago'?'date':'text'} inputMode={k==='monto'?'decimal':undefined} max={k==='fecha_pago'?todayInSantiago():undefined} placeholder={k==='monto'?'Ej.: 150000':undefined} value={form[k]} disabled={blocked} onChange={e=>change(k,e.target.value)}/></label>)}
 <Choice label="Categoría" value={form.categoria} onChange={v=>change('categoria',v)} options={CATS} disabled={blocked}/><Choice label="Medio de pago" value={form.medio} onChange={v=>change('medio',v)} options={MEANS} disabled={blocked}/>
 {[[ 'concepto','Concepto'],['beneficiario','Beneficiario']].map(([k,l])=><label className="form-label eg-half" key={k}>{l}<input className="form-control" required maxLength={200} value={form[k]} disabled={blocked} onChange={e=>change(k,e.target.value)}/></label>)}</div>
 <h3 className="eg-section-title">Información complementaria</h3><div className="eg-fields"><div className="eg-half"><WorkPicker value={form.obra} onChange={v=>change('obra',v)} disabled={blocked}/></div><label className="form-label eg-half">Referencia del respaldo<input className="form-control" placeholder="Número de comprobante" maxLength={500} required value={form.referencia_respaldo} disabled={blocked} onChange={e=>change('referencia_respaldo',e.target.value)}/></label><label className="form-label eg-full">Observaciones<textarea className="form-control" rows={2} maxLength={2000} value={form.observacion} disabled={blocked} onChange={e=>change('observacion',e.target.value)}/></label></div>
 <div className="eg-footer">{api.locked?<><p role="alert">El registro no pudo confirmarse. Reintenta la misma solicitud sin modificar sus datos para evitar duplicados.</p><button type="button" className="btn btn-fyag-primary" disabled={api.busy} onClick={()=>void save(null,true)}>Confirmar registro pendiente</button></>:<><Btn disabled={api.busy} onClick={()=>{setForm(null);navigate('list');}}>Cancelar</Btn><button className="btn btn-fyag-primary" disabled={disabled}>Registrar egreso</button></>}</div></form></section></>}
 {view==='detail'&&<><Btn className="btn btn-outline-secondary eg-back" icon="back" disabled={blocked} onClick={()=>navigate('list')}>Volver a egresos</Btn>{detail&&<>
 <header className="eg-detail-heading"><div><h2>{detail.concepto}</h2><p>{detail.beneficiario}</p></div><Status row={detail}/></header>
 <div className="portfolio-kpis eg-detail-kpis"><Metric label={detail.activo?'Monto pagado · CLP':'Monto anulado · CLP'} value={money(detail.monto)}/><Metric label="Fecha de pago" value={date(detail.fecha_pago)}/><Metric label="Categoría" value={CATS[detail.categoria]}/><Metric label="Medio de pago" value={MEANS[detail.medio]}/></div>
 <section className="card-fyag eg-panel"><h2>Información del egreso</h2><dl className="eg-facts"><Fact label="Beneficiario" value={detail.beneficiario}/><Fact label="Obra asociada" value={code(detail.obra)}/><Fact label="Referencia del respaldo" value={detail.referencia_respaldo}/><Fact label="Registrado" value={stamp(detail.registrado_en)}/><Fact label="Registrado por" value={'Usuario #'+detail.registrado_por}/><Fact label="Observaciones" value={detail.observacion}/>{!detail.activo&&<><Fact label="Fecha de anulación" value={stamp(detail.anulado_en)}/><Fact label="Motivo de anulación" value={detail.motivo_anulacion}/><Fact label="Referencia de corrección" value={detail.referencia_correccion}/></>}</dl>
 {detail.activo&&!correction&&!api.locked&&<div className="eg-footer"><button type="button" className="btn btn-outline-danger" disabled={disabled} onClick={()=>setCorrection({motivo:'',referencia_correccion:''})}>Anular egreso</button></div>}
 {detail.activo&&correction&&<form className="eg-annul" aria-label="Anular egreso" onSubmit={annul}><h3>Anular registro</h3><p className="commercial-help">No representa una devolución de dinero. El registro permanecerá en el historial.</p><div className="eg-fields"><label className="form-label eg-half">Motivo<textarea className="form-control" required rows={2} maxLength={2000} disabled={blocked} value={correction.motivo} onChange={e=>setCorrection({...correction,motivo:e.target.value})}/></label><label className="form-label eg-half">Referencia de corrección<input className="form-control" required maxLength={500} disabled={blocked} value={correction.referencia_correccion} onChange={e=>setCorrection({...correction,referencia_correccion:e.target.value})}/></label></div><div className="eg-footer"><Btn disabled={blocked} onClick={()=>setCorrection(null)}>Cancelar</Btn><button className="btn btn-outline-danger" disabled={disabled||!correction.motivo.trim()||!correction.referencia_correccion.trim()}>Confirmar anulación</button></div></form>}</section>
 <section className="card-fyag eg-panel"><div className="finance-history-head"><h2>Historial del egreso</h2><span>{history?history.count+' registros':'—'}</span></div><ol className="finance-timeline">{history?.results.map(e=><li key={e.id} data-type={e.tipo==='ANULACION'?'PAGO_ANULADO':'CREACION'}><strong>{e.tipo==='CREACION'?'Egreso registrado':'Egreso anulado'}</strong><div className="finance-event-meta">{stamp(e.creado_en)} · Usuario #{e.actor}</div>{e.motivo&&<div className="finance-event-reason"><strong>Motivo</strong><p>{e.motivo}</p></div>}</li>)}</ol>{history&&!history.count&&<p className="commercial-empty">No hay registros.</p>}{history&&(history.next||history.previous)&&<Pager data={history} page={historyPage} setPage={setHistoryPage} disabled={disabled} label="Paginación del historial"/>}</section></>}</>}
 </section>;
}
+a.toString()[0]+','+a.toString()[1]+' × 10^'+(a.toString().length-3);
      return (v<0n?'-':'')+'
function Fact({label,value}){return <div><dt>{label}</dt><dd>{value||'—'}</dd></div>;}
function Choice({label,value,onChange,options,all=false,disabled=false,id}){return <label className="form-label" htmlFor={id}>{label}<select id={id} className="form-select" value={value} disabled={disabled} onChange={e=>onChange(e.target.value)}>{all&&<option value="">Todos</option>}{Object.entries(options).map(([k,l])=><option key={k} value={k}>{l}</option>)}</select></label>;}
function WorkPicker({value,onChange,disabled}){
 const api=useApi(),[open,setOpen]=useState(false),[draft,setDraft]=useState(''),[search,setSearch]=useState(''),[page,setPage]=useState(1),[data,setData]=useState(null),[name,setName]=useState('');
 const params={buscar:search};
 const path=query(WORK,{page,...params});
 useEffect(()=>{if(!open)return;setData(null);api.setError(null);void api.load('works',path,v=>{const p=readPage(v,WORK,25,params);for(const r of p.results)if(!positiveInteger(r.id)||typeof r.codigo!=='string'||typeof r.cliente_nombre!=='string')bad();setData(p);});return ()=>api.cancelRead('works');},[open,path]);
 return <div className="eg-work"><label className="form-label">Obra asociada (opcional)</label><div className="eg-toolbar"><span>{value?name||code(value):'Sin obra asociada'}</span><Btn disabled={disabled} onClick={()=>setOpen(v=>!v)} aria-expanded={open}>{open?'Cerrar búsqueda':value?'Cambiar obra':'Seleccionar obra'}</Btn>{value&&<Btn disabled={disabled} onClick={()=>{onChange(null);setName('');setOpen(false);}}>Quitar</Btn>}</div>
 {open&&<div className="eg-work-picker"><div className="eg-toolbar"><input className="form-control" aria-label="Buscar obra" placeholder="Código de obra o cliente" maxLength={150} value={draft} disabled={disabled} onChange={e=>setDraft(e.target.value)} onKeyDown={e=>{if(e.key==='Enter'){e.preventDefault();setPage(1);setSearch(draft.trim());}}}/><Btn disabled={disabled||api.loading} onClick={()=>{setPage(1);setSearch(draft.trim());}}>Buscar</Btn></div><Errors error={api.error}/>{api.loading&&<p role="status">Cargando obras…</p>}
 <div className="eg-work-results">{data?.results.map(r=><div key={r.id}><span><strong>{r.codigo}</strong> · {r.cliente_nombre}</span><Btn disabled={disabled} onClick={()=>{onChange(r.id);setName(r.codigo+' · '+r.cliente_nombre);setOpen(false);}}>Seleccionar</Btn></div>)}</div>{data&&!data.count&&<p>No se encontraron obras.</p>}{data&&(data.next||data.previous)&&<Pager data={data} page={page} setPage={setPage} disabled={disabled||api.loading} label="Paginación de obras"/>}</div>}
 </div>;
}
export default function FinanzasEgresos(){
 const api=useApi(),app=useApp(),inFlight=useRef(false);
 const [view,setView]=useState('list'),[draft,setDraft]=useState(FILTERS),[filters,setFilters]=useState(FILTERS),[expanded,setExpanded]=useState(false),[page,setPage]=useState(1),[snapshot,setSnapshot]=useState(null);
 const [form,setForm]=useState(null),[selected,setSelected]=useState(null),[detail,setDetail]=useState(null),[history,setHistory]=useState(null),[historyPage,setHistoryPage]=useState(1),[correction,setCorrection]=useState(null),[message,setMessage]=useState('');
 const [period,setPeriod]=useState(month),[appliedPeriod,setAppliedPeriod]=useState(null),[flowData,setFlowData]=useState(null);
 const listFilters={...filters,resumen:'true'},path=query(BASE,{page,...listFilters});
 const data=snapshot?.path===path?snapshot.data:null;
 const blocked=api.busy||api.locked,disabled=blocked||api.loading;
 const nav=app?.setNavigationBlocked;
 useEffect(()=>{nav?.(blocked);return ()=>nav?.(false);},[blocked,nav]);
 function readList(){setSnapshot(null);return api.load('list',path,v=>{
   const p=readPage(v,BASE,25,listFilters);p.results.forEach(expense);
   const s=strictObject(p.resumen,['moneda','total','pagos']);
   if(s.moneda!=='CLP'||!decimalString(s.total)||!Number.isSafeInteger(s.pagos)||s.pagos<0||s.pagos>p.count)bad();
   setSnapshot({path,data:p});
 });}
 function readDetail(id=selected){return api.load('detail',BASE+id+'/',v=>{const d=expense(v);if(d.id!==id)bad();setDetail(d);if(!d.activo)setCorrection(null);});}
 function readHistory(id=selected,p=historyPage){setHistory(null);return api.load('history',BASE+id+'/historial/?page='+p,v=>{const h=readPage(v,BASE+id+'/historial/');for(const e of h.results)if(!positiveInteger(e.id)||e.egreso!==id||!positiveInteger(e.actor)||!['CREACION','ANULACION'].includes(e.tipo)||typeof e.motivo!=='string'||!Number.isFinite(Date.parse(e.creado_en)))bad();setHistory(h);});}
 function readFlow(p=appliedPeriod){if(!p)return Promise.resolve(true);setFlowData(null);return api.load('flow',query(FLOW,p),v=>setFlowData(flow(v,p)));}
 useEffect(()=>{api.setError(null);setMessage('');if(view==='list')void readList();return ()=>api.cancelRead('list');},[view,path]);
 useEffect(()=>{if(view==='detail'&&selected){void readDetail();void readHistory();}return ()=>{api.cancelRead('detail');api.cancelRead('history');};},[view,selected,historyPage]);
 useEffect(()=>{if(view==='flow'&&appliedPeriod)void readFlow();return ()=>api.cancelRead('flow');},[view,appliedPeriod]);
 function navigate(next){if(blocked)return;api.setError(null);setMessage('');setCorrection(null);setView(next);}
 function inspect(r){setSelected(r.id);setDetail(null);setHistory(null);setHistoryPage(1);navigate('detail');}
 function begin(){setForm({...EMPTY,clave:crypto.randomUUID()});navigate('create');}
 function apply(e){e.preventDefault();if((draft.desde||draft.hasta)&&!civilRange(draft.desde,draft.hasta)){setMessage('Selecciona ambas fechas y un período de hasta 366 días.');return;}setMessage('');setPage(1);setFilters({...draft,buscar:draft.buscar.trim()});}
 async function refresh(){setMessage('');await api.reconcile(async()=>{if(view==='list')return readList();if(view==='detail'){const r=await Promise.all([readDetail(),readHistory()]);return r.every(Boolean);}if(view==='flow')return readFlow();return false;});}
 const change=(k,v)=>setForm(p=>({...p,[k]:v}));
 async function save(e,retry=false){
   e?.preventDefault();if(inFlight.current||api.busy||(!retry&&api.locked)||!form)return;
   const {clave,...values}=form;
   const body={...values,monto:values.monto.trim(),concepto:values.concepto.trim(),beneficiario:values.beneficiario.trim(),referencia_respaldo:values.referencia_respaldo.trim(),observacion:values.observacion.trim()};
   if(!validMoney(body.monto)||!isoDate(body.fecha_pago)||body.fecha_pago>todayInSantiago()||!body.concepto||!body.beneficiario||!body.referencia_respaldo){setMessage('Completa los datos obligatorios con un monto positivo y una fecha válida.');return;}
   inFlight.current=true;setMessage('');
   try{
     // Un resultado incierto solo admite repetir el mismo payload con la misma UUID.
     if(retry&&!await api.reconcile(()=>Promise.resolve(true)))return;
     await api.write(BASE,'POST',body,async v=>{
       const created=expense(v);if(!created.activo)bad();
       let current;
       await api.requiredLoad('confirm-create',BASE+created.id+'/',x=>{current=expense(x);if(current.id!==created.id)bad();});
       setDetail(current);setSelected(current.id);setHistoryPage(1);setHistory(null);setForm(null);setView('detail');
     },{headers:{'Idempotency-Key':clave}});
   }finally{inFlight.current=false;}
 }
 async function annul(e){
   e.preventDefault();if(inFlight.current||disabled||!detail?.activo||!correction?.motivo.trim()||!correction?.referencia_correccion.trim())return;
   if(!globalThis.confirm('¿Anular este registro de egreso? Esta acción no devuelve dinero.'))return;
   inFlight.current=true;setMessage('');
   try{await api.write(BASE+selected+'/anular/','POST',{motivo:correction.motivo.trim(),referencia_correccion:correction.referencia_correccion.trim()},async v=>{
     const d=expense(v);if(d.id!==selected||d.activo)bad();
     if(!(await Promise.all([readDetail(),readHistory()])).every(Boolean))throw Error('No se pudo confirmar el estado. Actualiza antes de continuar.');
     setCorrection(null);
   });}finally{inFlight.current=false;}
 }
 const notice=<><Errors error={api.error}/>{message&&<p role="alert" className="alert alert-warning">{message}</p>}{api.loading&&<p role="status">Cargando datos…</p>}</>;
 return <section className="commercial-page manager-portfolio cobranzas-page manager-cobranzas manager-egresos finance-egresos">
 <PageHead title="Egresos" sub="Consulta y registra pagos ya realizados. No representa cuentas por pagar ni saldo bancario.">{view!=='create'&&<Btn icon="refresh" disabled={api.busy||api.loading} onClick={()=>void refresh()}>Actualizar</Btn>}{view==='list'&&<button type="button" className="btn btn-fyag-primary" disabled={disabled} onClick={begin}>+ Registrar egreso</button>}</PageHead>
 {(view==='list'||view==='flow')&&<nav className="manager-work-tabs" aria-label="Secciones de egresos"><button type="button" aria-pressed={view==='list'} onClick={()=>navigate('list')}>Registro de egresos</button><button type="button" aria-pressed={view==='flow'} onClick={()=>navigate('flow')}>Flujo de dinero</button></nav>}
 {notice}
 {view==='list'&&<>
 <div className="portfolio-kpis eg-kpis"><Metric label="Total de egresos activos" value={money(data?.resumen.total)}/><Metric label="Pagos activos registrados" value={data?.resumen.pagos??'—'}/></div>
 <p className="commercial-help">Indicadores del conjunto filtrado, excluyen registros anulados.</p>
 <section className="card-fyag portfolio-list eg-list"><div className="portfolio-list-head"><div><h2>Registro de egresos</h2><span>{data?data.count+' registros · CLP':'—'}</span></div><Btn icon="filter" aria-expanded={expanded} onClick={()=>setExpanded(v=>!v)}>Filtros</Btn></div>
 <form className="eg-filters" onSubmit={apply} aria-label="Filtros de egresos"><div className="eg-toolbar"><label className="form-label eg-search">Buscar egreso<input className="form-control" maxLength={100} value={draft.buscar} placeholder="Concepto, beneficiario o código de obra" onChange={e=>setDraft({...draft,buscar:e.target.value})}/></label><Choice label="Estado" value={draft.activo} onChange={v=>setDraft({...draft,activo:v})} options={{true:'Activos',false:'Anulados'}} all/><button className="btn btn-fyag-primary" disabled={disabled}>Buscar</button>{(Object.values(filters).some(Boolean)||Object.values(draft).some(Boolean))&&<Btn disabled={disabled} onClick={()=>{setDraft(FILTERS);setFilters(FILTERS);setPage(1);setMessage('');}}>Limpiar filtros</Btn>}</div>
 {expanded&&<div className="eg-fields"><Choice label="Categoría" value={draft.categoria} onChange={v=>setDraft({...draft,categoria:v})} options={CATS} all/><Choice label="Medio de pago" value={draft.medio} onChange={v=>setDraft({...draft,medio:v})} options={MEANS} all/>{[['desde','Pagado desde'],['hasta','Pagado hasta']].map(([k,l])=><label key={k} className="form-label">{l}<input className="form-control" type="date" value={draft[k]} onChange={e=>setDraft({...draft,[k]:e.target.value})}/></label>)}</div>}</form>
 {data&&<><div className="table-responsive" role="region" aria-label="Listado de egresos" tabIndex={0}><table className="table commercial-table eg-table"><thead><tr>{['Concepto / Beneficiario','Fecha de pago','Categoría','Medio de pago','Monto CLP','Estado','Detalle'].map(l=><th scope="col" key={l}>{l}</th>)}</tr></thead><tbody>{data.results.map(r=><tr key={r.id}><td><strong>{r.concepto}</strong><span className="eg-client">{r.beneficiario}</span></td><td>{date(r.fecha_pago)}</td><td>{CATS[r.categoria]}</td><td>{MEANS[r.medio]}</td><td>{money(r.monto)}</td><td><Status row={r}/></td><td><Btn disabled={disabled} onClick={()=>inspect(r)}>Ver detalle</Btn></td></tr>)}</tbody></table></div>{!data.count&&<p className="commercial-empty">No se encontraron egresos.</p>}{(data.next||data.previous)&&<Pager data={data} page={page} setPage={setPage} disabled={disabled} label="Paginación de egresos"/>}</>}{api.error?.status===404&&page>1&&<Btn onClick={()=>setPage(1)}>Volver a primera página</Btn>}</section></>}
 {view==='flow'&&<section className="card-fyag eg-panel"><h2>Flujo de dinero registrado</h2><p className="commercial-help">Ingresos recibidos menos egresos activos del período. No es saldo bancario ni conciliación.</p><form className="eg-toolbar" onSubmit={e=>{e.preventDefault();if(!civilRange(period.desde,period.hasta)){setMessage('Selecciona un período válido de hasta 366 días.');return;}setMessage('');setAppliedPeriod({...period});}}>{[['desde','Desde'],['hasta','Hasta']].map(([k,l])=><label className="form-label" key={k}>{l}<input className="form-control" type="date" value={period[k]} onChange={e=>setPeriod({...period,[k]:e.target.value})}/></label>)}<button className="btn btn-fyag-primary" disabled={disabled}>Consultar</button></form>{!appliedPeriod&&<div className="eg-flow-empty" role="status"><TecIcon name="calendar"/><strong>Selecciona un período</strong><p>Indica las fechas y pulsa Consultar para visualizar los ingresos y egresos registrados.</p></div>}{flowData&&<><p className="commercial-help">{date(appliedPeriod.desde)} – {date(appliedPeriod.hasta)} · CLP</p><div className="portfolio-kpis eg-flow-kpis"><Metric label="Ingresos recibidos" value={money(flowData.ingresos_recibidos)}/><Metric label="Egresos pagados" value={money(flowData.egresos_pagados)}/><Metric label="Flujo neto registrado" value={money(flowData.flujo_neto_registrado)}/></div></>}</section>}
 {view==='create'&&form&&<><Btn className="btn btn-outline-secondary eg-back" icon="back" disabled={blocked} onClick={()=>{setForm(null);navigate('list');}}>Volver a egresos</Btn><section className="card-fyag eg-panel"><h2>Registrar egreso</h2><p className="commercial-help">Ingresa los datos de un pago ya realizado.</p><form onSubmit={save} aria-label="Registro de egreso">
 <h3>Datos del pago</h3><div className="eg-fields">
 {[[ 'monto','Monto pagado (CLP)'],['fecha_pago','Fecha de pago']].map(([k,l])=><label className="form-label" key={k}>{l}<input className="form-control" required type={k==='fecha_pago'?'date':'text'} inputMode={k==='monto'?'decimal':undefined} max={k==='fecha_pago'?todayInSantiago():undefined} placeholder={k==='monto'?'Ej.: 150000':undefined} value={form[k]} disabled={blocked} onChange={e=>change(k,e.target.value)}/></label>)}
 <Choice label="Categoría" value={form.categoria} onChange={v=>change('categoria',v)} options={CATS} disabled={blocked}/><Choice label="Medio de pago" value={form.medio} onChange={v=>change('medio',v)} options={MEANS} disabled={blocked}/>
 {[[ 'concepto','Concepto'],['beneficiario','Beneficiario']].map(([k,l])=><label className="form-label eg-half" key={k}>{l}<input className="form-control" required maxLength={200} value={form[k]} disabled={blocked} onChange={e=>change(k,e.target.value)}/></label>)}</div>
 <h3 className="eg-section-title">Información complementaria</h3><div className="eg-fields"><div className="eg-half"><WorkPicker value={form.obra} onChange={v=>change('obra',v)} disabled={blocked}/></div><label className="form-label eg-half">Referencia del respaldo<input className="form-control" placeholder="Número de comprobante" maxLength={500} required value={form.referencia_respaldo} disabled={blocked} onChange={e=>change('referencia_respaldo',e.target.value)}/></label><label className="form-label eg-full">Observaciones<textarea className="form-control" rows={2} maxLength={2000} value={form.observacion} disabled={blocked} onChange={e=>change('observacion',e.target.value)}/></label></div>
 <div className="eg-footer">{api.locked?<><p role="alert">El registro no pudo confirmarse. Reintenta la misma solicitud sin modificar sus datos para evitar duplicados.</p><button type="button" className="btn btn-fyag-primary" disabled={api.busy} onClick={()=>void save(null,true)}>Confirmar registro pendiente</button></>:<><Btn disabled={api.busy} onClick={()=>{setForm(null);navigate('list');}}>Cancelar</Btn><button className="btn btn-fyag-primary" disabled={disabled}>Registrar egreso</button></>}</div></form></section></>}
 {view==='detail'&&<><Btn className="btn btn-outline-secondary eg-back" icon="back" disabled={blocked} onClick={()=>navigate('list')}>Volver a egresos</Btn>{detail&&<>
 <header className="eg-detail-heading"><div><h2>{detail.concepto}</h2><p>{detail.beneficiario}</p></div><Status row={detail}/></header>
 <div className="portfolio-kpis eg-detail-kpis"><Metric label={detail.activo?'Monto pagado · CLP':'Monto anulado · CLP'} value={money(detail.monto)}/><Metric label="Fecha de pago" value={date(detail.fecha_pago)}/><Metric label="Categoría" value={CATS[detail.categoria]}/><Metric label="Medio de pago" value={MEANS[detail.medio]}/></div>
 <section className="card-fyag eg-panel"><h2>Información del egreso</h2><dl className="eg-facts"><Fact label="Beneficiario" value={detail.beneficiario}/><Fact label="Obra asociada" value={code(detail.obra)}/><Fact label="Referencia del respaldo" value={detail.referencia_respaldo}/><Fact label="Registrado" value={stamp(detail.registrado_en)}/><Fact label="Registrado por" value={'Usuario #'+detail.registrado_por}/><Fact label="Observaciones" value={detail.observacion}/>{!detail.activo&&<><Fact label="Fecha de anulación" value={stamp(detail.anulado_en)}/><Fact label="Motivo de anulación" value={detail.motivo_anulacion}/><Fact label="Referencia de corrección" value={detail.referencia_correccion}/></>}</dl>
 {detail.activo&&!correction&&!api.locked&&<div className="eg-footer"><button type="button" className="btn btn-outline-danger" disabled={disabled} onClick={()=>setCorrection({motivo:'',referencia_correccion:''})}>Anular egreso</button></div>}
 {detail.activo&&correction&&<form className="eg-annul" aria-label="Anular egreso" onSubmit={annul}><h3>Anular registro</h3><p className="commercial-help">No representa una devolución de dinero. El registro permanecerá en el historial.</p><div className="eg-fields"><label className="form-label eg-half">Motivo<textarea className="form-control" required rows={2} maxLength={2000} disabled={blocked} value={correction.motivo} onChange={e=>setCorrection({...correction,motivo:e.target.value})}/></label><label className="form-label eg-half">Referencia de corrección<input className="form-control" required maxLength={500} disabled={blocked} value={correction.referencia_correccion} onChange={e=>setCorrection({...correction,referencia_correccion:e.target.value})}/></label></div><div className="eg-footer"><Btn disabled={blocked} onClick={()=>setCorrection(null)}>Cancelar</Btn><button className="btn btn-outline-danger" disabled={disabled||!correction.motivo.trim()||!correction.referencia_correccion.trim()}>Confirmar anulación</button></div></form>}</section>
 <section className="card-fyag eg-panel"><div className="finance-history-head"><h2>Historial del egreso</h2><span>{history?history.count+' registros':'—'}</span></div><ol className="finance-timeline">{history?.results.map(e=><li key={e.id} data-type={e.tipo==='ANULACION'?'PAGO_ANULADO':'CREACION'}><strong>{e.tipo==='CREACION'?'Egreso registrado':'Egreso anulado'}</strong><div className="finance-event-meta">{stamp(e.creado_en)} · Usuario #{e.actor}</div>{e.motivo&&<div className="finance-event-reason"><strong>Motivo</strong><p>{e.motivo}</p></div>}</li>)}</ol>{history&&!history.count&&<p className="commercial-empty">No hay registros.</p>}{history&&(history.next||history.previous)&&<Pager data={history} page={historyPage} setPage={setHistoryPage} disabled={disabled} label="Paginación del historial"/>}</section></>}</>}
 </section>;
}
+String(tenths/10n)+(tenths%10n?','+String(tenths%10n):'')+suffix;
    }
  }
  return flowTick(v);
};
export function flowGeometry(data){
  const income=flowUnits(data.ingresos_recibidos),expense=flowUnits(data.egresos_pagados),net=flowUnits(data.flujo_neto_registrado);
  if(income===0n&&expense===0n)return null;
  const max=income>expense?income:expense;
  const low=net<0n?net:0n,high=income;
  const y=(v,min,max)=>18+Number((max-v)*170000n/(max-min))/1000;
  const plot=(min,max,items)=>{
    const coordinate=v=>y(v,min,max);
    const ticks=[min,max,0n];
    for(let i=1n;i<4n;i++)ticks.push(min+(max-min)*i/4n);
    return {zero:coordinate(0n),ticks:[...new Set(ticks)].sort((a,b)=>a<b?-1:a>b?1:0).map(value=>({value,y:coordinate(value)})).filter((t,i,all)=>t.value===0n||!all.some(o=>o.value===0n&&Math.abs(o.y-t.y)<15)).filter((t,i,all)=>i===0||Math.abs(t.y-all[i-1].y)>=15||t.value===0n),
      bars:items.map(([label,tone,start,end,x,amount])=>({label,tone,x,amount,y:Math.min(coordinate(start),coordinate(end)),height:Math.abs(coordinate(start)-coordinate(end)),startY:coordinate(start),endY:coordinate(end)}))};
  };
  return {comparison:plot(0n,max,[['Ingresos','income',0n,income,188,data.ingresos_recibidos],['Egresos','expense',0n,expense,348,data.egresos_pagados]]),
    bridge:plot(low,high,[['Ingresos','income',0n,income,128,data.ingresos_recibidos],['Egresos','expense',income,net,268,expense===0n?data.egresos_pagados:'-'+data.egresos_pagados],['Flujo neto',net<0n?'expense':net>0n?'income':'neutral',0n,net,408,data.flujo_neto_registrado]])};
}
function FlowPlot({title,plot,bridge=false}){
  const bars=plot.bars,width=bridge?66:84;
  return <svg className="eg-flow-svg" viewBox="0 0 500 222" role="img" aria-label={title+': '+bars.map(b=>b.label+' '+money(b.amount)).join(', ')}>
    {plot.ticks.map(t=><g key={String(t.value)}><line x1="92" x2="482" y1={t.y} y2={t.y} className={t.value===0n?'eg-chart-zero':'eg-chart-grid'}/><text x="84" y={t.y+4} textAnchor="end" className="eg-chart-axis">{axisTick(t.value)}</text></g>)}
    {bridge&&bars.slice(0,-1).map((b,i)=><line key={b.label} x1={b.x+width/2} x2={bars[i+1].x-width/2} y1={b.endY} y2={b.endY} className="eg-chart-connector"/>)}
    {bars.map(b=><g key={b.label}>
      <rect data-chart-bar={b.label} className={'eg-chart-'+b.tone} x={b.x-width/2} y={b.y} width={width} height={b.height} rx="2"><title>{b.label}: {money(b.amount)}</title></rect>
      {b.height===0&&<line x1={b.x-width/2} x2={b.x+width/2} y1={b.y} y2={b.y} className={'eg-chart-zero-mark eg-chart-'+b.tone}/>}
      <text x={b.x} y="210" textAnchor="middle" className="eg-chart-label">{b.label}</text>
    </g>)}
  </svg>;
}
function FlowCharts({data}){
  const geometry=flowGeometry(data);
  if(!geometry)return <div className="eg-flow-empty" role="status"><TecIcon name="calendar"/><strong>Sin movimientos en este período</strong><p>No se registran importes de ingresos ni egresos para las fechas consultadas.</p></div>;
  const net=flowUnits(data.flujo_neto_registrado);
  return <div className="eg-flow-charts" aria-label="Visualización del flujo de dinero">
    <section className="eg-flow-chart"><h3>Comparación de ingresos y egresos</h3><p className="commercial-help">Importes recibidos y pagados, en una escala común.</p><FlowPlot title="Comparación de ingresos y egresos" plot={geometry.comparison}/></section>
    <section className="eg-flow-chart"><h3>Composición del flujo neto</h3><p className="commercial-help">Ingresos menos egresos del período consultado.</p><FlowPlot title="Gráfico de puente del flujo neto" plot={geometry.bridge} bridge/><p className={'eg-flow-result '+(net<0n?'is-negative':net>0n?'is-positive':'')}><strong>{net<0n?'Flujo neto negativo':net>0n?'Flujo neto positivo':'Flujo neto equilibrado'}:</strong> {net<0n?'Los egresos superan los ingresos.':net>0n?'Los ingresos superan los egresos.':'Los ingresos y egresos son iguales.'}</p></section>
  </div>;
}

function Fact({label,value}){return <div><dt>{label}</dt><dd>{value||'—'}</dd></div>;}
function Choice({label,value,onChange,options,all=false,disabled=false,id}){return <label className="form-label" htmlFor={id}>{label}<select id={id} className="form-select" value={value} disabled={disabled} onChange={e=>onChange(e.target.value)}>{all&&<option value="">Todos</option>}{Object.entries(options).map(([k,l])=><option key={k} value={k}>{l}</option>)}</select></label>;}
function WorkPicker({value,onChange,disabled}){
 const api=useApi(),[open,setOpen]=useState(false),[draft,setDraft]=useState(''),[search,setSearch]=useState(''),[page,setPage]=useState(1),[data,setData]=useState(null),[name,setName]=useState('');
 const params={buscar:search};
 const path=query(WORK,{page,...params});
 useEffect(()=>{if(!open)return;setData(null);api.setError(null);void api.load('works',path,v=>{const p=readPage(v,WORK,25,params);for(const r of p.results)if(!positiveInteger(r.id)||typeof r.codigo!=='string'||typeof r.cliente_nombre!=='string')bad();setData(p);});return ()=>api.cancelRead('works');},[open,path]);
 return <div className="eg-work"><label className="form-label">Obra asociada (opcional)</label><div className="eg-toolbar"><span>{value?name||code(value):'Sin obra asociada'}</span><Btn disabled={disabled} onClick={()=>setOpen(v=>!v)} aria-expanded={open}>{open?'Cerrar búsqueda':value?'Cambiar obra':'Seleccionar obra'}</Btn>{value&&<Btn disabled={disabled} onClick={()=>{onChange(null);setName('');setOpen(false);}}>Quitar</Btn>}</div>
 {open&&<div className="eg-work-picker"><div className="eg-toolbar"><input className="form-control" aria-label="Buscar obra" placeholder="Código de obra o cliente" maxLength={150} value={draft} disabled={disabled} onChange={e=>setDraft(e.target.value)} onKeyDown={e=>{if(e.key==='Enter'){e.preventDefault();setPage(1);setSearch(draft.trim());}}}/><Btn disabled={disabled||api.loading} onClick={()=>{setPage(1);setSearch(draft.trim());}}>Buscar</Btn></div><Errors error={api.error}/>{api.loading&&<p role="status">Cargando obras…</p>}
 <div className="eg-work-results">{data?.results.map(r=><div key={r.id}><span><strong>{r.codigo}</strong> · {r.cliente_nombre}</span><Btn disabled={disabled} onClick={()=>{onChange(r.id);setName(r.codigo+' · '+r.cliente_nombre);setOpen(false);}}>Seleccionar</Btn></div>)}</div>{data&&!data.count&&<p>No se encontraron obras.</p>}{data&&(data.next||data.previous)&&<Pager data={data} page={page} setPage={setPage} disabled={disabled||api.loading} label="Paginación de obras"/>}</div>}
 </div>;
}
export default function FinanzasEgresos(){
 const api=useApi(),app=useApp(),inFlight=useRef(false);
 const [view,setView]=useState('list'),[draft,setDraft]=useState(FILTERS),[filters,setFilters]=useState(FILTERS),[expanded,setExpanded]=useState(false),[page,setPage]=useState(1),[snapshot,setSnapshot]=useState(null);
 const [form,setForm]=useState(null),[selected,setSelected]=useState(null),[detail,setDetail]=useState(null),[history,setHistory]=useState(null),[historyPage,setHistoryPage]=useState(1),[correction,setCorrection]=useState(null),[message,setMessage]=useState('');
 const [period,setPeriod]=useState(month),[appliedPeriod,setAppliedPeriod]=useState(null),[flowData,setFlowData]=useState(null);
 const listFilters={...filters,resumen:'true'},path=query(BASE,{page,...listFilters});
 const data=snapshot?.path===path?snapshot.data:null;
 const blocked=api.busy||api.locked,disabled=blocked||api.loading;
 const nav=app?.setNavigationBlocked;
 useEffect(()=>{nav?.(blocked);return ()=>nav?.(false);},[blocked,nav]);
 function readList(){setSnapshot(null);return api.load('list',path,v=>{
   const p=readPage(v,BASE,25,listFilters);p.results.forEach(expense);
   const s=strictObject(p.resumen,['moneda','total','pagos']);
   if(s.moneda!=='CLP'||!decimalString(s.total)||!Number.isSafeInteger(s.pagos)||s.pagos<0||s.pagos>p.count)bad();
   setSnapshot({path,data:p});
 });}
 function readDetail(id=selected){return api.load('detail',BASE+id+'/',v=>{const d=expense(v);if(d.id!==id)bad();setDetail(d);if(!d.activo)setCorrection(null);});}
 function readHistory(id=selected,p=historyPage){setHistory(null);return api.load('history',BASE+id+'/historial/?page='+p,v=>{const h=readPage(v,BASE+id+'/historial/');for(const e of h.results)if(!positiveInteger(e.id)||e.egreso!==id||!positiveInteger(e.actor)||!['CREACION','ANULACION'].includes(e.tipo)||typeof e.motivo!=='string'||!Number.isFinite(Date.parse(e.creado_en)))bad();setHistory(h);});}
 function readFlow(p=appliedPeriod){if(!p)return Promise.resolve(true);setFlowData(null);return api.load('flow',query(FLOW,p),v=>setFlowData(flow(v,p)));}
 useEffect(()=>{api.setError(null);setMessage('');if(view==='list')void readList();return ()=>api.cancelRead('list');},[view,path]);
 useEffect(()=>{if(view==='detail'&&selected){void readDetail();void readHistory();}return ()=>{api.cancelRead('detail');api.cancelRead('history');};},[view,selected,historyPage]);
 useEffect(()=>{if(view==='flow'&&appliedPeriod)void readFlow();return ()=>api.cancelRead('flow');},[view,appliedPeriod]);
 function navigate(next){if(blocked)return;api.setError(null);setMessage('');setCorrection(null);setView(next);}
 function inspect(r){setSelected(r.id);setDetail(null);setHistory(null);setHistoryPage(1);navigate('detail');}
 function begin(){setForm({...EMPTY,clave:crypto.randomUUID()});navigate('create');}
 function apply(e){e.preventDefault();if((draft.desde||draft.hasta)&&!civilRange(draft.desde,draft.hasta)){setMessage('Selecciona ambas fechas y un período de hasta 366 días.');return;}setMessage('');setPage(1);setFilters({...draft,buscar:draft.buscar.trim()});}
 async function refresh(){setMessage('');await api.reconcile(async()=>{if(view==='list')return readList();if(view==='detail'){const r=await Promise.all([readDetail(),readHistory()]);return r.every(Boolean);}if(view==='flow')return readFlow();return false;});}
 const change=(k,v)=>setForm(p=>({...p,[k]:v}));
 async function save(e,retry=false){
   e?.preventDefault();if(inFlight.current||api.busy||(!retry&&api.locked)||!form)return;
   const {clave,...values}=form;
   const body={...values,monto:values.monto.trim(),concepto:values.concepto.trim(),beneficiario:values.beneficiario.trim(),referencia_respaldo:values.referencia_respaldo.trim(),observacion:values.observacion.trim()};
   if(!validMoney(body.monto)||!isoDate(body.fecha_pago)||body.fecha_pago>todayInSantiago()||!body.concepto||!body.beneficiario||!body.referencia_respaldo){setMessage('Completa los datos obligatorios con un monto positivo y una fecha válida.');return;}
   inFlight.current=true;setMessage('');
   try{
     // Un resultado incierto solo admite repetir el mismo payload con la misma UUID.
     if(retry&&!await api.reconcile(()=>Promise.resolve(true)))return;
     await api.write(BASE,'POST',body,async v=>{
       const created=expense(v);if(!created.activo)bad();
       let current;
       await api.requiredLoad('confirm-create',BASE+created.id+'/',x=>{current=expense(x);if(current.id!==created.id)bad();});
       setDetail(current);setSelected(current.id);setHistoryPage(1);setHistory(null);setForm(null);setView('detail');
     },{headers:{'Idempotency-Key':clave}});
   }finally{inFlight.current=false;}
 }
 async function annul(e){
   e.preventDefault();if(inFlight.current||disabled||!detail?.activo||!correction?.motivo.trim()||!correction?.referencia_correccion.trim())return;
   if(!globalThis.confirm('¿Anular este registro de egreso? Esta acción no devuelve dinero.'))return;
   inFlight.current=true;setMessage('');
   try{await api.write(BASE+selected+'/anular/','POST',{motivo:correction.motivo.trim(),referencia_correccion:correction.referencia_correccion.trim()},async v=>{
     const d=expense(v);if(d.id!==selected||d.activo)bad();
     if(!(await Promise.all([readDetail(),readHistory()])).every(Boolean))throw Error('No se pudo confirmar el estado. Actualiza antes de continuar.');
     setCorrection(null);
   });}finally{inFlight.current=false;}
 }
 const notice=<><Errors error={api.error}/>{message&&<p role="alert" className="alert alert-warning">{message}</p>}{api.loading&&<p role="status">Cargando datos…</p>}</>;
 return <section className="commercial-page manager-portfolio cobranzas-page manager-cobranzas manager-egresos finance-egresos">
 <PageHead title="Egresos" sub="Consulta y registra pagos ya realizados. No representa cuentas por pagar ni saldo bancario.">{view!=='create'&&<Btn icon="refresh" disabled={api.busy||api.loading} onClick={()=>void refresh()}>Actualizar</Btn>}{view==='list'&&<button type="button" className="btn btn-fyag-primary" disabled={disabled} onClick={begin}>+ Registrar egreso</button>}</PageHead>
 {(view==='list'||view==='flow')&&<nav className="manager-work-tabs" aria-label="Secciones de egresos"><button type="button" aria-pressed={view==='list'} onClick={()=>navigate('list')}>Registro de egresos</button><button type="button" aria-pressed={view==='flow'} onClick={()=>navigate('flow')}>Flujo de dinero</button></nav>}
 {notice}
 {view==='list'&&<>
 <div className="portfolio-kpis eg-kpis"><Metric label="Total de egresos activos" value={money(data?.resumen.total)}/><Metric label="Pagos activos registrados" value={data?.resumen.pagos??'—'}/></div>
 <p className="commercial-help">Indicadores del conjunto filtrado, excluyen registros anulados.</p>
 <section className="card-fyag portfolio-list eg-list"><div className="portfolio-list-head"><div><h2>Registro de egresos</h2><span>{data?data.count+' registros · CLP':'—'}</span></div><Btn icon="filter" aria-expanded={expanded} onClick={()=>setExpanded(v=>!v)}>Filtros</Btn></div>
 <form className="eg-filters" onSubmit={apply} aria-label="Filtros de egresos"><div className="eg-toolbar"><label className="form-label eg-search">Buscar egreso<input className="form-control" maxLength={100} value={draft.buscar} placeholder="Concepto, beneficiario o código de obra" onChange={e=>setDraft({...draft,buscar:e.target.value})}/></label><Choice label="Estado" value={draft.activo} onChange={v=>setDraft({...draft,activo:v})} options={{true:'Activos',false:'Anulados'}} all/><button className="btn btn-fyag-primary" disabled={disabled}>Buscar</button>{(Object.values(filters).some(Boolean)||Object.values(draft).some(Boolean))&&<Btn disabled={disabled} onClick={()=>{setDraft(FILTERS);setFilters(FILTERS);setPage(1);setMessage('');}}>Limpiar filtros</Btn>}</div>
 {expanded&&<div className="eg-fields"><Choice label="Categoría" value={draft.categoria} onChange={v=>setDraft({...draft,categoria:v})} options={CATS} all/><Choice label="Medio de pago" value={draft.medio} onChange={v=>setDraft({...draft,medio:v})} options={MEANS} all/>{[['desde','Pagado desde'],['hasta','Pagado hasta']].map(([k,l])=><label key={k} className="form-label">{l}<input className="form-control" type="date" value={draft[k]} onChange={e=>setDraft({...draft,[k]:e.target.value})}/></label>)}</div>}</form>
 {data&&<><div className="table-responsive" role="region" aria-label="Listado de egresos" tabIndex={0}><table className="table commercial-table eg-table"><thead><tr>{['Concepto / Beneficiario','Fecha de pago','Categoría','Medio de pago','Monto CLP','Estado','Detalle'].map(l=><th scope="col" key={l}>{l}</th>)}</tr></thead><tbody>{data.results.map(r=><tr key={r.id}><td><strong>{r.concepto}</strong><span className="eg-client">{r.beneficiario}</span></td><td>{date(r.fecha_pago)}</td><td>{CATS[r.categoria]}</td><td>{MEANS[r.medio]}</td><td>{money(r.monto)}</td><td><Status row={r}/></td><td><Btn disabled={disabled} onClick={()=>inspect(r)}>Ver detalle</Btn></td></tr>)}</tbody></table></div>{!data.count&&<p className="commercial-empty">No se encontraron egresos.</p>}{(data.next||data.previous)&&<Pager data={data} page={page} setPage={setPage} disabled={disabled} label="Paginación de egresos"/>}</>}{api.error?.status===404&&page>1&&<Btn onClick={()=>setPage(1)}>Volver a primera página</Btn>}</section></>}
 {view==='flow'&&<section className="card-fyag eg-panel"><h2>Flujo de dinero registrado</h2><p className="commercial-help">Ingresos recibidos menos egresos activos del período. No es saldo bancario ni conciliación.</p><form className="eg-toolbar" onSubmit={e=>{e.preventDefault();if(!civilRange(period.desde,period.hasta)){setMessage('Selecciona un período válido de hasta 366 días.');return;}setMessage('');setAppliedPeriod({...period});}}>{[['desde','Desde'],['hasta','Hasta']].map(([k,l])=><label className="form-label" key={k}>{l}<input className="form-control" type="date" value={period[k]} onChange={e=>setPeriod({...period,[k]:e.target.value})}/></label>)}<button className="btn btn-fyag-primary" disabled={disabled}>Consultar</button></form>{!appliedPeriod&&<div className="eg-flow-empty" role="status"><TecIcon name="calendar"/><strong>Selecciona un período</strong><p>Indica las fechas y pulsa Consultar para visualizar los ingresos y egresos registrados.</p></div>}{flowData&&<><p className="commercial-help">{date(appliedPeriod.desde)} – {date(appliedPeriod.hasta)} · CLP</p><div className="portfolio-kpis eg-flow-kpis"><Metric label="Ingresos recibidos" value={money(flowData.ingresos_recibidos)}/><Metric label="Egresos pagados" value={money(flowData.egresos_pagados)}/><Metric label="Flujo neto registrado" value={money(flowData.flujo_neto_registrado)}/></div></>}</section>}
 {view==='create'&&form&&<><Btn className="btn btn-outline-secondary eg-back" icon="back" disabled={blocked} onClick={()=>{setForm(null);navigate('list');}}>Volver a egresos</Btn><section className="card-fyag eg-panel"><h2>Registrar egreso</h2><p className="commercial-help">Ingresa los datos de un pago ya realizado.</p><form onSubmit={save} aria-label="Registro de egreso">
 <h3>Datos del pago</h3><div className="eg-fields">
 {[[ 'monto','Monto pagado (CLP)'],['fecha_pago','Fecha de pago']].map(([k,l])=><label className="form-label" key={k}>{l}<input className="form-control" required type={k==='fecha_pago'?'date':'text'} inputMode={k==='monto'?'decimal':undefined} max={k==='fecha_pago'?todayInSantiago():undefined} placeholder={k==='monto'?'Ej.: 150000':undefined} value={form[k]} disabled={blocked} onChange={e=>change(k,e.target.value)}/></label>)}
 <Choice label="Categoría" value={form.categoria} onChange={v=>change('categoria',v)} options={CATS} disabled={blocked}/><Choice label="Medio de pago" value={form.medio} onChange={v=>change('medio',v)} options={MEANS} disabled={blocked}/>
 {[[ 'concepto','Concepto'],['beneficiario','Beneficiario']].map(([k,l])=><label className="form-label eg-half" key={k}>{l}<input className="form-control" required maxLength={200} value={form[k]} disabled={blocked} onChange={e=>change(k,e.target.value)}/></label>)}</div>
 <h3 className="eg-section-title">Información complementaria</h3><div className="eg-fields"><div className="eg-half"><WorkPicker value={form.obra} onChange={v=>change('obra',v)} disabled={blocked}/></div><label className="form-label eg-half">Referencia del respaldo<input className="form-control" placeholder="Número de comprobante" maxLength={500} required value={form.referencia_respaldo} disabled={blocked} onChange={e=>change('referencia_respaldo',e.target.value)}/></label><label className="form-label eg-full">Observaciones<textarea className="form-control" rows={2} maxLength={2000} value={form.observacion} disabled={blocked} onChange={e=>change('observacion',e.target.value)}/></label></div>
 <div className="eg-footer">{api.locked?<><p role="alert">El registro no pudo confirmarse. Reintenta la misma solicitud sin modificar sus datos para evitar duplicados.</p><button type="button" className="btn btn-fyag-primary" disabled={api.busy} onClick={()=>void save(null,true)}>Confirmar registro pendiente</button></>:<><Btn disabled={api.busy} onClick={()=>{setForm(null);navigate('list');}}>Cancelar</Btn><button className="btn btn-fyag-primary" disabled={disabled}>Registrar egreso</button></>}</div></form></section></>}
 {view==='detail'&&<><Btn className="btn btn-outline-secondary eg-back" icon="back" disabled={blocked} onClick={()=>navigate('list')}>Volver a egresos</Btn>{detail&&<>
 <header className="eg-detail-heading"><div><h2>{detail.concepto}</h2><p>{detail.beneficiario}</p></div><Status row={detail}/></header>
 <div className="portfolio-kpis eg-detail-kpis"><Metric label={detail.activo?'Monto pagado · CLP':'Monto anulado · CLP'} value={money(detail.monto)}/><Metric label="Fecha de pago" value={date(detail.fecha_pago)}/><Metric label="Categoría" value={CATS[detail.categoria]}/><Metric label="Medio de pago" value={MEANS[detail.medio]}/></div>
 <section className="card-fyag eg-panel"><h2>Información del egreso</h2><dl className="eg-facts"><Fact label="Beneficiario" value={detail.beneficiario}/><Fact label="Obra asociada" value={code(detail.obra)}/><Fact label="Referencia del respaldo" value={detail.referencia_respaldo}/><Fact label="Registrado" value={stamp(detail.registrado_en)}/><Fact label="Registrado por" value={'Usuario #'+detail.registrado_por}/><Fact label="Observaciones" value={detail.observacion}/>{!detail.activo&&<><Fact label="Fecha de anulación" value={stamp(detail.anulado_en)}/><Fact label="Motivo de anulación" value={detail.motivo_anulacion}/><Fact label="Referencia de corrección" value={detail.referencia_correccion}/></>}</dl>
 {detail.activo&&!correction&&!api.locked&&<div className="eg-footer"><button type="button" className="btn btn-outline-danger" disabled={disabled} onClick={()=>setCorrection({motivo:'',referencia_correccion:''})}>Anular egreso</button></div>}
 {detail.activo&&correction&&<form className="eg-annul" aria-label="Anular egreso" onSubmit={annul}><h3>Anular registro</h3><p className="commercial-help">No representa una devolución de dinero. El registro permanecerá en el historial.</p><div className="eg-fields"><label className="form-label eg-half">Motivo<textarea className="form-control" required rows={2} maxLength={2000} disabled={blocked} value={correction.motivo} onChange={e=>setCorrection({...correction,motivo:e.target.value})}/></label><label className="form-label eg-half">Referencia de corrección<input className="form-control" required maxLength={500} disabled={blocked} value={correction.referencia_correccion} onChange={e=>setCorrection({...correction,referencia_correccion:e.target.value})}/></label></div><div className="eg-footer"><Btn disabled={blocked} onClick={()=>setCorrection(null)}>Cancelar</Btn><button className="btn btn-outline-danger" disabled={disabled||!correction.motivo.trim()||!correction.referencia_correccion.trim()}>Confirmar anulación</button></div></form>}</section>
 <section className="card-fyag eg-panel"><div className="finance-history-head"><h2>Historial del egreso</h2><span>{history?history.count+' registros':'—'}</span></div><ol className="finance-timeline">{history?.results.map(e=><li key={e.id} data-type={e.tipo==='ANULACION'?'PAGO_ANULADO':'CREACION'}><strong>{e.tipo==='CREACION'?'Egreso registrado':'Egreso anulado'}</strong><div className="finance-event-meta">{stamp(e.creado_en)} · Usuario #{e.actor}</div>{e.motivo&&<div className="finance-event-reason"><strong>Motivo</strong><p>{e.motivo}</p></div>}</li>)}</ol>{history&&!history.count&&<p className="commercial-empty">No hay registros.</p>}{history&&(history.next||history.previous)&&<Pager data={history} page={historyPage} setPage={setHistoryPage} disabled={disabled} label="Paginación del historial"/>}</section></>}</>}
 </section>;
}
