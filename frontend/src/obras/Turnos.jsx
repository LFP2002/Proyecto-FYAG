import React, { useEffect, useMemo, useRef, useState } from 'react';
import { useAuth } from '../auth/AuthContext';
import { collectionPath, obraPath, readPage } from './api.js';
import { AF, G, S, T, timestamp, validId } from './domain.js';
import { Feedback, Field, Pager, useOperational } from './ui.jsx';
import { civilTime, duration } from './tecnicoDomain.js';
import TecIcon from './TecIcon.jsx';
import {useApp} from '../context/AppContext.jsx';

const estados = { ABIERTO: 'Abierto', PENDIENTE_REVISION: 'Pendiente de revisión', OBSERVADO: 'Observado', VALIDADO: 'Validado' };
const title = { iniciar: 'Iniciar turno', finalizar: 'Cerrar turno', subsanar: 'Subsanar turno', revisar: 'Revisar turno', corregir: 'Corregir turno', cerrar: 'Cierre administrativo' };
const fotoPath = (obra, turno, foto) => `${obraPath(obra)}turnos/${turno}/fotos/${foto}/`;

function validPhotos(files, existing = 0) {
  const list = Array.from(files || []);
  if (list.length + existing > 5) return 'Máximo 5 fotografías por turno.';
  if (list.some((file) => !['image/jpeg', 'image/png', 'image/webp'].includes(file.type))) return 'Solo se admiten imágenes JPEG, PNG o WebP.';
  if (list.some((file) => file.size < 1 || file.size > 5 * 1024 * 1024)) return 'Cada fotografía debe medir entre 1 byte y 5 MiB.';
  return '';
}

