import React,{useEffect,useRef,useState} from 'react';
import {useApp} from '../context/AppContext.jsx';
import {useAuth} from '../auth/AuthContext.jsx';
import {useApi} from '../integrations/useApi.js';
import {Errors,Pager} from '../comercial/ui.jsx';
import BodegaIcon from '../bodega/icons.jsx';
import {ROOT,modules,movementAmount,shortUnit,recordCount,authorizationStatus,timestamp,pathFor,readPage,readSummary,preview,milli} from '../bodega/domain.js';
import '../styles/pages/bodega.css';

const titles={resumen:'Resumen de bodega',inventario:'Inventario',movimientos:'Movimientos de inventario',entregas:'Entregas de materiales',devoluciones:'Devoluciones de materiales'};
const descriptions={resumen:'Situación actual y operaciones pendientes.',inventario:'Catálogo de materiales y existencias físicas.',movimientos:'Historial de entradas y salidas de materiales.',entregas:'Despachos autorizados y entregas realizadas.',devoluciones:'Recepciones autorizadas y devoluciones realizadas.'};
const kinds={INGRESO:'Ingreso',SALIDA:'Salida',DEVOLUCION:'Devolución',MERMA:'Merma',ENTREGA:'Entrega'};
const operations={INGRESO:['ingresos/','Registrar ingreso','Confirmar ingreso'],ENTREGA:['entregas/','Despachar material','Confirmar despacho'],DEVOLUCION:['devoluciones/','Recibir devolución','Confirmar devolución']};
const blank=section=>['entregas','devoluciones'].includes(section)?{vista:'pendientes',buscar:''}:section==='inventario'?{buscar:'',estado:'',stock:''}:section==='movimientos'?{buscar:'',tipo:'',desde:'',hasta:'',articulo:''}:{};
export const Button=({icon,children,primary=false,...props})=><button type="button" className={'btn bodega-button '+(primary?'btn-fyag-primary':'btn-outline-secondary')} {...props}>{icon&&<BodegaIcon name={icon}/>}{children}</button>;
export function Field({label,value,onChange,type='text',disabled=false,required=false,maxLength,inputMode}){return <label className="bodega-field">{label}{type==='textarea'?<textarea className="form-control" rows={3} {...{value,disabled,required,maxLength}} onChange={e=>onChange(e.target.value)}/>:<input className="form-control" {...{type,value,disabled,required,maxLength,inputMode}} onChange={e=>onChange(e.target.value)}/>}</label>;}
const emptyStates={
 filtered:['No hay resultados','Ningún registro coincide con los filtros aplicados. Prueba otra búsqueda o limpia los filtros.'],
 inventory:['No hay materiales registrados','Los materiales que registres aparecerán aquí.'],
 movements:['No hay movimientos registrados','Las entradas y salidas registradas aparecerán aquí.'],
 deliveries:['No hay entregas pendientes','Las nuevas autorizaciones de entrega aparecerán aquí.'],
 returns:['No hay devoluciones pendientes','Las nuevas autorizaciones de devolución aparecerán aquí.'],
 deliveryHistory:['No hay entregas registradas','Los despachos realizados aparecerán aquí.'],
 returnHistory:['No hay devoluciones registradas','Las recepciones realizadas aparecerán aquí.'],
 deliveryAuth:['No hay autorizaciones de entrega','Las autorizaciones registradas aparecerán aquí.'],
 returnAuth:['No hay autorizaciones de devolución','Las autorizaciones registradas aparecerán aquí.'],
 stock:['No hay materiales activos sin stock','Los materiales activos que agoten sus existencias aparecerán aquí.'],
 losses:['No hay mermas registradas','Los reportes de pérdida de materiales aparecerán aquí.'],
 lossPending:['No hay mermas pendientes','Las mermas que esperan una decisión aparecerán aquí.']
};
export function Empty({state,compact=false}){
 const [title,description]=emptyStates[state];
 return <div className={'bodega-empty'+(compact?' bodega-empty-compact':'')} role="status">
  <span className="bodega-empty-icon"><BodegaIcon name="inbox"/></span>
  <strong>{title}</strong><p>{description}</p>
 </div>;
}
function listEmptyState(section,filters){
 if(Object.entries(filters).some(([key,value])=>key!=='vista'&&value))return 'filtered';
 if(section==='inventario')return 'inventory';
 if(section==='movimientos')return 'movements';
 const receive=section==='devoluciones';
 return filters.vista==='historial'?(receive?'returnHistory':'deliveryHistory'):filters.vista==='autorizaciones'?(receive?'returnAuth':'deliveryAuth'):(receive?'returns':'deliveries');
}
export function Material({row}){return <div className="bodega-material"><strong>{row.nombre}</strong><small>{row.codigo}</small></div>;}
export function Fact({label,children}){return <div className="bodega-fact"><small>{label}</small><strong>{children}</strong></div>;}
export function Header({title,sub,children,detail=false}){return <header className={'bodega-heading'+(detail?' fyag-detail-heading':'')}><div><h1>{title}</h1>{sub&&<p>{sub}</p>}</div><div className="bodega-actions">{children}</div></header>;}
export function Tabs({items,value,onChange,disabled=false,label}){return <div className="bodega-tabs" role="group" aria-label={label}>{items.map(([key,title])=><button key={key} type="button" aria-pressed={value===key} disabled={disabled} onClick={()=>onChange(key)}>{title}</button>)}</div>;}
function Pending({row,receive,onAction,disabled}){const [status,tone]=authorizationStatus(row);return <article className="bodega-pending"><div className="bodega-row"><small>Autorización #{row.id} · {row.obra||'Obra no disponible'}</small><span className={'bodega-'+tone}>{status}</span></div><Material row={row}/><div className="bodega-facts"><Fact label="Autorizado">{movementAmount(row.cantidad,row.unidad)}</Fact><Fact label={receive?'Recibido':'Entregado'}>{movementAmount(row.ejecutada,row.unidad)}</Fact><div className="bodega-pending-amount"><Fact label={receive?'Por recibir':'Por entregar'}>{movementAmount(row.pendiente,row.unidad)}</Fact></div></div><div className="bodega-row bodega-pending-footer"><div><small>Existencias actuales</small><strong>{movementAmount(row.saldo,row.unidad)}</strong>{row.bloqueo&&<small className="bodega-warn">{row.bloqueo}</small>}</div><Button primary icon={receive?'returns':'delivery'} disabled={disabled||!!row.bloqueo||!(milli(row.maximo)>0n)} onClick={()=>onAction(row)}>{receive?'Recibir':'Despachar'}</Button></div></article>;}
export function Table({headers,children,empty,emptyState="filtered",numericColumns=[]}){if(empty)return <Empty state={emptyState}/>;return <div className="table-responsive bodega-table-region" tabIndex={0} role="region" aria-label="Listado de bodega"><table className="table bodega-table"><thead><tr>{headers.map((h,i)=><th scope="col" key={h} className={numericColumns.includes(i)?'bodega-number-cell':undefined}>{h}</th>)}</tr></thead><tbody>{children}</tbody></table></div>;}
export function MaterialPicker({value,onChange,disabled,label='Material recibido'}){
 const api=useApi(),[page,setPage]=useState(1),[text,setText]=useState(''),[search,setSearch]=useState(''),[data,setData]=useState(null),[open,setOpen]=useState(false);
 const path=pathFor('inventario',{estado:'activo',buscar:search},page);
 useEffect(()=>{if(!open)return;setData(null);api.setError(null);void api.load('picker',path,v=>setData(readPage(v)));return()=>api.cancelRead('picker');},[path,open]);
 const choose=r=>{onChange(r);setOpen(false);};
 const applySearch=()=>{setSearch(text.trim());setPage(1);};
 return <div className="bodega-picker">
  <span className="bodega-field">{label}</span>
  <button type="button" className="bodega-picker-trigger" aria-label={label} aria-expanded={open} disabled={disabled} onClick={()=>setOpen(v=>!v)}><BodegaIcon name="search"/><span>{value?<><strong>{value.nombre}</strong><small className="bodega-muted">{value.codigo}</small></>: 'Selecciona un material por nombre o código'}</span><BodegaIcon name="chevron"/></button>
  {open&&!disabled&&<div className="bodega-picker-menu" onKeyDown={e=>{if(e.key==='Escape'){e.stopPropagation();setOpen(false);}}}>
   <div className="bodega-search"><input aria-label="Buscar material" className="form-control" value={text} maxLength={150} placeholder="Nombre o código" onChange={e=>setText(e.target.value)} onKeyDown={e=>{if(e.key==='Enter'){e.preventDefault();applySearch();}}}/><Button icon="search" disabled={api.loading} onClick={applySearch}>Buscar</Button></div>
   <Errors error={api.error}/>{api.loading&&<p role="status">Cargando materiales…</p>}
   {data&&!api.loading&&!api.error&&<div className="bodega-picker-results">{data.results.map(r=><button type="button" key={r.id} className="bodega-picker-option" onClick={()=>choose(r)}><Material row={r}/><small>{movementAmount(r.saldo,r.unidad)}</small></button>)}{!data.results.length&&<Empty state="filtered" compact/>}</div>}
   {data&&(data.next||data.previous)&&<Pager data={data} page={page} setPage={setPage} disabled={api.loading}/>}
  </div>}
 </div>;
}
export function MovementTable({rows,emptyState="movements"}){
 return <Table headers={['Material','Operación','Cantidad','Stock anterior','Stock final','Fecha','Referencia / motivo']} numericColumns={[2,3,4]} empty={!rows.length} emptyState={emptyState}>
  {rows.map(r=>{
   const inbound=r.tipo==='INGRESO'||r.tipo==='DEVOLUCION';
   return <tr key={r.id}>
    <td><Material row={r}/></td>
    <td><span className="bodega-movement-kind"><span className={inbound?'bodega-movement-in':'bodega-movement-out'}><BodegaIcon name={inbound?'in':'out'}/></span>{kinds[r.tipo]||r.tipo}</span></td>
    <td className="bodega-number-cell"><span className={inbound?'bodega-movement-in':'bodega-movement-out'}>{milli(r.cantidad)===null?'—':(inbound?'+':'−')+movementAmount(r.cantidad,r.unidad)}</span></td>
    <td className="bodega-number-cell">{movementAmount(r.saldo_anterior,r.unidad)}</td>
    <td className="bodega-number-cell"><strong>{movementAmount(r.saldo_posterior,r.unidad)}</strong></td>
    <td>{timestamp(r.creado_en)}</td>
    <td>{r.referencia||'—'}{r.motivo&&<small className="bodega-muted">{r.motivo}</small>}<small className="bodega-muted">{r.actor}</small></td>
   </tr>;
  })}
 </Table>;
}
export function OperationTable({rows,emptyState,authorization=false,receive=false}){
 const headers=authorization?['Material','Obra','Registro','Autorizado',receive?'Recibido':'Entregado','Pendiente','Estado','Referencia / motivo','Fecha']:['Material','Obra','Registro','Cantidad','Referencia / motivo','Fecha'];
 return <Table headers={headers} numericColumns={authorization?[3,4,5]:[3]} empty={!rows.length} emptyState={emptyState}>{rows.map(r=>{
  const [status,tone]=authorizationStatus(r);
  return <tr key={r.id}><td><Material row={r}/></td><td>{r.obra||'—'}</td><td>#{r.id}{r.autorizacion&&<small className="bodega-muted">Autorización #{r.autorizacion}</small>}{r.entrega&&<small className="bodega-muted">Entrega #{r.entrega}</small>}</td>
   <td className="bodega-number-cell">{movementAmount(r.cantidad,r.unidad)}</td>
   {authorization&&<><td className="bodega-number-cell">{movementAmount(r.ejecutada,r.unidad)}</td><td className="bodega-number-cell">{movementAmount(r.pendiente,r.unidad)}</td><td><span className={'bodega-'+tone}>{status}</span>{tone==='warn'&&r.bloqueo&&<small className="bodega-muted">{r.bloqueo}</small>}</td></>}
   <td>{r.referencia||'—'}{r.motivo&&<small className="bodega-muted">{r.motivo}</small>}<small className="bodega-muted">{r.actor}</small></td><td>{timestamp(r.creado_en)}</td></tr>;
 })}</Table>;
}
function ArticleDetail({row,onBack,onEdit,onIngress,disabled}){
 const api=useApi(),[page,setPage]=useState(1),[data,setData]=useState(null);
 const path=pathFor('movimientos',{articulo:row.id},page);
 useEffect(()=>{setData(null);void api.load('history',path,v=>setData(readPage(v)));return()=>api.cancelRead('history');},[path]);
 return <><div className="bodega-actions"><Button icon="back" onClick={onBack}>Volver al inventario</Button></div><Header detail title={row.nombre} sub={row.codigo}><Button icon="edit" onClick={()=>onEdit(row)} disabled={disabled}>Editar material</Button>{row.activo&&<Button primary icon="plus" onClick={()=>onIngress(row)} disabled={disabled}>Registrar ingreso</Button>}</Header><section className="card-fyag bodega-panel"><h2>Información general</h2><div className="bodega-facts"><Fact label="Existencias">{movementAmount(row.saldo,row.unidad)}</Fact><Fact label="Estado administrativo">{row.activo?'Activo':'Inactivo'}</Fact><Fact label="Unidad">{row.unidad}</Fact></div><p>{row.descripcion||'Sin descripción registrada.'}</p></section><section className="card-fyag bodega-panel"><h2>Historial de movimientos</h2><Errors error={api.error}/>{data&&(data.results.length>0||!api.loading&&!api.error)&&<MovementTable rows={data.results}/>}{data&&(data.next||data.previous)&&<Pager data={data} page={page} setPage={setPage} disabled={api.loading}/>}</section></>;
}
export default function Bodega(){
 const {user}=useAuth(),{mod,go,setNavigationBlocked}=useApp(),api=useApi(),section=modules[mod]||'resumen';
 const [queries,setQueries]=useState({}),[drafts,setDrafts]=useState({}),[filterOpen,setFilterOpen]=useState(false),[loaded,setLoaded]=useState(null),[revision,setRevision]=useState(0),[form,setForm]=useState(null),[detail,setDetail]=useState(null),[message,setMessage]=useState(''),[intent,setIntent]=useState(null),[replay,setReplay]=useState(false),[discard,setDiscard]=useState(false);
 const pendingRef=useRef(false);
 const current=queries[section]||{filters:blank(section),page:1},draft=drafts[section]||current.filters;
 const path=pathFor(section,current.filters,current.page);
 const data=loaded?.path===path?loaded.value:null,disabled=api.busy||api.loading||api.locked||!!intent;
 const commitData=(p,v)=>setLoaded({path:p,value:section==='resumen'?readSummary(v):readPage(v)});
 const load=()=>api.load('list',path,v=>commitData(path,v));
 useEffect(()=>{if(user.role!=='BODEGUERO')return;api.setError(null);void load();return()=>api.cancelRead('list');},[path,revision]);
 useEffect(()=>{setFilterOpen(false);setDetail(null);setMessage('');if(!intent&&!pendingRef.current)setForm(null);},[mod]);
 useEffect(()=>{setNavigationBlocked(!!intent||api.busy||api.locked);return()=>setNavigationBlocked(false);},[intent,api.busy,api.locked,setNavigationBlocked]);
 function setQuery(filters,page=1){setQueries(old=>({...old,[section]:{filters,page}}));}
 function changeDraft(key,value){setDrafts(old=>({...old,[section]:{...draft,[key]:value}}));}
 function apply(e){e.preventDefault();if(draft.desde&&draft.hasta&&draft.desde>draft.hasta){api.setError({message:'El rango de fechas está invertido.'});return;}setQuery({...draft,buscar:(draft.buscar||'').trim()});setFilterOpen(false);}
 function filter(key,value){const f={...current.filters,[key]:value};setQuery(f);setDrafts(old=>({...old,[section]:f}));}
 function navigate(to){if(!disabled)go(to);}
 function navigatePending(to){const target=modules[to],f=blank(target);setQueries(old=>({...old,[target]:{filters:f,page:1}}));setDrafts(old=>({...old,[target]:f}));navigate(to);}
 function begin(kind,row=null){if(disabled)return;setMessage('');api.setError(null);setForm({kind,row,cantidad:'',referencia:'',motivo:'',key:crypto.randomUUID()});setDetail(null);}
 function edit(row){if(disabled)return;setDetail(null);setForm({kind:'ARTICLE',row,values:row?{codigo:row.codigo,nombre:row.nombre,unidad:row.unidad,descripcion:row.descripcion,activo:row.activo}:{codigo:'',nombre:'',unidad:'',descripcion:'',activo:true}});}
 function close(){if(api.busy||api.locked||intent)return;setForm(null);api.setError(null);}
 function update(k,v){setForm(f=>({...f,[k]:v}));}
 function updateArticle(k,v){setForm(f=>({...f,values:{...f.values,[k]:v}}));}
 async function write(i){
  if(pendingRef.current)return;
  pendingRef.current=true;setNavigationBlocked(true);setIntent(i);setReplay(false);setDiscard(false);
  const ok=await api.write(i.path,i.method,i.body,async result=>{
   if(!Number.isSafeInteger(result?.id)||result.id<1)throw Error('No se confirmó el identificador de la operación.');
   // Page 1 avoids an out-of-range page when a pending authorization is consumed.
   const first=pathFor(section,current.filters,1);
   await api.requiredLoad('list',first,v=>commitData(first,v));
   setQuery(current.filters,1);
   setMessage('Operación confirmada.');setForm(null);setDetail(null);setIntent(null);
  });
  pendingRef.current=false;
  if(ok)setIntent(null);
 }
 useEffect(()=>{if(intent&&!api.busy&&!api.locked&&!replay&&api.error&&typeof api.error.status==='number'&&api.error.status>0&&api.error.status<500&&api.error.status!==409)setIntent(null);},[api.busy,api.locked,api.error,intent,replay]);
 async function submit(e){
  e.preventDefault();if(disabled||!form)return;
  if(form.kind==='ARTICLE'){
   const v=form.values;const body={codigo:v.codigo.trim(),nombre:v.nombre.trim(),unidad:v.unidad.trim(),descripcion:v.descripcion.trim()};
   if(!body.codigo||!body.nombre||!body.unidad){api.setError({message:'Completa código, nombre y unidad.'});return;}
   if(form.row)body.activo=v.activo;
   await write({kind:'ARTICLE',path:ROOT+'articulos/'+(form.row?form.row.id+'/':''),method:form.row?'PATCH':'POST',body});return;
  }
  const result=preview(form);
  if(!result){api.setError({message:'Selecciona el material y una cantidad válida dentro del límite disponible.'});return;}
  const body={cantidad:result.cantidad,referencia:form.referencia.trim(),motivo:form.motivo.trim(),clave_idempotencia:form.key,[form.kind==='INGRESO'?'articulo':'autorizacion']:form.row.id};
  await write({kind:form.kind,path:ROOT+operations[form.kind][0],method:'POST',body});
 }
 async function reconcile(){
  if(!intent||api.busy||api.loading)return;
  const first=pathFor(section,current.filters,1),reload=()=>api.load('list',first,v=>commitData(first,v));
  if(intent.kind==='ARTICLE'){
   const ok=await api.reconcile(reload);
   if(ok){setQuery(current.filters,1);setIntent(null);setForm(null);setMessage('Listado actualizado. Revisa si el material quedó guardado antes de repetir la operación.');}
   return;
  }
  const definitiveConflict=api.error?.status===409;
  let confirmed=null;
  const ok=await api.reconcile(async()=>{
   const found=await api.load('confirmation',pathFor('confirmacion',{tipo:intent.kind,clave:intent.body.clave_idempotencia}),v=>{if(!v||!(v.id===null||Number.isSafeInteger(v.id)&&v.id>0))throw Error('Confirmación inesperada.');confirmed=v.id;});
   return found&&await reload();
  });
  if(ok){setQuery(current.filters,1);if(confirmed){setMessage('Operación confirmada por la API.');setForm(null);setIntent(null);setReplay(false);}else {setReplay(true);setDiscard(definitiveConflict);}}
 }
 if(user.role!=='BODEGUERO')return <p role="alert">No tiene permiso para operar Bodega.</p>;
 if(form){
  const article=form.kind==='ARTICLE',result=article?null:preview(form),locked=api.busy||api.locked||!!intent;
  return <section className="commercial-page bodega-page"><div className="bodega-actions"><Button icon="back" onClick={close} disabled={locked}>{section==='resumen'?'Volver al resumen':section==='inventario'?'Volver al inventario':section==='movimientos'?'Volver a movimientos':section==='entregas'?'Volver a entregas':'Volver a devoluciones'}</Button></div><Header title={article?(form.row?'Editar material':'Nuevo material'):operations[form.kind][1]}/><Errors error={api.error}/>
   <form onSubmit={submit} className="bodega-form">
    {article?<div className="bodega-form-grid"><section className="card-fyag bodega-panel"><h2>Identificación del material</h2><div className="bodega-fields"><Field label="Código" value={form.values.codigo} onChange={v=>updateArticle('codigo',v)} disabled={locked||!!form.row} required maxLength={50}/><Field label="Unidad" value={form.values.unidad} onChange={v=>updateArticle('unidad',v)} disabled={locked||!!form.row} required maxLength={30}/><Field label="Nombre" value={form.values.nombre} onChange={v=>updateArticle('nombre',v)} disabled={locked} required maxLength={150}/></div><Field label="Descripción" type="textarea" value={form.values.descripcion} onChange={v=>updateArticle('descripcion',v)} disabled={locked} maxLength={2000}/></section><section className="card-fyag bodega-panel"><h2>Estado del material</h2>{form.row?<><label className="bodega-check"><input type="checkbox" checked={form.values.activo} disabled={locked} onChange={e=>updateArticle('activo',e.target.checked)}/> Activo</label><p>La desactivación conserva el historial. Código y unidad se mantienen sin cambios.</p></>:<p>Se creará activo y sin existencias. Registra el ingreso físico por separado.</p>}</section></div>:<div className="bodega-form-grid"><section className="card-fyag bodega-panel"><h2>{form.kind==='INGRESO'?'Material recibido':'Información de la autorización'}</h2>{form.kind==='INGRESO'?<MaterialPicker value={form.row} onChange={v=>update('row',v)} disabled={locked}/>:<><Material row={form.row}/><div className="bodega-facts"><Fact label="Obra">{form.row.obra}</Fact><Fact label="Autorización">#{form.row.id}</Fact><Fact label="Cantidad pendiente">{movementAmount(form.row.pendiente,form.row.unidad)}</Fact><Fact label="Máximo operativo">{movementAmount(form.row.maximo,form.row.unidad)}</Fact></div></>}<div className="bodega-fields"><Field label={form.row?'Cantidad (' + shortUnit(form.row.unidad) + ')':'Cantidad'} value={form.cantidad} onChange={v=>update('cantidad',v)} disabled={locked} inputMode="decimal" required maxLength={13}/><Field label="Referencia de respaldo" value={form.referencia} onChange={v=>update('referencia',v)} disabled={locked} maxLength={150}/></div><Field label="Motivo" type="textarea" value={form.motivo} onChange={v=>update('motivo',v)} disabled={locked} maxLength={2000}/></section><section className="card-fyag bodega-panel"><h2>Resultado previsto</h2><div className="bodega-stock-preview"><Fact label="Stock actual">{movementAmount(form.row?.saldo,form.row?.unidad)}</Fact><span aria-hidden="true">{form.kind==='ENTREGA'?'−':'+'}</span><Fact label={form.kind==='ENTREGA'?'Salida':'Ingreso'}>{result?movementAmount(result.cantidad,form.row?.unidad):'—'}</Fact><span aria-hidden="true">=</span><Fact label="Stock resultante">{result?movementAmount(result.saldo,form.row?.unidad):'—'}</Fact></div>{form.cantidad&&!result&&<p className="bodega-warn">La cantidad debe ser positiva y no superar el límite disponible (hasta tres decimales).</p>}<p>El servidor comprueba las existencias y autorizaciones al confirmar.</p>{form.kind==='INGRESO'&&<p>Finanzas registrará el costo de adquisición.</p>}</section></div>}
    {intent&&<div className="card-fyag bodega-panel"><h2>Verificar operación</h2><p>El resultado debe confirmarse antes de realizar otra operación. No se reenviará automáticamente.</p><div className="bodega-actions">{api.locked&&<Button icon="refresh" onClick={()=>void reconcile()} disabled={api.busy||api.loading}>{article?'Actualizar y revisar listado':'Verificar registro'}</Button>}{replay&&<Button primary onClick={()=>void write(intent)} disabled={api.busy||api.loading}>Reintentar con los mismos datos</Button>}{discard&&<Button onClick={()=>{setIntent(null);setReplay(false);setDiscard(false);setForm(null);setMessage('No se encontró un registro de la operación rechazada.');}} disabled={api.busy||api.loading}>Descartar intento rechazado</Button>}</div></div>}
    <div className="bodega-actions bodega-end"><Button onClick={close} disabled={locked}>Cancelar</Button><button className="btn btn-fyag-primary bodega-button" type="submit" disabled={disabled||!article&&!result}><BodegaIcon name="check"/>{article?'Guardar material':operations[form.kind][2]}</button></div>
   </form></section>;
 }
 if(detail)return <section className="commercial-page bodega-page"><ArticleDetail row={detail} onBack={()=>setDetail(null)} onEdit={edit} onIngress={r=>begin('INGRESO',r)} disabled={disabled}/></section>;
 const paginated=data&&section!=='resumen',receive=section==='devoluciones',isOperations=section==='entregas'||receive;
 const emptyState=listEmptyState(section,current.filters);
 return <section className="commercial-page bodega-page"><Header title={titles[section]} sub={descriptions[section]}><Button icon="refresh" aria-label="Actualizar" disabled={api.busy||api.loading||api.locked} onClick={()=>setRevision(n=>n+1)}>Actualizar</Button>{section==='inventario'&&<Button primary icon="plus" disabled={disabled} onClick={()=>edit(null)}>Nuevo material</Button>}{section==='movimientos'&&<Button primary icon="plus" disabled={disabled} onClick={()=>begin('INGRESO')}>Registrar ingreso</Button>}</Header><Errors error={api.error}/>{message&&<p role="status" className="alert alert-info">{message}</p>}{api.loading&&(!data||section!=='resumen'&&!data.results.length)&&<p role="status">Cargando datos…</p>}
 {section==='resumen'?<><div className="bodega-kpis">{[['materiales','Materiales registrados','inventory','inventario'],['sin_stock','Materiales activos sin stock','warning','inventario'],['entregas','Entregas pendientes','delivery','bodega_entregas'],['devoluciones','Devoluciones pendientes','returns','bodega_devoluciones']].map(([key,label,icon,to])=><button type="button" key={key} className={'card-fyag bodega-kpi '+(key==='sin_stock'?'bodega-kpi-warning':'')} disabled={disabled} onClick={()=>{const target=modules[to],f=key==='sin_stock'?{...blank('inventario'),stock:'sin_stock',estado:'activo'}:blank(target);setQueries(old=>({...old,[target]:{filters:f,page:1}}));setDrafts(old=>({...old,[target]:f}));navigate(to);}}><span>{label}<BodegaIcon name={icon}/></span><strong>{data?.[key]??'—'}</strong></button>)}</div><section className="card-fyag bodega-panel"><h2>Acciones rápidas</h2><div className="bodega-quick">{[['plus','Registrar ingreso',()=>begin('INGRESO')],['delivery','Despachar material',()=>navigatePending('bodega_entregas')],['returns','Recibir devolución',()=>navigatePending('bodega_devoluciones')]].map(([icon,label,action])=><button className="bodega-quick-action" type="button" key={label} disabled={disabled} onClick={action}><BodegaIcon name={icon}/>{label}<BodegaIcon name="chevron"/></button>)}</div></section>{data&&!api.loading&&!api.error&&<div className="bodega-summary-grid"><section className="card-fyag bodega-panel"><div className="bodega-row"><h2>Entregas por realizar</h2><Button onClick={()=>navigatePending('bodega_entregas')}>Ver todas</Button></div>{data.pendientes.length?data.pendientes.map(row=><Pending key={row.id} row={row} onAction={r=>begin('ENTREGA',r)} disabled={disabled}/>):<Empty state="deliveries" compact/>}</section><div className="bodega-stack"><section className="card-fyag bodega-panel"><h2>Devoluciones pendientes</h2>{data.retornos.length?data.retornos.map(row=><Pending key={row.id} row={row} receive onAction={r=>begin('DEVOLUCION',r)} disabled={disabled}/>):<Empty state="returns" compact/>}</section><section className="card-fyag bodega-panel"><h2>Materiales sin existencias</h2>{data.faltantes.length?data.faltantes.map(row=><div className="bodega-row bodega-faltante" key={row.id}><Material row={row}/><strong className="bodega-negative">{movementAmount(row.saldo,row.unidad)}</strong></div>):<Empty state="stock" compact/>}</section></div></div>}</>:<>
 {isOperations&&<Tabs label="Vista de operaciones" value={current.filters.vista} onChange={v=>filter('vista',v)} disabled={disabled} items={[['pendientes','Pendientes'],['historial','Historial'],['autorizaciones','Autorizaciones']]}/>}
 <section className="card-fyag bodega-panel"><div className="bodega-row"><div><h2>{section==='inventario'?'Catálogo de materiales':section==='movimientos'?'Historial de movimientos':current.filters.vista==='pendientes'?'Autorizaciones pendientes':current.filters.vista==='historial'?'Operaciones realizadas':'Todas las autorizaciones'}</h2><small>{data?recordCount(data.count):'—'}</small></div>{!isOperations&&<Button icon="filter" aria-expanded={filterOpen} onClick={()=>setFilterOpen(x=>!x)}>Filtros</Button>}</div>
 <form onSubmit={apply} className="bodega-filter-form"><div className="bodega-search"><input aria-label="Buscar registros" className="form-control" maxLength={150} placeholder={isOperations?'Material, código de obra o referencia':'Nombre o código de material'} value={draft.buscar||''} disabled={disabled} onChange={e=>changeDraft('buscar',e.target.value)}/><button className="btn btn-outline-secondary bodega-button" disabled={disabled}><BodegaIcon name="search"/>Buscar</button></div>
 {filterOpen&&<div className="bodega-filters">{section==='inventario'?<label className="bodega-field">Estado administrativo<select className="form-select" value={draft.estado} onChange={e=>changeDraft('estado',e.target.value)} disabled={disabled}><option value="">Todos</option><option value="activo">Activo</option><option value="inactivo">Inactivo</option></select></label>:<><label className="bodega-field">Tipo<select className="form-select" value={draft.tipo} onChange={e=>changeDraft('tipo',e.target.value)} disabled={disabled}><option value="">Todos</option>{['INGRESO','SALIDA','DEVOLUCION','MERMA'].map(k=><option key={k} value={k}>{kinds[k]}</option>)}</select></label><Field label="Desde" type="date" value={draft.desde} onChange={v=>changeDraft('desde',v)} disabled={disabled}/><Field label="Hasta" type="date" value={draft.hasta} onChange={v=>changeDraft('hasta',v)} disabled={disabled}/></>}<button className="btn btn-fyag-primary" disabled={disabled}>Aplicar filtros</button></div>}
 </form>
 {section==='inventario'&&<Tabs label="Disponibilidad" value={current.filters.stock} onChange={v=>filter('stock',v)} disabled={disabled} items={[['','Todos'],['con_stock','Con stock'],['sin_stock','Sin stock']]}/>}
 {Object.entries(current.filters).some(([k,v])=>k!=='vista'&&v)&&<div className="bodega-row"><small>Filtros aplicados</small><Button onClick={()=>{const f=blank(section);if(isOperations)f.vista=current.filters.vista;setQuery(f);setDrafts(old=>({...old,[section]:f}));}} disabled={disabled}>Limpiar filtros</Button></div>}
 {paginated&&(data.results.length>0||!api.loading&&!api.error)&&(section==='inventario'?<Table headers={['Material','Disponible','Estado administrativo','Disponibilidad','Detalle']} empty={!data.results.length} emptyState={emptyState}>{data.results.map(row=><tr key={row.id}><td><Material row={row}/></td><td><strong className={milli(row.saldo)===0n?'bodega-negative':''}>{movementAmount(row.saldo,row.unidad)}</strong></td><td>{row.activo?'Activo':'Inactivo'}</td><td>{milli(row.saldo)===null?'No disponible':milli(row.saldo)===0n?<span className="bodega-negative">Sin stock</span>:<span className="bodega-good">Con stock</span>}</td><td><button type="button" className="btn btn-link bodega-open" aria-label={'Ver material '+row.nombre} disabled={disabled} onClick={()=>setDetail(row)}><BodegaIcon name="chevron"/></button></td></tr>)}</Table>:section==='movimientos'?<MovementTable rows={data.results} emptyState={emptyState}/>:current.filters.vista==='pendientes'?(data.results.length?<div className="bodega-pending-grid">{data.results.map(row=><Pending key={row.id} row={row} receive={receive} onAction={r=>begin(receive?'DEVOLUCION':'ENTREGA',r)} disabled={disabled}/>)}</div>:<Empty state={emptyState}/>):<OperationTable rows={data.results} emptyState={emptyState} authorization={current.filters.vista==='autorizaciones'} receive={receive}/>)}
 {paginated&&(data.next||data.previous)&&<Pager data={data} page={current.page} setPage={page=>setQuery(current.filters,page)} disabled={disabled}/>}</section></>}
 </section>;
}
