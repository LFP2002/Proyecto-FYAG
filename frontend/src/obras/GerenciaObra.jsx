import React,{useEffect,useState} from 'react';
import {useAuth} from '../auth/AuthContext';
import {ApiError} from '../auth/client.js';
import {budgetPath} from '../comercial/api.js';
import {formatCompactCLP,formatCivilDate} from '../utils/format.js';
import {collectionPath,obraPath,readPage} from './api.js';
import {G,OBRA_STATES,projectObra} from './domain.js';
import {Feedback,ObraStatus,Pager,useOperational} from './ui.jsx';
import EvidenceMetadata from '../integrations/EvidenceMetadata.jsx';
import Adjuntos from '../integrations/Adjuntos.jsx';
import {economicDifference,units,asDecimal,managerDateTime as timestamp} from './managerEconomy.js';
import '../styles/pages/obras-gerencia.css';

const money=value=>formatCompactCLP(value);
const amount=value=>typeof value==='string'&&/^\d+(?:\.\d{1,2})?$/.test(value);
const date=value=>value?formatCivilDate(value):'Sin programar';
const status={PLANIFICADA:'Pendiente de inicio',EN_PROCESO:'En ejecución',SUSPENDIDA:'Obra suspendida',FINALIZADA:'Obra finalizada',CANCELADA:'Obra cancelada'};
const states={CREACION:'Obra creada',EDICION:'Obra actualizada',CAMBIO_ESTADO:'Cambio de estado',CAMBIO_TECNICO:'Cambio de responsable',FINALIZACION:'Obra finalizada'};
function Fact({label,children}){return <div><dt>{label}</dt><dd>{children}</dd></div>;}
function Money({label,value,detail,tone="blue"}){return <div className={"manager-money manager-money-"+tone}><span>{label}</span><strong>{money(value)}</strong>{detail&&<small>{detail}</small>}</div>;}

