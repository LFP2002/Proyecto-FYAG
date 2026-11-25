import React,{useEffect,useState} from 'react';
import {useAuth} from '../auth/AuthContext';
import {ApiError} from '../auth/client.js';
import {budgetPath} from '../comercial/api.js';
import {formatCompactCLP,formatCivilDate} from '../utils/format.js';
import {collectionPath,obraPath,readPage} from './api.js';
import {G,OBRA_STATES,projectObra,timestamp} from './domain.js';
import {Feedback,ObraStatus,Pager,RefreshButton,useOperational} from './ui.jsx';
import EvidenceMetadata from '../integrations/EvidenceMetadata.jsx';
import Adjuntos from '../integrations/Adjuntos.jsx';

const money=value=>formatCompactCLP(value);
const amount=value=>typeof value==='string'&&/^\d+(?:\.\d{1,2})?$/.test(value);
const date=value=>value?formatCivilDate(value):'Sin programar';
const status={PLANIFICADA:'Pendiente de inicio',EN_PROCESO:'En ejecución',SUSPENDIDA:'Obra suspendida',FINALIZADA:'Obra finalizada',CANCELADA:'Obra cancelada'};
const states={CREACION:'Obra creada',EDICION:'Obra actualizada',CAMBIO_ESTADO:'Cambio de estado',CAMBIO_TECNICO:'Cambio de responsable',FINALIZACION:'Obra finalizada'};
function Fact({label,children}){return <div><dt>{label}</dt><dd>{children}</dd></div>;}
function Money({label,value,detail}){return <div className="manager-money"><span>{label}</span><strong>{money(value)}</strong>{detail&&<small>{detail}</small>}</div>;}