export function TurnoEditor({ obraId, item, mode, api, onCancel, onSaved }) {
  const [form, setForm] = useState({ descripcion_trabajo: '', decision: 'VALIDAR', motivo: '', costo_hora_neto: item?.costo_hora_neto || '', duracion_ajustada_segundos: item?.duracion_ajustada_segundos ?? '', fotos: [] });
  const [validation, setValidation] = useState('');
  const disabled = api.busy || api.locked;
  const submitting=useRef(false);
  async function submit(event) {
    event.preventDefault();
    if (disabled||submitting.current) return;
    const errors = {};
    if (['finalizar', 'cerrar'].includes(mode) && !form.descripcion_trabajo.trim()) errors.descripcion_trabajo = 'Campo obligatorio';
    if (['revisar', 'corregir', 'cerrar'].includes(mode) && !form.motivo.trim()) errors.motivo = 'Campo obligatorio';
    if (mode === 'subsanar' && !form.descripcion_trabajo.trim() && !form.fotos.length) errors.descripcion_trabajo = 'Agrega una aclaración o fotografías.';
    if (mode === 'revisar' && form.decision === 'VALIDAR' && !/^\d{1,13}\.\d{2}$/.test(form.costo_hora_neto)) errors.costo_hora_neto = 'Ingresa la tarifa como decimal con dos cifras, por ejemplo 8000.00.';
    if (form.duracion_ajustada_segundos !== '' && (!validId(form.duracion_ajustada_segundos))) errors.duracion_ajustada_segundos = 'Ingresa un entero positivo.';
    if (Object.keys(errors).length) { setValidation(Object.values(errors).join(' ')); return; }
    setValidation('');
    let action = mode, body = {};
    if (mode === 'finalizar' || mode === 'subsanar') {
      action = `${item.turno_id}/${mode}/`;
      if (form.fotos.length) {
        body = new FormData();
        if (form.descripcion_trabajo.trim()) body.append('descripcion_trabajo', form.descripcion_trabajo.trim());
        form.fotos.forEach((file) => body.append('fotos[]', file));
      } else if (form.descripcion_trabajo.trim()) body = { descripcion_trabajo: form.descripcion_trabajo.trim() };
    } else if (mode === 'revisar') {
      action = `${item.turno_id}/revisar/`;
      body = { decision: form.decision, motivo: form.motivo.trim(), ...(form.decision === 'VALIDAR' ? { costo_hora_neto: form.costo_hora_neto } : {}) };
    } else if (mode === 'corregir') {
      action = `${item.turno_id}/corregir/`;
      body = { motivo: form.motivo.trim(), ...(form.duracion_ajustada_segundos !== '' ? { duracion_ajustada_segundos: Number(form.duracion_ajustada_segundos) } : {}), ...(form.costo_hora_neto ? { costo_hora_neto: form.costo_hora_neto } : {}) };
    } else if (mode === 'cerrar') {
      action = `${item.turno_id}/cerrar-administrativamente/`;
      body = { motivo: form.motivo.trim(), descripcion_trabajo: form.descripcion_trabajo.trim(), ...(form.duracion_ajustada_segundos !== '' ? { duracion_ajustada_segundos: Number(form.duracion_ajustada_segundos) } : {}) };
    }
    if (mode === 'iniciar') { action = 'iniciar/'; body = {}; }
    submitting.current=true;
    try{await api.write(`${obraPath(obraId)}turnos/${action}`, 'POST', body, async () => onSaved());}finally{submitting.current=false;}
  }
  const set = (key, value) => setForm((previous) => ({ ...previous, [key]: value }));
  return <form className="card-fyag commercial-form" noValidate onSubmit={submit}>
    <h3>{title[mode]}</h3>
    {['finalizar', 'subsanar', 'cerrar'].includes(mode) && <Field name="descripcion_trabajo" label="Descripción del trabajo" type="textarea" value={form.descripcion_trabajo} onChange={(v) => set('descripcion_trabajo', v)} disabled={disabled} maxLength={2000} required={mode !== 'subsanar'} />}
    {['finalizar', 'subsanar'].includes(mode) && <div className="obras-field"><label className="form-label" htmlFor="turno-fotos">Fotografías (JPEG, PNG o WebP; máximo 5 por turno)</label><input id="turno-fotos" className="form-control" type="file" accept="image/jpeg,image/png,image/webp" multiple disabled={disabled} onChange={(e) => { const files = Array.from(e.target.files || []); const issue = validPhotos(files, item.fotos?.length || 0); setValidation(issue); set('fotos', issue ? [] : files); }} /></div>}
    {mode === 'revisar' && <Field name="decision" label="Decisión" options={[[ 'VALIDAR', 'Validar' ], [ 'OBSERVAR', 'Observar' ]]} value={form.decision} onChange={(v) => set('decision', v)} disabled={disabled} />}
    {['revisar', 'corregir'].includes(mode) && <Field name="costo_hora_neto" label="Costo horario neto (string decimal)" value={form.costo_hora_neto} onChange={(v) => set('costo_hora_neto', v)} disabled={disabled || (mode === 'revisar' && form.decision !== 'VALIDAR')} />}
    {['cerrar', 'corregir'].includes(mode) && <Field name="duracion_ajustada_segundos" label="Duración ajustada (segundos, opcional)" value={form.duracion_ajustada_segundos} onChange={(v) => set('duracion_ajustada_segundos', v)} disabled={disabled} />}
    {['revisar', 'corregir', 'cerrar'].includes(mode) && <Field name="motivo" label="Motivo" type="textarea" value={form.motivo} onChange={(v) => set('motivo', v)} disabled={disabled} maxLength={2000} required />}
    {validation && <p className="invalid-feedback d-block" role="alert">{validation}</p>}
    <div className="commercial-form-actions"><button className="btn btn-fyag-primary" type="submit" disabled={disabled}>{api.busy ? 'Guardando…' : 'Confirmar'}</button><button className="btn btn-outline-secondary" type="button" disabled={api.busy||api.locked} onClick={onCancel}>Cancelar</button></div>
  </form>;
}

