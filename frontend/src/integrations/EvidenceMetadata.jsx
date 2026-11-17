import React, { useEffect, useState } from 'react';
import { useAuth } from '../auth/AuthContext.jsx';
import { useApi } from './useApi.js';

const ATTRIBUTES = new Set(['ubicacion_general','vista','componente','condicion','tipo_evidencia','fase_trabajo','iluminacion','orientacion','equipo_tipo','zona_tecnica','requiere_revision','estado_visual']);
function validItem(item) {
  if (!item || !Number.isSafeInteger(item.evidencia_id) || item.evidencia_id < 1 || !Number.isSafeInteger(item.revision) || item.revision < 0
      || typeof item.descripcion !== 'string' || !Array.isArray(item.etiquetas) || !item.etiquetas.every((tag) => typeof tag === 'string')
      || !item.atributos || typeof item.atributos !== 'object' || Array.isArray(item.atributos)) throw new Error('Metadatos de evidencia inválidos.');
  return item;
}
export default function EvidenceMetadata({ obraId }) {
  const { user } = useAuth(), api = useApi();
  const [page, setPage] = useState(1), [data, setData] = useState(null), [selected, setSelected] = useState(null), [description, setDescription] = useState(''), [tags, setTags] = useState(''), [attributes, setAttributes] = useState('{}'), [notice, setNotice] = useState('');
  const path = `/api/documentos-metadata/?obra=${obraId}&page=${page}`;
  const reload = () => api.load('metadata', path, (value) => {
    if (!value || !Number.isSafeInteger(value.count) || !Array.isArray(value.results) || value.results.length > 25 || !['EVENTUAL'].includes(value.proyeccion) || value.fuente_autoritativa !== 'POSTGRESQL') throw new Error('Listado de metadatos inválido.');
    setData({ ...value, results: value.results.map(validItem) });
  });
  useEffect(() => { setData(null); void reload(); }, [path, user?.id, user?.role]);
  function select(item) { setSelected(item); setDescription(item.descripcion); setTags(item.etiquetas.join(', ')); setAttributes(JSON.stringify(item.atributos, null, 2)); setNotice(''); }
  async function save(event) {
    event.preventDefault();
    let parsed;
    try { parsed = JSON.parse(attributes); } catch { setNotice('Los atributos deben ser un objeto JSON válido.'); return; }
    if (!parsed || typeof parsed !== 'object' || Array.isArray(parsed) || Object.keys(parsed).some((key) => !ATTRIBUTES.has(key))) { setNotice('Usa solo las claves técnicas permitidas.'); return; }
    const body = { revision: selected.revision, descripcion, etiquetas: tags.split(',').map((tag) => tag.trim()).filter(Boolean), atributos: parsed };
    const ok = await api.write(`/api/documentos-metadata/evidencias/${selected.evidencia_id}/`, 'PATCH', body, async (value) => {
      const saved = validItem(value); setSelected(saved); setDescription(saved.descripcion); setTags(saved.etiquetas.join(', ')); setAttributes(JSON.stringify(saved.atributos, null, 2));
      await api.requiredLoad('metadata', path, (list) => setData({ ...list, results: list.results.map(validItem) })); setNotice('Anotaciones actualizadas.');
    });
    if (!ok && api.error?.status === 409) setNotice('La revisión cambió. Vuelve a consultar el elemento; no se sobrescribieron datos de otra persona.');
    else if (!ok && api.error?.status === 503) setNotice('MongoDB no está disponible. No se guardaron ni confirmaron cambios.');
  }
  if (!['GERENCIA','SUPERVISOR_OBRAS'].includes(user.role)) return null;
  return <section className="card-fyag p-3 my-3" aria-label="Metadatos de evidencias fotográficas"><div className="d-flex justify-content-between flex-wrap gap-2"><h3>Metadatos técnicos de evidencias</h3><button className="btn btn-outline-secondary btn-sm" type="button" disabled={api.loading} onClick={() => void reload()}>Actualizar metadatos</button></div>
    {api.error && <p className="alert alert-warning" role="alert">{api.error.status === 503 ? 'MongoDB no disponible; la consulta/edición de metadatos no se completó.' : api.error.status === 409 ? 'Metadatos pendientes de sincronización; vuelve a consultar más tarde.' : api.error.status === 403 ? 'No tienes permiso para consultar metadatos.' : api.error.message}</p>}
    {notice && <p className="alert alert-info" role="status">{notice}</p>}
    {data && !data.count && <p>No hay metadatos de evidencias para esta Obra.</p>}
    <ul className="list-group">{data?.results.map((item) => <li key={item.evidencia_id} className="list-group-item d-flex justify-content-between gap-2"><span>Evidencia #{item.evidencia_id} · Turno #{item.turno_id} · {item.tipo_mime} · revisión {item.revision}</span><button type="button" className="btn btn-outline-secondary btn-sm" onClick={() => select(item)}>Consultar / editar anotaciones</button></li>)}</ul>
    {selected && <form className="commercial-form mt-3" onSubmit={save}><h4>Evidencia #{selected.evidencia_id}</h4><label className="form-label" htmlFor="metadata-description">Descripción técnica</label><textarea id="metadata-description" className="form-control" maxLength={1000} value={description} disabled={api.busy || api.locked} onChange={(event) => setDescription(event.target.value)} /><label className="form-label mt-2" htmlFor="metadata-tags">Etiquetas separadas por coma</label><input id="metadata-tags" className="form-control" maxLength={500} value={tags} disabled={api.busy || api.locked} onChange={(event) => setTags(event.target.value)} /><label className="form-label mt-2" htmlFor="metadata-attributes">Atributos técnicos JSON</label><textarea id="metadata-attributes" className="form-control" rows={5} value={attributes} disabled={api.busy || api.locked} onChange={(event) => setAttributes(event.target.value)} /><div className="commercial-form-actions mt-2"><button className="btn btn-fyag-primary" type="submit" disabled={api.busy || api.locked}>Guardar anotaciones</button><button className="btn btn-outline-secondary" type="button" disabled={api.busy} onClick={() => setSelected(null)}>Cerrar</button></div></form>}
    {data && <nav className="commercial-pager" aria-label="Paginación de metadatos"><button className="btn btn-outline-secondary btn-sm" type="button" disabled={api.loading || page <= 1} onClick={() => setPage(page - 1)}>Anterior</button><span>Página {page} · {data.count} evidencias</span><button className="btn btn-outline-secondary btn-sm" type="button" disabled={api.loading || !data.next} onClick={() => setPage(page + 1)}>Siguiente</button></nav>}
  </section>;
}
