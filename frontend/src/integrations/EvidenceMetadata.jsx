import React, { useEffect, useRef, useState } from 'react';
import { useAuth } from '../auth/AuthContext.jsx';
import { ApiError } from '../auth/client.js';
import { readPage, safePage, useApi } from './useApi.js';

function validItem(item,obraId) {
  if(!item||!Number.isSafeInteger(item.evidencia_id)||item.evidencia_id<1||item.obra_id!==Number(obraId)||!Number.isSafeInteger(item.revision)||item.revision<0
      ||typeof item.descripcion!=='string'||!Array.isArray(item.etiquetas)||!item.etiquetas.every((tag)=>typeof tag==='string')
      ||!item.atributos||typeof item.atributos!=='object'||Array.isArray(item.atributos))throw new ApiError(502,'Metadatos de evidencia inválidos.');
  return item;
}
export default function EvidenceMetadata(props) {
  const {user}=useAuth();
  if(!['GERENCIA','SUPERVISOR_OBRAS'].includes(user.role))return null;
  return <EvidenceScreen key={`${user.id}:${user.role}:${props.obraId}`} {...props}/>;
}
function EvidenceScreen({obraId,gallery=false,supervisorPresentation=false}) {
  const {user}=useAuth(),canEdit=user.role==='SUPERVISOR_OBRAS';
  const isGallery=gallery&&!canEdit;
  const api=useApi(),pending=useRef(false);
  const [page,setPage]=useState(1),[data,setData]=useState(null),[selected,setSelected]=useState(null),[form,setForm]=useState(null),[notice,setNotice]=useState('');
  const path=`/api/documentos-metadata/?obra=${obraId}&page=${page}`;
  const fields=(value)=>({descripcion:value.descripcion});
  function list(value) {
    readPage(value,'/api/documentos-metadata/',25,{obra:obraId});
    if(value.proyeccion!=='EVENTUAL'||value.fuente_autoritativa!=='POSTGRESQL')throw new ApiError(502,'Listado de metadatos inválido.');
    return {...value,results:value.results.map((item)=>validItem(item,obraId))};
  }
  const reload=()=>{setData(null);return api.load('metadata',path,(value)=>setData(list(value)));};
  useEffect(()=>{setSelected(null);setForm(null);api.cancelRead('selected-metadata');void reload();},[page]);
  async function select(item) {
    if(!canEdit)return;
    setSelected(null);setForm(null);setNotice('');
    await api.reconcile(async()=>api.load('selected-metadata',`/api/documentos-metadata/evidencias/${item.evidencia_id}/`,(value)=>{
      const next=validItem(value,obraId);if(next.evidencia_id!==item.evidencia_id)throw new ApiError(502,'Evidencia inesperada.');setSelected(next);setForm(fields(next));
    }));
  }
  async function save(event) {
    event.preventDefault();if(!canEdit||!selected||!form||pending.current||api.busy||api.locked)return;
    const item=selected;pending.current=true;setNotice('');api.cancelRead('selected-metadata');
    try{
      await api.write(`/api/documentos-metadata/evidencias/${item.evidencia_id}/`,'PATCH',{revision:item.revision,descripcion:form.descripcion,etiquetas:item.etiquetas,atributos:item.atributos},async(value)=>{
        const saved=validItem(value,obraId);if(saved.evidencia_id!==item.evidencia_id||saved.revision!==item.revision+1)throw new ApiError(502,'Revisión de evidencia inesperada.');
        await api.requiredLoad('metadata',path,(value)=>setData(list(value)));
        setSelected(saved);setForm(fields(saved));setNotice('Anotaciones actualizadas.');
      });
    }finally{pending.current=false;}
  }
  return <section className="card-fyag p-3 my-3" aria-label="Metadatos de evidencias fotográficas"><div className="d-flex justify-content-between flex-wrap gap-2"><h3>Evidencias fotográficas</h3><button className="btn btn-outline-secondary btn-sm" type="button" disabled={api.loading||api.busy} onClick={()=>{setSelected(null);setForm(null);api.cancelRead('selected-metadata');void reload();}}>Actualizar</button></div>
    {api.error&&<p className="alert alert-warning" role="alert">{api.error.status===503?'No se pudo consultar o confirmar la información. Intenta actualizar.':api.error.status===409?'La información cambió o no está confirmada. Actualiza antes de continuar.':api.error.status===403?'No tienes permiso para metadatos.':api.error.message}</p>}
    {api.locked&&<p role="alert">Escrituras bloqueadas hasta consultar nuevamente la evidencia y su revisión.</p>}{notice&&<p className="alert alert-info" role="status">{notice}</p>}
    {data&&!data.count&&(supervisorPresentation?<div className="so-empty" role="status"><strong>Sin evidencias fotográficas</strong><p>Las fotografías registradas en los turnos aparecerán aquí.</p></div>:<p className={isGallery?"manager-evidence-empty":undefined}>No hay evidencias fotográficas registradas para esta obra.</p>)}
    {isGallery?<div className="manager-evidence-grid">{data?.results.map(item=><PrivatePhoto key={item.evidencia_id} item={item} obraId={obraId}/>)}</div>:<ul className="list-group">{data?.results.map((item)=><li key={item.evidencia_id} className="list-group-item d-flex justify-content-between gap-2"><div><strong>Evidencia #{item.evidencia_id}</strong><div className="commercial-help">Fotografía · Turno #{item.turno_id}</div>{item.descripcion&&<p className="mb-0 text-break">{item.descripcion}</p>}</div>{canEdit&&<button type="button" className="btn btn-outline-secondary btn-sm" disabled={api.busy} onClick={()=>void select(item)}>Editar descripción</button>}</li>)}</ul>}
    {canEdit&&selected&&form&&<form className="commercial-form mt-3" onSubmit={save} aria-label="Anotaciones de evidencia"><h4>Descripción de evidencia #{selected.evidencia_id}</h4><label className="form-label">Descripción<textarea className="form-control" rows={3} maxLength={1000} value={form.descripcion} disabled={api.busy||api.locked} onChange={(e)=>setForm({descripcion:e.target.value})}/></label><div className="commercial-form-actions mt-2"><button className="btn btn-fyag-primary" disabled={api.busy||api.locked}>Guardar anotaciones</button><button className="btn btn-outline-secondary" type="button" disabled={api.busy} onClick={()=>void select(selected)}>Reconsultar revisión</button><button type="button" className="btn btn-outline-secondary" disabled={api.busy} onClick={()=>{api.cancelRead('selected-metadata');setSelected(null);setForm(null);}}>Cancelar</button></div></form>}
    {data&&((!isGallery&&!supervisorPresentation)||data.next||data.previous)&&<nav className="commercial-pager" aria-label="Paginación de metadatos"><button type="button" className="btn btn-outline-secondary btn-sm" disabled={api.loading||api.busy||!data.previous} onClick={()=>setPage(safePage(data.previous,'/api/documentos-metadata/'))}>Anterior</button><span>Página {page} · {data.count} evidencias</span><button type="button" className="btn btn-outline-secondary btn-sm" disabled={api.loading||api.busy||!data.next} onClick={()=>setPage(safePage(data.next,'/api/documentos-metadata/'))}>Siguiente</button></nav>}
  </section>;
}

function PrivatePhoto({item,obraId}){
 const {request}=useAuth(),[attempt,setAttempt]=useState(0),[url,setUrl]=useState(null),[error,setError]=useState(false);
 useEffect(()=>{if(!attempt)return;let current=true,objectUrl;const controller=new AbortController();setUrl(null);setError(false);
 (async()=>{try{
  if(!Number.isSafeInteger(item.turno_id)||item.turno_id<1||!Number.isSafeInteger(item.evidencia_id)||item.evidencia_id<1)throw Error();
  const blob=await request('/api/obras/'+obraId+'/turnos/'+item.turno_id+'/fotos/'+item.evidencia_id+'/',{responseType:'blob',signal:controller.signal});
  if(!['image/jpeg','image/png','image/webp'].includes(blob.type)||blob.size>5*1024*1024)throw Error();
  if(current){objectUrl=URL.createObjectURL(blob);setUrl(objectUrl);}
 }catch{if(current)setError(true);}})();
 return ()=>{current=false;controller.abort();if(objectUrl)URL.revokeObjectURL(objectUrl);};
 },[attempt,item.evidencia_id,item.turno_id,obraId,request]);
 return <article className="manager-evidence-card">{url&&!error?<img src={url} alt={item.descripcion||'Evidencia fotográfica'} onError={()=>setError(true)}/>:<div className="manager-evidence-placeholder">{error&&<small role="status">Fotografía no disponible</small>}<button type="button" className="btn btn-outline-secondary btn-sm" disabled={attempt>0&&!error} onClick={()=>setAttempt(n=>n+1)}>{error?'Reintentar':attempt?'Cargando…':'Ver fotografía'}</button></div>}<strong>Evidencia #{item.evidencia_id}</strong>{item.descripcion&&<p>{item.descripcion}</p>}</article>;
}