export default function Turnos({ obraId, obraState, onOperationalLock }) {
  const { user, request } = useAuth(), api = useOperational();
  const app=useApp();
  useEffect(()=>{onOperationalLock?.(api.busy||api.locked);return()=>onOperationalLock?.(false);},[api.busy,api.locked,onOperationalLock]);
  useEffect(()=>{if(user.role!==T||!app?.setNavigationBlocked)return;app.setNavigationBlocked(api.busy||api.locked);return()=>app.setNavigationBlocked(false);},[api.busy,api.locked,user.role,app?.setNavigationBlocked]);
  const [page, setPage] = useState(1), [data, setData] = useState(null), [editor, setEditor] = useState(null), [downloadError, setDownloadError] = useState(''), [downloading, setDownloading] = useState(null);
  const blobUrls = useRef(new Set());
  const base = `${obraPath(obraId)}turnos/`;
  const path = useMemo(() => collectionPath(base, page), [base, page]);
  const reload = () => api.load('turnos', path, (result) => setData(readPage(result, base)));
  useEffect(() => { setData(null); void reload(); }, [path]);
  useEffect(() => () => { blobUrls.current.forEach((url) => URL.revokeObjectURL(url)); blobUrls.current.clear(); }, []);
  const blocked = api.busy || api.loading || api.locked;
  async function reconcile() {
    const ok = await reload();
    if (ok) api.reconcile(async () => true);
    return ok;
  }
  async function refreshAfterWrite() {
    await api.requiredLoad('turnos', path, (result) => { setData(readPage(result, base)); setEditor(null); });
  }
  async function download(turno, foto) {
    const path = fotoPath(obraId, turno.turno_id, foto.id);
    setDownloadError(''); setDownloading(foto.id);
    let url;
    try {
      const blob = await request(path, { responseType: 'blob' });
      if (!['image/jpeg', 'image/png', 'image/webp'].includes(blob.type)) throw new Error('Tipo de archivo inesperado.');
      url = URL.createObjectURL(blob); blobUrls.current.add(url);
      const extension = { 'image/jpeg': 'jpg', 'image/png': 'png', 'image/webp': 'webp' }[blob.type];
      const link = document.createElement('a');
      link.href = url; link.download = `evidencia-${foto.id}.${extension}`; link.rel = 'noopener';
      document.body.appendChild(link); link.click(); link.remove();
      setTimeout(() => { URL.revokeObjectURL(url); blobUrls.current.delete(url); }, 1000);
    } catch (error) { setDownloadError(error.message || 'No se pudo descargar la evidencia.'); }
    finally { setDownloading(null); }
  }
  const canTechnician = user.role === T;
  const canSupervisor = user.role === S;
  const canReview = user.role === S;
  return <section className={canTechnician?"card-fyag tec-panel tec-turnos":undefined} aria-labelledby="turnos-title">
    <div className="commercial-section-head"><h3 id="turnos-title">{canTechnician?"Mis turnos de esta obra":"Turnos y evidencia"}</h3><button type="button" className="btn btn-outline-secondary btn-sm" disabled={api.busy || api.loading} onClick={() => void reconcile()}>Actualizar turnos</button></div>
    <Feedback api={api} />
    {downloadError && <p className="alert alert-warning" role="alert">{downloadError}</p>}
    {!data?.results.length && data && <p className="commercial-empty">No hay turnos registrados.</p>}
    <ol className={canTechnician?"tec-shifts":"list-group list-group-numbered mb-3"}>{data?.results.map((turno) => <li className={canTechnician?"tec-shift":"list-group-item"} key={turno.turno_id}>
      <div className="d-flex flex-wrap justify-content-between gap-2"><strong>{canTechnician?estados[turno.estado_revision]:`Turno #${turno.turno_id} · ${estados[turno.estado_revision]||turno.estado_revision}`}</strong><span>{(canTechnician?civilTime:timestamp)(turno.iniciado_en)}{turno.terminado_en ? ` – ${(canTechnician?civilTime:timestamp)(turno.terminado_en)}` : ''}</span></div>
      <p className="mb-1">{canTechnician?(turno.terminado_en?duration(turno)+" · ":""):`Técnico #${turno.tecnico} · `}{turno.modo_cierre === 'SUPERVISOR' ? 'Cierre administrativo' : turno.modo_cierre === 'TECNICO' ? 'Cierre del técnico' : 'Abierto'}</p>
      {turno.descripcion_trabajo && <p className="commercial-long-text">{turno.descripcion_trabajo}</p>}
      {turno.observacion && <p className="alert alert-warning">Observación: {turno.observacion}</p>}
      {[S, G].includes(user.role) && turno.observacion_revision && <p>Motivo de revisión: {turno.observacion_revision}</p>}
      {[S, G].includes(user.role) && turno.costo_mano_obra != null && <p>Costo mano de obra neto: {turno.costo_mano_obra}</p>}
      {!!turno.fotos?.length && <ul aria-label={`Evidencias del turno ${turno.turno_id}`}>{turno.fotos.map((foto) => <li key={foto.id}>Foto {foto.id} · {foto.tipo_mime} · {Math.ceil(foto.tamano / 1024)} KiB <button type="button" className="btn btn-outline-secondary btn-sm" disabled={downloading === foto.id} onClick={() => void download(turno, foto)}>{downloading === foto.id ? 'Descargando…' : 'Descargar evidencia privada'}</button></li>)}</ul>}
      {editor?.turno_id === turno.turno_id && <TurnoEditor obraId={obraId} item={turno} mode={editor.mode} api={api} onCancel={() => setEditor(null)} onSaved={async () => { await refreshAfterWrite(); }} />}
      {!editor && <div className="commercial-actions">
        {canTechnician && turno.tecnico === user.id && turno.estado_revision === 'ABIERTO' && <button type="button" className="btn btn-fyag-primary" disabled={blocked} onClick={() => setEditor({ turno_id: turno.turno_id, mode: 'finalizar' })}>Cerrar mi turno</button>}
        {canTechnician && turno.estado_revision === 'OBSERVADO' && turno.tecnico === user.id && <button type="button" className="btn btn-outline-secondary" disabled={blocked} onClick={() => setEditor({ turno_id: turno.turno_id, mode: 'subsanar' })}>Subsanar turno</button>}
        {canReview && ['EN_PROCESO', 'SUSPENDIDA'].includes(obraState) && turno.estado_revision === 'PENDIENTE_REVISION' && <button type="button" className="btn btn-outline-secondary" disabled={blocked} onClick={() => setEditor({ turno_id: turno.turno_id, mode: 'revisar' })}>Revisar turno</button>}
        {canSupervisor && ['EN_PROCESO', 'SUSPENDIDA'].includes(obraState) && turno.terminado_en && <button type="button" className="btn btn-outline-secondary" disabled={blocked} onClick={() => setEditor({ turno_id: turno.turno_id, mode: 'corregir' })}>Corregir turno</button>}
        {canSupervisor && obraState === 'EN_PROCESO' && turno.estado_revision === 'ABIERTO' && <button type="button" className="btn btn-outline-secondary" disabled={blocked} onClick={() => setEditor({ turno_id: turno.turno_id, mode: 'cerrar' })}>Cerrar administrativamente</button>}
      </div>}
    </li>)}</ol>
    {(!canTechnician||data?.next||data?.previous)&&<Pager label="Paginación de turnos" data={data} page={page} setPage={setPage} disabled={blocked || !!editor} />}
    {canTechnician && obraState === 'EN_PROCESO' && data && !data.results.some(t=>t.estado_revision==='ABIERTO') && <button type="button" className="btn btn-fyag-primary" disabled={blocked || !!editor} onClick={async () => { await api.write(`${base}iniciar/`, 'POST', {}, refreshAfterWrite); }}>Iniciar turno</button>}
    {AF === user.role && <p className="commercial-help">Los turnos no están disponibles para este rol.</p>}
  </section>;
}
