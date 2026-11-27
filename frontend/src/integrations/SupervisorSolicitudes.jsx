import React,{useEffect,useRef,useState} from 'react';
import {PageHead} from '../components/ui/index.js';
import {Errors,Pager} from '../comercial/ui.jsx';
import {useApp} from '../context/AppContext.jsx';
import {useApi,readPage,positiveInteger} from './useApi.js';
import {normalizeDecimalInput,quantityHint} from '../utils/decimalInput.js';
import TecIcon from '../obras/TecIcon.jsx';

const ROOT='/api/inventario/solicitudes-supervisor/',WRITE='/api/inventario/solicitudes-materiales/';
const STATES={PENDIENTE:['Pendiente','amber'],APROBADA:['Aprobada','green'],RECHAZADA:['Rechazada','red']};
const Q=v=>typeof v==='string'&&/^\d{1,9}\.\d{3}$/.test(v);
const num=v=>BigInt(v.replace('.',''));
const amount=(v,u)=>Q(v)?v.replace(/0+$/,'').replace(/\.$/,'').replace('.',',')+' '+u:'—';
const date=v=>new Date(v).toLocaleString('es-CL',{timeZone:'America/Santiago',hour12:false});
const operational=r=>['EN_PROCESO','SUSPENDIDA'].includes(r.obra_estado);
const canDecide=r=>r.estado==='PENDIENTE'&&operational(r);
const label=r=>STATES[r.estado]?.[0];
function valid(r,detail=false){
 if(!r||!positiveInteger(r.id)||!Object.hasOwn(STATES,r.estado)||!Q(r.cantidad_solicitada)||!(r.cantidad_aprobada===null||Q(r.cantidad_aprobada))||!(r.saldo===null||Q(r.saldo))||
 !['obra','obra_estado','material','codigo','unidad','solicitante','justificacion','motivo_decision'].every(k=>typeof r[k]==='string')||!Number.isFinite(Date.parse(r.creado_en))||
 (detail&&(!Array.isArray(r.historial)||r.historial.some(e=>!positiveInteger(e.id)||!['CREACION','APROBACION','RECHAZO'].includes(e.tipo)||!Number.isFinite(Date.parse(e.creado_en))||typeof e.actor!=='string'||typeof e.motivo!=='string'))))throw Error('Solicitud inesperada.');
 return r;
}
function Status({r}){return <span className={'chip '+STATES[r.estado][1]}>{label(r)}</span>;}
function Button({icon,children,...props}){return <button type="button" className="btn btn-outline-secondary ss-button" {...props}>{icon&&<TecIcon name={icon}/>} {children}</button>;}
function Actions({r,onChoose,disabled}){return canDecide(r)?<div className="ss-actions"><Button className="btn btn-outline-success ss-button" onClick={()=>onChoose('APROBAR')} disabled={disabled}>Aprobar</Button><Button className="btn btn-outline-danger ss-button" onClick={()=>onChoose('RECHAZAR')} disabled={disabled}>Rechazar</Button></div>:r.estado==='PENDIENTE'?<small className="commercial-help">Obra no operativa</small>:null;}
function Fact({label,children}){return <div><dt>{label}</dt><dd>{children}</dd></div>;}
export default function SupervisorSolicitudes(){
 const api=useApi(), app=useApp(), pending=useRef(false), frozen=useRef(null), uncertain=useRef(false);
 const [filter,setFilter]=useState({estado:'PENDIENTE',buscar:'',page:1}),[search,setSearch]=useState(''),[snapshot,setSnapshot]=useState(null),[revision,setRevision]=useState(0);
 const [selected,setSelected]=useState(null),[opening,setOpening]=useState(false),[decision,setDecision]=useState(null),[intent,setIntent]=useState(null),[issue,setIssue]=useState(''),[notice,setNotice]=useState('');
 const path=ROOT+'?'+new URLSearchParams(Object.entries(filter).filter(([,v])=>v!==''));
 const data=snapshot?.path===path?snapshot.data:null;
 const load=()=>api.load('list',path,v=>{
  const p=readPage(v,ROOT,25,Object.fromEntries(Object.entries(filter).filter(([k,v])=>k!=='page'&&v!=='')));
  if(!p.resumen||!['pendientes','aprobadas','rechazadas'].every(k=>Number.isSafeInteger(p.resumen[k])&&p.resumen[k]>=0))throw Error('Resumen inesperado.');
  p.results.forEach(r=>valid(r));setSnapshot({path,data:p});
 });
 useEffect(()=>{api.setError(null);setSnapshot(null);void load();return()=>api.cancelRead('list');},[path,revision]);
 const locked=!!intent||api.busy||api.locked;
 const block=app?.setNavigationBlocked;
 useEffect(()=>{block?.(locked);return()=>block?.(false);},[block,locked]);
 function change(p){api.cancelRead('list');setSnapshot(null);setFilter(old=>({...old,...p,page:p.page??1}));setRevision(v=>v+1);}
 function choose(r,kind){setIssue('');setDecision({kind,quantity:r.cantidad_solicitada.replace('.',','),reason:''});}
 async function open(r,kind){
  if(locked||opening)return;
  setOpening(true);setIssue('');setNotice('');api.setError(null);setDecision(null);
  await api.load('detail',ROOT+r.id+'/',v=>{const detail=valid(v,true);if(detail.id!==r.id)throw Error('Solicitud inesperada.');setSelected(detail);if(kind&&canDecide(detail))choose(detail,kind);});
  setOpening(false);
 }
 function back(){if(locked)return;api.cancelRead('detail');setDecision(null);setSelected(null);setIssue('');api.setError(null);}
 async function send(body,retry=false){
  if(!body||pending.current||!selected)return;
  pending.current=true;setIssue('');const id=selected.id;
  try{
   if(retry&&api.locked)await api.reconcile(async()=>true);
   const ok=await api.write(WRITE+id+'/decidir/','POST',body,async saved=>{
    if(saved?.id!==id||saved.estado!==(body.decision==='APROBAR'?'APROBADA':'RECHAZADA'))throw Error('No se pudo confirmar la decisión.');
    await api.requiredLoad('detail',ROOT+id+'/',v=>{const r=valid(v,true);if(r.id!==id||r.estado!==saved.estado)throw Error('Decisión no confirmada.');setSelected(r);});
   });
   if(ok){frozen.current=null;uncertain.current=false;setIntent(null);setDecision(null);setNotice(body.decision==='APROBAR'?'Solicitud aprobada. Bodega debe confirmar el despacho.':'Solicitud rechazada.');setFilter(old=>({...old,page:1}));setRevision(n=>n+1);}
  }finally{pending.current=false;}
 }
 useEffect(()=>{if(intent&&api.error&&(api.error.status===0||api.error.status>=500||typeof api.error.status!=='number'))uncertain.current=true;},[api.error,intent]);
 async function submit(e){
  e.preventDefault();if(!selected||!decision||frozen.current||pending.current||locked)return;
  const approved=decision.kind==='APROBAR',q=normalizeDecimalInput(decision.quantity,9,3,{positive:true,fixed:true});
  if(approved&&(!q||num(q)>num(selected.cantidad_solicitada))){setIssue('La cantidad debe ser positiva y no superar lo solicitado.');return;}
  if(!decision.reason.trim()){setIssue('Ingresa el motivo de la decisión.');return;}
  const key=globalThis.crypto?.randomUUID?.();if(!key){setIssue('No se pudo generar una clave segura.');return;}
  const body={decision:decision.kind,motivo:decision.reason.trim(),clave_idempotencia:key,...(approved?{cantidad_aprobada:q}:{})};
  frozen.current=body;setIntent(body);await send(body);
 }
 async function reviewRejected(){
  if(!intent||pending.current||uncertain.current)return;
  const id=selected.id;
  const ok=await api.reconcile(()=>api.load('detail',ROOT+id+'/',v=>{const r=valid(v,true);if(r.id!==id)throw Error('Solicitud inesperada.');setSelected(r);}));
  if(ok){frozen.current=null;setIntent(null);setDecision(null);setIssue('');setRevision(n=>n+1);}
 }
 const rejected=intent&&!uncertain.current&&[400,403,404,409,422].includes(api.error?.status);
 return <section className="commercial-page supervisor-requests">
 {notice&&<p className="alert alert-info" role="status">{notice}</p>}
 <Errors error={api.error}/>{opening&&<p role="status">Consultando solicitud…</p>}
 {selected?<><Button icon="back" className="btn btn-outline-secondary ss-button ss-back" disabled={locked} onClick={back}>Volver al listado</Button>
 <header className="ss-heading"><div><h1>{selected.material}</h1><p className="commercial-help">Solicitud #{selected.id} · {selected.codigo} · {selected.obra}</p></div><Status r={selected}/></header>
 <section className="card-fyag ss-panel"><h2>Información de la solicitud</h2><dl className="ss-summary"><Fact label="Cantidad solicitada"><strong>{amount(selected.cantidad_solicitada,selected.unidad)}</strong></Fact><Fact label="Stock físico actual"><strong>{amount(selected.saldo,selected.unidad)}</strong></Fact>{selected.estado==='APROBADA'&&<Fact label="Cantidad aprobada"><strong>{amount(selected.cantidad_aprobada,selected.unidad)}</strong></Fact>}</dl>
 <dl className="ss-facts"><Fact label="Solicitante">{selected.solicitante}</Fact><Fact label="Obra">{selected.obra}</Fact><Fact label="Fecha">{date(selected.creado_en)}</Fact></dl><div><h3>Justificación</h3><p className="ss-long">{selected.justificacion||'—'}</p></div>
 {selected.estado!=='PENDIENTE'&&<div><h3>Motivo de la decisión</h3><p className="ss-long">{selected.motivo_decision||'—'}</p><p className="commercial-help">{selected.decidido_por||'—'}{selected.decidido_en?' · '+date(selected.decidido_en):''}</p>{selected.estado==='APROBADA'&&<p className="commercial-help">Autorización #{selected.autorizacion} · La aprobación no confirma el despacho.</p>}</div>}
 {selected.estado==='PENDIENTE'&&!operational(selected)&&<p className="alert alert-warning">La obra no está operativa; no se puede decidir esta solicitud.</p>}
 {!decision&&<Actions r={selected} disabled={locked} onChoose={k=>choose(selected,k)}/>}
 {decision&&<form className="ss-decision" aria-label="Confirmar decisión" onSubmit={submit}><h2>{decision.kind==='APROBAR'?'Aprobar solicitud':'Rechazar solicitud'}</h2>
 <p className="commercial-help">{decision.kind==='APROBAR'?'Se generará una autorización para Bodega, sin reservar ni descontar stock.':'No se generará una autorización de entrega.'}</p>
 {decision.kind==='APROBAR'&&<label className="ss-field">Cantidad aprobada ({selected.unidad})<input className="form-control" id="ss-quantity" inputMode="decimal" title={quantityHint} required value={decision.quantity} disabled={locked} onChange={e=>setDecision({...decision,quantity:e.target.value})}/></label>}
 <label className="ss-field">Motivo de la decisión<textarea className="form-control" id="ss-reason" rows={3} required maxLength={2000} value={decision.reason} disabled={locked} onChange={e=>setDecision({...decision,reason:e.target.value})}/></label>
 {issue&&<p role="alert" className="alert alert-warning">{issue}</p>}
 {intent?<><p role="status" className="commercial-help">Se conserva la decisión original hasta confirmar su resultado.</p><div className="ss-actions"><Button disabled={api.busy} onClick={()=>void send(frozen.current,true)}>Reintentar misma decisión</Button>{rejected&&<Button disabled={api.busy} onClick={()=>void reviewRejected()}>Reconsultar solicitud</Button>}</div></>:<div className="ss-actions"><Button onClick={()=>{setDecision(null);setIssue('');}}>Cancelar</Button><button type="submit" className={'btn ss-button '+(decision.kind==='APROBAR'?'btn-fyag-primary':'btn-outline-danger')}>Confirmar {decision.kind==='APROBAR'?'aprobación':'rechazo'}</button></div>}</form>}
 </section><section className="card-fyag ss-panel"><h2>Historial</h2>{selected.historial.length?<ol className="commercial-timeline">{selected.historial.map(e=><li key={e.id}><strong>{{CREACION:'Solicitud creada',APROBACION:'Aprobación',RECHAZO:'Rechazo'}[e.tipo]}</strong><div className="commercial-help">{date(e.creado_en)} · {e.actor}</div><p className="ss-long">{e.motivo}</p></li>)}</ol>:<p className="commercial-help">Sin eventos registrados.</p>}</section></>:<>
 <PageHead title="Solicitudes de materiales"><Button icon="refresh" disabled={api.loading} onClick={()=>change({page:filter.page})}>Actualizar</Button></PageHead>
 <div className="ss-kpis">{[['PENDIENTE','Pendientes','pendientes'],['APROBADA','Aprobadas','aprobadas'],['RECHAZADA','Rechazadas','rechazadas']].map(([k,title,key])=><button type="button" className="card-fyag ss-kpi" key={k} data-state={k} aria-pressed={filter.estado===k} onClick={()=>change({estado:k})}><span>{title}</span><strong>{data?.resumen[key]??'—'}</strong></button>)}</div>
 <section className="card-fyag ss-panel"><div className="ss-heading"><div><h2>{filter.estado?({PENDIENTE:'Solicitudes pendientes',APROBADA:'Solicitudes aprobadas',RECHAZADA:'Solicitudes rechazadas'})[filter.estado]:'Todas las solicitudes'}</h2><span className="commercial-help">{data?data.count+' registros':'—'}</span></div></div>
 <form className="ss-toolbar" onSubmit={e=>{e.preventDefault();change({buscar:search.trim()});}}><div className="ss-search"><input className="form-control" aria-label="Buscar solicitud" placeholder="Material, código, obra o solicitante" maxLength={150} value={search} onChange={e=>setSearch(e.target.value)}/><button className="btn btn-outline-secondary ss-button" type="submit"><TecIcon name="search"/>Buscar</button></div><select className="form-select" aria-label="Estado de solicitud" value={filter.estado} onChange={e=>change({estado:e.target.value})}><option value="">Todas</option>{Object.entries(STATES).map(([k,[name]])=><option key={k} value={k}>{k==='PENDIENTE'?'Pendientes':name+'s'}</option>)}</select>{filter.buscar&&<Button onClick={()=>{setSearch('');change({buscar:''});}}>Limpiar búsqueda</Button>}</form>
 {api.loading&&!opening&&<p role="status">Consultando solicitudes…</p>}
 {data&&(data.results.length?<div className="table-responsive" role="region" aria-label="Solicitudes de materiales" tabIndex={0}><table className="table table-hover align-middle commercial-table ss-table"><thead><tr>{['Material / Obra','Solicitante','Cantidad solicitada','Estado','Acciones'].map(h=><th key={h} scope="col">{h}</th>)}</tr></thead><tbody>{data.results.map(r=><tr key={r.id}><td><strong>{r.material}</strong><small className="commercial-help d-block">{r.codigo} · {r.obra} · #{r.id}</small></td><td>{r.solicitante}<small className="commercial-help d-block">{date(r.creado_en)}</small></td><td><strong>{amount(r.cantidad_solicitada,r.unidad)}</strong></td><td><Status r={r}/></td><td><div className="ss-actions"><Actions r={r} disabled={opening} onChoose={kind=>void open(r,kind)}/><Button disabled={opening} onClick={()=>void open(r)}>{canDecide(r)?'Ver':'Ver detalle'}<TecIcon name="chevron"/></Button></div></td></tr>)}</tbody></table></div>:<div className="ss-empty" role="status"><TecIcon name="inbox"/><strong>{filter.estado==='PENDIENTE'&&!filter.buscar?'No hay solicitudes pendientes':'No hay solicitudes para mostrar'}</strong><p className="commercial-help">Puedes consultar otros estados o modificar la búsqueda.</p></div>)}
 {data&&(data.next||data.previous)&&<Pager data={data} page={filter.page} setPage={page=>change({page})} disabled={api.loading||opening}/>}</section></>}
 </section>;
}