export default function GerenciaObra({id,onBack}){
  const {user}=useAuth();
  const [revision,setRevision]=useState(0);
  const [section,setSection]=useState('resumen');
  if(user.role!==G)return null;
  return <div className="manager-work">
    <div className="manager-work-toolbar"><button type="button" className="btn btn-outline-secondary" aria-label="Volver al listado" onClick={onBack}><span aria-hidden="true">← </span>Volver al listado</button><RefreshButton onClick={()=>setRevision(n=>n+1)}/></div>
    <ManagerContent key={revision} id={id} section={section} setSection={setSection}/>
  </div>;
}
function ManagerContent({id,section,setSection}){
  const api=useOperational(),base=obraPath(id);
  const [obra,setObra]=useState(null),[budget,setBudget]=useState(null),[cost,setCost]=useState(null),[members,setMembers]=useState(null);
  useEffect(()=>{
    void api.load('work',base,data=>{
      if(data?.id!==id||!OBRA_STATES[data.estado])throw new ApiError(502,'No se pudo confirmar la obra.');
      setObra(projectObra(data,G));
    });
  },[id]);
  useEffect(()=>{
    if(!obra)return;
    if(Number.isSafeInteger(obra.presupuesto)&&obra.presupuesto>0)void api.load('budget',budgetPath(obra.presupuesto),data=>{
      if(data?.id!==obra.presupuesto||!amount(data.monto_neto))throw new ApiError(502,'No se pudo consultar el presupuesto.');
      setBudget(data.monto_neto);
    });
    void api.load('cost',base+'costos/resumen/',data=>{
      if(data?.obra!==id||!['materiales_total','otros_total','mano_obra_total','costo_total'].every(k=>amount(data[k]))||typeof data.costos_validados!=='boolean'||typeof data.cortesia_sin_cobro!=='boolean')throw new ApiError(502,'No se pudo confirmar el resumen económico.');
      setCost(Object.fromEntries(['materiales_total','otros_total','mano_obra_total','costo_total','costos_validados','cortesia_sin_cobro','provisional'].map(k=>[k,data[k]])));
    });
    const path=base+'participantes/';
    void api.load('members',collectionPath(path,1,{activo:'true'}),data=>setMembers(readPage(data,path).count));
  },[obra]);
  const tabs=[['resumen','Resumen'],['economia','Resumen económico'],['actividad','Actividad reciente'],['turnos','Turnos'],['documentos','Documentación']];
  return <>
    <Feedback api={api}/>
    {obra&&<>
      <header className="manager-work-heading"><div><h1>{obra.codigo}</h1><p>{obra.cliente_nombre} · {obra.categoria_nombre}</p></div><ObraStatus state={obra.estado}/></header>
      <div className="manager-work-kpis">
        <Money label="Presupuesto neto" value={budget} detail="CLP"/>
        <Money label="Costo acumulado neto" value={cost?.costo_total} detail={cost?(cost.costos_validados&&!cost.provisional?'Validado':'Provisional'):'CLP'}/>
        <div className="manager-money"><span>Técnicos activos</span><strong>{members===null?'—':members}</strong><small>{obra.tecnico_nombre||'Sin responsable'}</small></div>
        <div className="manager-money"><span>Programación</span><strong className="manager-date">{date(obra.fecha_programada)}</strong><small>{status[obra.estado]}</small></div>
      </div>
      <nav className="manager-work-tabs" aria-label="Secciones gerenciales">{tabs.map(([key,label])=><button key={key} type="button" aria-pressed={section===key} onClick={()=>setSection(key)}>{label}</button>)}</nav>
      {section==='resumen'&&<section className="card-fyag manager-work-panel" aria-label="Resumen de la obra"><h2>Situación de la obra</h2><p className="manager-status">{status[obra.estado]}</p>{obra.descripcion&&<p className="commercial-long-text">{obra.descripcion}</p>}
        <dl className="manager-facts"><Fact label="Responsable">{obra.tecnico_nombre||'Sin asignar'}</Fact><Fact label="Presupuesto de origen">{obra.presupuesto_codigo||'—'}</Fact><Fact label="Inicio efectivo">{timestamp(obra.iniciado_en)}</Fact>{obra.finalizado_en&&<Fact label="Finalización">{timestamp(obra.finalizado_en)}</Fact>}</dl>
        {cost?.cortesia_sin_cobro&&<p className="manager-note">Obra registrada sin cobro.</p>}
      </section>}
      {section==='economia'&&<section className="card-fyag manager-work-panel" aria-label="Resumen económico"><h2>Distribución de costos netos · CLP</h2>{cost?<><dl className="manager-economy"><Fact label="Materiales">{money(cost.materiales_total)}</Fact><Fact label="Mano de obra">{money(cost.mano_obra_total)}</Fact><Fact label="Otros gastos">{money(cost.otros_total)}</Fact><Fact label="Costo total">{money(cost.costo_total)}</Fact></dl><p className="manager-note">{cost.costos_validados&&!cost.provisional?'Costos validados':'Costos pendientes de validación o provisionales'}</p>{cost.cortesia_sin_cobro&&<p>Obra registrada sin cobro.</p>}</>:<p>{api.loading?'Cargando costos…':'Costos no disponibles.'}</p>}</section>}
      {section==='actividad'&&<Activity id={id}/>}
      {section==='turnos'&&<ManagerTurns id={id}/>}
      {section==='documentos'&&<section className="manager-documentation"><EvidenceMetadata obraId={id}/><Adjuntos type="INFORME_TECNICO" destinationId={id} canUpload={false} readOnly/></section>}
    </>}
  </>;
}

function Activity({id}){
  const api=useOperational(),path=obraPath(id)+'historial/';
  const [data,setData]=useState(null),[page,setPage]=useState(1),[expanded,setExpanded]=useState(false);
  const [initial,setInitial]=useState(true);
  useEffect(()=>{
    setData(null);setExpanded(false);
    void api.load('history',collectionPath(path,page),result=>{
      const next=readPage(result,path);
      const last=Math.max(1,Math.ceil(next.count/25));
      if(initial){setInitial(false);if(last!==page){setPage(last);return;}}
      setData(next);
    });
  },[page,id]);
  const events=data?[...data.results].reverse():[];
  return <section className="card-fyag manager-work-panel" aria-label="Actividad reciente"><h2>Actividad reciente</h2><Feedback api={api}/>
    {data&&events.length===0&&<p>No hay actividad registrada.</p>}
    <ol className="manager-events">{(expanded?events:events.slice(0,5)).map(event=><li key={event.id}><strong>{states[event.tipo]||String(event.tipo).replaceAll('_',' ').toLocaleLowerCase('es-CL')}</strong><small>{timestamp(event.creado_en)}</small>{event.estado_nuevo&&<span><ObraStatus state={event.estado_nuevo}/></span>}{event.motivo&&<p>{event.motivo}</p>}</li>)}</ol>
    {events.length>5&&<button type="button" className="btn btn-outline-secondary btn-sm" onClick={()=>setExpanded(v=>!v)}>{expanded?'Ver menos':'Ver más actividad'}</button>}
    {data&&(data.previous||data.next)&&<Pager label="Paginación de actividad" data={data} page={page} setPage={setPage} disabled={api.loading}/>}
  </section>;
}