export default function GerenciaObra({id,onBack}){
  const {user}=useAuth();
  const [revision,setRevision]=useState(0);
  const [section,setSection]=useState('resumen');
  if(user.role!==G)return null;
  return <div className="manager-work manager-obras-detail">
    <div className="manager-work-toolbar"><button type="button" className="manager-obras-back" aria-label="Volver al listado" onClick={onBack}><svg width="18" height="18" viewBox="0 0 16 16" fill="currentColor" aria-hidden="true"><path fillRule="evenodd" d="M15 8a.5.5 0 0 0-.5-.5H2.707l3.647-3.646a.5.5 0 1 0-.708-.708l-4.5 4.5a.5.5 0 0 0 0 .708l4.5 4.5a.5.5 0 0 0 .708-.708L2.707 8.5H14.5A.5.5 0 0 0 15 8"/></svg>Volver al listado</button><button type="button" className="btn btn-outline-secondary manager-obras-icon" aria-label="Actualizar datos" onClick={()=>setRevision(n=>n+1)}><svg width="16" height="16" viewBox="0 0 16 16" fill="currentColor" aria-hidden="true"><path fillRule="evenodd" d="M8 3a5 5 0 1 1-4.546 2.914.5.5 0 0 0-.908-.417A6 6 0 1 0 8 2z"/><path d="M8 4.466V.534a.25.25 0 0 0-.41-.192L5.23 2.308a.25.25 0 0 0 0 .384l2.36 1.966A.25.25 0 0 0 8 4.466"/></svg>Actualizar</button></div>
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
    void api.load('members',collectionPath(path,1,{activo:'true'}),data=>setMembers(readPage(data,path)));
  },[obra]);
  const definitive=obra?.estado==='FINALIZADA'&&cost?.costos_validados&&!cost.provisional&&!cost.cortesia_sin_cobro;
  const diff=economicDifference(budget,cost?.costo_total,definitive);
  const names=new Map((members?.results||[]).filter(m=>Number.isSafeInteger(m.tecnico)&&typeof m.tecnico_nombre==='string'&&m.tecnico_nombre).map(m=>[m.tecnico,m.tecnico_nombre]));
  if(obra?.tecnico_responsable&&obra.tecnico_nombre)names.set(obra.tecnico_responsable,obra.tecnico_nombre);
  const tabs=[['resumen','Resumen'],['economia','Resumen económico'],['actividad','Actividad reciente'],['turnos','Turnos'],['documentos','Documentación']];
  return <>
    <Feedback api={api}/>
    {obra&&<>
      <header className="manager-work-heading"><div><h1>{obra.codigo}</h1><p>{obra.cliente_nombre} · {obra.categoria_nombre}</p></div><ObraStatus state={obra.estado}/></header>
      <div className="manager-work-kpis">
        <Money label="Presupuesto neto" value={budget} detail="CLP"/>
        <Money label="Costo acumulado neto" value={cost?.costo_total} tone={diff?.tone==="red"?"red":"gray"} detail={cost?(cost.costos_validados&&!cost.provisional?'Validado':'Provisional'):'CLP'}/>
        <div className="manager-money"><span>Técnicos activos</span><strong>{members===null?'—':members.count}</strong><small>{obra.tecnico_nombre||'Sin responsable'}</small></div>
        <div className="manager-money"><span>Programación</span><strong className="manager-date">{date(obra.fecha_programada)}</strong><small>{status[obra.estado]}</small></div>
      </div>
      <nav className="manager-work-tabs" aria-label="Secciones gerenciales">{tabs.map(([key,label])=><button key={key} type="button" aria-pressed={section===key} onClick={()=>setSection(key)}>{label}</button>)}</nav>
      {section==='resumen'&&<div className="manager-obras-summary"><section className="card-fyag manager-work-panel" aria-label="Resumen de la obra"><h2>Información general</h2>{obra.descripcion&&<><span className="manager-obras-caption">Descripción</span><p className="commercial-long-text">{obra.descripcion}</p></>}
        <dl className="manager-facts"><Fact label="Responsable">{obra.tecnico_nombre||'Sin asignar'}</Fact><Fact label="Presupuesto de origen">{obra.presupuesto_codigo||'—'}</Fact></dl>{cost?.cortesia_sin_cobro&&<p className="manager-note">Obra registrada sin cobro.</p>}</section>
        <section className="card-fyag manager-work-panel"><h2>Situación actual</h2><p className="manager-status">{status[obra.estado]}</p>{diff&&<div className="manager-obras-diff"><span>{diff.label}{cost?.provisional||!cost?.costos_validados?' provisional':''}</span><strong className={'manager-difference '+diff.tone}>{diff.value}</strong><small>{diff.detail}</small></div>}<dl className="manager-facts"><Fact label="Inicio efectivo">{timestamp(obra.iniciado_en)}</Fact>{obra.finalizado_en&&<Fact label="Finalización">{timestamp(obra.finalizado_en)}</Fact>}{obra.cancelado_en&&<Fact label="Cancelación">{timestamp(obra.cancelado_en)}</Fact>}</dl></section></div>}
      {section==='economia'&&<section className="card-fyag manager-work-panel" aria-label="Resumen económico"><h2>Composición de costos netos · CLP</h2>{cost?<><CostChart cost={cost}/><dl className="manager-facts manager-obras-cost-summary"><Fact label="Costo total">{money(cost.costo_total)}</Fact><Fact label="Desviación presupuestaria"><span className={'manager-difference '+(diff?.tone||'neutral')}>{diff?.deviation||'—'}</span></Fact><Fact label={diff?.label||'Diferencia presupuestaria'}><span className={'manager-difference '+(diff?.tone||'neutral')}>{diff?.value||'—'}</span></Fact></dl><p className="manager-note">{cost.costos_validados&&!cost.provisional?'Costos validados':'Costos pendientes de validación o provisionales'}</p>{cost.cortesia_sin_cobro&&<p>Obra registrada sin cobro.</p>}</>:<p>{api.loading?'Cargando costos…':'Costos no disponibles.'}</p>}</section>}
      {section==='actividad'&&<Activity id={id}/>}
      {section==='turnos'&&<ManagerTurns id={id} names={names}/>}
      {section==='documentos'&&<section className="manager-documentation"><EvidenceMetadata obraId={id} gallery/><Adjuntos type="INFORME_TECNICO" destinationId={id} canUpload={false} readOnly/></section>}
    </>}
  </>;
}

