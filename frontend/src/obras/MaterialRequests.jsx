import React, { useEffect, useMemo, useState } from 'react';
import { useAuth } from '../auth/AuthContext.jsx';
import { PageHead } from '../components/ui/index.js';
import { useApi, readPage, positiveInteger } from '../integrations/useApi.js';
import { Pager } from '../comercial/ui.jsx';

const ROOT='/api/inventario/';
const UUID=()=>globalThis.crypto?.randomUUID?.()||`${Date.now()}-${Math.random().toString(16).slice(2)}-4000-8000-000000000000`;
const DECIMAL=/^(?:0|[1-9][0-9]{0,8})(?:\.[0-9]{1,3})?$/;
function pageShape(value,path){
  const result=readPage(value,path);
  for(const row of result.results)if(!positiveInteger(row.id)||!positiveInteger(row.obra)||!positiveInteger(row.articulo)||typeof row.unidad!=='string'||typeof row.cantidad_solicitada!=='string'||typeof row.justificacion!=='string'||!['PENDIENTE','APROBADA','RECHAZADA'].includes(row.estado))throw new Error('La respuesta de solicitudes no coincide con el contrato.');
  return result;
}
export default function MaterialRequests({obraId,obraState}){
  const {user}=useAuth(),api=useApi(),technician=user.role==='TECNICO',supervisor=user.role==='SUPERVISOR_OBRAS';
  const [page,setPage]=useState(1),[requests,setRequests]=useState(null),[articles,setArticles]=useState(null),[formOpen,setFormOpen]=useState(false),[form,setForm]=useState({articulo:'',cantidad:'',justificacion:''}),[message,setMessage]=useState('');
  const url=useMemo(()=>`${ROOT}solicitudes-materiales/?obra=${obraId}&page=${page}`,[obraId,page]);
  useEffect(()=>{setRequests(null);void api.load('material-requests',url,(value)=>setRequests(pageShape(value,`${ROOT}solicitudes-materiales/`)));},[url,user.id,user.role]);
  async function openForm(){setMessage('');setArticles(null);const ok=await api.load('material-catalog',`${ROOT}articulos-solicitables/?page=1`,(value)=>setArticles(readPage(value,`${ROOT}articulos-solicitables/`)));if(ok)setFormOpen(true);}
  async function submit(event){
    event.preventDefault();if(!/^[1-9][0-9]{0,18}$/.test(form.articulo)||!DECIMAL.test(form.cantidad)||Number(form.cantidad)<=0||!form.justificacion.trim()){setMessage('Selecciona artículo, indica cantidad positiva y explica la justificación.');return;}
    setMessage('');await api.write(`${ROOT}solicitudes-materiales/`,'POST',{obra:obraId,articulo:Number(form.articulo),cantidad:form.cantidad,justificacion:form.justificacion.trim(),clave_idempotencia:UUID()},async()=>{await api.requiredLoad('material-requests',url,(value)=>setRequests(pageShape(value,`${ROOT}solicitudes-materiales/`)));setMessage('Solicitud enviada al Supervisor.');setFormOpen(false);setForm({articulo:'',cantidad:'',justificacion:''});});
  }
  async function decide(row,decision){
    const motivo=window.prompt(decision==='APROBAR'?'Motivo de aprobación:':'Motivo de rechazo:');if(motivo===null||!motivo.trim())return;let cantidad_aprobada;
    if(decision==='APROBAR'){cantidad_aprobada=window.prompt(`Cantidad aprobada (máximo ${row.cantidad_solicitada} ${row.unidad}):`,row.cantidad_solicitada);if(cantidad_aprobada===null||!DECIMAL.test(cantidad_aprobada)||Number(cantidad_aprobada)<=0||Number(cantidad_aprobada)>Number(row.cantidad_solicitada))return;}
    await api.write(`${ROOT}solicitudes-materiales/${row.id}/decidir/`,'POST',{decision,motivo:motivo.trim(),clave_idempotencia:UUID(),...(decision==='APROBAR'?{cantidad_aprobada}:{})},async()=>{await api.requiredLoad('material-requests',url,(value)=>setRequests(pageShape(value,`${ROOT}solicitudes-materiales/`)));});
  }
  const canCreate=technician&&obraState==='EN_PROCESO';
  return <section className="card-fyag inventario-requests">
    <PageHead title="Solicitudes de materiales" sub={technician?'Solicita material para esta Obra; el Supervisor revisa la solicitud.':'Solicitudes de materiales autorizadas para esta Obra.'}>{canCreate&&<button className="btn btn-fyag-primary" disabled={api.busy||api.loading||formOpen} onClick={()=>void openForm()}>Nueva solicitud</button>}</PageHead>
    {api.error&&<p className="alert alert-warning" role="alert">{api.error.status===403?'No tienes permiso para esta operación.':api.error.status===409?'La Obra, solicitud o artículo cambió de estado; actualiza la lista.':api.error.message}</p>}{message&&<p className="alert alert-info" role="status">{message}</p>}
    {formOpen&&<form className="commercial-form" onSubmit={submit}><h3>Nueva solicitud para Obra #{obraId}</h3><label className="form-label">Artículo<select className="form-select" required value={form.articulo} disabled={api.busy||api.loading} onChange={(event)=>setForm({...form,articulo:event.target.value})}><option value="">Seleccionar artículo</option>{articles?.results.map((article)=><option key={article.id} value={article.id}>{article.codigo} · {article.nombre} ({article.unidad})</option>)}</select></label><label className="form-label">Cantidad<input className="form-control" inputMode="decimal" value={form.cantidad} disabled={api.busy} onChange={(event)=>setForm({...form,cantidad:event.target.value})} required /></label><label className="form-label">Justificación<textarea className="form-control" maxLength={2000} value={form.justificacion} disabled={api.busy} onChange={(event)=>setForm({...form,justificacion:event.target.value})} required /></label><div className="commercial-form-actions"><button className="btn btn-fyag-primary" type="submit" disabled={api.busy||api.loading}>Enviar solicitud</button><button className="btn btn-outline-secondary" type="button" disabled={api.busy} onClick={()=>setFormOpen(false)}>Cancelar</button></div><p className="commercial-help">La solicitud no reserva ni descuenta existencias y no muestra información económica.</p></form>}
    <div className="table-responsive" role="region" aria-label="Solicitudes de materiales de la Obra" tabIndex={0}><table className="table table-hover align-middle commercial-table"><thead><tr>{['Solicitud','Artículo','Cantidad','Estado','Justificación / decisión','Fecha',...(supervisor?['Acción']:[])].map((label)=><th key={label}>{label}</th>)}</tr></thead><tbody>{requests?.results.map((row)=><tr key={row.id}><td>#{row.id}</td><td>Artículo #{row.articulo} · {row.unidad}</td><td>{row.cantidad_solicitada} {row.unidad}{row.cantidad_aprobada?` · aprobado ${row.cantidad_aprobada}`:''}</td><td>{row.estado.replaceAll('_',' ')}</td><td>{row.justificacion}{row.motivo_decision?<span className="d-block small">Decisión: {row.motivo_decision}</span>:null}</td><td>{row.creado_en?new Date(row.creado_en).toLocaleString('es-CL'):'—'}</td>{supervisor&&<td>{row.estado==='PENDIENTE'&&<div className="inventario-row-actions"><button type="button" className="btn btn-sm btn-fyag-primary" disabled={api.busy||api.loading} onClick={()=>void decide(row,'APROBAR')}>Aprobar</button><button type="button" className="btn btn-sm btn-outline-danger" disabled={api.busy||api.loading} onClick={()=>void decide(row,'RECHAZAR')}>Rechazar</button></div>}</td>}</tr>)}</tbody></table></div>
    {requests&&!requests.count&&<p className="commercial-empty">No hay solicitudes de materiales en esta Obra.</p>}<Pager data={requests} page={page} setPage={setPage} disabled={api.loading||api.busy} label="Paginación de solicitudes de materiales" />
  </section>;
}