function ManagerTurns({id}){
  const {request}=useAuth(),api=useOperational(),path=obraPath(id)+'turnos/';
  const [data,setData]=useState(null),[page,setPage]=useState(1),[download,setDownload]=useState(null),[issue,setIssue]=useState('');
  useEffect(()=>{setData(null);void api.load('turns',collectionPath(path,page),result=>setData(readPage(result,path)));},[id,page]);
  async function photo(turn,photo){
    if(download!==null)return;
    setDownload(photo.id);setIssue('');
    let url;
    try{
      if(!Number.isSafeInteger(turn.turno_id)||turn.turno_id<1||!Number.isSafeInteger(photo.id)||photo.id<1)throw Error('Fotografía no disponible.');
      const blob=await request(path+turn.turno_id+'/fotos/'+photo.id+'/',{responseType:'blob'});
      const extension={'image/jpeg':'jpg','image/png':'png','image/webp':'webp'}[blob.type];
      if(!extension)throw Error('Fotografía no disponible.');
      url=URL.createObjectURL(blob);
      const link=document.createElement('a');link.href=url;link.download='evidencia-'+photo.id+'.'+extension;link.rel='noopener';
      document.body.appendChild(link);link.click();link.remove();
    }catch{setIssue('No se pudo descargar la fotografía.');}
    finally{if(url)setTimeout(()=>URL.revokeObjectURL(url),1000);setDownload(null);}
  }
  const closed=data?.results.filter(t=>t.terminado_en)||[];
  const durations=closed.map(t=>t.duracion_ajustada_segundos??t.duracion_segundos);
  const hours=durations.every(v=>v!==null&&v!==undefined&&v!==''&&Number.isFinite(Number(v))&&Number(v)>=0)?durations.reduce((sum,v)=>sum+Number(v),0)/3600:null;
  const states={ABIERTO:'Abierto',PENDIENTE_REVISION:'Pendiente de revisión',VALIDADO:'Validado',OBSERVADO:'Observado'};
  return <section className="card-fyag manager-work-panel" aria-label="Resumen de turnos"><h2>Turnos registrados</h2><Feedback api={api}/>{issue&&<p role="alert">{issue}</p>}
    {data&&<dl className="manager-facts"><Fact label="Total de turnos">{data.count}</Fact><Fact label={data.next||data.previous?'Horas cerradas de esta página':'Horas cerradas'}>{hours===null?'—':hours.toLocaleString('es-CL',{maximumFractionDigits:2})+' h'}</Fact></dl>}
    {data&&!data.count&&<p>No hay turnos registrados.</p>}
    <ul className="manager-turns">{data?.results.map(turn=><li key={turn.turno_id}><div><strong>{states[turn.estado_revision]||'Estado no disponible'}</strong><small>{timestamp(turn.iniciado_en)}{turn.terminado_en?' – '+timestamp(turn.terminado_en):''}</small>{turn.descripcion_trabajo&&<p>{turn.descripcion_trabajo}</p>}</div>{!!turn.fotos?.length&&<div className="manager-photo-actions">{turn.fotos.map((item,i)=><button key={item.id} type="button" className="btn btn-outline-secondary btn-sm" disabled={download!==null} onClick={()=>void photo(turn,item)}>Descargar foto {i+1}</button>)}</div>}</li>)}</ul>
    {data&&(data.next||data.previous)&&<Pager label="Paginación de turnos" data={data} page={page} setPage={setPage} disabled={api.loading}/>}
  </section>;
}
