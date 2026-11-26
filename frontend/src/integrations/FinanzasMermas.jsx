import React,{useEffect,useRef,useState} from 'react';
import {PageHead} from '../components/ui/index.js';
import {useApp} from '../context/AppContext.jsx';
import {Errors,Pager} from '../comercial/ui.jsx';
import {useApi,readPage,positiveInteger,decimalString} from './useApi.js';
import {formatCompactCLP} from '../utils/format.js';
import TecIcon from '../obras/TecIcon.jsx';
import '../styles/pages/inventario-finanzas.css';
import '../styles/pages/mermas-finanzas.css';

const BASE='/api/inventario/mermas-bodega/';
const TYPES={DANO:'Daño',VENCIMIENTO:'Vencimiento',EXTRAVIO:'Extravío',DIFERENCIA_CONTEO:'Diferencia de conteo',OTRA:'Otra'};
const STATES={PENDIENTE:'Pendiente',APROBADA:'Aprobada',RECHAZADA:'Rechazada'};
const CHIPS={PENDIENTE:'amber',APROBADA:'green',RECHAZADA:'red'};
const EVENTS={CREACION:'Merma informada',APROBACION:'Merma aprobada',RECHAZO:'Merma rechazada'};
const EMPTY={buscar:'',estado:'',tipo:''};
const money=v=>v==null?'—':formatCompactCLP(v);
const quantity=r=>r.cantidad.replace(/(\.\d*?)0+$/,'$1').replace(/\.$/,'').replace('.',',')+' '+({unidad:r.cantidad==='1.000'?'unidad':'unidades',litro:r.cantidad==='1.000'?'litro':'litros'}[r.unidad]||r.unidad);
const stamp=v=>v?new Intl.DateTimeFormat('es-CL',{timeZone:'America/Santiago',day:'2-digit',month:'2-digit',year:'numeric',hour:'2-digit',minute:'2-digit'}).format(new Date(v)):'—';
const invalid=()=>{throw Error('El servidor devolvió datos de mermas inesperados.');};
const count=v=>Number.isSafeInteger(v)&&v>=0;
const validDate=v=>typeof v==='string'&&Number.isFinite(Date.parse(v));
function validateRow(r,detail=false){
 if(!r||!positiveInteger(r.id)||r.ambito!=='BODEGA'||!positiveInteger(r.articulo)||!Object.hasOwn(STATES,r.estado)||!Object.hasOwn(TYPES,r.tipo)||!['articulo_nombre','articulo_codigo','informado_nombre','unidad','motivo','referencia','motivo_decision'].every(k=>typeof r[k]==='string')||!(/^\d+\.\d{3}$/.test(r.cantidad)&&typeof r.cantidad==='string')||!validDate(r.creado_en))invalid();
 if(r.estado==='APROBADA'?(!decimalString(r.importe_perdida)||!decimalString(r.costo_unitario_neto)):(r.importe_perdida!==null||r.costo_unitario_neto!==null))invalid();
 if(r.estado==='PENDIENTE'?(r.decidido_nombre!==null||r.decidido_en!==null):typeof r.decidido_nombre!=='string'||!validDate(r.decidido_en))invalid();
 if(detail&&(!Array.isArray(r.historial)||r.historial.length<1||r.historial.length>2||r.historial.some(e=>!positiveInteger(e.id)||!positiveInteger(e.actor)||!Object.hasOwn(EVENTS,e.tipo)||!validDate(e.creado_en)||typeof e.motivo!=='string')))invalid();
 return r;
}
function validatePage(v,p){
 const data=readPage(v,BASE,25,p);
 if(!data.resumen||!['pendientes','aprobadas','rechazadas'].every(k=>count(data.resumen[k]))||!decimalString(data.resumen.perdida_neta))invalid();
 data.results.forEach(r=>validateRow(r));
 return data;
}
function Btn({icon,children,...props}){return <button type="button" className="btn btn-outline-secondary" {...props}>{icon&&<TecIcon name={icon}/>} {children}</button>;}
function State({r}){return <span className={'chip '+CHIPS[r.estado]}>{STATES[r.estado]}</span>;}
function Metric({label,value,tone='neutral'}){return <div className="portfolio-kpi if-metric" data-tone={tone}><span>{label}</span><strong>{value}</strong></div>;}
function Fact({label,value}){return <div><dt>{label}</dt><dd>{value||'—'}</dd></div>;}
function Empty({title,description}){return <div className="if-empty" role="status"><TecIcon name="inbox"/><strong>{title}</strong><p>{description}</p></div>;}
export default function FinanzasMermas(){
 const api=useApi(),app=useApp(),inFlight=useRef(false);
 const [draft,setDraft]=useState(EMPTY),[filters,setFilters]=useState(EMPTY),[page,setPage]=useState(1),[open,setOpen]=useState(false),[snapshot,setSnapshot]=useState(null);
 const [selected,setSelected]=useState(null),[detail,setDetail]=useState(null),[decision,setDecision]=useState(null),[msg,setMsg]=useState('');
 const p={vista:'finanzas',...Object.fromEntries(Object.entries(filters).filter(([,v])=>v))};
 const path=BASE+'?'+new URLSearchParams({...p,page}),data=snapshot?.path===path?snapshot.data:null;
 const blocked=api.busy||api.locked,disabled=blocked||api.loading;
 const nav=app?.setNavigationBlocked;
 useEffect(()=>{nav?.(blocked);return ()=>nav?.(false);},[blocked,nav]);
 function readList(){setSnapshot(null);return api.load('mermas-af-list',path,v=>setSnapshot({path,data:validatePage(v,p)}));}
 function readDetail(id=selected,accept=()=>{}){return api.load('mermas-af-detail',BASE+id+'/?vista=finanzas',v=>{const r=validateRow(v,true);if(r.id!==id)invalid();setDetail(r);accept(r);});}
 useEffect(()=>{api.setError(null);if(selected===null)void readList();else void readDetail();return ()=>{api.cancelRead('mermas-af-list');api.cancelRead('mermas-af-detail');};},[path,selected]);
 function inspect(r){if(disabled)return;setSelected(r.id);setDetail(null);setDecision(null);setMsg('');}
 function back(){if(blocked)return;setSelected(null);setDetail(null);setDecision(null);setMsg('');}
 function setState(estado){if(disabled)return;setDraft(d=>({...d,estado}));setFilters(f=>({...f,estado}));setPage(1);setMsg('');}
 function apply(e){e.preventDefault();if(disabled)return;setFilters({...draft,buscar:draft.buscar.trim()});setPage(1);setMsg('');}
 function clear(){setDraft(EMPTY);setFilters(EMPTY);setPage(1);setMsg('');}
 function begin(kind){if(disabled||detail?.estado!=='PENDIENTE')return;setDecision({kind,motivo:'',clave_idempotencia:crypto.randomUUID()});setMsg('');api.setError(null);}
 async function refresh(){
  if(api.busy||api.loading)return;
  const conflict=api.error?.status===409;
  setMsg('');
  if(selected===null){api.setError(null);await readList();return;}
  if(!api.locked){api.setError(null);await readDetail(selected,r=>{if(r.estado!=='PENDIENTE')setDecision(null);});return;}
  await api.reconcile(async()=>{
   let current;
   if(!await readDetail(selected,r=>{current=r;}))return false;
   if(current.estado!=='PENDIENTE'||conflict){setDecision(null);setMsg(current.estado==='PENDIENTE'?'La merma continúa pendiente. Revisa el conflicto antes de intentar otra decisión.':'Se confirmó el estado actual de la merma.');return true;}
   setMsg('La merma sigue pendiente. Reintenta únicamente la misma decisión con los mismos datos.');
   return false;
  });
 }
 async function save(e,retry=false){
  e?.preventDefault();if(!decision||!detail||inFlight.current||api.busy||api.loading||(!retry&&api.locked)||detail.estado!=='PENDIENTE')return;
  const motivo=decision.motivo.trim();
  if(!motivo||motivo.length>2000||/[\u0000-\u001f\u007f-\u009f]/.test(motivo)){setMsg('Escribe un motivo válido, sin saltos de línea ni caracteres de control.');return;}
  const body={decision:decision.kind,motivo,clave_idempotencia:decision.clave_idempotencia},id=selected;
  const expected=decision.kind==='APROBAR'?'APROBADA':'RECHAZADA';
  inFlight.current=true;setMsg('');
  try{
   if(retry&&!await api.reconcile(()=>Promise.resolve(true)))return;
   await api.write(BASE+id+'/decidir/','POST',body,async v=>{
    if(v?.id!==id||v.estado!==expected)invalid();
    await api.requiredLoad('mermas-af-confirm',BASE+id+'/?vista=finanzas',x=>{const r=validateRow(x,true);if(r.id!==id||r.estado!==expected)invalid();setDetail(r);});
    setDecision(null);setMsg('Decisión registrada y confirmada.');
   });
  }finally{inFlight.current=false;}
 }
 const summary=data?.resumen;
 return <section className="commercial-page manager-portfolio finance-inventory finance-mermas">
 <PageHead title="Mermas de bodega" sub="Revisa y administra las pérdidas de materiales informadas."><Btn icon="refresh" disabled={api.busy||api.loading} onClick={()=>void refresh()}>Actualizar</Btn></PageHead>
 <Errors error={api.error}/>{msg&&<p className="alert alert-info" role="status">{msg}</p>}{api.loading&&<p role="status">Cargando mermas…</p>}
 {selected===null?<><div className="portfolio-kpis if-kpis">
 <Metric label="Pendientes de revisión" value={summary?.pendientes??'—'} tone={summary?.pendientes>0?'warning':'neutral'}/>
 <Metric label="Aprobadas" value={summary?.aprobadas??'—'}/>
 <Metric label="Rechazadas" value={summary?.rechazadas??'—'}/>
 <Metric label="Pérdidas valorizadas · CLP neto" value={money(summary?.perdida_neta)} tone={summary?.perdida_neta&&summary.perdida_neta!=='0.00'?'danger':'neutral'}/>
 </div><p className="commercial-help">Totales de todas las mermas de bodega. Solo las aprobadas integran la pérdida económica.</p>
 <nav className="manager-work-tabs" aria-label="Estado de las mermas">{[['','Todas'],['PENDIENTE','Pendientes'],['APROBADA','Aprobadas'],['RECHAZADA','Rechazadas']].map(([k,l])=><button type="button" key={k} disabled={disabled} aria-pressed={filters.estado===k} onClick={()=>setState(k)}>{l}</button>)}</nav>
 <section className="card-fyag portfolio-list"><div className="portfolio-list-head"><div><h2>Registro de mermas</h2><span>{data?data.count+' registros':'—'}</span></div><Btn icon="filter" aria-expanded={open} onClick={()=>setOpen(x=>!x)}>Filtros</Btn></div>
 <form className="if-filter" aria-label="Buscar mermas" onSubmit={apply}><div className="if-toolbar"><label className="form-label if-search">Buscar material<input className="form-control" maxLength={150} value={draft.buscar} placeholder="Nombre o código del material" onChange={e=>setDraft({...draft,buscar:e.target.value})}/></label><button className="btn btn-fyag-primary" disabled={disabled}>Buscar</button>{Object.values(draft).some(Boolean)&&<Btn disabled={disabled} onClick={clear}>Limpiar filtros</Btn>}</div>
 {open&&<div className="if-fields if-advanced"><label className="form-label">Tipo de merma<select className="form-select" value={draft.tipo} onChange={e=>setDraft({...draft,tipo:e.target.value})}><option value="">Todos</option>{Object.entries(TYPES).map(([k,l])=><option key={k} value={k}>{l}</option>)}</select></label><button className="btn btn-outline-secondary" disabled={disabled}>Aplicar filtros</button></div>}</form>
 {data?.results.length>0&&<div className="table-responsive" role="region" aria-label="Registro de mermas" tabIndex={0}><table className="table commercial-table if-table mf-table"><thead><tr>{['Material','Cantidad','Tipo','Fecha del reporte','Pérdida neta CLP','Estado','Detalle'].map((h,i)=><th scope="col" key={h} className={i===4?'if-money':undefined}>{h}</th>)}</tr></thead><tbody>{data.results.map(r=><tr key={r.id}><td><strong>{r.articulo_nombre}</strong><small className="commercial-help d-block">{r.articulo_codigo}</small></td><td className="mf-qty">{quantity(r)}</td><td>{TYPES[r.tipo]}</td><td>{stamp(r.creado_en)}</td><td className="if-money"><strong>{money(r.importe_perdida)}</strong>{r.estado==='PENDIENTE'&&<small className="commercial-help d-block">Por determinar</small>}</td><td><State r={r}/></td><td><button type="button" className={'btn '+(r.estado==='PENDIENTE'?'btn-fyag-primary':'btn-outline-secondary')} disabled={disabled} onClick={()=>inspect(r)}>{r.estado==='PENDIENTE'?'Revisar':'Ver detalle'}</button></td></tr>)}</tbody></table></div>}
 {data&&!data.count&&<Empty title={Object.values(filters).some(Boolean)?(filters.estado==='PENDIENTE'&&!filters.buscar&&!filters.tipo?'No hay mermas pendientes':'No hay resultados'):'No hay mermas registradas'} description={Object.values(filters).some(Boolean)?'Puedes cambiar o limpiar los filtros para consultar otros reportes.':'Los reportes informados por Bodega aparecerán aquí.'}/>}
 {data&&(data.next||data.previous)&&<Pager data={data} page={page} setPage={setPage} disabled={disabled} label="Paginación de mermas"/>}
 {api.error&&<div className="if-retry">{page>1&&api.error.status===404?<Btn onClick={()=>setPage(1)}>Volver a la primera página</Btn>:<Btn disabled={disabled} onClick={()=>void refresh()}>Reintentar consulta</Btn>}</div>}
 </section></>:<><Btn icon="back" className="btn btn-outline-secondary if-back" disabled={blocked} onClick={back}>Volver a mermas</Btn>
 {detail&&<><section className="card-fyag if-panel if-record-detail"><header className="if-heading"><div><p className="commercial-help">Merma de bodega · N.º {detail.id}</p><h2>{detail.articulo_nombre}</h2><p className="commercial-help">{detail.articulo_codigo} · {TYPES[detail.tipo]}</p></div><State r={detail}/></header>
 <div className="if-detail-summary"><div><span>Cantidad informada</span><strong>{quantity(detail)}</strong></div><div><span>Costo unitario neto</span><strong className="if-secondary-value">{money(detail.costo_unitario_neto)}</strong><small>{detail.estado==='PENDIENTE'?'Por determinar':detail.estado==='RECHAZADA'?'No aplica':'CLP · por '+detail.unidad}</small></div><div><span>Pérdida económica</span><strong className={detail.estado==='APROBADA'?'if-negative':undefined}>{money(detail.importe_perdida)}</strong><small>{detail.estado==='PENDIENTE'?'Se determina al aprobar la merma':detail.estado==='RECHAZADA'?'Sin pérdida registrada por esta merma':'CLP · neto confirmado'}</small></div></div>
 <div className="if-detail-info"><h3>Información del reporte</h3><dl className="if-facts"><Fact label="Tipo de merma" value={TYPES[detail.tipo]}/><Fact label="Informado por" value={detail.informado_nombre}/><Fact label="Fecha del reporte" value={stamp(detail.creado_en)}/><Fact label="Referencia de respaldo" value={detail.referencia||'Sin referencia registrada'}/><div className="mf-wide"><dt>Motivo informado</dt><dd>{detail.motivo}</dd></div></dl></div>
 {detail.estado!=='PENDIENTE'&&<div className="if-detail-info if-detail-divider"><h3>Decisión registrada</h3><dl className="if-facts"><Fact label="Decidido por" value={detail.decidido_nombre}/><Fact label="Fecha de decisión" value={stamp(detail.decidido_en)}/><Fact label="Motivo de la decisión" value={detail.motivo_decision}/></dl></div>}
 {detail.estado==='PENDIENTE'&&<div className="mf-resolution"><h3>Resolver reporte</h3>
 {!decision?<><p className="commercial-help">Revisa la información antes de decidir. La aprobación está sujeta a las existencias, la vigencia del reporte y la valoración actual.</p><div className="if-toolbar mf-actions"><button type="button" className="btn btn-outline-danger" disabled={disabled} onClick={()=>begin('RECHAZAR')}>Rechazar merma</button><button type="button" className="btn btn-fyag-primary" disabled={disabled} onClick={()=>begin('APROBAR')}>Aprobar merma</button></div></>:<form aria-label="Confirmar decisión de merma" onSubmit={save}>
 <h3>{decision.kind==='APROBAR'?'Aprobar merma':'Rechazar merma'}</h3><p className="mf-warning"><TecIcon name="warning"/> {decision.kind==='APROBAR'?'La aprobación descontará existencias y registrará la pérdida económica si el backend confirma las condiciones.':'El rechazo no descontará existencias ni registrará una pérdida.'} La decisión es irreversible.</p>
 <label className="form-label">Motivo de la decisión<input className="form-control" required maxLength={2000} disabled={blocked} placeholder="Describe el motivo de tu decisión" value={decision.motivo} onChange={e=>setDecision({...decision,motivo:e.target.value})}/></label>
 <div className="if-footer">{api.locked?<><p role="alert">La decisión no pudo confirmarse. Actualiza para verificar el estado o reintenta con la misma solicitud.</p><button type="button" className="btn btn-fyag-primary" disabled={api.busy||api.loading} onClick={()=>void save(null,true)}>Confirmar decisión pendiente</button></>:<><Btn disabled={disabled} onClick={()=>setDecision(null)}>Cancelar</Btn><button className={'btn '+(decision.kind==='APROBAR'?'btn-fyag-primary':'btn-outline-danger')} disabled={disabled||!decision.motivo.trim()}>{decision.kind==='APROBAR'?'Confirmar aprobación':'Confirmar rechazo'}</button></>}</div>
 </form>}</div>}
 </section><section className="card-fyag if-panel if-record-detail"><h3>Historial de actividad</h3><ol className="commercial-timeline mf-history">{detail.historial.map(e=><li key={e.id}><strong>{EVENTS[e.tipo]}</strong><p className="commercial-help">{stamp(e.creado_en)} · {e.tipo==='CREACION'?detail.informado_nombre:detail.decidido_nombre}</p><p>{e.motivo}</p></li>)}</ol></section></>}
 {!detail&&!api.loading&&api.error&&<Empty title="No se pudo consultar la merma" description="Pulsa Actualizar para volver a intentar la consulta."/>}</>}
 </section>;
}
