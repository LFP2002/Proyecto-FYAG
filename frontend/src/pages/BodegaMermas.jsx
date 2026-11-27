import {quantityHint} from '../utils/decimalInput.js';
import React,{useEffect,useRef,useState} from 'react';
import {useAuth} from '../auth/AuthContext.jsx';
import {useApp} from '../context/AppContext.jsx';
import {useApi} from '../integrations/useApi.js';
import {Errors,Pager} from '../comercial/ui.jsx';
import {Button,Header,Tabs,Table,Empty,Material,Fact,Field,MaterialPicker} from './Bodega.jsx';
import BodegaIcon from '../bodega/icons.jsx';
import {ROOT,pathFor,readPage,movementAmount,milli,decimal,shortUnit,timestamp,recordCount} from '../bodega/domain.js';

const types={DANO:'Daño',VENCIMIENTO:'Vencimiento',EXTRAVIO:'Extravío',DIFERENCIA_CONTEO:'Diferencia de conteo',OTRA:'Otra'};
const states={PENDIENTE:'Pendiente',APROBADA:'Aprobada',RECHAZADA:'Rechazada'};
const events={CREACION:'Merma informada',APROBACION:'Merma aprobada',RECHAZO:'Merma rechazada'};
const initial={buscar:'',estado:'',tipo:''};
function status(row){return row.estado==='APROBADA'?'good':row.estado==='RECHAZADA'?'negative':'warn';}
function validate(row,detail=false){
 if(!row||!Number.isSafeInteger(row.id)||row.id<1||!Number.isSafeInteger(row.articulo)||row.articulo<1||!Object.hasOwn(types,row.tipo)||!Object.hasOwn(states,row.estado)||!(milli(row.cantidad)>0n)||!['nombre','codigo','unidad','actor','creado_en','motivo','referencia','motivo_decision'].every(k=>typeof row[k]==='string')||!Number.isFinite(Date.parse(row.creado_en)))throw Error('Respuesta de merma inesperada.');
 if(detail&&(!Array.isArray(row.historial)||row.historial.length>2||row.historial.some(e=>!Number.isSafeInteger(e.id)||!Object.hasOwn(events,e.tipo)||!['actor','motivo','creado_en'].every(k=>typeof e[k]==='string'))))throw Error('Historial de merma inesperado.');
 return row;
}
function readLossPage(v){const result=readPage(v);result.results.forEach(r=>validate(r));return result;}
function LossDetail({row,onBack,onRefresh,busy}){
 return <div className="bodega-stack bodega-loss-detail">
  <div className="bodega-actions"><Button icon="back" onClick={onBack}>Volver a mermas</Button></div>
  <Header detail title={'Merma #'+row.id} sub={row.nombre+' · '+row.codigo}><span className={'bodega-'+status(row)}>{states[row.estado]}</span><Button icon="refresh" disabled={busy} onClick={onRefresh}>Actualizar</Button></Header>
  <section className="card-fyag bodega-panel"><div className="bodega-facts"><Fact label="Cantidad afectada">{movementAmount(row.cantidad,row.unidad)}</Fact><Fact label="Tipo de merma">{types[row.tipo]}</Fact><Fact label="Fecha de registro">{timestamp(row.creado_en)}</Fact></div></section>
  <div className="bodega-form-grid">
   <section className="card-fyag bodega-panel"><h2>Información de la merma</h2><div><small className="bodega-muted">Motivo informado</small><p className="commercial-long-text">{row.motivo}</p></div><div><small className="bodega-muted">Referencia de respaldo</small><p className="commercial-long-text">{row.referencia||'—'}</p></div><Fact label="Informado por">{row.actor}</Fact></section>
   <section className={'card-fyag bodega-panel bodega-resolution '+(row.estado==='APROBADA'?'approved':row.estado==='RECHAZADA'?'rejected':'')}><h2>Resolución</h2>{row.estado==='PENDIENTE'?<p>En espera de revisión por Finanzas. El reporte por sí solo no modifica las existencias.</p>:<><Fact label="Decisión">{states[row.estado]}</Fact><div><small className="bodega-muted">Motivo de la decisión</small><p className="commercial-long-text">{row.motivo_decision||'—'}</p></div><Fact label="Resuelto por">{row.decidido_por||'—'}</Fact><Fact label="Fecha de resolución">{timestamp(row.decidido_en)}</Fact></>}</section>
  </div>
  <section className="card-fyag bodega-panel"><h2>Historial de la merma</h2>{row.historial.length?<ol className="bodega-loss-history">{row.historial.map(e=><li key={e.id}><strong>{events[e.tipo]}</strong><small className="bodega-muted">{timestamp(e.creado_en)} · {e.actor}</small><p className="commercial-long-text">{e.motivo}</p></li>)}</ol>:<p>No hay eventos registrados.</p>}</section>
 </div>;
}
export default function BodegaMermas(){
 const {user}=useAuth(),{setNavigationBlocked}=useApp(),api=useApi();
 const [filters,setFilters]=useState(initial),[draft,setDraft]=useState(initial),[filterOpen,setFilterOpen]=useState(false),[page,setPage]=useState(1),[data,setData]=useState(null),[selected,setSelected]=useState(null),[form,setForm]=useState(null),[intent,setIntent]=useState(null),[message,setMessage]=useState(''),[replay,setReplay]=useState(false),[discard,setDiscard]=useState(false),[revision,setRevision]=useState(0);
 const writing=useRef(false);
 const path=pathFor('mermas',filters,page),disabled=api.loading||api.busy||api.locked||!!intent;
 const load=(p=path)=>api.load('losses',p,v=>setData(readLossPage(v)));
 useEffect(()=>{if(user.role!=='BODEGUERO')return;setData(null);api.setError(null);void load();return()=>api.cancelRead('losses');},[path,revision,user.role]);
 useEffect(()=>{setNavigationBlocked(!!intent||api.busy||api.locked);return()=>setNavigationBlocked(false);},[intent,api.busy,api.locked,setNavigationBlocked]);
 function inspect(id){api.setError(null);void api.load('loss-detail',pathFor('merma_detalle',{merma:id}),v=>{const row=validate(v,true);if(row.id!==id)throw Error('Merma distinta a la solicitada.');setSelected(row);});}
 function start(){if(disabled)return;api.setError(null);setMessage('');setForm({row:null,cantidad:'',tipo:'DANO',referencia:'',motivo:'',key:crypto.randomUUID()});}
 function update(key,value){setForm(old=>({...old,[key]:value}));}
 function close(){if(intent||api.busy||api.locked)return;setForm(null);api.setError(null);}
 function apply(event){event.preventDefault();if(disabled)return;setPage(1);setFilters({...draft,buscar:draft.buscar.trim()});setFilterOpen(false);}
 function changeState(estado){const next={...filters,estado};setFilters(next);setDraft(next);setPage(1);}
 async function confirm(i){
  if(writing.current)return;
  writing.current=true;setNavigationBlocked(true);setIntent(i);setReplay(false);setDiscard(false);
  try{
   const ok=await api.write(ROOT+'mermas-bodega/','POST',i,async v=>{
    if(!Number.isSafeInteger(v?.id)||v.id<1)throw Error('No se confirmó el registro de merma.');
    const first=pathFor('mermas',filters,1);
    await api.requiredLoad('losses',first,val=>setData(readLossPage(val)));
    await api.requiredLoad('loss-detail',pathFor('merma_detalle',{merma:v.id}),val=>{const row=validate(val,true);if(row.id!==v.id)throw Error('Merma distinta a la registrada.');setSelected(row);});
    setPage(1);setIntent(null);setForm(null);setMessage('Reporte de merma registrado.');
   });
   if(ok)setIntent(null);
  }finally{writing.current=false;}
 }
 useEffect(()=>{if(intent&&!api.busy&&!api.locked&&!replay&&api.error&&typeof api.error.status==='number'&&api.error.status>0&&api.error.status<500&&api.error.status!==409)setIntent(null);},[intent,api.busy,api.locked,api.error,replay]);
 async function submit(event){
  event.preventDefault();if(disabled||!form||!form.row||!(milli(form.cantidad)>0n)||!form.referencia.trim()||!form.motivo.trim())return;
  await confirm({articulo:form.row.id,cantidad:decimal(milli(form.cantidad)),tipo:form.tipo,referencia_respaldo:form.referencia.trim(),motivo:form.motivo.trim(),clave_idempotencia:form.key});
 }
 async function reconcile(){
  if(!intent||api.busy||api.loading)return;
  let id=null,detail=null;
  const conflict=api.error?.status===409;
  const ok=await api.reconcile(async()=>{
   const found=await api.load('loss-confirm',pathFor('confirmacion',{tipo:'MERMA',clave:intent.clave_idempotencia}),v=>{if(!v||!(v.id===null||Number.isSafeInteger(v.id)&&v.id>0))throw Error('Confirmación inesperada.');id=v.id;});
   if(!found)return false;
   if(id&&!await api.load('loss-detail',pathFor('merma_detalle',{merma:id}),v=>{detail=validate(v,true);if(detail.id!==id)throw Error('Merma distinta a la registrada.');}))return false;
   return load(pathFor('mermas',filters,1));
  });
  if(ok){setPage(1);if(id){setSelected(detail);setForm(null);setIntent(null);setReplay(false);setMessage('Reporte confirmado por la API.');}else{setReplay(true);setDiscard(conflict);}}
 }
 if(user.role!=='BODEGUERO')return <p role="alert">No tiene permiso para esta consulta de Bodega.</p>;
 if(form){
  const locked=api.busy||api.locked||!!intent;
  const ready=!!form.row&&milli(form.cantidad)>0n&&!!form.referencia.trim()&&!!form.motivo.trim();
  return <section className="commercial-page bodega-page"><div className="bodega-actions"><Button icon="back" disabled={locked} onClick={close}>Volver a mermas</Button></div><Header title="Informar merma" sub="Registra una pérdida física de materiales."/><Errors error={api.error}/>
   <form className="bodega-form" onSubmit={submit}>
    <div className="bodega-form-grid"><section className="card-fyag bodega-panel"><h2>Datos de la merma</h2><MaterialPicker label="Material afectado" value={form.row} onChange={r=>update('row',r)} disabled={locked}/><div className="bodega-fields"><Field label={form.row?'Cantidad ('+shortUnit(form.row.unidad)+')':'Cantidad'} value={form.cantidad} onChange={v=>update('cantidad',v)} inputMode="decimal" placeholder="Ej.: 2,5" title={quantityHint} maxLength={13} required disabled={locked}/><label className="bodega-field">Tipo de merma<select className="form-select" value={form.tipo} disabled={locked} onChange={e=>update('tipo',e.target.value)}>{Object.entries(types).map(([k,v])=><option key={k} value={k}>{v}</option>)}</select></label></div><Field label="Referencia de respaldo" value={form.referencia} onChange={v=>update('referencia',v)} required maxLength={150} disabled={locked}/><Field label="Motivo" value={form.motivo} onChange={v=>update('motivo',v)} required maxLength={2000} disabled={locked} type="textarea"/></section>
    <section className="card-fyag bodega-panel"><h2>Revisión de la merma</h2><Fact label="Existencias consultadas">{movementAmount(form.row?.saldo,form.row?.unidad)}</Fact><Fact label="Cantidad informada">{movementAmount(form.cantidad,form.row?.unidad)}</Fact><p>El reporte queda pendiente de revisión por Finanzas. Las existencias solo se modifican si se aprueba la merma y se cumplen las validaciones del servidor.</p>{form.row&&milli(form.row.saldo)!==null&&milli(form.cantidad)>milli(form.row.saldo)&&<p className="bodega-warn">La cantidad informada supera el stock consultado. Finanzas deberá verificar las existencias antes de aprobar.</p>}</section></div>
    {intent&&<section className="card-fyag bodega-panel"><h2>Verificar registro</h2><p>La operación no se reenviará automáticamente.</p><div className="bodega-actions">{api.locked&&<Button icon="refresh" disabled={api.loading||api.busy} onClick={()=>void reconcile()}>Verificar registro</Button>}{replay&&<Button primary disabled={api.loading||api.busy} onClick={()=>void confirm(intent)}>Reintentar con los mismos datos</Button>}{discard&&<Button disabled={api.loading||api.busy} onClick={()=>{setIntent(null);setReplay(false);setDiscard(false);setForm(null);setMessage('No se encontró un registro del intento rechazado.');}}>Descartar intento rechazado</Button>}</div></section>}
    <div className="bodega-actions bodega-end"><Button disabled={locked} onClick={close}>Cancelar</Button><button className="btn btn-fyag-primary bodega-button" type="submit" disabled={disabled||!ready}><BodegaIcon name="check"/>Registrar merma</button></div>
   </form></section>;
 }
 if(selected)return <section className="commercial-page bodega-page"><Errors error={api.error}/>{message&&<p role="status" className="alert alert-info">{message}</p>}<LossDetail row={selected} onBack={()=>{setSelected(null);setMessage('');api.cancelRead('loss-detail');}} onRefresh={()=>inspect(selected.id)} busy={api.loading}/></section>;
 const filtered=!!(filters.buscar||filters.tipo);
 return <section className="commercial-page bodega-page"><Header title="Mermas" sub="Registro y seguimiento de pérdidas de materiales."><Button icon="refresh" disabled={disabled} onClick={()=>setRevision(n=>n+1)}>Actualizar</Button><Button icon="plus" primary disabled={disabled} onClick={start}>Informar merma</Button></Header><Errors error={api.error}/>{message&&<p className="alert alert-info" role="status">{message}</p>}
  <Tabs label="Estado de mermas" items={[['','Todas'],['PENDIENTE','Pendientes'],['APROBADA','Aprobadas'],['RECHAZADA','Rechazadas']]} value={filters.estado} onChange={changeState} disabled={disabled}/>
  <section className="card-fyag bodega-panel"><div className="bodega-row"><div><h2>Registro de mermas</h2><small>{data?recordCount(data.count):'—'}</small></div><Button icon="filter" aria-expanded={filterOpen} onClick={()=>setFilterOpen(x=>!x)}>Filtros</Button></div>
  <form className="bodega-filter-form" onSubmit={apply}><div className="bodega-search"><input className="form-control" aria-label="Buscar material" placeholder="Nombre o código de material" maxLength={150} value={draft.buscar} disabled={disabled} onChange={e=>setDraft({...draft,buscar:e.target.value})}/><button className="btn btn-outline-secondary bodega-button" disabled={disabled}><BodegaIcon name="search"/>Buscar</button></div>{filterOpen&&<div className="bodega-filters"><label className="bodega-field">Tipo de merma<select className="form-select" disabled={disabled} value={draft.tipo} onChange={e=>setDraft({...draft,tipo:e.target.value})}><option value="">Todos</option>{Object.entries(types).map(([k,v])=><option key={k} value={k}>{v}</option>)}</select></label><button className="btn btn-fyag-primary" disabled={disabled}>Aplicar filtros</button></div>}</form>
  {filtered&&<div className="bodega-row"><small>Filtros aplicados</small><Button disabled={disabled} onClick={()=>{const next={...initial,estado:filters.estado};setFilters(next);setDraft(next);setPage(1);}}>Limpiar filtros</Button></div>}
  {api.loading&&!data&&<p role="status">Cargando datos…</p>}
  {data&&!api.loading&&!api.error&&<Table headers={['Material','Tipo','Cantidad','Estado','Fecha','Detalle']} numericColumns={[2]} empty={!data.results.length} emptyState={filtered||['APROBADA','RECHAZADA'].includes(filters.estado)?'filtered':filters.estado==='PENDIENTE'?'lossPending':'losses'}>{data.results.map(r=><tr key={r.id}><td><Material row={r}/><small className="bodega-muted">Merma #{r.id}</small></td><td>{types[r.tipo]}</td><td className="bodega-number-cell">{movementAmount(r.cantidad,r.unidad)}</td><td><span className={'bodega-'+status(r)}>{states[r.estado]}</span></td><td>{timestamp(r.creado_en)}</td><td><button type="button" className="btn btn-link bodega-open" aria-label={'Ver merma #'+r.id} onClick={()=>inspect(r.id)} disabled={disabled}><BodegaIcon name="chevron"/></button></td></tr>)}</Table>}
  {data&&(data.next||data.previous)&&<Pager data={data} page={page} setPage={setPage} disabled={disabled}/>}</section></section>;
}
