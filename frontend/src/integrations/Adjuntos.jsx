import React, { useEffect, useRef, useState } from 'react';
import { useAuth } from '../auth/AuthContext.jsx';
import { ApiError } from '../auth/client.js';
import { readPage, useApi } from './useApi.js';

const MIME = new Set(['application/pdf', 'image/jpeg', 'image/png']);
const MAX_PDF = 8 * 1024 * 1024, MAX_IMAGE = 5 * 1024 * 1024;
function validateFile(file) {
  if (!file || !MIME.has(file.type)) return 'Selecciona un archivo PDF, JPEG o PNG.';
  if (file.size < 1 || file.size > (file.type === 'application/pdf' ? MAX_PDF : MAX_IMAGE)) return 'El archivo está vacío o supera el límite permitido.';
  return '';
}
function validAttachment(row) {
  if (!row || !Number.isSafeInteger(row.id) || row.id < 1 || typeof row.tipo !== 'string' || typeof row.nombre_visible !== 'string'
    || !MIME.has(row.mime) || !Number.isSafeInteger(row.tamano_bytes) || typeof row.estado !== 'string' || typeof row.registrado_en !== 'string') throw new ApiError(502, 'Respuesta documental inválida.');
  return row;
}
function download(blob, name) {
  if (!MIME.has(blob.type)) throw new Error('El servidor devolvió un tipo documental no permitido.');
  const url = URL.createObjectURL(blob), a = document.createElement('a');
  a.href = url; a.download = name.replace(/[\\/\x00-\x1f]/g, '_'); a.rel = 'noopener'; document.body.appendChild(a); a.click(); a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}
