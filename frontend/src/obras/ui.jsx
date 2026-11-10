import React, { useEffect, useState } from 'react';
import { Chip } from '../components/ui';
import { Pager, useCommercial } from '../comercial/ui.jsx';
import { collectionPath, readPage } from './api.js';
import { OBRA_STATES, timestamp } from './domain.js';
export { Pager };
export const useOperational = useCommercial;

export function RefreshButton({ busy, onClick, label = 'Actualizar datos' }) {
  return <button type="button" className="btn btn-outline-secondary budget-refresh" disabled={busy} onClick={onClick} aria-label={label} title={label} aria-busy={!!busy}>
    {busy ? <span className="spinner-border spinner-border-sm" aria-hidden="true" /> : <svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" fill="currentColor" className="bi bi-arrow-counterclockwise" viewBox="0 0 16 16" aria-hidden="true" focusable="false">
      <path fillRule="evenodd" d="M8 3a5 5 0 1 1-4.546 2.914.5.5 0 0 0-.908-.417A6 6 0 1 0 8 2z" />
      <path d="M8 4.466V.534a.25.25 0 0 0-.41-.192L5.23 2.308a.25.25 0 0 0 0 .384l2.36 1.966A.25.25 0 0 0 8 4.466" />
    </svg>}
  </button>;
}
export function ObraStatus({ state }) {
  const [label, color] = OBRA_STATES[state] || ['Estado desconocido', 'gray'];
  return <Chip cls={color}>{label}</Chip>;
}
const fieldLabels = { descripcion: 'Descripción', nombre: 'Nombre', motivo: 'Motivo', presupuesto: 'Presupuesto', categoria_servicio: 'Categoría', tecnico: 'Técnico', tecnico_responsable: 'Responsable', fecha_programada: 'Fecha programada' };
export function OperationalErrors({ error }) {
  if (!error) return null;
  return <div className="alert alert-warning commercial-feedback" role="alert">
    <p>{error.message || 'Revisa los datos.'}</p>
    {error.code === 'sin_cambios' && <p>No hay un cambio aplicable. Consulta el estado actual.</p>}
    {error.code === 'presupuesto_utilizado' && <p>El presupuesto ya tiene una Obra asociada.</p>}
    {Object.entries(error.fieldErrors || {}).map(([field, values]) => <p key={field}>{fieldLabels[field] || (field === 'detail' || field === 'non_field_errors' ? 'Detalle' : field)}: {values.join(' ')}</p>)}
    {error.retryAfter && <p>Espera indicada por el servidor: {error.retryAfter}.</p>}
  </div>;
}
export function Feedback({ api }) {
  return <><OperationalErrors error={api.error} />
    {api.locked && <p className="alert alert-warning" role="status">Falta confirmar el resultado. Actualiza los datos antes de realizar otra operación.</p>}
    {api.loading && <p className="commercial-loading" role="status">Cargando datos…</p>}
  </>;
}
export function Field({ name, label, value, onChange, error, type = 'text', options, disabled, maxLength, required = false }) {
  const props = { id: `obras-${name}`, value: value ?? '', disabled, required, 'aria-invalid': !!error, 'aria-describedby': error ? `obras-${name}-error` : undefined, onChange: (e) => onChange(e.target.value) };
  return <div className="obras-field"><label className="form-label" htmlFor={props.id}>{label}</label>
    {options ? <select {...props} className={`form-select${error ? ' is-invalid' : ''}`}>{options.map(([key, text]) => <option key={key} value={key}>{text}</option>)}</select>
      : type === 'textarea' ? <textarea {...props} rows={3} maxLength={maxLength} className={`form-control${error ? ' is-invalid' : ''}`} />
        : <input {...props} type={type} maxLength={maxLength} className={`form-control${error ? ' is-invalid' : ''}`} />}
    {error && <div id={`obras-${name}-error`} className="invalid-feedback">{error}</div>}
  </div>;
}
export function focusError(event, errors) {
  const name = Object.keys(errors)[0];
  if (name) event.currentTarget?.querySelector(`#obras-${name}`)?.focus();
}
export function PagedSelect({ name, label, path, value, onChange, disabled, activeOnly = false, selectedLabel, error, required = false, refreshKey = 0 }) {
  const api = useOperational();
  const [page, setPage] = useState(1), [data, setData] = useState(null), [chosen, setChosen] = useState(null);
  const filters = activeOnly ? { activo: 'true' } : {};
  const read = () => api.load('choices', collectionPath(path, page, filters), (result) => setData(readPage(result, path)));
  useEffect(() => { setData(null); void read(); }, [path, page, activeOnly, refreshKey]);
  const optionText = (row) => row.codigo ? `${row.codigo} · ${row.cliente_nombre} · #${row.id}` : `${row.nombre} · #${row.id}`;
  const options = [['', 'Selecciona una opción'], ...(data?.results || []).map((row) => [String(row.id), optionText(row)])];
  if (value && !options.some(([id]) => id === String(value))) options.push([String(value), chosen?.id === Number(value) ? optionText(chosen) : selectedLabel || `Seleccionado #${value}`]);
  return <div className="obras-selector">
    <Field name={name} label={label} value={value} disabled={disabled || api.loading} error={error} required={required} options={options} onChange={(next) => {
      setChosen(data?.results.find((row) => row.id === Number(next)) || null); onChange(next);
    }} />
    <OperationalErrors error={api.error} />
    {api.error && <button type="button" className="btn btn-outline-secondary btn-sm" disabled={api.loading} onClick={read}>Reconsultar {label.toLowerCase()}</button>}
    {api.error?.status === 404 && page > 1 && <button type="button" className="btn btn-outline-secondary btn-sm" onClick={() => setPage(1)}>Primera página de {label.toLowerCase()}</button>}
    {data && <Pager label={`Páginas de ${label.toLowerCase()}`} data={data} page={page} setPage={setPage} disabled={disabled || api.loading} />}
    {data && !data.count && <p className="commercial-help">No hay opciones disponibles.</p>}
  </div>;
}
const eventKeys = { estado: 'Estado', categoria_servicio: 'Categoría (ID)', presupuesto: 'Presupuesto (ID)', descripcion: 'Descripción', tecnico_responsable: 'Responsable (ID)', fecha_programada: 'Fecha programada', iniciado_en: 'Inicio', finalizado_en: 'Finalización', nombre: 'Nombre', activo: 'Activo', tecnico: 'Técnico (ID)', asignado_por: 'Asignado por', asignado_en: 'Asignación', motivo_asignacion: 'Motivo de asignación', desasignado_por: 'Desasignado por', desasignado_en: 'Desasignación', motivo_desasignacion: 'Motivo de desasignación', origen_registro: 'Origen' };
export function EventList({ data, title }) {
  return <section className="commercial-history"><h3>{title}</h3>
    {data && !data.results.length && <p className="commercial-help">No hay eventos registrados.</p>}
    <ol className="commercial-timeline">{data?.results.map((event) => <li key={event.id}>
      <strong>{event.tipo.replaceAll('_', ' ')}{event.participante ? ` · Miembro #${event.participante}` : ''}</strong>
      {event.estado_nuevo && <div>{event.estado_anterior && <><ObraStatus state={event.estado_anterior} /> → </>}<ObraStatus state={event.estado_nuevo} /></div>}
      <p className="commercial-help">{timestamp(event.creado_en)} · Usuario #{event.registrado_por}</p><p className="commercial-long-text">{event.motivo || 'Sin motivo'}</p>
      <dl className="obras-event-changes">{Object.entries(eventKeys).filter(([key]) => Object.hasOwn(event.datos_nuevos || {}, key) || Object.hasOwn(event.datos_anteriores || {}, key)).map(([key, label]) => <div key={key}><dt>{label}</dt><dd>{String(event.datos_anteriores?.[key] ?? '—')} → {String(event.datos_nuevos?.[key] ?? '—')}</dd></div>)}</dl>
    </li>)}</ol>
  </section>;
}
export function PendingSection({ children }) {
  return <div className="alert alert-light border mt-3"><strong>Pendiente de integración frontend</strong><p className="mb-0">{children}</p></div>;
}