function CostChart({cost}){
 const rows=[['Materiales',cost.materiales_total,'#3478DC'],['Mano de obra',cost.mano_obra_total,'#427D8D'],['Otros gastos',cost.otros_total,'#8492A6']];
 const max=rows.reduce((a,[,v])=>units(v)>a?units(v):a,0n);
 if(max===0n)return <p className="commercial-empty">No hay costos registrados.</p>;
 const magnitude=10n**BigInt(max.toString().length-1),step=(max+4n*magnitude-1n)/(4n*magnitude)*magnitude||1n,top=step*4n;
 return <div className="manager-obras-chart"><div className="manager-obras-plot"><svg viewBox="0 0 480 174" role="img" aria-label="Comparación de materiales, mano de obra y otros gastos en CLP, desde cero">{Array.from({length:5},(_,i)=><line key={i} x1={122+i*86} x2={122+i*86} y1="6" y2="145" stroke="#dce5ee" strokeDasharray={i?'3 3':undefined}/>)}{rows.map(([label,val,color],i)=><g key={label}><text x="114" y={28+i*48} textAnchor="end" fontSize="12" fill="#16324D">{label}</text><rect x="122" y={10+i*48} height="27" width={Number(units(val))/Number(top)*344} fill={color} rx="3"/></g>)}<text x="122" y="164" fontSize="11" fill="#526578">$0</text><text x="466" y="164" textAnchor="end" fontSize="11" fill="#526578">{money(asDecimal(top))}</text></svg></div><dl className="manager-obras-chart-values">{rows.map(([label,val,color])=><div key={label}><dt><span style={{background:color}}/>{label}</dt><dd>{money(val)}</dd></div>)}</dl></div>;
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
    <ol className="manager-events">{(expanded?events:events.slice(0,5)).map(event=><li key={event.id} data-state={event.estado_nuevo||"CREACION"}><strong>{event.tipo==="CAMBIO_ESTADO"&&event.estado_nuevo==="EN_PROCESO"?(event.estado_anterior==="SUSPENDIDA"?"Reanudación de obra":event.estado_anterior==="PLANIFICADA"?"Inicio de ejecución":"Cambio de estado"):states[event.tipo]||String(event.tipo).replaceAll('_',' ').toLocaleLowerCase('es-CL')}</strong><small>{timestamp(event.creado_en)}</small>{event.estado_nuevo&&<span><ObraStatus state={event.estado_nuevo}/></span>}{event.motivo&&<p>{event.motivo}</p>}</li>)}</ol>
    {events.length>5&&<button type="button" className="btn btn-outline-secondary btn-sm" onClick={()=>setExpanded(v=>!v)}>{expanded?'Ver menos':'Ver más actividad'}</button>}
    {data&&(data.previous||data.next)&&<Pager label="Paginación de actividad" data={data} page={page} setPage={setPage} disabled={api.loading}/>}
  </section>;
}

function ManagerTurns({id,names}){
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
    {data?.results.length>0&&<div className="table-responsive manager-obras-turn-table" tabIndex={0} role="region" aria-label="Detalle de turnos"><table className="table commercial-table"><thead><tr>{['Técnico','Inicio','Término','Duración','Estado','Trabajo realizado'].map(x=><th key={x} scope="col">{x}</th>)}</tr></thead><tbody>{data.results.map(turn=>{const seconds=turn.duracion_ajustada_segundos??turn.duracion_segundos;const duration=turn.terminado_en&&seconds!==null&&seconds!==undefined&&seconds!==''&&Number.isFinite(Number(seconds))&&Number(seconds)>=0?(Number(seconds)/3600).toLocaleString('es-CL',{maximumFractionDigits:2})+' h':'—';return <tr key={turn.turno_id}><td>{names.get(turn.tecnico)||(turn.tecnico?'Técnico #'+turn.tecnico:'—')}</td><td>{timestamp(turn.iniciado_en)}</td><td>{turn.terminado_en?timestamp(turn.terminado_en):'En curso'}</td><td>{duration}</td><td><span className={'chip '+({VALIDADO:'green',ABIERTO:'blue',PENDIENTE_REVISION:'amber',OBSERVADO:'red'}[turn.estado_revision]||'gray')}>{states[turn.estado_revision]||'Estado no disponible'}</span></td><td><p>{turn.descripcion_trabajo||'—'}</p>{!!turn.fotos?.length&&<div className="manager-photo-actions">{turn.fotos.map((item,i)=><button key={item.id} type="button" className="btn btn-outline-secondary btn-sm" disabled={download!==null} onClick={()=>void photo(turn,item)}>Descargar foto {i+1}</button>)}</div>}</td></tr>;})}</tbody></table></div>}
    {data&&(data.next||data.previous)&&<Pager label="Paginación de turnos" data={data} page={page} setPage={setPage} disabled={api.loading}/>}
  </section>;
}
