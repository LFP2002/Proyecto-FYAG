import React, { useEffect, useRef, useState } from 'react';
import { useAuth } from '../auth/AuthContext.jsx';
import { ApiError } from '../auth/client.js';
import { positiveInteger, readPage, safePage, strictObject, useApi } from './useApi.js';

const MIME = new Set(['application/pdf','image/jpeg','image/png']);
function validateFile(file) {
  if (!file || !MIME.has(file.type)) return 'Selecciona un archivo PDF, JPEG o PNG.';
  return file.size < 1 || file.size > (file.type === 'application/pdf' ? 8 : 5) * 1024 * 1024 ? 'El archivo está vacío o supera el límite permitido.' : '';
}
function attachment(row, type, destinationId) {
  strictObject(row,['id','tipo','destino','nombre_visible','mime','tamano_bytes','estado','registrado_por','registrado_en']);
  const target = type === 'RESPALDO_FACTURA' ? 'documento_cobro' : 'obra';
  strictObject(row.destino,[target]);
  if (!positiveInteger(row.id) || row.tipo !== type || row.destino[target] !== Number(destinationId) || typeof row.nombre_visible !== 'string'
      || !MIME.has(row.mime) || !positiveInteger(row.tamano_bytes) || row.estado !== 'DISPONIBLE') throw new ApiError(502,'Respuesta documental inválida.');
  return row;
}
function annotation(value, row, type, destinationId) {
  strictObject(value,['adjunto_id','tipo','destino_id','mime','tamano_bytes','registrado_en','sincronizado_en','descripcion','etiquetas','atributos','revision']);
  if (value.adjunto_id !== row.id || value.tipo !== type || value.destino_id !== Number(destinationId) || !Number.isSafeInteger(value.revision) || value.revision < 0
      || typeof value.descripcion !== 'string' || !Array.isArray(value.etiquetas) || !value.etiquetas.every((tag)=>typeof tag==='string')
      || !value.atributos || typeof value.atributos !== 'object' || Array.isArray(value.atributos)) throw new ApiError(502,'Anotaciones documentales inválidas.');
  return value;
}
const editForm = (value) => ({descripcion:value.descripcion,etiquetas:value.etiquetas.join(', '),atributos:JSON.stringify(value.atributos,null,2)});
function download(blob,row) {
  if (blob.type !== row.mime || !MIME.has(blob.type)) throw new ApiError(502,'El tipo descargado no coincide con el registro.');
  const url=URL.createObjectURL(blob), link=document.createElement('a');
  link.href=url;link.download=row.nombre_visible.replace(/[\\/\x00-\x1f]/g,'_');link.rel='noopener';document.body.appendChild(link);link.click();link.remove();
  setTimeout(()=>URL.revokeObjectURL(url),1000);
}
export default function Adjuntos(props) {
  const { user }=useAuth();
  const allowed=props.type==='RESPALDO_FACTURA'?['ADMINISTRATIVO_FINANZAS','GERENCIA']:props.type==='INFORME_TECNICO'?['GERENCIA','SUPERVISOR_OBRAS','TECNICO']:[];
  if (!allowed.includes(user.role) || !positiveInteger(Number(props.destinationId))) return null;
  return <AttachmentScreen key={`${user.id}:${user.role}:${props.type}:${props.destinationId}`} {...props}/>;
}
function AttachmentScreen({type,destinationId,canUpload,readOnly=false}) {
  const {user}=useAuth(),api=useApi();
  const [rows,setRows]=useState(null),[page,setPage]=useState(1),[selected,setSelected]=useState(null),[file,setFile]=useState(null);
  const [message,setMessage]=useState(''),[intent,setIntent]=useState(null),[detail,setDetail]=useState(null),[metadata,setMetadata]=useState(null),[form,setForm]=useState(null);
  const intention=useRef(null),fileRef=useRef(null),pending=useRef(false);
  const canEdit=!readOnly&&(type==='RESPALDO_FACTURA'?user.role==='ADMINISTRATIVO_FINANZAS':['SUPERVISOR_OBRAS','TECNICO'].includes(user.role));
  const path=type==='RESPALDO_FACTURA'?`/api/adjuntos/documentos-cobro/${destinationId}/`:`/api/adjuntos/obras/${destinationId}/`;
  const project=(value)=>attachment(value,type,destinationId);
  const reload=()=>{setRows(null);return api.load('attachments',`${path}?page=${page}`,(data)=>setRows({...readPage(data,path),results:data.results.map(project)}));};
  function clearSelection(){api.cancelRead('attachment-selection');api.cancelRead('attachment-download');setSelected(null);setDetail(null);setMetadata(null);setForm(null);setMessage('');}
  useEffect(()=>{clearSelection();void reload();},[page]);
  async function upload(event,retry=false) {
    event?.preventDefault();if(!canEdit||!canUpload||pending.current||api.busy||(!retry&&api.locked))return;
    const issue=validateFile(intention.current?.file||file);if(issue){setMessage(issue);return;}
    pending.current=true;setMessage('');
    try{
      if(retry&&api.locked&&!await api.reconcile(reload))return;
      const current=intention.current||{key:globalThis.crypto?.randomUUID?.(),file};
      if(!current.key){setMessage('No se pudo generar una clave segura de idempotencia.');return;}
      intention.current=current;setIntent(current);
      const body=new FormData();body.append('archivo',current.file,current.file.name);
      await api.write(path,'POST',body,async(value)=>{
        project(value);
        if(!await reload())throw new ApiError(502,'La carga pudo completarse, pero no se confirmó el listado. Conserva la intención y el archivo.');
        intention.current=null;setIntent(null);setFile(null);if(fileRef.current)fileRef.current.value='';setMessage('Archivo aceptado y listado confirmado.');
      },{headers:{'Idempotency-Key':current.key}});
    }finally{pending.current=false;}
  }
  async function inspect(row){clearSelection();setSelected(row);await api.load('attachment-selection',`/api/adjuntos/${row.id}/`,(value)=>{const next=project(value);if(next.id!==row.id)throw new ApiError(502,'Adjunto inesperado.');setDetail(next);});}
  async function loadMetadata(row) {
    clearSelection();setSelected(row);
    const read=()=>api.load('attachment-selection',`/api/adjuntos/${row.id}/anotaciones/`,(value)=>{const next=annotation(value,row,type,destinationId);setMetadata(next);setForm(editForm(next));});
    // Releer notas reconcilia solamente su CAS, nunca una carga pendiente.
    return intention.current ? read() : api.reconcile(read);
  }
  async function saveMetadata(event) {
    event.preventDefault();if(!canEdit||!metadata||!selected||api.busy||api.locked||pending.current||intention.current)return;
    let attributes;try{attributes=JSON.parse(form.atributos);}catch{setMessage('Atributos debe ser un objeto JSON válido.');return;}
    if(!attributes||typeof attributes!=='object'||Array.isArray(attributes)){setMessage('Atributos debe ser un objeto JSON.');return;}
    const row=selected,revision=metadata.revision;pending.current=true;setMessage('');api.cancelRead('attachment-selection');
    try{
      await api.write(`/api/adjuntos/${row.id}/anotaciones/`,'PATCH',{revision,descripcion:form.descripcion,etiquetas:form.etiquetas.split(',').map((x)=>x.trim()).filter(Boolean),atributos:attributes},async(value)=>{
        const next=annotation(value,row,type,destinationId);if(next.revision!==revision+1)throw new ApiError(502,'Revisión documental inesperada.');setMetadata(next);setForm(editForm(next));setMessage('Anotaciones actualizadas.');
      });
    }finally{pending.current=false;}
  }
  const blocked=api.busy||api.locked||!!intent;
  return <section className="card-fyag p-3 my-3" aria-label={type==='RESPALDO_FACTURA'?'Adjuntos de factura externa':'Informes técnicos adjuntos'}>
    <div className="d-flex flex-wrap justify-content-between align-items-center gap-2"><h3>{type==='RESPALDO_FACTURA'?'Respaldos de factura externa':'Informes técnicos'}</h3><button type="button" className="btn btn-outline-secondary btn-sm" disabled={api.loading||api.busy} onClick={()=>{setMessage('');void reload();}}>Actualizar adjuntos</button></div>
    {api.error&&<p className="alert alert-warning" role="alert">{({403:'No tienes permiso para esta operación.',404:'Adjunto o destino no disponible.',409:'Conflicto documental o revisión CAS obsoleta/pendiente: reconsulta antes de editar, sin sobrescribir.',413:'El archivo supera el máximo permitido.',422:'Archivo rechazado por validación de contenido.',503:'Scanner, almacenamiento o MongoDB no disponible. El resultado no se considera confirmado.'})[api.error.status]||api.error.message}</p>}
    {api.locked&&<p role="alert">Escrituras bloqueadas hasta reconsultar la revisión; una carga incierta conserva la misma clave y archivo.</p>}
    {message&&<p role="status" className="alert alert-info">{message}</p>}
    {canUpload&&canEdit&&<form className="commercial-form mb-3" onSubmit={upload}><label className="form-label" htmlFor={`adjunto-${type}-${destinationId}`}>Subir PDF, JPEG o PNG</label><input ref={fileRef} id={`adjunto-${type}-${destinationId}`} className="form-control" type="file" accept="application/pdf,image/jpeg,image/png" disabled={blocked} onChange={(e)=>{setFile(e.target.files?.[0]||null);setMessage('');}}/>
      <button className="btn btn-fyag-primary mt-2" disabled={!file||blocked}>Subir archivo privado</button><p>La API valida contenido, dimensiones y antimalware; no se confirma éxito sin relectura.</p>
    </form>}
    {intent&&<><p>Se conserva la intención de carga sin cambiar archivo ni clave.</p><button type="button" className="btn btn-outline-secondary" disabled={api.loading||api.busy} onClick={()=>void upload(null,true)}>Reconsultar y reintentar misma carga</button>
      {!api.locked&&[400,403,404,413,415,422].includes(api.error?.status)&&<button type="button" className="btn btn-outline-secondary" disabled={api.busy} onClick={()=>{intention.current=null;setIntent(null);api.setError(null);setMessage('Carga rechazada descartada; selecciona explícitamente otro archivo si corresponde.');}}>Nueva intención tras rechazo de archivo</button>}</>}
    {rows&&!rows.count&&<p>No hay adjuntos registrados.</p>}
    <ul className="list-group">{rows?.results.map((row)=><li className="list-group-item d-flex flex-wrap justify-content-between gap-2" key={row.id}><span>{row.nombre_visible} · {row.mime} · {Math.ceil(row.tamano_bytes/1024)} KiB · {row.estado}</span><span className="d-flex gap-2">
      <button type="button" className="btn btn-outline-secondary btn-sm" disabled={api.busy} onClick={()=>void inspect(row)}>Detalle</button><button type="button" className="btn btn-outline-secondary btn-sm" disabled={api.busy} onClick={()=>void loadMetadata(row)}>Anotaciones</button><button type="button" className="btn btn-outline-secondary btn-sm" disabled={api.busy} onClick={()=>void api.load('attachment-download',`/api/adjuntos/${row.id}/descargar/`,(blob)=>download(blob,row),{responseType:'blob'})}>Descargar privado</button>
    </span></li>)}</ul>
    {detail&&<p role="status">Detalle del adjunto #{detail.id} · destino {detail.destino.documento_cobro||detail.destino.obra} · registrado {detail.registrado_en}</p>}
    {selected&&<button type="button" className="btn btn-outline-secondary mt-2" disabled={api.busy||api.loading} onClick={()=>void loadMetadata(selected)}>Reconsultar anotaciones seleccionadas</button>}
    {metadata&&form&&<form className="commercial-form mt-3" onSubmit={saveMetadata} aria-label="Anotaciones de adjunto"><h4>Adjunto #{metadata.adjunto_id} · Anotaciones técnicas · revisión {metadata.revision}</h4>
      {canEdit?<><label className="form-label">Descripción<textarea className="form-control" maxLength={1000} disabled={blocked} value={form.descripcion} onChange={(e)=>setForm({...form,descripcion:e.target.value})}/></label><label className="form-label">Etiquetas separadas por coma<input className="form-control" disabled={blocked} value={form.etiquetas} onChange={(e)=>setForm({...form,etiquetas:e.target.value})}/></label><label className="form-label">Atributos técnicos JSON<textarea className="form-control" rows={4} disabled={blocked} value={form.atributos} onChange={(e)=>setForm({...form,atributos:e.target.value})}/></label><button className="btn btn-fyag-primary mt-2" disabled={blocked}>Guardar anotaciones</button></>:<><p>Consulta de solo lectura.</p><p>{metadata.descripcion}</p><p>{metadata.etiquetas.join(', ')}</p><pre>{JSON.stringify(metadata.atributos,null,2)}</pre></>}
    </form>}
    {rows&&<nav className="commercial-pager" aria-label="Paginación de adjuntos"><button type="button" className="btn btn-outline-secondary btn-sm" disabled={api.loading||api.busy||!!intent||!rows.previous} onClick={()=>setPage(safePage(rows.previous,path))}>Anterior</button><span>Página {page} · {rows.count} registros</span><button type="button" className="btn btn-outline-secondary btn-sm" disabled={api.loading||api.busy||!!intent||!rows.next} onClick={()=>setPage(safePage(rows.next,path))}>Siguiente</button></nav>}
  </section>;
}
