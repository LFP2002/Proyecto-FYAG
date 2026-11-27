import React,{useEffect,useState} from 'react';
import {useAuth} from '../auth/AuthContext.jsx';
import {PageHead} from '../components/ui/index.js';
import {Errors,Pager} from '../comercial/ui.jsx';
import {validatePage} from '../comercial/api.js';
import {useApi} from './useApi.js';
import InventoryPicker from './InventoryPicker.jsx';
import InventoryActions from './InventoryActions.jsx';
import TecIcon from '../obras/TecIcon.jsx';
import {formatCLP} from '../utils/format.js';
import {isoDate} from './dates.js';
import '../styles/pages/inventario-supervisor.css';

const ROOT='/api/inventario/';
const TABS=[
 ['catalogo','Materiales','articulos/'],['existencias','Existencias','existencias/'],
 ['movimientos','Movimientos','movimientos/'],['autorizaciones','Autorizaciones de entrega','autorizaciones-entrega/'],
 ['entregas','Entregas','entregas/'],['devoluciones','Autorizaciones de devolución','autorizaciones-devolucion/']
];
const EMPTY={buscar:'',articulo:'',obra:'',autorizacion:'',entrega:'',tipo:'',desde:'',hasta:''};
const TYPES={INGRESO:'Ingreso',SALIDA:'Salida',DEVOLUCION:'Devolución',MERMA:'Merma'};
const ids=['articulo','obra','autorizacion','entrega'];
const fieldsFor=tab=>tab==='catalogo'?['buscar']:tab==='existencias'?['articulo']:tab==='movimientos'?['articulo','tipo','desde','hasta']:ids;
const validId=v=>/^[1-9][0-9]{0,18}$/.test(v)&&BigInt(v)<=9223372036854775807n;
const quantity=v=>typeof v==='string'&&/^\d+\.\d{3}$/.test(v)?v.replace(/0+$/,'').replace(/\.$/,'').replace('.',','):'—';
const withUnit=(v,u)=>quantity(v)==='—'?'—':quantity(v)+(u?' '+u:'');
const stamp=v=>typeof v==='string'&&Number.isFinite(Date.parse(v))?new Intl.DateTimeFormat('es-CL',{timeZone:'America/Santiago',day:'2-digit',month:'2-digit',year:'numeric',hour:'2-digit',minute:'2-digit',hour12:false}).format(new Date(v)).replaceAll('-','/'):'—';
const text=v=>v===null||v===undefined||v===''?'—':String(v);
const ref=(label,v)=>v==null?'—':label+' #'+v;
const source=tab=>ROOT+TABS.find(([key])=>key===tab)[2];
function listURL(tab,filters,page){const p=new URLSearchParams({page:String(page)});for(const k of fieldsFor(tab))if(filters[k])p.set(k,filters[k]);return source(tab)+'?'+p;}
function checkedPage(value,path){const p=validatePage(value,path);if(p.results.length>25||p.results.some(r=>!Number.isSafeInteger(r.id??r.articulo)||(r.id??r.articulo)<1))throw Error('Respuesta de inventario inesperada.');return p;}
function Button({icon,children,...props}){return <button type="button" className="btn btn-outline-secondary si-button" {...props}>{icon&&<TecIcon name={icon}/>} {children}</button>;}
function Empty({title,description}){return <div className="si-empty" role="status"><TecIcon name="inbox"/><strong>{title}</strong><p>{description}</p></div>;}
function Material({row,article}){return <div className="si-material"><strong>{article?.nombre||row.nombre||row.codigo||ref('Material',row.articulo)}</strong>{(article?.codigo||row.codigo)&&<small>{article?.codigo||row.codigo}</small>}</div>;}
function Fact({label,children}){return <div><dt>{label}</dt><dd>{children}</dd></div>;}
function Status({row}){return <span className={'chip '+(row.activo===true?'green':'gray')}>{row.activo===true?'Activo':row.activo===false?'Inactivo':'Estado no confirmado'}</span>;}
function Stock({row}){return <span className={'si-stock '+(row.saldo==='0.000'?'si-negative':'')}>{withUnit(row.saldo,row.unidad)}<small>{row.saldo==='0.000'?'Sin stock':quantity(row.saldo)==='—'?'Stock no confirmado':'Existencias físicas'}</small></span>;}
const columns={
 catalogo:['Material','Unidad','Estado','Detalle'],
 existencias:['Material','Cantidad disponible','Detalle'],
 movimientos:['Material','Movimiento','Cantidad','Stock resultante','Fecha','Detalle'],
 autorizaciones:['Material','Obra','Cantidad autorizada','Fecha','Detalle'],
 entregas:['Material','Obra','Cantidad entregada','Fecha','Detalle'],
 devoluciones:['Material','Obra','Cantidad autorizada','Por recibir','Fecha','Detalle']
};
function RecordDetail({row,tab,article,onBack,onRelated}){
 const api=useApi(),[stock,setStock]=useState(null);
 useEffect(()=>{if(tab!=='catalogo')return;void api.load('stock',ROOT+'existencias/?articulo='+row.id,v=>{const p=checkedPage(v,ROOT+'existencias/');if(p.results.length>1||p.results.some(r=>r.articulo!==row.id))throw Error('Existencia inesperada.');setStock(p.results[0]||null);});return()=>api.cancelRead('stock');},[tab,row.id]);
 const material=tab==='catalogo'?row:article;
 const unit=material?.unidad||row.unidad;
 const movement=tab==='movimientos',catalog=tab==='catalogo',exist=tab==='existencias';
 const inbound=['INGRESO','DEVOLUCION'].includes(row.tipo);
 const title=catalog||exist?'Ficha del material':movement?'Detalle del movimiento':TABS.find(t=>t[0]===tab)[1]+' · #'+row.id;
 return <><Button icon="back" className="btn btn-outline-secondary si-back si-button" onClick={onBack}>Volver al listado</Button>
 <section className="card-fyag si-panel si-detail"><header className="si-heading"><div><p className="commercial-help">{title}</p><h2>{material?.nombre||row.codigo||ref('Material',row.articulo)}</h2><p className="commercial-help">{material?.codigo||row.codigo||'Referencia de material #'+row.articulo}</p></div>{catalog&&<Status row={row}/>}</header>
 <Errors error={api.error}/>{api.loading&&<p role="status">Consultando existencias…</p>}
 <div className="si-summary">
 {catalog||exist?<div><span>Existencias actuales</span><strong className={(catalog?stock:row)?.saldo==='0.000'?'si-negative':undefined}>{withUnit((catalog?stock:row)?.saldo,unit)}</strong><small>{(catalog?stock:row)?.saldo==='0.000'?'Sin stock':(catalog?stock:row)?'Cantidad física registrada':'Stock no confirmado'}</small></div>:<div><span>{movement?'Cantidad del movimiento':tab==='entregas'?'Cantidad entregada':'Cantidad autorizada'}</span><strong className={movement?(inbound?'si-positive':'si-negative'):undefined}>{movement?(inbound?'+':'−'):''}{withUnit(row.cantidad,unit)}</strong><small>{movement?TYPES[row.tipo]:unit}</small></div>}
 {movement&&<><div><span>Stock anterior</span><strong className="si-secondary">{withUnit(row.saldo_anterior,unit)}</strong></div><div><span>Stock resultante</span><strong>{withUnit(row.saldo_posterior,unit)}</strong></div></>}
 {tab==='devoluciones'&&<div><span>Cantidad por recibir</span><strong>{withUnit(row.cantidad_recibible_efectiva,unit)}</strong><small>Saldo recibible efectivo informado por la API</small></div>}
 {tab==='entregas'&&<div><span>Costo unitario neto registrado</span><strong>{row.costo_unitario_neto==null?'—':formatCLP(row.costo_unitario_neto)}</strong><small>CLP por {unit||'unidad'}</small></div>}
 </div>
 <h3>{catalog||exist?'Información del material':'Información del registro'}</h3><dl className="si-facts"><Fact label="Unidad de medida">{text(unit)}</Fact>{catalog?<Fact label="Descripción">{row.descripcion||'Sin descripción registrada'}</Fact>:!exist&&<><Fact label="Fecha">{stamp(row.creado_en)}</Fact>{row.obra!=null&&<Fact label="Obra">{ref('Obra',row.obra)}</Fact>}{row.autorizacion!=null&&<Fact label="Autorización">{ref('Autorización',row.autorizacion)}</Fact>}{row.entrega!=null&&<Fact label="Entrega">{ref('Entrega',row.entrega)}</Fact>}<Fact label="Referencia">{text(row.referencia)}</Fact><Fact label="Motivo">{text(row.motivo)}</Fact><Fact label="Registrado por">{ref('Usuario',row.actor)}</Fact></>}</dl>
 {(catalog||exist)&&<div className="si-related"><h3>Consultar registros relacionados</h3><div className="si-toolbar">{[['movimientos','Ver movimientos'],['autorizaciones','Ver autorizaciones'],['entregas','Ver entregas'],['devoluciones','Ver devoluciones']].map(([key,label])=><Button key={key} onClick={()=>onRelated(key,String(row.id??row.articulo))}>{label}<TecIcon name="chevron"/></Button>)}</div></div>}
 </section></>;
}
export default function SupervisorInventario(){
 const api=useApi(),{request}=useAuth();
 const [tab,setTab]=useState('catalogo'),[page,setPage]=useState(1),[filters,setFilters]=useState(EMPTY),[draft,setDraft]=useState(EMPTY),[open,setOpen]=useState(false),[snapshot,setSnapshot]=useState(null),[selected,setSelected]=useState(null),[validation,setValidation]=useState(''),[articles,setArticles]=useState({}),[revision,setRevision]=useState(0);
 const path=listURL(tab,filters,page),data=snapshot?.path===path?snapshot.data:null;
 const load=()=>{setSnapshot(null);return api.load('list',path,v=>setSnapshot({path,data:checkedPage(v,source(tab))}));};
 useEffect(()=>{api.setError(null);void load();return()=>api.cancelRead('list');},[path,revision]);
 // La proyección operativa original no contiene nombres en todos los registros.
 // Resuelve solo materiales de la página actual, sin recorrer el catálogo global.
 useEffect(()=>{if(!data||tab==='catalogo')return;const controller=new AbortController();
  const pending=[...new Set(data.results.map(r=>r.articulo))].filter(id=>Number.isSafeInteger(id)&&id>0);
  async function worker(){while(pending.length&&!controller.signal.aborted){const id=pending.shift();try{const item=await request(ROOT+'articulos/'+id+'/',{signal:controller.signal});if(!controller.signal.aborted&&item.id===id&&typeof item.nombre==='string'&&typeof item.codigo==='string'&&typeof item.unidad==='string')setArticles(old=>({...old,[id]:item}));}catch{/* Mantener referencia confirmada si el nombre no está disponible. */}}}
  void Promise.all(Array.from({length:Math.min(4,pending.length)},worker));return()=>controller.abort();
 },[data,tab,request]);
 function selectTab(key,material=''){api.cancelRead('list');setSelected(null);setTab(key);setPage(1);setFilters({...EMPTY,articulo:material});setDraft({...EMPTY,articulo:material});setOpen(false);setValidation('');}
 function apply(e){e.preventDefault();const f=Object.fromEntries(Object.entries(draft).map(([k,v])=>[k,v.trim()]));
  if(ids.some(k=>f[k]&&!validId(f[k]))||(tab==='movimientos'&&(!!f.desde!==!!f.hasta||f.desde&&(!isoDate(f.desde)||!isoDate(f.hasta)||f.desde>f.hasta)))){setValidation('Revisa las referencias y el período indicado.');return;}
  setValidation('');setPage(1);setFilters(f);setOpen(false);setRevision(v=>v+1);}
 function clear(){setFilters(EMPTY);setDraft(EMPTY);setPage(1);setValidation('');setRevision(v=>v+1);}
 const filtered=fieldsFor(tab).some(k=>!!filters[k]);
 const update=(key,value)=>setDraft(old=>({...old,[key]:value}));
 return <section className="commercial-page supervisor-inventory">
 {selected?<RecordDetail key={tab+':'+(selected.id??selected.articulo)} row={selected} tab={tab} article={articles[selected.articulo]} onBack={()=>setSelected(null)} onRelated={selectTab}/>:<>
 <PageHead title="Inventario y bodega"><Button icon="refresh" disabled={api.loading} onClick={()=>void api.reconcile(load)}>Actualizar</Button></PageHead>
 <div className="si-tabs" role="group" aria-label="Secciones de inventario">{TABS.map(([key,label])=><button type="button" key={key} aria-pressed={tab===key} onClick={()=>selectTab(key)}>{label}</button>)}</div>
 <Errors error={api.error}/>{api.loading&&<p role="status">Consultando inventario…</p>}
 <section className="card-fyag si-panel"><div className="si-heading"><div><h2>{TABS.find(t=>t[0]===tab)[1]}</h2><span className="commercial-help">{data?data.count+' registros':'—'}</span></div>{tab!=='catalogo'&&<Button icon="filter" aria-expanded={open} aria-controls="si-filters" onClick={()=>setOpen(v=>!v)}>Filtros</Button>}</div>
 {tab==='catalogo'?<form className="si-toolbar" onSubmit={apply}><input aria-label="Buscar artículo" className="form-control si-search" value={draft.buscar} maxLength={150} placeholder="Nombre o código del material" onChange={e=>update('buscar',e.target.value)}/><button type="submit" className="btn btn-outline-secondary si-button"><TecIcon name="search"/>Buscar</button></form>:open&&<form id="si-filters" className="si-filters" onSubmit={apply}><InventoryPicker compact label="Material" value={draft.articulo} onChange={v=>update('articulo',v)}/>
 {tab==='movimientos'?<><label className="form-label">Movimiento<select className="form-select" value={draft.tipo} onChange={e=>update('tipo',e.target.value)}><option value="">Todos</option>{Object.entries(TYPES).map(([k,v])=><option key={k} value={k}>{v}</option>)}</select></label>{[['desde','Desde'],['hasta','Hasta']].map(([k,l])=><label className="form-label" key={k}>{l}<input className="form-control" type="date" value={draft[k]} onChange={e=>update(k,e.target.value)}/></label>)}</>:tab!=='existencias'&&<><InventoryPicker compact kind="obra" label="Obra" value={draft.obra} onChange={v=>update('obra',v)}/>{[['autorizacion','N.º de autorización'],['entrega','N.º de entrega']].map(([k,l])=><label key={k} className="form-label">{l}<input className="form-control" inputMode="numeric" value={draft[k]} onChange={e=>update(k,e.target.value)}/></label>)}</>}
 <div className="si-toolbar"><button type="submit" className="btn btn-fyag-primary si-button">Aplicar filtros</button><Button onClick={clear}>Limpiar filtros</Button></div></form>}
 {validation&&<p className="alert alert-warning" role="alert">{validation}</p>}{filtered&&<div className="si-toolbar"><span className="commercial-help">Filtros aplicados{filters.buscar?' · '+filters.buscar:''}</span><Button onClick={clear}>Quitar filtros</Button></div>}
 {data&&(data.results.length?<div className="table-responsive" role="region" aria-label={TABS.find(t=>t[0]===tab)[1]} tabIndex={0}><table className="table table-hover align-middle commercial-table si-table"><thead><tr>{columns[tab].map(h=><th scope="col" key={h}>{h}</th>)}</tr></thead><tbody>{data.results.map(r=>{const a=articles[r.articulo],unit=a?.unidad||r.unidad,inbound=['INGRESO','DEVOLUCION'].includes(r.tipo);return <tr key={r.id??r.articulo}><td><Material row={r} article={a}/></td>{tab==='catalogo'?<><td>{r.unidad}</td><td><Status row={r}/></td></>:tab==='existencias'?<td><Stock row={r}/></td>:tab==='movimientos'?<><td>{TYPES[r.tipo]||'Movimiento'}</td><td className={inbound?'si-positive':'si-negative'}>{inbound?'+':'−'}{withUnit(r.cantidad,unit)}</td><td>{withUnit(r.saldo_posterior,unit)}</td><td>{stamp(r.creado_en)}</td></>:<><td>{ref('Obra',r.obra)}</td><td><strong>{withUnit(r.cantidad,unit)}</strong></td>{tab==='devoluciones'&&<td>{withUnit(r.cantidad_recibible_efectiva,unit)}</td>}<td>{stamp(r.creado_en)}</td></>}<td><Button className="btn btn-outline-secondary btn-sm si-button" onClick={()=>setSelected(r)}>Ver detalle<TecIcon name="chevron"/></Button></td></tr>;})}</tbody></table></div>:<Empty title={filtered?'No hay resultados':'No hay registros en esta sección'} description={filtered?'Modifica o limpia los filtros para ampliar la consulta.':'Los registros disponibles aparecerán aquí.'}/>)}
 {data&&(data.next||data.previous)&&<Pager data={data} page={page} setPage={setPage} disabled={api.loading} label="Paginación de inventario"/>}</section></>}
 <InventoryActions role="SUPERVISOR_OBRAS" onSuccess={load}/>
 </section>;
}
