import React, { useEffect, useRef, useState } from 'react';
import { useAuth } from '../auth/AuthContext.jsx';
import { ApiError } from '../auth/client.js';
import { readPage, safePage, useApi } from './useApi.js';

const ATTRIBUTES=new Set(['ubicacion_general','vista','componente','condicion','tipo_evidencia','fase_trabajo','iluminacion','orientacion','equipo_tipo','zona_tecnica','requiere_revision','estado_visual']);
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
function EvidenceScreen({obraId}) {
  const api=useApi(),pending=useRef(false);
  const [page,setPage]=useState(1),[data,setData]=useState(null),[selected,setSelected]=useState(null),[form,setForm]=useState(null),[notice,setNotice]=useState('');
  const path=`/api/documentos-metadata/?obra=${obraId}&page=${page}`;
  const fields=(value)=>({descripcion:value.descripcion,etiquetas:value.etiquetas.join(', '),atributos:JSON.stringify(value.atributos,null,2)});
  function list(value) {
    readPage(value,'/api/documentos-metadata/',25,{obra:obraId});
    if(value.proyeccion!=='EVENTUAL'||value.fuente_autoritativa!=='POSTGRESQL')throw new ApiError(502,'Listado de metadatos inválido.');
    return {...value,results:value.results.map((item)=>validItem(item,obraId))};
  }
  const reload=()=>{setData(null);return api.load('metadata',path,(value)=>setData(list(value)));};
  useEffect(()=>{setSelected(null);setForm(null);api.cancelRead('selected-metadata');void reload();},[page]);
  async function select(item) {
    setSelected(null);setForm(null);setNotice('');
    await api.reconcile(async()=>api.load('selected-metadata',`/api/documentos-metadata/evidencias/${item.evidencia_id}/`,(value)=>{
      const next=validItem(value,obraId);if(next.evidencia_id!==item.evidencia_id)throw new ApiError(502,'Evidencia inesperada.');setSelected(next);setForm(fields(next));
    }));
  }
  async function save(event) {
    event.preventDefault();if(!selected||!form||pending.current||api.busy||api.locked)return;
    let attrs;try{attrs=JSON.parse(form.atributos);}catch{setNotice('Los atributos deben ser un objeto JSON válido.');return;}
    if(!attrs||typeof attrs!=='object'||Array.isArray(attrs)||Object.keys(attrs).some((key)=>!ATTRIBUTES.has(key))){setNotice('Usa solo las claves técnicas permitidas.');return;}
    const item=selected;pending.current=true;setNotice('');api.cancelRead('selected-metadata');
    try{
      await api.write(`/api/documentos-metadata/evidencias/${item.evidencia_id}/`,'PATCH',{revision:item.revision,descripcion:form.descripcion,etiquetas:form.etiquetas.split(',').map((tag)=>tag.trim()).filter(Boolean),atributos:attrs},async(value)=>{
        const saved=validItem(value,obraId);if(saved.evidencia_id!==item.evidencia_id||saved.revision!==item.revision+1)throw new ApiError(502,'Revisión de evidencia inesperada.');
        await api.requiredLoad('metadata',path,(value)=>setData(list(value)));
        setSelected(saved);setForm(fields(saved));setNotice('Anotaciones actualizadas y listado reconsultado.');
      });
    }finally{pending.current=false;}
  }
  return <section className="card-fyag p-3 my-3" aria-label="Metadatos de evidencias fotográficas"><div className="d-flex justify-content-between flex-wrap gap-2"><h3>Metadatos técnicos de evidencias</h3><button className="btn btn-outline-secondary btn-sm" type="button" disabled={api.loading||api.busy} onClick={()=>{setSelected(null);setForm(null);api.cancelRead('selected-metadata');void reload();}}>Actualizar metadatos</button></div>
    {api.error&&<p className="alert alert-warning" role="alert">{api.error.status===503?'MongoDB no disponible; el cambio no se considera confirmado.':api.error.status===409?'Revisión obsoleta o metadata pendiente: vuelve a consultar; no se sobrescribieron datos.':api.error.status===403?'No tienes permiso para metadatos.':api.error.message}</p>}
    {api.locked&&<p role="alert">Escrituras bloqueadas hasta consultar nuevamente la evidencia y su revisión.</p>}{notice&&<p className="alert alert-info" role="status">{notice}</p>}
    {data&&!data.count&&<p>No hay metadatos de evidencias para esta Obra.</p>}
    <ul className="list-group">{data?.results.map((item)=><li key={item.evidencia_id} className="list-group-item d-flex justify-content-between gap-2"><span>Evidencia #{item.evidencia_id} · Turno #{item.turno_id} · {item.tipo_mime} · revisión {item.revision}</span><button type="button" className="btn btn-outline-secondary btn-sm" disabled={api.busy} onClick={()=>void select(item)}>Consultar / editar anotaciones</button></li>)}</ul>
    {selected&&form&&<form className="commercial-form mt-3" onSubmit={save} aria-label="Anotaciones de evidencia"><h4>Evidencia #{selected.evidencia_id} · revisión {selected.revision}</h4>{[['descripcion','Descripción técnica'],['etiquetas','Etiquetas separadas por coma'],['atributos','Atributos técnicos JSON']].map(([key,label])=><label key={key} className="form-label">{label}<textarea className="form-control" maxLength={key==='descripcion'?1000:undefined} value={form[key]} disabled={api.busy||api.locked} onChange={(e)=>setForm({...form,[key]:e.target.value})}/></label>)}<div className="commercial-form-actions mt-2"><button className="btn btn-fyag-primary" disabled={api.busy||api.locked}>Guardar anotaciones</button><button className="btn btn-outline-secondary" type="button" disabled={api.busy} onClick={()=>void select(selected)}>Reconsultar revisión</button></div></form>}
    {data&&<nav className="commercial-pager" aria-label="Paginación de metadatos"><button type="button" className="btn btn-outline-secondary btn-sm" disabled={api.loading||api.busy||!data.previous} onClick={()=>setPage(safePage(data.previous,'/api/documentos-metadata/'))}>Anterior</button><span>Página {page} · {data.count} evidencias</span><button type="button" className="btn btn-outline-secondary btn-sm" disabled={api.loading||api.busy||!data.next} onClick={()=>setPage(safePage(data.next,'/api/documentos-metadata/'))}>Siguiente</button></nav>}
  </section>;
}
