import React,{useEffect,useRef,useState} from 'react';
import {useAuth} from '../auth/AuthContext.jsx';
import {useApp} from '../context/AppContext.jsx';
import {obraPath,readPage} from '../obras/api.js';
import {Feedback,Pager,useOperational} from '../obras/ui.jsx';
import {TurnoEditor} from '../obras/Turnos.jsx';
import {civilTime,duration,elapsed} from '../obras/tecnicoDomain.js';
import TecIcon from '../obras/TecIcon.jsx';
import '../styles/pages/tecnico.css';
const base='/api/obras/mis-turnos/';
const states={ABIERTO:'En curso',PENDIENTE_REVISION:'Pendiente de revisión',OBSERVADO:'Observado',VALIDADO:'Validado'};
const getPath=(page,state)=>base+'?'+new URLSearchParams({page:String(page),...(state?{estado:state}:{})});
function validate(data,user){
 const p=readPage(data,base);
 function row(r,active){
  if(!r||r.tecnico!==user.id||!Number.isSafeInteger(r.turno_id)||r.turno_id<=0||!Number.isSafeInteger(r.obra)||r.obra<=0||typeof r.obra_codigo!=='string'||typeof r.categoria_nombre!=='string'||!Object.hasOwn(states,r.estado_revision)||!Number.isFinite(Date.parse(r.iniciado_en))||!Array.isArray(r.fotos)||(active?r.estado_revision!=='ABIERTO'||r.terminado_en!==null:r.estado_revision==='ABIERTO'||!Number.isFinite(Date.parse(r.terminado_en))))throw Error('Turno no válido para esta sesión.');
 }
 if(!Number.isFinite(Date.parse(p.hora_servidor)))throw Error('Hora del servidor no disponible.');
 if(p.activo!==null)row(p.activo,true);
 p.results.forEach(r=>row(r,false));
 return p;
}
function Clock({start,server,anchor}){
 const compute=()=>elapsed((Date.parse(server)-Date.parse(start)+Math.max(0,performance.now()-anchor))/1000);
 const [value,setValue]=useState(compute);
 useEffect(()=>{setValue(compute());const timer=setInterval(()=>setValue(compute()),1000);return()=>clearInterval(timer);},[start,server,anchor]);
 return <div className="tec-clock"><small>Tiempo transcurrido estimado</small><strong>{value}</strong><small>Inicio: {civilTime(start)}</small></div>;
}
function Status({row}){return <span className={'tec-status '+(row.estado_revision==='VALIDADO'||row.estado_revision==='ABIERTO'?'good':row.estado_revision==='OBSERVADO'?'warn':'neutral')}><TecIcon name={row.estado_revision==='VALIDADO'?'check':row.estado_revision==='OBSERVADO'?'warning':'clock'}/>{states[row.estado_revision]}</span>;}
export default function MisTurnos(){
 const {user,request}=useAuth(),{go,setNavigationBlocked}=useApp(),api=useOperational();
 const [page,setPage]=useState(1),[state,setState]=useState(''),[data,setData]=useState(null),[editor,setEditor]=useState(null),[download,setDownload]=useState(null),[downloadError,setDownloadError]=useState('');
 const blobUrls=useRef(new Set()),alive=useRef(true);
 const path=getPath(page,state),blocked=api.busy||api.loading||api.locked||!!api.error;
 const commit=v=>setData({...validate(v,user),anchor:performance.now()});
 const reload=()=>api.load('mine',path,commit);
 useEffect(()=>{if(user.role!=='TECNICO')return;setData(null);void reload();},[path,user.id,user.role]);
 useEffect(()=>{setNavigationBlocked(api.busy||api.locked);return()=>setNavigationBlocked(false);},[api.busy,api.locked,setNavigationBlocked]);
 useEffect(()=>{alive.current=true;return()=>{alive.current=false;for(const url of blobUrls.current)URL.revokeObjectURL(url);blobUrls.current.clear();};},[]);
 async function refresh(){setData(null);await api.reconcile(async()=>{const ok=await reload();if(ok)setEditor(null);return ok;});}
 async function saved(){await api.requiredLoad('mine',getPath(1,state),commit);setPage(1);setEditor(null);}
 async function evidence(row,foto){
  if(download!==null||!Number.isSafeInteger(foto.id)||foto.id<=0)return;
  setDownload(foto.id);setDownloadError('');
  try{
   const blob=await request(obraPath(row.obra)+'turnos/'+row.turno_id+'/fotos/'+foto.id+'/',{responseType:'blob'});
   if(!alive.current)return;
   const ext={'image/jpeg':'jpg','image/png':'png','image/webp':'webp'}[blob.type];
   if(!ext)throw Error('Tipo de evidencia inesperado.');
   const url=URL.createObjectURL(blob);blobUrls.current.add(url);
   const a=document.createElement('a');a.href=url;a.download='evidencia-'+foto.id+'.'+ext;a.rel='noopener';document.body.appendChild(a);a.click();a.remove();
   setTimeout(()=>{URL.revokeObjectURL(url);blobUrls.current.delete(url);},1000);
  }catch(e){if(alive.current)setDownloadError(e.message||'No se pudo descargar la evidencia.');}finally{if(alive.current)setDownload(null);}
 }
 if(user.role!=='TECNICO')return null;
 const active=data?.activo;
 if(editor)return <section className="commercial-page tecnico-page"><div className="tec-row"><button type="button" className="btn btn-outline-secondary tec-button" disabled={api.busy||api.locked} onClick={()=>setEditor(null)}><TecIcon name="back"/>Volver a mis turnos</button>{api.locked&&<button type="button" className="btn btn-outline-secondary" disabled={api.busy||api.loading} onClick={()=>void refresh()}>Actualizar datos</button>}</div><header className="tec-heading"><div><h1>{editor.mode==='finalizar'?'Finalizar turno':'Subsanar turno'}</h1><p>{editor.row.obra_codigo} · {editor.row.categoria_nombre}</p></div></header><Feedback api={api}/>{editor.row.observacion&&<section className="card-fyag tec-panel"><h2>Observación del supervisor</h2><p>{editor.row.observacion}</p></section>}<TurnoEditor obraId={editor.row.obra} item={editor.row} mode={editor.mode} api={api} onCancel={()=>{if(!api.locked)setEditor(null);}} onSaved={saved}/></section>;
 return <section className="commercial-page tecnico-page">
  <header className="tec-heading"><div><h1>Mis turnos</h1><p>Consulta tu jornada, horas registradas y observaciones.</p></div><button type="button" className="btn btn-outline-secondary tec-button" disabled={api.busy||api.loading} onClick={()=>void refresh()}><TecIcon name="refresh"/>Actualizar</button></header>
  <Feedback api={api}/>{downloadError&&<p role="alert" className="alert alert-warning">{downloadError}</p>}
  {data&&!api.error&&<section className="card-fyag tec-panel tec-active"><div className="tec-row"><h2>Turno actual</h2>{active&&<Status row={active}/>}</div>
   {active?<><p>{active.obra_codigo} · {active.categoria_nombre}</p><Clock start={active.iniciado_en} server={data.hora_servidor} anchor={data.anchor}/><button type="button" className="btn btn-fyag-primary tec-button tec-full" disabled={blocked} onClick={()=>setEditor({row:active,mode:'finalizar'})}><TecIcon name="stop"/>Finalizar turno</button></>:<div className="tec-empty"><TecIcon name="clock"/><strong>No tienes un turno en curso</strong><p>Selecciona una obra en ejecución para iniciar tu jornada.</p><button type="button" className="btn btn-fyag-primary" disabled={blocked} onClick={()=>go('obras')}>Ir a mis obras</button></div>}
  </section>}
  <section className="card-fyag tec-panel"><h2>Historial de turnos</h2><div className="tec-tabs" role="group" aria-label="Estado de revisión">{[['','Todos'],['OBSERVADO','Observados'],['PENDIENTE_REVISION','Por revisar'],['VALIDADO','Validados']].map(([k,l])=><button type="button" key={k} aria-pressed={state===k} disabled={blocked} onClick={()=>{setState(k);setPage(1);}}>{l}</button>)}</div>
   {data&&!api.error&&!data.results.length&&<div className="tec-empty" role="status"><TecIcon name="inbox"/><strong>No hay turnos {state?'para este estado':'registrados'}</strong><p>Los turnos cerrados aparecerán aquí.</p></div>}
   <ol className="tec-shifts">{data?.results.map(r=><li key={r.turno_id} className="tec-shift"><div className="tec-row"><div><strong>{r.obra_codigo}</strong><small className="tec-muted">{r.categoria_nombre}</small></div><Status row={r}/></div><div className="tec-row"><span>{civilTime(r.iniciado_en)} – {civilTime(r.terminado_en)}</span><strong>{duration(r)}</strong></div>{r.modo_cierre==='SUPERVISOR'&&<small>Cierre administrativo</small>}{r.descripcion_trabajo&&<p>{r.descripcion_trabajo}</p>}{r.observacion&&<p className="tec-observation"><strong>Observación:</strong> {r.observacion}</p>}{r.fotos.length>0&&<div className="tec-evidence">{r.fotos.map((f,i)=><button key={f.id} type="button" className="btn btn-outline-secondary btn-sm" disabled={download!==null} onClick={()=>void evidence(r,f)}>Descargar evidencia {i+1}</button>)}</div>}{r.estado_revision==='OBSERVADO'&&<button className="btn btn-outline-secondary tec-button" type="button" disabled={blocked} onClick={()=>setEditor({row:r,mode:'subsanar'})}>Subsanar turno</button>}</li>)}</ol>
   {data&&(data.next||data.previous)&&<Pager data={data} page={page} setPage={setPage} disabled={blocked} label="Paginación de mis turnos"/>}
  </section>
 </section>;
}