export default function Adjuntos({ type, destinationId, canUpload }) {
  const { request, user } = useAuth(), api = useApi();
  const [rows, setRows] = useState(null), [page, setPage] = useState(1), [selected, setSelected] = useState(null);
  const [file, setFile] = useState(null), [message, setMessage] = useState(''), [pendingKey, setPendingKey] = useState(null), [detail, setDetail] = useState(null), [metadata, setMetadata] = useState(null), [metadataForm, setMetadataForm] = useState(null);
  const path = type === 'RESPALDO_FACTURA' ? `/api/adjuntos/documentos-cobro/${destinationId}/` : `/api/adjuntos/obras/${destinationId}/`;
  const fileRef = useRef(null);
  const reload = () => api.load('attachments', `${path}${page > 1 ? `?page=${page}` : ''}`, (data) => setRows({ ...readPage(data, path), results: data.results.map(validAttachment) }));
  useEffect(() => { setRows(null); setSelected(null); void reload(); }, [path, page, user?.id, user?.role]);
  async function upload(event) {
    event.preventDefault();
    const issue = validateFile(file); if (issue) { setMessage(issue); return; }
    const key = pendingKey || globalThis.crypto?.randomUUID?.(); if(!key){setMessage('Este navegador no permite generar una clave segura de idempotencia.');return;} setPendingKey(key); setMessage('');
    const body = new FormData(); body.append('archivo', file, file.name);
    const ok = await api.write(path, 'POST', body, async () => {
      await api.requiredLoad('attachments', `${path}${page > 1 ? `?page=${page}` : ''}`, (data) => setRows({ ...readPage(data, path), results: data.results.map(validAttachment) }));
      setPendingKey(null); setFile(null); if (fileRef.current) fileRef.current.value = '';
    }, { headers: { 'Idempotency-Key': key } });
    if (!ok) setMessage(api.error?.status===503?'El escáner o el almacenamiento no está disponible; la carga falló de forma segura.':api.error?.status===409?'Conflicto de carga/idempotencia; actualiza antes de intentar de nuevo.':api.error?.status===422?'El archivo fue rechazado por validación de contenido.':api.error?.status===413?'El archivo supera el máximo permitido.':'No se confirmó la carga. Si el resultado fue incierto, conserva la misma clave y archivo para un reintento seguro.');
  }
  async function inspect(row) {
    setSelected(row.id); setDetail(null); setMessage('');
    try { const value = await request(`/api/adjuntos/${row.id}/`); setDetail(validAttachment(value)); }
    catch (error) { setMessage(error.message || 'No se pudo consultar el detalle.'); }
  }
  async function loadMetadata(row) {
    setSelected(row.id); setMetadata(null); setMetadataForm(null); setMessage('');
    try { const value = await request(`/api/adjuntos/${row.id}/anotaciones/`); if (!Number.isSafeInteger(value.revision) || !Array.isArray(value.etiquetas) || !value.atributos || typeof value.atributos !== 'object') throw new Error('Anotaciones documentales inválidas.'); setMetadata(value); setMetadataForm({ descripcion: value.descripcion || '', etiquetas: value.etiquetas.join(', '), atributos: JSON.stringify(value.atributos, null, 2) }); }
    catch (error) { setMessage(error.status === 503 ? 'MongoDB no disponible; las anotaciones no se consultaron.' : error.status === 409 ? 'Las anotaciones todavía no se sincronizaron.' : error.status === 403 ? 'No tienes permiso para editar estas anotaciones.' : error.message || 'No se pudieron consultar anotaciones.'); }
  }
  async function saveMetadata(event) {
    event.preventDefault(); if (!metadata || !metadataForm) return;
    let atributos; try { atributos = JSON.parse(metadataForm.atributos); } catch { setMessage('Atributos debe ser un objeto JSON válido.'); return; }
    if (!atributos || typeof atributos !== 'object' || Array.isArray(atributos)) { setMessage('Atributos debe ser un objeto JSON.'); return; }
    const result = await request(`/api/adjuntos/${metadata.adjunto_id}/anotaciones/`, { method: 'PATCH', body: { revision: metadata.revision, descripcion: metadataForm.descripcion, etiquetas: metadataForm.etiquetas.split(',').map((x) => x.trim()).filter(Boolean), atributos } }).catch((error) => { setMessage(error.status === 409 ? 'Revisión obsoleta. Vuelve a consultar antes de editar; no se sobrescribió ningún cambio.' : error.status === 503 ? 'MongoDB no disponible. El cambio no se confirmó.' : error.message); return null; });
    if (result) { setMetadata(result); setMetadataForm({ descripcion: result.descripcion || '', etiquetas: result.etiquetas.join(', '), atributos: JSON.stringify(result.atributos, null, 2) }); setMessage('Anotaciones actualizadas.'); }
  }
  async function downloadFile(row) {
    setMessage('');
    try { const blob = await request(`/api/adjuntos/${row.id}/descargar/`, { responseType: 'blob' }); if (blob.type !== row.mime) throw new Error('El tipo descargado no coincide con el registro.'); download(blob, row.nombre_visible); }
    catch (error) { setMessage(error.message || 'No se pudo descargar el archivo privado.'); }
  }
  return <section className="card-fyag p-3 my-3" aria-label={type === 'RESPALDO_FACTURA' ? 'Adjuntos de factura externa' : 'Informes técnicos adjuntos'}>
    <div className="d-flex flex-wrap justify-content-between align-items-center gap-2"><h3>{type === 'RESPALDO_FACTURA' ? 'Respaldos de factura externa' : 'Informes técnicos'}</h3><button type="button" className="btn btn-outline-secondary btn-sm" disabled={api.loading} onClick={() => void reload()}>Actualizar adjuntos</button></div>
    {api.error && <p className="alert alert-warning" role="alert">{api.error.status === 503 ? 'Servicio de archivos temporalmente no disponible; la carga no se considera exitosa.' : api.error.status === 413 ? 'El archivo supera el límite del servidor.' : api.error.status === 422 ? 'El contenido fue rechazado por las validaciones de seguridad.' : api.error.status === 409 ? 'Conflicto documental: actualiza la lista y revisa el estado antes de reintentar.' : api.error.status === 403 ? 'No tienes permiso para esta operación.' : api.error.message}</p>}
    {message && <p role="alert" className="alert alert-warning">{message}</p>}
    {canUpload && <form className="commercial-form mb-3" onSubmit={upload}><label className="form-label" htmlFor={`adjunto-${type}-${destinationId}`}>Subir PDF, JPEG o PNG</label><input ref={fileRef} id={`adjunto-${type}-${destinationId}`} className="form-control" type="file" accept="application/pdf,image/jpeg,image/png" disabled={api.busy || api.locked} onChange={(e) => { setFile(e.target.files?.[0] || null); setPendingKey(null); setMessage(''); }} /><button className="btn btn-fyag-primary mt-2" type="submit" disabled={!file || api.busy || api.locked}>{api.busy ? 'Subiendo…' : 'Subir archivo privado'}</button><p className="commercial-help">La API valida el archivo y el escáner antimalware; un fallo del escáner no cuenta como subida exitosa.</p></form>}
    {rows && !rows.count && <p>No hay adjuntos registrados.</p>}
    <ul className="list-group">{rows?.results.map((row) => <li className="list-group-item d-flex flex-wrap justify-content-between gap-2" key={row.id}><span>{row.nombre_visible} · {row.mime} · {Math.ceil(row.tamano_bytes / 1024)} KiB · {row.estado}</span><span className="d-flex gap-2"><button className="btn btn-outline-secondary btn-sm" type="button" onClick={() => void inspect(row)}>Detalle</button><button className="btn btn-outline-secondary btn-sm" type="button" onClick={() => void loadMetadata(row)}>Anotaciones</button><button className="btn btn-outline-secondary btn-sm" type="button" onClick={() => void downloadFile(row)}>Descargar privado</button></span></li>)}</ul>
    {detail && selected && <div className="mt-2" role="status">Detalle del adjunto #{detail.id} · destino {detail.destino.documento_cobro || detail.destino.obra} · registrado {detail.registrado_en}</div>}
    {metadata && metadataForm && <form className="commercial-form mt-3" onSubmit={saveMetadata}><h4>Anotaciones técnicas · revisión {metadata.revision}</h4>{user.role !== 'GERENCIA' && <><label className="form-label" htmlFor={`adj-desc-${metadata.adjunto_id}`}>Descripción</label><textarea id={`adj-desc-${metadata.adjunto_id}`} className="form-control" maxLength={1000} value={metadataForm.descripcion} onChange={(e)=>setMetadataForm({...metadataForm,descripcion:e.target.value})}/><label className="form-label mt-2" htmlFor={`adj-tags-${metadata.adjunto_id}`}>Etiquetas separadas por coma</label><input id={`adj-tags-${metadata.adjunto_id}`} className="form-control" value={metadataForm.etiquetas} onChange={(e)=>setMetadataForm({...metadataForm,etiquetas:e.target.value})}/><label className="form-label mt-2" htmlFor={`adj-attrs-${metadata.adjunto_id}`}>Atributos técnicos JSON</label><textarea id={`adj-attrs-${metadata.adjunto_id}`} rows={4} className="form-control" value={metadataForm.atributos} onChange={(e)=>setMetadataForm({...metadataForm,atributos:e.target.value})}/><button className="btn btn-fyag-primary mt-2" type="submit">Guardar anotaciones</button></>}{user.role === 'GERENCIA' && <p>Consulta de solo lectura.</p>}</form>}
    {rows && <nav className="commercial-pager" aria-label="Paginación de adjuntos"><button className="btn btn-outline-secondary btn-sm" type="button" disabled={api.loading || page <= 1} onClick={() => setPage(page - 1)}>Anterior</button><span>Página {page} · {rows.count} registros</span><button className="btn btn-outline-secondary btn-sm" type="button" disabled={api.loading || !rows.next} onClick={() => setPage(page + 1)}>Siguiente</button></nav>}
  </section>;
}
