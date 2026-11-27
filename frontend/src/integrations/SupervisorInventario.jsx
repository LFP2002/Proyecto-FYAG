import React,{useEffect,useState} from 'react';
import {PageHead} from '../components/ui/index.js';
import {Errors,Pager} from '../comercial/ui.jsx';
import {useApi,readPage,positiveInteger,strictObject} from './useApi.js';
import TecIcon from '../obras/TecIcon.jsx';
import '../styles/pages/inventario-supervisor.css';

const ROOT='/api/inventario/disponibilidad/';
const TABS=[['disponibilidad','Disponibilidad'],['pendientes','Pendientes de despacho'],['historial','Entregas y devoluciones']];
const VIEWS=[['','Todas las realizadas'],['entregas','Entregas realizadas'],['devoluciones','Devoluciones recibidas'],['por_recibir','Devoluciones por recibir']];
const INITIAL={seccion:'disponibilidad',buscar:'',stock:'',vista:'',page:1};
const qty=v=>typeof v==='string'&&/^\d+\.\d{3}$/.test(v);
const amount=(v,u)=>qty(v)?v.replace(/0+$/,'').replace(/\.$/,'').replace('.',',')+' '+u:'—';
const count=v=>Number.isSafeInteger(v)&&v>=0;
const stamp=v=>new Intl.DateTimeFormat('es-CL',{timeZone:'America/Santiago',day:'2-digit',month:'2-digit',year:'numeric',hour:'2-digit',minute:'2-digit',hour12:false}).format(new Date(v));
const params=q=>Object.fromEntries(Object.entries(q).filter(([k,v])=>v!==''&&k!=='page'));
function validate(v,q){
 const p=readPage(v,ROOT,25,params(q));
 strictObject(p.resumen,['disponibles','sin_stock','despachos_pendientes']);
 if(!Object.values(p.resumen).every(count))throw Error('Indicadores inesperados.');
 const stock=q.seccion==='disponibilidad',pending=q.seccion==='pendientes'||q.vista==='por_recibir';
 for(const r of p.results){
  const common=['id','articulo','codigo','nombre','unidad'];
  strictObject(r,stock?[...common,'activo','descripcion','saldo']:[...common,'tipo','obra','cantidad','referencia','motivo','creado_en','origen',...(pending?['ejecutada','pendiente','saldo','bloqueo']:[])]);
  if(!positiveInteger(r.id)||!positiveInteger(r.articulo)||!['nombre','codigo','unidad'].every(k=>typeof r[k]==='string'))throw Error('Material inesperado.');
  if(stock){if(r.id!==r.articulo||r.activo!==true||typeof r.descripcion!=='string'||!(r.saldo===null||qty(r.saldo)))throw Error('Existencia inesperada.');}
  else {
   const types=q.seccion==='pendientes'?['AUTORIZACION_ENTREGA']:q.vista==='por_recibir'?['AUTORIZACION_DEVOLUCION']:q.vista==='entregas'?['ENTREGA']:q.vista==='devoluciones'?['DEVOLUCION']:['ENTREGA','DEVOLUCION'];
   if(!types.includes(r.tipo)||!qty(r.cantidad)||typeof r.obra!=='string'||!Number.isFinite(Date.parse(r.creado_en))||!['referencia','motivo'].every(k=>typeof r[k]==='string')||!['PRESUPUESTO','SOLICITUD','SIN_VINCULO_PRESUPUESTARIO'].includes(r.origen))throw Error('Registro inesperado.');
   if(pending&&(!qty(r.ejecutada)||!qty(r.pendiente)||r.pendiente==='0.000'||!(r.saldo===null||qty(r.saldo))||!(r.bloqueo===null||typeof r.bloqueo==='string')))throw Error('Remanente inesperado.');
  }
 }
 return p;
}
function Button({icon,children,...props}){return <button type="button" className="btn btn-outline-secondary si-button" {...props}>{icon&&<TecIcon name={icon}/>} {children}</button>;}
function Material({r}){return <div className="si-material"><strong>{r.nombre}</strong><small>{r.codigo}</small></div>;}
function state(r){
 if('activo' in r)return r.saldo===null?['Stock no confirmado','gray']:r.saldo==='0.000'?['Sin stock','red']:['Disponible','green'];
 if(r.tipo==='ENTREGA')return ['Entregado','green'];
 if(r.tipo==='DEVOLUCION')return ['Devuelto','green'];
 return [r.ejecutada==='0.000'?'Pendiente':r.tipo==='AUTORIZACION_ENTREGA'?'Despacho parcial':'Recepción parcial','amber'];
}
function State({r}){const [label,tone]=state(r);return <span className={'chip '+tone}>{label}</span>;}
function Fact({label,children}){return <div><dt>{label}</dt><dd>{children}</dd></div>;}
function Detail({r,onBack}){
 const stock='activo' in r,pending='pendiente' in r;
 return <><Button icon="back" className="btn btn-outline-secondary si-back si-button" onClick={onBack}>Volver al listado</Button>
 <section className="card-fyag si-panel si-detail"><div className="si-heading"><div><p className="commercial-help">{stock?'Ficha del material':r.obra}</p><h2>{r.nombre}</h2><p className="commercial-help">{r.codigo}</p></div><State r={r}/></div>
 <div className="si-summary"><div><span>{stock?'Existencias físicas':pending?'Cantidad autorizada':'Cantidad registrada'}</span><strong>{amount(stock?r.saldo:r.cantidad,r.unidad)}</strong></div>{pending&&<><div><span>{r.tipo==='AUTORIZACION_ENTREGA'?'Despachado':'Recibido'}</span><strong>{amount(r.ejecutada,r.unidad)}</strong></div><div><span>{r.tipo==='AUTORIZACION_ENTREGA'?'Pendiente de despacho':'Pendiente de recepción'}</span><strong>{amount(r.pendiente,r.unidad)}</strong></div></>}</div>
 {pending&&r.bloqueo&&<p className="alert alert-warning" role="status">{r.bloqueo}</p>}
 <h3>{stock?'Información del material':'Información del registro'}</h3><dl className="si-facts"><Fact label="Unidad de medida">{r.unidad}</Fact>{stock?<Fact label="Descripción">{r.descripcion||'Sin descripción registrada'}</Fact>:<><Fact label="Obra">{r.obra}</Fact><Fact label="Fecha">{stamp(r.creado_en)}</Fact><Fact label="Origen">{{PRESUPUESTO:'Presupuesto',SOLICITUD:'Solicitud aprobada',SIN_VINCULO_PRESUPUESTARIO:'Sin vínculo presupuestario'}[r.origen]}</Fact><Fact label="Referencia">{r.referencia||'—'}</Fact><Fact label="Motivo">{r.motivo||'—'}</Fact></>}</dl>
 {stock&&<p className="commercial-help">Las existencias físicas no están reservadas para una obra. La entrega efectiva se confirma en Bodega.</p>}
 </section></>;
}
export default function SupervisorInventario(){
 const api=useApi(),[q,setQ]=useState(INITIAL),[draft,setDraft]=useState(''),[snapshot,setSnapshot]=useState(null),[selected,setSelected]=useState(null),[revision,setRevision]=useState(0);
 const path=ROOT+'?'+new URLSearchParams({...params(q),page:String(q.page)});
 const data=snapshot?.path===path?snapshot.data:null;
 const load=()=>{setSnapshot(null);return api.load('list',path,v=>setSnapshot({path,data:validate(v,q)}));};
 useEffect(()=>{api.setError(null);void load();return()=>api.cancelRead('list');},[path,revision]);
 function change(patch,reset=false){api.cancelRead('list');setSnapshot(null);setSelected(null);setQ(old=>({... (reset?INITIAL:old),...patch,page:patch.page??1}));setRevision(v=>v+1);}
 function tab(section,stock=''){setDraft('');change({seccion:section,stock},true);}
 function search(e){e.preventDefault();change({buscar:draft.trim()});}
 const stock=q.seccion==='disponibilidad',pending=q.seccion==='pendientes'||q.vista==='por_recibir';
 return <section className="commercial-page supervisor-inventory">
 {selected?<Detail r={selected} onBack={()=>setSelected(null)}/>:<>
 <PageHead title="Disponibilidad de materiales"><Button icon="refresh" disabled={api.loading} onClick={()=>void api.reconcile(load)}>Actualizar</Button></PageHead>
 <div className="si-kpis">{[['Materiales disponibles','disponibles','green','disponibilidad','con_stock'],['Materiales sin stock','sin_stock','red','disponibilidad','sin_stock'],['Despachos pendientes','despachos_pendientes','amber','pendientes','']].map(([label,key,tone,section,filter])=><button type="button" key={key} className="card-fyag si-kpi" data-tone={tone} aria-pressed={q.seccion===section&&q.stock===filter&&!q.buscar} disabled={!data} onClick={()=>tab(section,filter)}><span>{label}</span><strong>{data?.resumen[key]??'—'}</strong>{key==='despachos_pendientes'&&<small>Autorizaciones con saldo pendiente</small>}</button>)}</div>
 <div className="si-tabs" role="group" aria-label="Secciones de materiales">{TABS.map(([key,label])=><button type="button" key={key} aria-pressed={q.seccion===key} onClick={()=>tab(key)}>{label}</button>)}</div>
 <Errors error={api.error}/>{api.loading&&<p role="status">Consultando materiales…</p>}
 <section className="card-fyag si-panel"><div className="si-heading"><div><h2>{stock?'Existencias de materiales':q.seccion==='pendientes'?'Despachos pendientes':'Entregas y devoluciones'}</h2><span className="commercial-help">{data?data.count+' registros':'—'}</span></div></div>
 <form className="si-toolbar si-query" onSubmit={search}><div className="si-search-group"><input aria-label="Buscar material" className="form-control si-search" value={draft} maxLength={150} placeholder={stock?'Nombre o código del material':'Material, código u obra'} onChange={e=>setDraft(e.target.value)}/><button type="submit" className="btn btn-outline-secondary si-button"><TecIcon name="search"/>Buscar</button></div>
 {stock?<label className="si-field"><span className="visually-hidden">Disponibilidad</span><select className="form-select" aria-label="Disponibilidad" value={q.stock} onChange={e=>change({stock:e.target.value})}><option value="">Todos los materiales activos</option><option value="con_stock">Con stock</option><option value="sin_stock">Sin stock</option></select></label>:q.seccion==='historial'?<label className="si-field"><span className="visually-hidden">Tipo de registro</span><select className="form-select" aria-label="Tipo de registro" value={q.vista} onChange={e=>change({vista:e.target.value})}>{VIEWS.map(([k,v])=><option key={k} value={k}>{v}</option>)}</select></label>:null}
 {(q.buscar||q.stock||q.vista)&&<Button onClick={()=>{setDraft('');change({buscar:'',stock:'',vista:''});}}>Limpiar filtros</Button>}</form>
 {stock&&<p className="commercial-help">Stock físico sin reserva. La disponibilidad no garantiza el despacho a una obra.</p>}
 {data&&(data.results.length?<div className="table-responsive" role="region" aria-label={TABS.find(t=>t[0]===q.seccion)[1]} tabIndex={0}><table className="table table-hover align-middle commercial-table si-table"><thead><tr>{(stock?['Material','Stock','Disponibilidad','Detalle']:['Material / Obra',pending?'Cantidad pendiente':'Cantidad','Estado','Detalle']).map(h=><th key={h} scope="col">{h}</th>)}</tr></thead><tbody>{data.results.map(r=><tr key={r.id}><td><Material r={r}/>{!stock&&<small className="commercial-help d-block">{r.obra}</small>}</td><td><strong className="si-stock">{amount(stock?r.saldo:pending?r.pendiente:r.cantidad,r.unidad)}</strong>{pending&&<small className="commercial-help d-block">De {amount(r.cantidad,r.unidad)} autorizados</small>}</td><td><State r={r}/>{r.bloqueo&&<small className="si-blockage">{r.bloqueo}</small>}</td><td><Button onClick={()=>setSelected(r)}>Ver detalle<TecIcon name="chevron"/></Button></td></tr>)}</tbody></table></div>:<div className="si-empty" role="status"><TecIcon name="inbox"/><strong>No hay registros para mostrar</strong><p>{q.buscar||q.stock||q.vista?'Prueba con otros filtros.':'No hay registros en esta sección.'}</p></div>)}
 {data&&(data.next||data.previous)&&<Pager data={data} page={q.page} setPage={page=>change({page})} disabled={api.loading} label="Paginación de materiales"/>}
 </section></>}
 </section>;
}
