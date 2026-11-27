import React, { useEffect, useState } from 'react';
import { useAuth } from '../auth/AuthContext.jsx';
import { Chip } from '../components/ui';
import { Pager, useCommercial } from '../comercial/ui.jsx';
import { collectionPath, readPage } from './api.js';
import TecIcon from './TecIcon.jsx';
import { formatCivilDate } from '../utils/format.js';
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
const fieldLabels = { buscar:'Búsqueda',materiales_estado:'Declaración de materiales',otros_estado:'Declaración de otros gastos',materiales_justificacion:'Justificación de materiales',otros_justificacion:'Justificación de otros gastos',justificacion:'Justificación',costo_unitario_neto:'Costo unitario neto',fecha_gasto:'Fecha del gasto',fecha_devolucion:'Fecha de devolución',descripcion: 'Descripción', nombre: 'Nombre', motivo: 'Motivo', presupuesto: 'Presupuesto', categoria_servicio: 'Categoría', tecnico: 'Técnico', tecnico_responsable: 'Responsable', fecha_programada: 'Fecha programada' };
const pendingLabels={responsable_no_elegible:'Verifica que el responsable esté activo y sea elegible.',responsable_sin_membresia:'El responsable debe ser participante activo.',sin_turno_acreditado:'Debe existir al menos un turno cerrado y validado.',turnos_sin_acreditar:'Hay turnos que todavía no se han acreditado.',turno_inconsistente:'Revisa la coherencia de los turnos.',turnos_abiertos:'Hay turnos abiertos.',turnos_pendientes_revision:'Hay turnos pendientes de revisión.',turnos_observados:'Hay turnos observados pendientes de subsanación.',turnos_sin_tarifa:'Falta valorar la mano de obra de uno o más turnos.',duracion_administrativa_sin_verificar:'Falta verificar la duración de un turno cerrado administrativamente.',ejecutor_inconsistente:'Revisa los participantes asociados a los turnos.',duracion_inconsistente:'Revisa las duraciones registradas.',evidencia_inconsistente:'Hay evidencias que requieren revisión.',gasto_inconsistente:'Revisa la coherencia de los gastos.',materiales_sin_declarar_o_incoherente:'Revisa la declaración de materiales y sus registros.',otros_sin_declarar_o_incoherente:'Revisa la declaración de otros gastos y sus registros.',costo_total_no_positivo:'El costo real total debe ser mayor que cero.',control_inexistente:'Falta el control de costos.',validacion_obsoleta_o_ausente:'La validación no está vigente.'};
export function OperationalErrors({ error }) {
  if (!error) return null;
  return <div className="alert alert-warning commercial-feedback" role="alert">
    <p>{error.message || 'Revisa los datos.'}</p>
    {error.code === 'sin_cambios' && <p>No hay un cambio aplicable. Consulta el estado actual.</p>}
    {error.code === 'presupuesto_utilizado' && <p>El presupuesto ya tiene una Obra asociada.</p>}
    {error.code === 'devolucion_pendiente' && <p>Coordina la recepción física con Bodega. Después actualiza los requisitos y, si cambió el costo, valida nuevamente antes de finalizar.</p>}
    {error.code === 'confirmacion_remanente_requerida' && <p>Actualiza la lista de despachos pendientes. Revisa las cantidades actuales y confirma otra vez cuáles quedarán inhabilitadas.</p>}
    {error.code === 'version_costos_obsoleta' && <p>Los costos cambiaron. Actualiza el resumen y los requisitos, revisa los nuevos datos y confirma otra vez.</p>}
    {!!error.fieldErrors?.materiales?.length&&<p>Solicita a Bodega revisar la actividad o la unidad del material indicado antes de volver a iniciar.</p>}
    {Object.entries(error.fieldErrors || {}).filter(([field])=>field!=='pendientes').map(([field, values]) => <p key={field}>{fieldLabels[field] || ({materiales:'Materiales previstos',version_costos_esperada:'Revisión económica',detail:'Detalle',non_field_errors:'Detalle'})[field] || field}: {values.join(' ')}</p>)}
    {!!error.fieldErrors?.pendientes?.some(key=>pendingLabels[key])&&<div><strong>Requisitos pendientes</strong><ul>{error.fieldErrors.pendientes.filter(key=>pendingLabels[key]).map(key=><li key={key}>{pendingLabels[key]}</li>)}</ul></div>}
    {error.retryAfter && <p>Espera indicada por el servidor: {error.retryAfter}.</p>}
  </div>;
}
export function Feedback({ api }) {
  return <><OperationalErrors error={api.error} />
    {api.locked && <p className="alert alert-warning" role="status">Falta confirmar el resultado. Actualiza los datos antes de realizar otra operación.</p>}
    {api.loading && <p className="commercial-loading" role="status">Cargando datos…</p>}
  </>;
}
export function Field({ name, label, value, onChange, error, type = 'text', options, disabled, maxLength, required = false, inputMode, placeholder }) {
  const props = { id: `obras-${name}`, value: value ?? '', disabled, required, 'aria-invalid': !!error, 'aria-describedby': error ? `obras-${name}-error` : undefined, onChange: (e) => onChange(e.target.value) };
  return <div className="obras-field"><label className="form-label" htmlFor={props.id}>{label}</label>
    {options ? <select {...props} className={`form-select${error ? ' is-invalid' : ''}`}>{options.map(([key, text]) => <option key={key} value={key}>{text}</option>)}</select>
      : type === 'textarea' ? <textarea {...props} rows={3} placeholder={placeholder} maxLength={maxLength} className={`form-control${error ? ' is-invalid' : ''}`} />
        : <input {...props} type={type} inputMode={inputMode} placeholder={placeholder} maxLength={maxLength} className={`form-control${error ? ' is-invalid' : ''}`} />}
    {error && <div id={`obras-${name}-error`} className="invalid-feedback">{error}</div>}
  </div>;
}
export function focusError(event, errors) {
  const name = Object.keys(errors)[0];
  if (name) event.currentTarget?.querySelector(`#obras-${name}`)?.focus();
}
export function PagedSelect({ name, label, path, value, onChange, disabled, activeOnly = false, selectedLabel, error, required = false, refreshKey = 0 }) {
  const api = useOperational(),{user}=useAuth();
  const supervisor=user.role==='SUPERVISOR_OBRAS';
  const [page, setPage] = useState(1), [data, setData] = useState(null), [chosen, setChosen] = useState(null);
  const filters = activeOnly ? { activo: 'true' } : {};
  const read = () => api.load('choices', collectionPath(path, page, filters), (result) => setData(readPage(result, path)));
  useEffect(() => { setData(null); void read(); }, [path, page, activeOnly, refreshKey]);
  const optionText = (row) => row.codigo ? `${row.codigo} · ${row.cliente_nombre}${supervisor?'':' · #'+row.id}` : `${row.nombre}${supervisor?'':' · #'+row.id}`;
  const options = [['', 'Selecciona una opción'], ...(data?.results || []).map((row) => [String(row.id), optionText(row)])];
  if (value && !options.some(([id]) => id === String(value))) options.push([String(value), chosen?.id === Number(value) ? optionText(chosen) : selectedLabel || `Seleccionado #${value}`]);
  return <div className="obras-selector">
    <Field name={name} label={label} value={value} disabled={disabled || api.loading} error={error} required={required} options={options} onChange={(next) => {
      setChosen(data?.results.find((row) => row.id === Number(next)) || null); onChange(next);
    }} />
    <OperationalErrors error={api.error} />
    {api.error && <button type="button" className="btn btn-outline-secondary btn-sm" disabled={api.loading} onClick={read}>Reconsultar {label.toLowerCase()}</button>}
    {api.error?.status === 404 && page > 1 && <button type="button" className="btn btn-outline-secondary btn-sm" onClick={() => setPage(1)}>Primera página de {label.toLowerCase()}</button>}
    {data && (!supervisor||data.next||data.previous) && <Pager label={`Páginas de ${label.toLowerCase()}`} data={data} page={page} setPage={setPage} disabled={disabled || api.loading} />}
    {data && !data.count && <p className="commercial-help">No hay opciones disponibles.</p>}
  </div>;
}
const eventKeys = { estado: 'Estado', categoria_servicio: 'Categoría (ID)', presupuesto: 'Presupuesto (ID)', descripcion: 'Descripción', tecnico_responsable: 'Responsable (ID)', fecha_programada: 'Fecha programada', iniciado_en: 'Inicio', finalizado_en: 'Finalización', nombre: 'Nombre', activo: 'Activo', tecnico: 'Técnico (ID)', asignado_por: 'Asignado por', asignado_en: 'Asignación', motivo_asignacion: 'Motivo de asignación', desasignado_por: 'Desasignado por', desasignado_en: 'Desasignación', motivo_desasignacion: 'Motivo de desasignación', origen_registro: 'Origen' };
const eventLabels={CREACION:'Creación',EDICION:'Edición de ficha',CAMBIO_ESTADO:'Cambio de estado',CAMBIO_TECNICO:'Cambio de responsable',ASIGNACION:'Asignación de participante',DESASIGNACION:'Desasignación de participante',REACTIVACION:'Reactivación de participante',RENOMBRE:'Renombre de categoría',ACTIVACION:'Activación',DESACTIVACION:'Desactivación'};
function eventValue(key,value){
 if(value===null||value===undefined||value==='')return 'No registrado';
 if(typeof value==='boolean')return value?'Sí':'No';
 if(key==='estado')return OBRA_STATES[value]?.[0]||String(value);
 if(key==='fecha_programada')return formatCivilDate(value);
 if(['iniciado_en','finalizado_en','asignado_en','desasignado_en'].includes(key))return timestamp(value);
 if(key==='origen_registro')return ({OPERACION:'Asignación operativa',MIGRACION_004B:'Registro histórico'})[value]||String(value);
 return String(value);
}
export function EventList({ data, title, supervisor=false }) {
  if(supervisor)return <section className="card-fyag so-panel so-event-panel"><h3>{title}</h3>
    {data&&!data.results.length&&<div className="so-empty" role="status"><TecIcon name="inbox"/><strong>Sin eventos registrados</strong><p>Los cambios realizados en esta sección aparecerán aquí.</p></div>}
    <ol className="commercial-timeline">{data?.results.map(event=>{
      const before=event.datos_anteriores||{},after=event.datos_nuevos||{};
      const entries=Object.entries(eventKeys).filter(([key])=>Object.hasOwn(before,key)||Object.hasOwn(after,key));
      const changed=entries.filter(([key])=>JSON.stringify(before[key]??null)!==JSON.stringify(after[key]??null));
      return <li key={event.id}><strong>{eventLabels[event.tipo]||event.tipo.replaceAll('_',' ')}{event.participante?' · Miembro #'+event.participante:''}</strong>
      {event.estado_nuevo&&<div>{event.estado_anterior&&<><ObraStatus state={event.estado_anterior}/> → </>}<ObraStatus state={event.estado_nuevo}/></div>}
      <p className="commercial-help">{timestamp(event.creado_en)} · Usuario #{event.registrado_por}</p>{event.motivo&&<p className="commercial-long-text">{event.motivo}</p>}
      {entries.length>0&&<details className="so-history"><summary>{changed.length?changed.length+' campos modificados':'Valores registrados'} · Ver comparación</summary><dl className="obras-event-changes">{entries.map(([key,label])=><div key={key}><dt>{label}</dt><dd><span className="so-event-previous">{eventValue(key,before[key])}</span> → <span className="so-event-new">{eventValue(key,after[key])}</span></dd></div>)}</dl></details>}</li>;
    })}</ol>
  </section>;
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
