import React,{useEffect,useRef,useState} from 'react';
import {PageHead} from '../components/ui/index.js';
import {useApp} from '../context/AppContext.jsx';
import {Errors,Pager} from '../comercial/ui.jsx';
import {useApi,readPage,positiveInteger,decimalString} from './useApi.js';
import {civilRange} from './dates.js';
import {formatCompactCLP} from '../utils/format.js';
import TecIcon from '../obras/TecIcon.jsx';
import '../styles/pages/inventario-finanzas.css';

const ROOT='/api/inventario/',BASE=ROOT+'finanzas/';
const TABS=[['inventario','Inventario'],['movimientos','Movimientos'],['valoraciones','Valoración'],['regularizaciones','Saldo inicial']];
const LABELS={inventario:'Materiales y existencias',movimientos:'Historial de movimientos',valoraciones:'Costos de adquisición',regularizaciones:'Regularizaciones de saldo inicial',ingresos:'Ingresos disponibles para valorizar',historicos:'Saldos históricos por regularizar'};
const TYPES={INGRESO:'Ingreso',SALIDA:'Salida',DEVOLUCION:'Devolución',MERMA:'Merma',VALORIZACION:'Valoración',REGULARIZACION:'Regularización'};
const EMPTY={buscar:'',filtro:'',tipo:'',desde:'',hasta:''};
const qty=v=>v===null?'—':String(v).replace(/(\.\d*?)0+$/,'$1').replace(/\.$/,'').replace('.',',');
const amount=v=>v===null||v===undefined?'—':formatCompactCLP(v);
const stamp=v=>v?new Intl.DateTimeFormat('es-CL',{timeZone:'America/Santiago',day:'2-digit',month:'2-digit',year:'numeric',hour:'2-digit',minute:'2-digit'}).format(new Date(v)):'—';
const isQty=v=>typeof v==='string'&&/^\d+\.\d{3}$/.test(v);
const count=v=>Number.isSafeInteger(v)&&v>=0;
const fail=()=>{throw Error('El servidor devolvió datos de inventario inesperados.');};
const candidate=s=>s==='ingresos'||s==='historicos';
const parent=s=>s==='ingresos'?'valoraciones':s==='historicos'?'regularizaciones':s;
function paramsFor(section,filters){const p={seccion:section};if(filters.buscar)p.buscar=filters.buscar;if(section==='inventario'&&filters.filtro)p.filtro=filters.filtro;if(section==='movimientos')for(const k of ['tipo','desde','hasta'])if(filters[k])p[k]=filters[k];return p;}
const url=(p,page)=>BASE+'?'+new URLSearchParams({...p,page});
function validate(v,p){
 const data=readPage(v,BASE,25,p),section=p.seccion;
 if(section==='inventario'){
   const s=data.resumen;
   if(!s||!['materiales','sin_stock','pendientes'].every(k=>count(s[k]))||s.sin_stock>s.materiales||s.pendientes>s.materiales||!decimalString(s.valor_neto))fail();
 }
 for(const r of data.results){
   if(!positiveInteger(r.id)||!['nombre','codigo','unidad'].every(k=>typeof r[k]==='string'))fail();
   if(section==='inventario'){if(typeof r.activo!=='boolean'||typeof r.pendiente!=='boolean'||!(r.saldo===null||isQty(r.saldo))||!(r.valor_neto===null||decimalString(r.valor_neto))||typeof r.descripcion!=='string')fail();}
   else {
     if(!isQty(r.cantidad))fail();
     if(section!=='historicos'&&(!TYPES[r.tipo]||!Number.isFinite(Date.parse(r.creado_en))||typeof r.referencia!=='string'||typeof r.motivo!=='string'))fail();
     if(section==='movimientos'||section==='ingresos'){if(!isQty(r.saldo_anterior)||!isQty(r.saldo_posterior)||!['INGRESO','SALIDA','DEVOLUCION','MERMA'].includes(r.tipo)||(section==='ingresos'&&r.tipo!=='INGRESO'))fail();}
     if(section==='valoraciones'||section==='regularizaciones'){if(r.tipo!==(section==='valoraciones'?'VALORIZACION':'REGULARIZACION')||!decimalString(r.costo_unitario_neto)||!['saldo_valorado_anterior','saldo_valorado_posterior'].every(k=>isQty(r[k]))||!['promedio_anterior','promedio_posterior'].every(k=>r[k]===null||decimalString(r[k])))fail();}
   }
 }
 return data;
}
function Button({icon,children,...props}){return <button type="button" className="btn btn-outline-secondary" {...props}>{icon&&<TecIcon name={icon}/>} {children}</button>;}
function Empty({title,description,icon='inbox'}){return <div className="if-empty" role="status"><TecIcon name={icon}/><strong>{title}</strong><p>{description}</p></div>;}
function Metric({label,value,detail}){return <div className="portfolio-kpi"><span>{label}</span><strong>{value}</strong>{detail&&<small>{detail}</small>}</div>;}
function Material({r}){return <><strong>{r.nombre}</strong><small className="commercial-help d-block">{r.codigo}</small></>;}
function StockStatus({r}){return <div className="if-status">{!r.activo&&<span className="chip gray">Inactivo</span>}{r.saldo==='0.000'&&<span className="chip red">Sin stock</span>}{r.pendiente?<span className="chip amber">Pendiente de valoración</span>:<span className="chip green">Valorizado</span>}</div>;}
function Fact({label,value}){return <div><dt>{label}</dt><dd>{value===null||value===undefined||value===''?'—':value}</dd></div>;}
function RowDetail({r,section,onBack}){
 const stock=section==='inventario',movement=section==='movimientos';
 return <><Button icon="back" className="btn btn-outline-secondary if-back" onClick={onBack}>Volver al listado</Button><section className="card-fyag if-panel"><header className="if-heading"><div><h2>{r.nombre}</h2><p className="commercial-help">{r.codigo} · {r.unidad}</p></div>{stock?<StockStatus r={r}/>:<span className="chip blue">{TYPES[r.tipo]}</span>}</header><dl className="if-facts">
 {stock?<><Fact label="Existencias" value={qty(r.saldo)+' '+r.unidad}/><Fact label="Valor neto de cantidades valorizadas" value={amount(r.valor_neto)}/><Fact label="Descripción" value={r.descripcion}/></>:<><Fact label="Fecha" value={stamp(r.creado_en)}/><Fact label="Cantidad" value={qty(r.cantidad)+' '+r.unidad}/>{movement?<><Fact label="Stock anterior" value={qty(r.saldo_anterior)+' '+r.unidad}/><Fact label="Stock resultante" value={qty(r.saldo_posterior)+' '+r.unidad}/></>:<><Fact label="Costo unitario neto" value={amount(r.costo_unitario_neto)}/><Fact label="Cantidad valorada anterior" value={qty(r.saldo_valorado_anterior)}/><Fact label="Cantidad valorada resultante" value={qty(r.saldo_valorado_posterior)}/><Fact label="Costo promedio anterior" value={amount(r.promedio_anterior)}/><Fact label="Costo promedio resultante" value={amount(r.promedio_posterior)}/>{r.referencia_ingreso&&<Fact label="Referencia del ingreso" value={r.referencia_ingreso}/>}</>}<Fact label="Referencia" value={r.referencia}/><Fact label="Motivo" value={r.motivo}/></>}
 </dl></section></>;
}
export default function FinanzasInventario(){
 const api=useApi(),app=useApp(),inFlight=useRef(false);
 const [section,setSection]=useState('inventario'),[draft,setDraft]=useState(EMPTY),[filters,setFilters]=useState(EMPTY),[page,setPage]=useState(1),[open,setOpen]=useState(false),[snapshot,setSnapshot]=useState(null),[detail,setDetail]=useState(null),[form,setForm]=useState(null),[message,setMessage]=useState('');
 const params=paramsFor(section,filters),path=url(params,page);
 const data=snapshot?.path===path?snapshot.data:null;
 const blocked=api.busy||api.locked,disabled=blocked||api.loading;
 const nav=app?.setNavigationBlocked;
 useEffect(()=>{nav?.(blocked);return ()=>nav?.(false);},[blocked,nav]);
 function read(){setSnapshot(null);return api.load('inventory-finance',path,v=>setSnapshot({path,data:validate(v,params)}));}
 useEffect(()=>{api.setError(null);void read();return ()=>api.cancelRead('inventory-finance');},[path]);
 function select(next){if(blocked)return;setSection(next);setDraft(EMPTY);setFilters(EMPTY);setPage(1);setOpen(false);setDetail(null);setForm(null);setMessage('');api.setError(null);}
 function apply(e){e.preventDefault();if(disabled)return;if(section==='movimientos'&&(draft.desde||draft.hasta)&&!civilRange(draft.desde,draft.hasta)){setMessage('Selecciona ambas fechas y un período válido de hasta 366 días.');return;}setMessage('');setFilters({...draft,buscar:draft.buscar.trim()});setPage(1);}
 function clear(){setDraft(EMPTY);setFilters(EMPTY);setPage(1);setMessage('');}
 function begin(r){if(disabled)return;setForm({row:r,kind:section,key:crypto.randomUUID(),cost:'',reference:'',reason:''});setMessage('');api.setError(null);}
 async function save(e,retry=false){
  e?.preventDefault();if(!form||inFlight.current||api.busy||(!retry&&api.locked))return;
  const historical=form.kind==='historicos',kind=historical?'REGULARIZACION':'VALORIZACION',dest=historical?'regularizaciones':'valoraciones';
  const cost=form.cost.trim(),reference=form.reference.trim(),reason=form.reason.trim();
  if(!/^\d{1,13}(?:\.\d{1,2})?$/.test(cost)||!reference||(historical&&!reason)){setMessage('Completa el costo unitario neto, la referencia y el motivo cuando corresponda.');return;}
  const body={clave_idempotencia:form.key,costo_unitario_neto:cost,referencia:reference,[historical?'articulo':'ingreso']:form.row.id};
  if(reason)body.motivo=reason;
  inFlight.current=true;setMessage('');
  try{
   if(retry&&!await api.reconcile(()=>Promise.resolve(true)))return;
   await api.write(ROOT+(historical?'regularizaciones-iniciales/':'valorizaciones/'),'POST',body,async v=>{
    if(!positiveInteger(v.id)||v.tipo!==kind||v[historical?'articulo':'ingreso']!==form.row.id||v.clave_idempotencia!==form.key)fail();
    const p=paramsFor(dest,EMPTY),next=url(p,1);
    await api.requiredLoad('confirm-inventory',next,x=>{setSnapshot({path:next,data:validate(x,p)});});
    setForm(null);setSection(dest);setFilters(EMPTY);setDraft(EMPTY);setPage(1);setMessage('Operación confirmada.');
   });
  }finally{inFlight.current=false;}
 }
 const stock=section==='inventario',movement=section==='movimientos',selection=candidate(section),historical=section==='historicos',history=!stock&&!movement&&!selection;
 const headers=stock?['Material','Existencias','Valor neto CLP','Situación','Detalle']:movement?['Material','Operación','Cantidad','Stock anterior','Stock resultante','Fecha','Detalle']:selection?(historical?['Material','Saldo histórico','Acción']:['Material','Cantidad','Referencia','Fecha','Acción']):['Material','Cantidad','Costo unitario neto','Costo promedio resultante','Fecha','Detalle'];
 const emptyTitle=filters.buscar||filters.filtro||filters.tipo||filters.desde?'Sin resultados':section==='historicos'?'No hay saldos históricos por regularizar':section==='ingresos'?'No hay ingresos disponibles para valorizar':section==='regularizaciones'?'No hay regularizaciones registradas':section==='valoraciones'?'No hay valoraciones registradas':section==='movimientos'?'No hay movimientos registrados':'No hay materiales registrados';
 return <section className="commercial-page manager-portfolio cobranzas-page manager-cobranzas finance-inventory">
 <PageHead title="Inventario y bodega" sub="Consulta existencias y administra los costos de adquisición.">{!form&&!detail&&<Button icon="refresh" disabled={disabled} onClick={()=>{api.setError(null);void read();}}>Actualizar</Button>}</PageHead>
 <Errors error={api.error}/>{message&&<p role="status" className="alert alert-info">{message}</p>}{api.loading&&<p role="status">Cargando inventario…</p>}
 {form?<><Button className="btn btn-outline-secondary if-back" icon="back" disabled={blocked} onClick={()=>{setForm(null);setMessage('');}}>Volver a la selección</Button><section className="card-fyag if-panel"><h2>{form.kind==='historicos'?'Regularizar saldo histórico':'Valorizar ingreso'}</h2><p className="commercial-help">Registra el costo neto de adquisición. Esta operación no cambia las existencias físicas ni registra un pago.</p><dl className="if-facts"><Fact label="Material" value={form.row.nombre}/><Fact label="Código" value={form.row.codigo}/><Fact label="Cantidad" value={qty(form.row.cantidad)+' '+form.row.unidad}/>{form.row.referencia&&<Fact label="Referencia del ingreso" value={form.row.referencia}/>}</dl><form className="if-form" aria-label="Registro de valoración" onSubmit={save}><div className="if-fields"><label className="form-label">Costo de adquisición unitario (neto CLP)<input className="form-control" inputMode="decimal" required value={form.cost} disabled={blocked} onChange={e=>setForm({...form,cost:e.target.value})} placeholder="Ej.: 8900"/></label><label className="form-label">Referencia de respaldo<input className="form-control" required maxLength={150} disabled={blocked} value={form.reference} onChange={e=>setForm({...form,reference:e.target.value})} placeholder="Factura u orden de compra"/></label><label className="form-label if-full">Motivo {form.kind==='historicos'?'':'(opcional)'}<textarea className="form-control" rows={2} required={form.kind==='historicos'} maxLength={2000} disabled={blocked} value={form.reason} onChange={e=>setForm({...form,reason:e.target.value})}/></label></div><div className="if-footer">{api.locked?<><p role="alert">No se confirmó la operación. Reintenta con los mismos datos para evitar duplicados.</p><button type="button" className="btn btn-fyag-primary" disabled={api.busy} onClick={()=>void save(null,true)}>Confirmar operación pendiente</button></>:<><Button disabled={disabled} onClick={()=>setForm(null)}>Cancelar</Button><button className="btn btn-fyag-primary" disabled={disabled}>Confirmar {form.kind==='historicos'?'regularización':'valoración'}</button></>}</div></form></section></>:detail?<RowDetail r={detail} section={section} onBack={()=>setDetail(null)}/>:<>
 <nav className="manager-work-tabs" aria-label="Secciones de inventario">{TABS.map(([k,l])=><button type="button" key={k} aria-pressed={parent(section)===k} disabled={blocked} onClick={()=>select(k)}>{l}</button>)}</nav>
 {stock&&<><div className="portfolio-kpis if-kpis"><Metric label="Materiales" value={data?.resumen.materiales??'—'}/><Metric label="Sin stock" value={data?.resumen.sin_stock??'—'} detail="Materiales activos"/><Metric label="Valoración pendiente" value={data?.resumen.pendientes??'—'}/><Metric label="Valor del inventario valorizado" value={amount(data?.resumen.valor_neto)} detail="CLP · neto"/></div><p className="commercial-help">Indicadores de todo el inventario. El valor incluye solo cantidades valorizadas.</p></>}
 {selection&&<Button className="btn btn-outline-secondary if-back" icon="back" disabled={blocked} onClick={()=>select(parent(section))}>Volver al historial</Button>}
 <section className="card-fyag portfolio-list if-list"><div className="portfolio-list-head"><div><h2>{LABELS[section]}</h2><span>{data?data.count+' registros':'—'}</span></div><div className="if-toolbar">{history&&<button type="button" className="btn btn-fyag-primary" disabled={disabled} onClick={()=>select(section==='valoraciones'?'ingresos':'historicos')}>{section==='valoraciones'?'Valorizar ingreso':'Regularizar saldo histórico'}</button>}{(stock||movement)&&<Button icon="filter" aria-expanded={open} onClick={()=>setOpen(x=>!x)}>Filtros</Button>}</div></div>
 {selection&&<p className="if-help commercial-help">{historical?'Selecciona un material con saldo histórico pendiente.':'Selecciona el siguiente ingreso elegible de cada material. Los ingresos con saldo histórico pendiente requieren regularización previa.'}</p>}
 <form className="if-filter" aria-label="Buscar y filtrar inventario" onSubmit={apply}><div className="if-toolbar"><label className="form-label if-search">Buscar material<input className="form-control" maxLength={150} placeholder="Nombre o código" value={draft.buscar} onChange={e=>setDraft({...draft,buscar:e.target.value})}/></label><button className="btn btn-fyag-primary" disabled={disabled}>Buscar</button>{Object.values(draft).some(Boolean)||Object.values(filters).some(Boolean)?<Button disabled={disabled} onClick={clear}>Limpiar filtros</Button>:null}</div>
 {open&&<div className="if-fields if-advanced">{stock?<label className="form-label">Situación<select className="form-select" value={draft.filtro} onChange={e=>setDraft({...draft,filtro:e.target.value})}><option value="">Todos</option><option value="sin_stock">Sin stock</option><option value="pendiente">Pendiente de valoración</option></select></label>:movement?<><label className="form-label">Tipo de movimiento<select className="form-select" value={draft.tipo} onChange={e=>setDraft({...draft,tipo:e.target.value})}><option value="">Todos</option>{['INGRESO','SALIDA','DEVOLUCION','MERMA'].map(t=><option key={t} value={t}>{TYPES[t]}</option>)}</select></label>{[['desde','Desde'],['hasta','Hasta']].map(([k,l])=><label className="form-label" key={k}>{l}<input className="form-control" type="date" value={draft[k]} onChange={e=>setDraft({...draft,[k]:e.target.value})}/></label>)}</>:null}<button className="btn btn-outline-secondary" disabled={disabled}>Aplicar filtros</button></div>}</form>
 {data&&data.results.length>0&&<div className="table-responsive" role="region" aria-label={LABELS[section]} tabIndex={0}><table className="table commercial-table if-table"><thead><tr>{headers.map((h,i)=><th scope="col" key={h} className={stock&&i===2||history&&(i===2||i===3)?'if-money':undefined}>{h}</th>)}</tr></thead><tbody>{data.results.map(r=><tr key={r.id}><td><Material r={r}/></td>{stock?<><td>{qty(r.saldo)} {r.saldo!==null?r.unidad:''}</td><td className="if-money">{r.pendiente&&r.valor_neto==='0.00'&&r.saldo!=='0.000'?'—':amount(r.valor_neto)}{r.pendiente&&<small className="commercial-help d-block">{r.valor_neto&&r.valor_neto!=='0.00'?'Valor parcial':'Sin valoración completa'}</small>}</td><td><StockStatus r={r}/></td></>:movement?<><td>{TYPES[r.tipo]}</td><td className={r.tipo==='SALIDA'||r.tipo==='MERMA'?'if-negative':'if-positive'}>{r.tipo==='SALIDA'||r.tipo==='MERMA'?'−':'+'}{qty(r.cantidad)} {r.unidad}</td><td>{qty(r.saldo_anterior)}</td><td>{qty(r.saldo_posterior)}</td><td>{stamp(r.creado_en)}</td></>:selection?<><td>{qty(r.cantidad)} {r.unidad}</td>{!historical&&<><td>{r.referencia}</td><td>{stamp(r.creado_en)}</td></>}</>:<><td>{qty(r.cantidad)} {r.unidad}</td><td className="if-money">{amount(r.costo_unitario_neto)}</td><td className="if-money">{amount(r.promedio_posterior)}</td><td>{stamp(r.creado_en)}</td></>}<td><Button disabled={disabled} onClick={()=>selection?begin(r):setDetail(r)}>{selection?'Seleccionar':'Ver detalle'}</Button></td></tr>)}</tbody></table></div>}
 {data&&!data.count&&<Empty title={emptyTitle} description={Object.values(filters).some(Boolean)?'Modifica o limpia los filtros para ampliar la búsqueda.':selection?'No existen operaciones elegibles en este momento.': 'Los registros aparecerán aquí cuando se incorporen al sistema.'}/>}
 {data&&(data.next||data.previous)&&<Pager data={data} page={page} setPage={setPage} disabled={disabled} label="Paginación de inventario"/>}{api.error?.status===404&&page>1&&<Button onClick={()=>setPage(1)}>Volver a la primera página</Button>}{api.error&&<div className="if-retry"><Button disabled={disabled} onClick={()=>{api.setError(null);void read();}}>Reintentar consulta</Button></div>}
 </section></>}
 </section>;
}
