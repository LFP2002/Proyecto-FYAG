import React, { useEffect, useRef, useState } from 'react';
import { useAuth } from '../auth/AuthContext.jsx';
import { ApiError } from '../auth/client.js';
import { positiveInteger, readPage, safePage, strictObject, useApi } from './useApi.js';
import '../styles/components/adjuntos.css';
import TecIcon from '../obras/TecIcon.jsx';
import {civilTime} from '../obras/tecnicoDomain.js';
import {useApp} from '../context/AppContext.jsx';

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
const editForm = (value) => ({descripcion:value.descripcion});
const fileType = row => row.mime==='application/pdf'?'PDF':row.mime==='image/png'?'PNG':'JPEG';
const fileSize = row => `${Math.ceil(row.tamano_bytes/1024)} KB`;
function registrationDate(value) {
  const date=new Date(value);
  return Number.isNaN(date.getTime())?value:new Intl.DateTimeFormat('es-CL',{timeZone:'America/Santiago',dateStyle:'short',timeStyle:'short'}).format(date);
}
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
function AttachmentScreen({type,destinationId,canUpload,readOnly=false,embedded=false,compactActions=false,obraCode,onOperationalLock}) {
  const {user}=useAuth(),api=useApi();
  const [rows,setRows]=useState(null),[page,setPage]=useState(1),[selected,setSelected]=useState(null),[file,setFile]=useState(null);
  const [message,setMessage]=useState(''),[intent,setIntent]=useState(null),[detail,setDetail]=useState(null),[metadata,setMetadata]=useState(null),[form,setForm]=useState(null);
  const [selectionMode,setSelectionMode]=useState(null),[menuId,setMenuId]=useState(null);
  const intention=useRef(null),fileRef=useRef(null),pending=useRef(false);
  const canEdit=!readOnly&&(type==='RESPALDO_FACTURA'?user.role==='ADMINISTRATIVO_FINANZAS':['SUPERVISOR_OBRAS','TECNICO'].includes(user.role));
  const path=type==='RESPALDO_FACTURA'?`/api/adjuntos/documentos-cobro/${destinationId}/`:`/api/adjuntos/obras/${destinationId}/`;
  const project=(value)=>attachment(value,type,destinationId);
  const reload=()=>{setRows(null);return api.load('attachments',`${path}?page=${page}`,(data)=>setRows({...readPage(data,path),results:data.results.map(project)}));};
  function clearSelection(){setMenuId(null);api.cancelRead('attachment-selection');api.cancelRead('attachment-download');setSelected(null);setSelectionMode(null);setDetail(null);setMetadata(null);setForm(null);setMessage('');}
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
  async function inspect(row){clearSelection();setSelected(row);setSelectionMode('info');await api.load('attachment-selection',`/api/adjuntos/${row.id}/`,(value)=>{const next=project(value);if(next.id!==row.id)throw new ApiError(502,'Adjunto inesperado.');setDetail(next);});}
  async function loadMetadata(row) {
    clearSelection();setSelected(row);setSelectionMode('notes');
    const read=()=>api.load('attachment-selection',`/api/adjuntos/${row.id}/anotaciones/`,(value)=>{const next=annotation(value,row,type,destinationId);setMetadata(next);setForm(editForm(next));});
    // Releer notas reconcilia solamente su CAS, nunca una carga pendiente.
    return intention.current ? read() : api.reconcile(read);
  }
  async function saveMetadata(event) {
    event.preventDefault();if(!canEdit||!metadata||!selected||api.busy||api.locked||pending.current||intention.current)return;
    const row=selected,revision=metadata.revision;pending.current=true;setMessage('');api.cancelRead('attachment-selection');
    try{
      await api.write(`/api/adjuntos/${row.id}/anotaciones/`,'PATCH',{revision,descripcion:form.descripcion,etiquetas:metadata.etiquetas,atributos:metadata.atributos},async(value)=>{
        const next=annotation(value,row,type,destinationId);if(next.revision!==revision+1)throw new ApiError(502,'Revisión documental inesperada.');setMetadata(next);setForm(editForm(next));setMessage('Anotaciones actualizadas.');
      });
    }finally{pending.current=false;}
  }
  const blocked=api.busy||api.locked||!!intent;
  const app=useApp();
  useEffect(()=>{if(!compactActions)return;onOperationalLock?.(blocked);app?.setNavigationBlocked?.(blocked);return()=>{onOperationalLock?.(false);app?.setNavigationBlocked?.(false);};},[compactActions,blocked,onOperationalLock,app?.setNavigationBlocked]);
  return <section className={`attachments-panel${embedded?'':' card-fyag p-3 my-3'}`} aria-label={type==='RESPALDO_FACTURA'?'Adjuntos de factura externa':'Informes técnicos adjuntos'}>
    <div className="attachments-header"><h3>{type==='RESPALDO_FACTURA'?'Respaldos documentales':'Informes técnicos'}</h3><button type="button" className="btn btn-outline-secondary btn-sm attachment-action" disabled={api.loading||api.busy} onClick={()=>{setMessage('');void reload();}}><svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" aria-hidden="true" focusable="false" fill="currentColor" className="bi bi-arrow-counterclockwise" viewBox="0 0 16 16"><path fillRule="evenodd" d="M8 3a5 5 0 1 1-4.546 2.914.5.5 0 0 0-.908-.417A6 6 0 1 0 8 2z"/><path d="M8 4.466V.534a.25.25 0 0 0-.41-.192L5.23 2.308a.25.25 0 0 0 0 .384l2.36 1.966A.25.25 0 0 0 8 4.466"/></svg>Actualizar adjuntos</button></div>
    {type==='RESPALDO_FACTURA'&&readOnly&&<p className="attachments-notice">Documento revertido · Archivos disponibles solo para consulta, sin nuevas cargas ni edición de anotaciones.</p>}
    {api.error&&<p className="alert alert-warning" role="alert">{({403:'No tienes permiso para esta operación.',404:'Adjunto o destino no disponible.',409:'Conflicto documental o revisión CAS obsoleta/pendiente: reconsulta antes de editar, sin sobrescribir.',413:'El archivo supera el máximo permitido.',422:'Archivo rechazado por validación de contenido.',503:'Scanner, almacenamiento o MongoDB no disponible. El resultado no se considera confirmado.'})[api.error.status]||api.error.message}</p>}
    {api.locked&&<p role="alert">Escrituras bloqueadas hasta reconsultar la revisión; una carga incierta conserva la misma clave y archivo.</p>}
    {message&&<p role="status" className="alert alert-info">{message}</p>}
    {canUpload&&canEdit&&<form className="commercial-form mb-3" onSubmit={upload}><label className="form-label" htmlFor={`adjunto-${type}-${destinationId}`}>Subir PDF, JPEG o PNG</label><input ref={fileRef} id={`adjunto-${type}-${destinationId}`} className="form-control" type="file" accept="application/pdf,image/jpeg,image/png" disabled={blocked} onChange={(e)=>{setFile(e.target.files?.[0]||null);setMessage('');}}/>
      <button className="btn btn-fyag-primary mt-2" disabled={!file||blocked}>Subir archivo</button><p className="commercial-help">PDF hasta 8 MB; imágenes hasta 5 MB.</p>
    </form>}
    {intent&&<><p>Se conserva la intención de carga sin cambiar archivo ni clave.</p><button type="button" className="btn btn-outline-secondary" disabled={api.loading||api.busy} onClick={()=>void upload(null,true)}>Reconsultar y reintentar misma carga</button>
      {!api.locked&&[400,403,404,413,415,422].includes(api.error?.status)&&<button type="button" className="btn btn-outline-secondary" disabled={api.busy} onClick={()=>{intention.current=null;setIntent(null);api.setError(null);setMessage('Carga rechazada descartada; selecciona explícitamente otro archivo si corresponde.');}}>Nueva intención tras rechazo de archivo</button>}</>}
    {rows&&!rows.count&&(user.role==='SUPERVISOR_OBRAS'&&type==='INFORME_TECNICO'?<div className="so-empty" role="status"><TecIcon name="document"/><strong>No hay adjuntos registrados.</strong><p>{canUpload&&canEdit?'Los informes técnicos que subas aparecerán aquí.':'Los informes técnicos asociados a esta obra aparecerán aquí.'}</p></div>:<p className="attachments-empty">No hay adjuntos registrados.</p>)}
    {!rows&&api.loading&&<p role="status" className="commercial-help">Cargando adjuntos…</p>}
    <ul className="attachments-list">{rows?.results.map(row=>{
      const active=selected?.id===row.id;
      const panelId=`attachment-${type}-${destinationId}-${row.id}`;
      return <li className="attachment-item" key={row.id}>
        <div className="attachment-row">
          <div className="attachment-file">
            {/* Bootstrap Icons v1.13.1, SVG inline. */}
            <span className={`attachment-file-icon${row.mime==='application/pdf'?' is-pdf':''}`}>{row.mime==='application/pdf'?<svg xmlns="http://www.w3.org/2000/svg" width="22" height="22" aria-hidden="true" focusable="false" fill="currentColor" className="bi bi-file-earmark-pdf" viewBox="0 0 16 16"><path d="M14 14V4.5L9.5 0H4a2 2 0 0 0-2 2v12a2 2 0 0 0 2 2h8a2 2 0 0 0 2-2M9.5 3A1.5 1.5 0 0 0 11 4.5h2V14a1 1 0 0 1-1 1H4a1 1 0 0 1-1-1V2a1 1 0 0 1 1-1h5.5z"/><path d="M4.603 14.087a.8.8 0 0 1-.438-.42c-.195-.388-.13-.776.08-1.102.198-.307.526-.568.897-.787a7.7 7.7 0 0 1 1.482-.645 20 20 0 0 0 1.062-2.227 7.3 7.3 0 0 1-.43-1.295c-.086-.4-.119-.796-.046-1.136.075-.354.274-.672.65-.823.192-.077.4-.12.602-.077a.7.7 0 0 1 .477.365c.088.164.12.356.127.538.007.188-.012.396-.047.614-.084.51-.27 1.134-.52 1.794a11 11 0 0 0 .98 1.686 5.8 5.8 0 0 1 1.334.05c.364.066.734.195.96.465.12.144.193.32.2.518.007.192-.047.382-.138.563a1.04 1.04 0 0 1-.354.416.86.86 0 0 1-.51.138c-.331-.014-.654-.196-.933-.417a5.7 5.7 0 0 1-.911-.95 11.7 11.7 0 0 0-1.997.406 11.3 11.3 0 0 1-1.02 1.51c-.292.35-.609.656-.927.787a.8.8 0 0 1-.58.029m1.379-1.901q-.25.115-.459.238c-.328.194-.541.383-.647.547-.094.145-.096.25-.04.361q.016.032.026.044l.035-.012c.137-.056.355-.235.635-.572a8 8 0 0 0 .45-.606m1.64-1.33a13 13 0 0 1 1.01-.193 12 12 0 0 1-.51-.858 21 21 0 0 1-.5 1.05zm2.446.45q.226.245.435.41c.24.19.407.253.498.256a.1.1 0 0 0 .07-.015.3.3 0 0 0 .094-.125.44.44 0 0 0 .059-.2.1.1 0 0 0-.026-.063c-.052-.062-.2-.152-.518-.209a4 4 0 0 0-.612-.053zM8.078 7.8a7 7 0 0 0 .2-.828q.046-.282.038-.465a.6.6 0 0 0-.032-.198.5.5 0 0 0-.145.04c-.087.035-.158.106-.196.283-.04.192-.03.469.046.822q.036.167.09.346z"/></svg>:<svg xmlns="http://www.w3.org/2000/svg" width="22" height="22" aria-hidden="true" focusable="false" fill="currentColor" className="bi bi-file-earmark-image" viewBox="0 0 16 16"><path d="M6.502 7a1.5 1.5 0 1 0 0-3 1.5 1.5 0 0 0 0 3"/><path d="M14 14a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V2a2 2 0 0 1 2-2h5.5L14 4.5zM4 1a1 1 0 0 0-1 1v10l2.224-2.224a.5.5 0 0 1 .61-.075L8 11l2.157-3.02a.5.5 0 0 1 .76-.063L13 10V4.5h-2A1.5 1.5 0 0 1 9.5 3V1z"/></svg>}</span>
            <div className="attachment-file-name"><strong>{row.nombre_visible}</strong><div className="commercial-help">{fileType(row)} · {fileSize(row)}{compactActions&&` · ${civilTime(row.registrado_en)}`} · <span className="attachment-available">Disponible</span></div></div>
          </div>
          <div className="attachment-actions">
            {compactActions?<div className="tec-attachment-menu" onKeyDown={e=>{if(e.key==='Escape'){e.stopPropagation();setMenuId(null);}}} onBlur={e=>{if(!e.currentTarget.contains(e.relatedTarget))setMenuId(null);}}>
              <button type="button" className="btn btn-outline-secondary btn-sm attachment-action" aria-label={'Más opciones de '+row.nombre_visible} aria-expanded={menuId===row.id} disabled={api.busy} onClick={()=>setMenuId(menuId===row.id?null:row.id)}><TecIcon name="more"/></button>
              {menuId===row.id&&<div className="tec-attachment-options">            <button type="button" className="btn btn-outline-secondary btn-sm attachment-action" aria-expanded={active&&selectionMode==='info'} aria-controls={panelId} disabled={api.busy} onClick={()=>{setMenuId(null);if(active&&selectionMode==='info')clearSelection();else void inspect(row);}}><svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" aria-hidden="true" focusable="false" fill="currentColor" className="bi bi-info-circle" viewBox="0 0 16 16"><path d="M8 15A7 7 0 1 1 8 1a7 7 0 0 1 0 14m0 1A8 8 0 1 0 8 0a8 8 0 0 0 0 16"/><path d="m8.93 6.588-2.29.287-.082.38.45.083c.294.07.352.176.288.469l-.738 3.468c-.194.897.105 1.319.808 1.319.545 0 1.178-.252 1.465-.598l.088-.416c-.2.176-.492.246-.686.246-.275 0-.375-.193-.304-.533zM9 4.5a1 1 0 1 1-2 0 1 1 0 0 1 2 0"/></svg>Información</button>
            <button type="button" className="btn btn-outline-secondary btn-sm attachment-action" aria-expanded={active&&selectionMode==='notes'} aria-controls={panelId} disabled={api.busy} onClick={()=>{setMenuId(null);if(active&&selectionMode==='notes')clearSelection();else void loadMetadata(row);}}><svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" aria-hidden="true" focusable="false" fill="currentColor" className="bi bi-journal-text" viewBox="0 0 16 16"><path d="M5 10.5a.5.5 0 0 1 .5-.5h2a.5.5 0 0 1 0 1h-2a.5.5 0 0 1-.5-.5m0-2a.5.5 0 0 1 .5-.5h5a.5.5 0 0 1 0 1h-5a.5.5 0 0 1-.5-.5m0-2a.5.5 0 0 1 .5-.5h5a.5.5 0 0 1 0 1h-5a.5.5 0 0 1-.5-.5m0-2a.5.5 0 0 1 .5-.5h5a.5.5 0 0 1 0 1h-5a.5.5 0 0 1-.5-.5"/><path d="M3 0h10a2 2 0 0 1 2 2v12a2 2 0 0 1-2 2H3a2 2 0 0 1-2-2v-1h1v1a1 1 0 0 0 1 1h10a1 1 0 0 0 1-1V2a1 1 0 0 0-1-1H3a1 1 0 0 0-1 1v1H1V2a2 2 0 0 1 2-2"/><path d="M1 5v-.5a.5.5 0 0 1 1 0V5h.5a.5.5 0 0 1 0 1h-2a.5.5 0 0 1 0-1zm0 3v-.5a.5.5 0 0 1 1 0V8h.5a.5.5 0 0 1 0 1h-2a.5.5 0 0 1 0-1zm0 3v-.5a.5.5 0 0 1 1 0v.5h.5a.5.5 0 0 1 0 1h-2a.5.5 0 0 1 0-1z"/></svg>Anotaciones</button>
</div>}
            </div>:<>            <button type="button" className="btn btn-outline-secondary btn-sm attachment-action" aria-expanded={active&&selectionMode==='info'} aria-controls={panelId} disabled={api.busy} onClick={()=>{if(active&&selectionMode==='info')clearSelection();else void inspect(row);}}><svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" aria-hidden="true" focusable="false" fill="currentColor" className="bi bi-info-circle" viewBox="0 0 16 16"><path d="M8 15A7 7 0 1 1 8 1a7 7 0 0 1 0 14m0 1A8 8 0 1 0 8 0a8 8 0 0 0 0 16"/><path d="m8.93 6.588-2.29.287-.082.38.45.083c.294.07.352.176.288.469l-.738 3.468c-.194.897.105 1.319.808 1.319.545 0 1.178-.252 1.465-.598l.088-.416c-.2.176-.492.246-.686.246-.275 0-.375-.193-.304-.533zM9 4.5a1 1 0 1 1-2 0 1 1 0 0 1 2 0"/></svg>Información</button>
            <button type="button" className="btn btn-outline-secondary btn-sm attachment-action" aria-expanded={active&&selectionMode==='notes'} aria-controls={panelId} disabled={api.busy} onClick={()=>{if(active&&selectionMode==='notes')clearSelection();else void loadMetadata(row);}}><svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" aria-hidden="true" focusable="false" fill="currentColor" className="bi bi-journal-text" viewBox="0 0 16 16"><path d="M5 10.5a.5.5 0 0 1 .5-.5h2a.5.5 0 0 1 0 1h-2a.5.5 0 0 1-.5-.5m0-2a.5.5 0 0 1 .5-.5h5a.5.5 0 0 1 0 1h-5a.5.5 0 0 1-.5-.5m0-2a.5.5 0 0 1 .5-.5h5a.5.5 0 0 1 0 1h-5a.5.5 0 0 1-.5-.5m0-2a.5.5 0 0 1 .5-.5h5a.5.5 0 0 1 0 1h-5a.5.5 0 0 1-.5-.5"/><path d="M3 0h10a2 2 0 0 1 2 2v12a2 2 0 0 1-2 2H3a2 2 0 0 1-2-2v-1h1v1a1 1 0 0 0 1 1h10a1 1 0 0 0 1-1V2a1 1 0 0 0-1-1H3a1 1 0 0 0-1 1v1H1V2a2 2 0 0 1 2-2"/><path d="M1 5v-.5a.5.5 0 0 1 1 0V5h.5a.5.5 0 0 1 0 1h-2a.5.5 0 0 1 0-1zm0 3v-.5a.5.5 0 0 1 1 0V8h.5a.5.5 0 0 1 0 1h-2a.5.5 0 0 1 0-1zm0 3v-.5a.5.5 0 0 1 1 0v.5h.5a.5.5 0 0 1 0 1h-2a.5.5 0 0 1 0-1z"/></svg>Anotaciones</button>
</>}
            <button type="button" className="btn btn-fyag-primary btn-sm attachment-action" disabled={api.busy} onClick={()=>void api.load('attachment-download',`/api/adjuntos/${row.id}/descargar/`,blob=>download(blob,row),{responseType:'blob'})}><svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" aria-hidden="true" focusable="false" fill="currentColor" className="bi bi-download" viewBox="0 0 16 16"><path d="M.5 9.9a.5.5 0 0 1 .5.5v2.5a1 1 0 0 0 1 1h12a1 1 0 0 0 1-1v-2.5a.5.5 0 0 1 1 0v2.5a2 2 0 0 1-2 2H2a2 2 0 0 1-2-2v-2.5a.5.5 0 0 1 .5-.5"/><path d="M7.646 11.854a.5.5 0 0 0 .708 0l3-3a.5.5 0 0 0-.708-.708L8.5 10.293V1.5a.5.5 0 0 0-1 0v8.793L5.354 8.146a.5.5 0 1 0-.708.708z"/></svg>Descargar</button>
          </div>
        </div>
        <div id={panelId} className="attachment-selection" hidden={!active}>
          {active&&<>
            <div className="attachments-header"><h4>{selectionMode==='info'?'Información del archivo':'Anotaciones técnicas'}</h4><button type="button" className="btn btn-outline-secondary btn-sm attachment-action attachment-close" aria-label="Cerrar información del adjunto" disabled={api.busy} onClick={clearSelection}><svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" aria-hidden="true" focusable="false" fill="currentColor" className="bi bi-x-lg" viewBox="0 0 16 16"><path d="M2.146 2.854a.5.5 0 1 1 .708-.708L8 7.293l5.146-5.147a.5.5 0 0 1 .708.708L8.707 8l5.147 5.146a.5.5 0 0 1-.708.708L8 8.707l-5.146 5.147a.5.5 0 0 1-.708-.708L7.293 8z"/></svg></button></div>
            {selectionMode==='info'&&<>
              {detail?<dl className="attachment-facts"><div><dt>Identificador</dt><dd>#{detail.id}</dd></div><div><dt>{type==='RESPALDO_FACTURA'?'Documento asociado':'Obra asociada'}</dt><dd>{compactActions&&obraCode?obraCode:'#'+(detail.destino.documento_cobro||detail.destino.obra)}</dd></div><div><dt>Fecha de registro</dt><dd><time dateTime={detail.registrado_en} title={detail.registrado_en}>{registrationDate(detail.registrado_en)}</time></dd></div><div><dt>Tamaño</dt><dd>{fileSize(detail)}</dd></div></dl>:<p className="commercial-help" role="status">{api.loading?'Consultando información…':'Información no confirmada.'}</p>}
            </>}
            {selectionMode==='notes'&&<>
              {metadata&&form?<form className="commercial-form attachment-notes" onSubmit={saveMetadata} aria-label="Anotaciones de adjunto">
                <p className="commercial-help">{compactActions?(!canEdit?'Solo lectura':'Descripción del informe'):`Revisión ${metadata.revision}${!canEdit?' · Solo lectura':''}`}</p>
                {canEdit?<><label className="form-label">Descripción<textarea className="form-control" placeholder={compactActions?'Escribe una anotación técnica…':undefined} maxLength={1000} disabled={blocked} value={form.descripcion} onChange={e=>setForm({...form,descripcion:e.target.value})}/></label><div className="attachment-actions"><button className="btn btn-fyag-primary btn-sm" disabled={blocked}>Guardar anotaciones</button><button type="button" className="btn btn-outline-secondary btn-sm" disabled={api.busy} onClick={clearSelection}>Cancelar</button></div></>:<div className="attachment-note-text"><span className="commercial-help">Descripción · Consulta de solo lectura.</span><p>{metadata.descripcion||'Sin descripción.'}</p></div>}
              </form>:<p className="commercial-help" role="status">{api.loading?'Consultando anotaciones…':'Anotaciones no confirmadas.'}</p>}
              <button type="button" className="btn btn-outline-secondary btn-sm attachment-action attachment-notes-refresh" disabled={api.busy||api.loading} onClick={()=>void loadMetadata(row)}><svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" aria-hidden="true" focusable="false" fill="currentColor" className="bi bi-arrow-counterclockwise" viewBox="0 0 16 16"><path fillRule="evenodd" d="M8 3a5 5 0 1 1-4.546 2.914.5.5 0 0 0-.908-.417A6 6 0 1 0 8 2z"/><path d="M8 4.466V.534a.25.25 0 0 0-.41-.192L5.23 2.308a.25.25 0 0 0 0 .384l2.36 1.966A.25.25 0 0 0 8 4.466"/></svg>Actualizar anotaciones</button>
            </>}
          </>}
        </div>
      </li>;
    })}</ul>
    {rows&&<p className="commercial-help attachments-count">{rows.count} {rows.count===1?'archivo asociado':'archivos asociados'}</p>}
    {rows&&(rows.previous||rows.next)&&<nav className="commercial-pager" aria-label="Paginación de adjuntos"><button type="button" className="btn btn-outline-secondary btn-sm" disabled={api.loading||api.busy||!!intent||!rows.previous} onClick={()=>setPage(safePage(rows.previous,path))}>Anterior</button><span>Página {page} · {rows.count} registros</span><button type="button" className="btn btn-outline-secondary btn-sm" disabled={api.loading||api.busy||!!intent||!rows.next} onClick={()=>setPage(safePage(rows.next,path))}>Siguiente</button></nav>}
  </section>;
}
