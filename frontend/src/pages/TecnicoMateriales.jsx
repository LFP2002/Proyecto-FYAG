import React,{useEffect,useRef,useState} from 'react';
import {useAuth} from '../auth/AuthContext.jsx';
import {useApp} from '../context/AppContext.jsx';
import {useApi} from '../integrations/useApi.js';
import {Errors,Pager} from '../comercial/ui.jsx';
import {movementAmount,milli,shortUnit,recordCount} from '../bodega/domain.js';
import {civilTime} from '../obras/tecnicoDomain.js';
import {ROOT,TYPES,STATES,path,record,readPage,payload} from '../obras/materialesTecnico.js';
import TecIcon from '../obras/TecIcon.jsx';
import '../styles/pages/tecnico.css';

const blank={buscar:'',tipo:''};
const labelState={EN_PROCESO:'En ejecución',SUSPENDIDA:'Suspendida'};
const eventLabels={CREACION:'Registro enviado',APROBACION:'Aprobación',RECHAZO:'Rechazo'};
function Button({icon,primary,children,...props}){return <button type="button" className={'btn tec-button '+(primary?'btn-fyag-primary':'btn-outline-secondary')} {...props}>{icon&&<TecIcon name={icon}/>} {children}</button>;}
function Status({row}){return <span className={'tec-status '+(row.estado==='APROBADA'?'good':row.estado==='RECHAZADA'?'bad':'warn')}>{STATES[row.estado]}</span>;}
function Fact({label,children}){return <div><small>{label}</small><strong>{children}</strong></div>;}
function Empty({title,description}){return <div className="tec-empty" role="status"><TecIcon name="inbox"/><strong>{title}</strong><p>{description}</p></div>;}
function Picker({section,label,value,onChange,workId,disabled}){
 const api=useApi(),[open,setOpen]=useState(false),[draft,setDraft]=useState(''),[term,setTerm]=useState(''),[page,setPage]=useState(1),[data,setData]=useState(null);
 const trigger=useRef(null);
 const url=path(section,{buscar:term,...(section==='entregas'?{obra:workId}:{})},page);
 useEffect(()=>{if(!open||disabled)return;setData(null);api.setError(null);void api.load('options',url,v=>setData(readPage(v,section,workId)));return()=>api.cancelRead('options');},[url,open,disabled]);
 const choose=r=>{onChange(r);setOpen(false);trigger.current?.focus?.();};
 const labelFor=r=>section==='obras'?r.codigo+' · '+r.cliente:section==='entregas'?r.material.nombre:r.nombre;
 const sub=r=>section==='obras'?r.categoria+' · '+labelState[r.estado]:section==='entregas'?r.material.codigo+' · Entrega #'+r.id+' · '+civilTime(r.creado_en):r.codigo+' · '+shortUnit(r.unidad);
 return <div className="tec-picker"><label className="form-label">{label}</label><button ref={trigger} type="button" className="tec-picker-trigger" disabled={disabled} aria-label={label} aria-expanded={open&&!disabled} onClick={()=>setOpen(v=>!v)}><TecIcon name="search"/><span>{value?<><strong>{labelFor(value)}</strong><small>{sub(value)}</small></>:'Seleccionar '+label.toLowerCase()}</span><TecIcon name="chevron"/></button>
 {open&&!disabled&&<div className="tec-picker-menu" onKeyDown={e=>{if(e.key==='Escape'){e.stopPropagation();setOpen(false);trigger.current?.focus();}}}><div className="tec-search"><input className="form-control" aria-label={'Buscar '+label.toLowerCase()} value={draft} maxLength={150} onChange={e=>setDraft(e.target.value)} onKeyDown={e=>{if(e.key==='Enter'){e.preventDefault();setTerm(draft.trim());setPage(1);}}}/><Button icon="search" disabled={api.loading} onClick={()=>{setTerm(draft.trim());setPage(1);}}>Buscar</Button></div>
 <Errors error={api.error}/>{api.loading&&<p role="status">Cargando opciones…</p>}
 {data&&!api.loading&&!api.error&&<div className="tec-picker-results">{data.results.map(r=><button key={r.id} type="button" className="tec-picker-option" onClick={()=>choose(r)}><span><strong>{labelFor(r)}</strong><small>{sub(r)}</small></span>{section==='entregas'&&<small>Remanente: {movementAmount(r.remanente,r.unidad)}</small>}</button>)}{!data.results.length&&<Empty title="No hay opciones disponibles" description={section==='obras'&&!term?'No tienes obras en ejecución o suspendidas.':section==='entregas'&&!term?'No hay entregas registradas para esta obra.':'Prueba con otra búsqueda.'}/>}</div>}
 {data&&(data.next||data.previous)&&<Pager data={data} page={page} setPage={setPage} disabled={api.loading}/>}</div>}</div>;
}
function TextField({label,value,onChange,disabled,area=false,max=2000,required=true}){
 const props={className:'form-control',value,onChange:e=>onChange(e.target.value),disabled,maxLength:max,required};
 return <label className="tec-field">{label}{area?<textarea rows={3} {...props}/>:<input {...props}/>}</label>;
}
function Detail({row,loss,onBack,onRefresh,loading}){
 const name=loss?'Merma':'Solicitud';
 return <><div className="tec-row"><Button icon="back" onClick={onBack}>Volver a {loss?'mis mermas':'solicitudes'}</Button><Button icon="refresh" disabled={loading} onClick={onRefresh}>Actualizar</Button></div>
 <header className="tec-heading fyag-detail-heading"><div><h1>{name} #{row.id}</h1><p>{row.obra.codigo} · {row.obra.cliente} · {row.obra.categoria}</p></div><Status row={row}/></header>
 <div className="tec-detail-kpis"><section className="card-fyag tec-panel"><small>{loss?'Cantidad afectada':'Cantidad solicitada'}</small><strong>{movementAmount(row.cantidad,row.unidad)}</strong></section><section className="card-fyag tec-panel"><small>{loss?'Tipo de merma':'Cantidad aprobada'}</small><strong>{loss?TYPES[row.tipo]:movementAmount(row.cantidad_aprobada,row.unidad)}</strong></section></div>
 <section className="card-fyag tec-panel"><h2>Información del material</h2><strong>{row.material.nombre}</strong><small className="tec-muted">{row.material.codigo}{loss?' · Entrega #'+row.entrega:''} · {civilTime(row.creado_en)}</small><div className="tec-record-text"><small>{loss?'Motivo informado':'Justificación'}</small><p>{loss?row.motivo:row.justificacion}</p></div>{loss&&<><div className="tec-record-text"><small>Actividad realizada</small><p>{row.actividad}</p></div>{row.referencia&&<div className="tec-record-text"><small>Referencia</small><p>{row.referencia}</p></div>}</>}</section>
 <section className="card-fyag tec-panel"><h2>Resolución</h2>{row.estado==='PENDIENTE'?<p>En espera de revisión por el supervisor.</p>:<><Status row={row}/><div className="tec-record-text"><small>Motivo de la decisión</small><p>{row.motivo_decision}</p></div><div className="tec-facts"><Fact label="Resuelto por">{row.decidido_por||'—'}</Fact><Fact label="Fecha de resolución">{civilTime(row.decidido_en)}</Fact></div>{!loss&&row.estado==='APROBADA'&&<p>La aprobación autoriza la entrega; no confirma que Bodega haya despachado el material.</p>}</>}</section>
 <section className="card-fyag tec-panel"><h2>Historial</h2>{row.historial.length?<ol className="tec-record-history">{row.historial.map(e=><li key={e.id}><strong>{eventLabels[e.tipo]}</strong><small className="tec-muted">{civilTime(e.creado_en)} · {e.actor}</small><p>{e.motivo}</p></li>)}</ol>:<p>No hay eventos registrados.</p>}</section></>;
}
export default function TecnicoMateriales({loss=false}){
 const {user}=useAuth(),app=useApp(),api=useApi();
 const [state,setState]=useState(''),[filters,setFilters]=useState(blank),[draft,setDraft]=useState(blank),[expanded,setExpanded]=useState(false),[page,setPage]=useState(1),[data,setData]=useState(null),[selected,setSelected]=useState(null),[form,setForm]=useState(null),[intent,setIntent]=useState(null),[retry,setRetry]=useState(false),[discard,setDiscard]=useState(false),[message,setMessage]=useState('');
 const writing=useRef(false);
 const section=loss?'mermas':'solicitudes',detailSection=loss?'merma_detalle':'solicitud_detalle',writePath=ROOT+(loss?'mermas-obra/':'solicitudes-materiales/');
 const url=path(section,{estado:state,buscar:filters.buscar,...(loss?{tipo:filters.tipo}:{})},page);
 const title=loss?'Mis mermas':'Solicitudes de materiales',back=loss?'Volver a mis mermas':'Volver a solicitudes';
 const blocked=api.busy||api.loading||api.locked||!!intent,locked=api.busy||api.locked||!!intent;
 const list=(target=url)=>api.load('list',target,v=>setData(readPage(v,section)));
 const detail=(id,apply=setSelected)=>api.load('detail',path(detailSection,{id}),v=>{const r=record(v,loss,true);if(r.id!==id)throw Error('Registro distinto al solicitado.');apply(r);});
 useEffect(()=>{if(user.role!=='TECNICO')return;setData(null);api.setError(null);void list();return()=>api.cancelRead('list');},[url,user.id,user.role]);
 useEffect(()=>{app?.setNavigationBlocked?.(locked);return()=>app?.setNavigationBlocked?.(false);},[locked,app?.setNavigationBlocked]);
 function start(){if(blocked)return;setMessage('');api.setError(null);setForm({work:null,material:null,cantidad:'',tipo:'CORTE_NO_REUTILIZABLE',motivo:'',actividad:'',referencia:'',key:crypto.randomUUID()});}
 function close(){if(locked)return;setForm(null);api.setError(null);}
 function update(k,v){setForm(old=>({...old,[k]:v,...(k==='work'?{material:null,cantidad:''}:k==='material'?{cantidad:''}:{})}));}
 function apply(e){e.preventDefault();if(blocked)return;setFilters({...draft,buscar:draft.buscar.trim()});setPage(1);setExpanded(false);}
 function clear(){setDraft(blank);setFilters(blank);setPage(1);}
 function inspect(id){api.setError(null);void detail(id);}
 async function confirm(body){
  if(writing.current)return;
  writing.current=true;app?.setNavigationBlocked?.(true);setIntent(body);setRetry(false);setDiscard(false);
  try{
   const ok=await api.write(writePath,'POST',body,async v=>{
    if(!Number.isSafeInteger(v?.id)||v.id<=0)throw Error('No se confirmó el registro.');
    let found=null;
    await api.requiredLoad('detail',path(detailSection,{id:v.id}),r=>{found=record(r,loss,true);if(found.id!==v.id)throw Error('Registro distinto al enviado.');});
    await api.requiredLoad('list',path(section,{estado:state,buscar:filters.buscar,...(loss?{tipo:filters.tipo}:{})},1),r=>setData(readPage(r,section)));
    setSelected(found);setPage(1);setIntent(null);setForm(null);setMessage(loss?'Merma informada.':'Solicitud enviada.');
   });
   if(ok)setIntent(null);
  }finally{writing.current=false;}
 }
 useEffect(()=>{if(intent&&!api.busy&&!api.locked&&!retry&&api.error&&Number.isInteger(api.error.status)&&api.error.status>0&&api.error.status<500&&api.error.status!==409){setIntent(null);setForm(old=>old?{...old,key:crypto.randomUUID()}:old);}},[intent,api.busy,api.locked,api.error,retry]);
 async function verify(){
  if(!intent||api.busy||api.loading)return;
  let id=null,row=null;
  const conflict=api.error?.status===409;
  const ok=await api.reconcile(async()=>{
   if(!await api.load('confirmation',path('confirmacion',{tipo:loss?'MERMA':'SOLICITUD',clave:intent.clave_idempotencia}),v=>{if(!v||!(v.id===null||Number.isSafeInteger(v.id)&&v.id>0))throw Error('Confirmación inesperada.');id=v.id;}))return false;
   if(id&&!await detail(id,r=>{row=r;}))return false;
   return list(path(section,{estado:state,buscar:filters.buscar,...(loss?{tipo:filters.tipo}:{})},1));
  });
  if(ok){setPage(1);if(id){setSelected(row);setForm(null);setIntent(null);setRetry(false);setDiscard(false);setMessage('Registro confirmado por el servidor.');}else{setRetry(true);setDiscard(conflict);}}
 }
 const body=form?payload(form,loss):null;
 if(user.role!=='TECNICO')return null;
 if(form)return <section className="commercial-page tecnico-page">
  <div className="tec-row"><Button icon="back" disabled={locked} onClick={close}>{back}</Button></div>
  <header className="tec-heading"><div><h1>{loss?'Informar merma':'Nueva solicitud'}</h1><p>{loss?'Registra una pérdida de material entregado a tu obra.':'Solicita material para una obra asignada.'}</p></div></header><Errors error={api.error}/>
  <form className="tec-material-form" onSubmit={e=>{e.preventDefault();if(!blocked&&body)void confirm(body);}}>
   <section className="card-fyag tec-panel"><h2>{loss?'Material afectado':'Material solicitado'}</h2>
   <Picker section="obras" label="Obra" value={form.work} onChange={r=>update('work',r)} disabled={locked}/>
   <Picker key={form.work?.id||0} section={loss?'entregas':'catalogo'} label={loss?'Material entregado':'Material'} workId={form.work?.id} value={form.material} onChange={r=>update('material',r)} disabled={locked||!form.work}/>
   {loss&&form.material&&<><div className="tec-facts tec-material-balance"><Fact label="Cantidad entregada">{movementAmount(form.material.cantidad,form.material.unidad)}</Fact><Fact label="Remanente consultado">{movementAmount(form.material.remanente,form.material.unidad)}</Fact></div><small className="tec-muted">Descuenta devoluciones recibidas y mermas aprobadas. Los reportes pendientes no reservan saldo.</small></>}
   </section>
   <section className="card-fyag tec-panel"><h2>{loss?'Datos de la merma':'Datos de la solicitud'}</h2><div className="tec-facts"><label className="tec-field">Cantidad {form.material?'('+shortUnit(form.material.unidad)+')':''}<input className="form-control" aria-label="Cantidad" required inputMode="decimal" maxLength={13} disabled={locked} value={form.cantidad} onChange={e=>update('cantidad',e.target.value)}/></label>
   {loss&&<label className="tec-field">Tipo de merma<select className="form-select" disabled={locked} value={form.tipo} onChange={e=>update('tipo',e.target.value)}>{Object.entries(TYPES).map(([k,v])=><option key={k} value={k}>{v}</option>)}</select></label>}</div>
   {loss&&form.material&&milli(form.cantidad)>milli(form.material.cantidad)&&<p className="tec-observation">La cantidad no puede superar la entrega original.</p>}
   {loss&&form.material&&milli(form.cantidad)>milli(form.material.remanente)&&milli(form.cantidad)<=milli(form.material.cantidad)&&<p className="tec-observation">La cantidad supera el remanente consultado. El supervisor deberá verificarla antes de aprobar.</p>}
   <TextField label={loss?'Motivo':'Justificación'} area value={form.motivo} onChange={v=>update('motivo',v)} disabled={locked}/>
   {loss&&<><TextField label="Actividad realizada" area value={form.actividad} onChange={v=>update('actividad',v)} disabled={locked}/><TextField label="Referencia de respaldo (opcional)" max={150} required={false} value={form.referencia} onChange={v=>update('referencia',v)} disabled={locked}/></>}
   <small className="tec-muted">{loss?'La declaración queda pendiente de revisión por el supervisor.':'El supervisor aprueba o rechaza la solicitud. La aprobación no equivale a un despacho.'}</small>
   </section>
   {intent&&<section className="card-fyag tec-panel"><h2>Verificar registro</h2><p>No se reenviará automáticamente. Consulta al servidor antes de continuar.</p><div className="tec-card-actions">{api.locked&&<Button icon="refresh" disabled={api.busy||api.loading} onClick={()=>void verify()}>Verificar registro</Button>}{retry&&<Button primary disabled={api.busy||api.loading} onClick={()=>void confirm(intent)}>Reintentar con los mismos datos</Button>}{discard&&<Button disabled={api.busy||api.loading} onClick={()=>{setIntent(null);setRetry(false);setDiscard(false);setForm(old=>({...old,key:crypto.randomUUID()}));}}>Descartar intento rechazado</Button>}</div></section>}
   <div className="tec-card-actions"><Button disabled={locked} onClick={close}>Cancelar</Button><button type="submit" className="btn btn-fyag-primary tec-button" disabled={blocked||!body}><TecIcon name="check"/>{loss?'Registrar merma':'Enviar solicitud'}</button></div>
  </form></section>;
 if(selected)return <section className="commercial-page tecnico-page"><Errors error={api.error}/>{message&&<p role="status" className="alert alert-info">{message}</p>}<Detail row={selected} loss={loss} loading={api.loading} onBack={()=>{api.cancelRead('detail');setSelected(null);setMessage('');api.setError(null);}} onRefresh={()=>inspect(selected.id)}/></section>;
 const filtered=!!(filters.buscar||filters.tipo);
 return <section className="commercial-page tecnico-page"><header className="tec-heading"><div><h1>{title}</h1><p>{loss?'Informa y consulta pérdidas de materiales en tus obras.':'Solicita materiales y consulta su estado.'}</p></div><div className="tec-heading-actions"><Button icon="refresh" disabled={blocked} onClick={()=>{api.setError(null);void list();}}>Actualizar</Button><Button icon="plus" primary disabled={blocked} onClick={start}>{loss?'Informar merma':'Nueva solicitud'}</Button></div></header>
 <div className="tec-tabs" role="group" aria-label="Estado del registro">{[['','Todas'],...Object.entries(STATES).map(([k,v])=>[k,v+'s'])].map(([k,v])=><button type="button" key={k} aria-pressed={state===k} disabled={blocked} onClick={()=>{setState(k);setPage(1);}}>{v}</button>)}</div>
 <section className="card-fyag tec-panel"><div className="tec-row"><h2>{loss?'Registro de mermas':'Mis solicitudes'}</h2><small>{data?recordCount(data.count):'—'}</small></div>
 <form className="tec-search" onSubmit={apply}><input className="form-control" aria-label="Buscar material u obra" placeholder="Material, código de obra o cliente" value={draft.buscar} maxLength={150} disabled={blocked} onChange={e=>setDraft({...draft,buscar:e.target.value})}/><button type="submit" className="btn btn-outline-secondary tec-button" disabled={blocked}><TecIcon name="search"/>Buscar</button>{loss&&<Button icon="filter" aria-expanded={expanded} disabled={blocked} onClick={()=>setExpanded(v=>!v)}>Filtros</Button>}</form>
 {expanded&&loss&&<form className="tec-filters" onSubmit={apply}><label className="tec-field">Tipo de merma<select className="form-select" value={draft.tipo} disabled={blocked} onChange={e=>setDraft({...draft,tipo:e.target.value})}><option value="">Todos</option>{Object.entries(TYPES).map(([k,v])=><option key={k} value={k}>{v}</option>)}</select></label><button type="submit" className="btn btn-fyag-primary" disabled={blocked}>Aplicar filtros</button></form>}
 {filtered&&<div className="tec-row"><small>Filtros aplicados</small><Button disabled={blocked} onClick={clear}>Limpiar filtros</Button></div>}
 <Errors error={api.error}/>{api.loading&&!data&&<p role="status">Cargando registros…</p>}
 {data&&!api.error&&!api.loading&&!data.results.length&&<Empty title={filtered?'No hay resultados':state?'No tienes '+(loss?'mermas ':'solicitudes ')+STATES[state].toLowerCase()+'s':loss?'Todavía no tienes mermas':'Todavía no tienes solicitudes'} description={filtered?'Prueba otra búsqueda o limpia los filtros.':state?'Los registros con este estado aparecerán aquí.':loss?'Las pérdidas informadas aparecerán aquí.':'Las solicitudes de materiales para tus obras aparecerán aquí.'}/>}
 {data&&!api.error&&!api.loading&&data.results.length>0&&<div className="tec-work-grid">{data.results.map(r=><article className="tec-work" key={r.id}><div className="tec-row"><small>{loss?'Merma':'Solicitud'} #{r.id} · {r.obra.codigo}</small><Status row={r}/></div><div><h2>{r.material.nombre}</h2><small>{r.material.codigo} · {r.obra.cliente}</small></div><div className="tec-facts"><Fact label={loss?'Cantidad afectada':'Cantidad solicitada'}>{movementAmount(r.cantidad,r.unidad)}</Fact><Fact label={loss?'Tipo de merma':'Cantidad aprobada'}>{loss?TYPES[r.tipo]:movementAmount(r.cantidad_aprobada,r.unidad)}</Fact></div><div className="tec-card-actions"><small>{civilTime(r.creado_en)}</small><Button icon="chevron" disabled={blocked} onClick={()=>inspect(r.id)}>Ver detalle</Button></div></article>)}</div>}
 {data&&(data.next||data.previous)&&<Pager data={data} page={page} setPage={setPage} disabled={blocked}/>}
 {api.error?.status===404&&page!==1&&<Button onClick={()=>setPage(1)}>Volver a la primera página</Button>}
 </section></section>;
}
