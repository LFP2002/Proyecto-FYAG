import React, { useEffect, useMemo, useRef, useState } from 'react';
import { useAuth } from '../auth/AuthContext.jsx';
import { PageHead } from '../components/ui';
import { useApi } from '../integrations/useApi.js';
import { AUDIT_MODULES as ROLES, AUDIT_SOURCES as SOURCES, auditSources, validAuditRange } from '../integrations/audit.js';

import { formatCompactCLP, formatCivilDate } from '../utils/format.js';

const INITIAL = {modulo:'',fuente:'',tipo:'',actor:'',recurso_tipo:'',recurso_id:'',desde:'',hasta:'',limit:'25'};
const LABELS = {COMERCIAL:'Comercial',OBRAS:'Obras',FINANZAS:'Finanzas',USUARIOS:'Usuarios',PRESUPUESTO_EVENTO:'Presupuestos',OBRA_EVENTO:'Obras',PARTICIPANTE_EVENTO:'Participantes',CATEGORIA_SERVICIO_EVENTO:'Categorías de servicio',TURNO_EVENTO:'Turnos',COSTO_OBRA_EVENTO:'Costos de obra',FINANZAS_EVENTO:'Documentos y pagos',USUARIO_EVENTO:'Usuarios',CREACION:'Creación',EDICION:'Edición',CAMBIO_TECNICO:'Cambio de técnico',ASIGNACION:'Asignación',DESASIGNACION:'Desasignación',REACTIVACION:'Reactivación',ACTIVACION:'Activación',DESACTIVACION:'Desactivación',OBSERVACION:'Observación',SUBSANACION:'Subsanación',VALIDACION:'Validación',CORRECCION:'Corrección',DEVOLUCION:'Devolución',ANULACION:'Anulación',DECLARACION:'Declaración',CORTESIA:'Cortesía',CATEGORIA_SERVICIO:'Categoría de servicio',CONTROL_COSTOS:'Control de costos',CIERRE_SIN_COBRO:'Cierre sin cobro',REEMISION:'Reemisión de credencial',CREACION_CREDENCIAL_TEMPORAL:'Emisión inicial temporal',ESTABLECER_CLAVE:'Establecimiento de contraseña',CAMBIO_CLAVE_PROPIA:'Cambio propio de contraseña',CAMBIO_INICIAL:'Confirmación de contraseña personal',TECNICO:'Técnico',ADMINISTRATIVO_FINANZAS:'Administración y Finanzas',SUPERVISOR_OBRAS:'Supervisión de obras',ADMINISTRADOR_TI:'Administración TI',GERENCIA:'Gerencia',BODEGUERO:'Bodeguero',FACTURA_AFECTA:'Factura afecta',FACTURA_EXENTA:'Factura exenta'};
const FIELDS = {tecnico:'Técnico',tecnico_responsable:'Técnico responsable',categoria_servicio:'Categoría de servicio',descripcion_trabajo:'Descripción del trabajo',referencia_rectificacion_externa:'Referencia de rectificación externa',motivo_reversion:'Motivo de reversión',monto_neto:'Monto neto (CLP)',monto_impuesto:'Impuesto (CLP)',monto_total:'Monto total (CLP)',monto:'Monto (CLP)',costo_hora_neto:'Costo por hora neto (CLP)',costo_unitario_neto:'Costo unitario neto (CLP)',duracion_segundos:'Duración (segundos)',duracion_ajustada_segundos:'Duración ajustada (segundos)'};
const MONEY = new Set(['monto','monto_neto','monto_impuesto','monto_total','costo_hora_neto','costo_unitario_neto']);
const ENUM = new Set(['estado','estado_revision','tipo','tipo_documento','rol','role','modo_cierre','origen_registro','materiales_estado','otros_estado','medio']);
const pretty = v => (Object.hasOwn(LABELS,v)?LABELS[v]:null) || (typeof v==='string'&&v ? v.charAt(0).toUpperCase()+v.slice(1).toLowerCase().replaceAll('_',' ') : '—');
const stamp = v => typeof v==='string'&&Number.isFinite(Date.parse(v)) ? new Intl.DateTimeFormat('es-CL',{timeZone:'America/Santiago',day:'2-digit',month:'2-digit',year:'numeric',hour:'2-digit',minute:'2-digit',second:'2-digit',hour12:false}).format(new Date(v)).replaceAll('-','/') : v;
function display(key,value){
 if(value===null)return 'Sin valor';
 if(value==='')return 'Vacío';
 if(typeof value==='boolean')return value?'Sí':'No';
 if(MONEY.has(key)&&typeof value==='string'&&/^-?\d+(?:\.\d{1,2})?$/.test(value))return formatCompactCLP(value);
 if(typeof value==='string'&&(key.endsWith('_en')||key.startsWith('fecha_'))){
  if(/^\d{4}-\d{2}-\d{2}$/.test(value))return formatCivilDate(value);
  if(/^\d{4}-\d{2}-\d{2}T/.test(value))return stamp(value);
 }
 if(ENUM.has(key)&&typeof value==='string'&&/^[A-Z_]+$/.test(value))return pretty(value);
 return typeof value==='object'?JSON.stringify(value):String(value);
}
const TYPES = {
 PRESUPUESTO_EVENTO:['CREACION','CAMBIO_ESTADO'], OBRA_EVENTO:['CREACION','CAMBIO_ESTADO','CAMBIO_TECNICO','EDICION'],
 PARTICIPANTE_EVENTO:['ASIGNACION','DESASIGNACION','REACTIVACION'], CATEGORIA_SERVICIO_EVENTO:['CREACION','EDICION','ACTIVACION','DESACTIVACION'],
 TURNO_EVENTO:['INICIO','CIERRE','CIERRE_ADMINISTRATIVO','OBSERVACION','SUBSANACION','VALIDACION','CORRECCION'],
 COSTO_OBRA_EVENTO:['ALTA','CORRECCION','DEVOLUCION','ANULACION','DECLARACION','VALIDACION','CORTESIA'],
 FINANZAS_EVENTO:['DOCUMENTO_REGISTRADO','DOCUMENTO_REVERTIDO','SIN_COBRO_REGISTRADO','PAGO_REGISTRADO','PAGO_ANULADO'],
 USUARIO_EVENTO:['CREACION','EDICION','ACTIVACION','DESACTIVACION','CAMBIO_ROL','ESTABLECER_CLAVE','CAMBIO_CLAVE_PROPIA','REEMISION','CAMBIO_INICIAL']
};
function Icon({name}){
 const icons={filter:'M6 11.5a.5.5 0 0 1 .5-.5h3a.5.5 0 0 1 0 1h-3a.5.5 0 0 1-.5-.5m-2-4a.5.5 0 0 1 .5-.5h7a.5.5 0 0 1 0 1h-7a.5.5 0 0 1-.5-.5m-2-4a.5.5 0 0 1 .5-.5h11a.5.5 0 0 1 0 1h-11a.5.5 0 0 1-.5-.5',back:'M15 8a.5.5 0 0 0-.5-.5H2.707l3.647-3.646a.5.5 0 1 0-.708-.708l-4.5 4.5a.5.5 0 0 0 0 .708l4.5 4.5a.5.5 0 1 0 .708-.708L2.707 8.5H14.5A.5.5 0 0 0 15 8',refresh:'M8 3a5 5 0 1 1-4.546 2.914.5.5 0 0 0-.908-.417A6 6 0 1 0 8 2zM8 4.466V.534a.25.25 0 0 0-.41-.192L5.23 2.308a.25.25 0 0 0 0 .384l2.36 1.966A.25.25 0 0 0 8 4.466',chevron:'M6.646 1.646a.5.5 0 0 1 .708 0l6 6a.5.5 0 0 1 0 .708l-6 6a.5.5 0 0 1-.708-.708L12.293 8 6.646 2.354a.5.5 0 0 1 0-.708'};
 return <svg width="16" height="16" viewBox="0 0 16 16" fill="currentColor" aria-hidden="true"><path fillRule="evenodd" d={icons[name]}/></svg>;
}
function EventDetail({event,onBack}){
 const heading=useRef(null);
 useEffect(()=>{heading.current?.focus();},[]);
 const keys=[...new Set([...Object.keys(event.datos_anteriores),...Object.keys(event.datos_nuevos)])];
 const cell=(obj,key)=>Object.hasOwn(obj,key)?<span title={typeof obj[key]==='string'?obj[key]:undefined}>{display(key,obj[key])}</span>:<span className="audit-not-recorded">No registrado</span>;
 return <div className="audit-detail">
 <button type="button" className="audit-back" onClick={onBack}><Icon name="back"/>Volver al historial</button>
 <h1 tabIndex={-1} ref={heading}>{pretty(event.tipo)}</h1>
 <p className="commercial-help">{pretty(event.modulo)} · {pretty(event.recurso_tipo)} #{event.recurso_id}</p>
 <section className="card-fyag audit-detail-card"><h2>Información del evento</h2><dl className="audit-facts"><div><dt>Fecha y hora</dt><dd title={event.creado_en}>{stamp(event.creado_en)}</dd></div><div><dt>Registrado por</dt><dd>{event.actor_etiqueta||'Usuario #'+event.actor}</dd></div><div><dt>Origen</dt><dd>{pretty(event.fuente)}</dd></div><div><dt>Referencia del evento</dt><dd>#{event.evento_id}</dd></div></dl>{event.motivo&&<div className="audit-reason"><h3>Motivo</h3><p>{event.motivo}</p></div>}</section>
 <section className="card-fyag audit-detail-card"><h2>Valores registrados</h2>{keys.length?<div className="table-responsive" role="region" aria-label="Comparación de valores" tabIndex={0}><table className="table commercial-table audit-comparison"><thead><tr><th scope="col">Campo</th><th scope="col">Anterior</th><th scope="col">Nuevo</th></tr></thead><tbody>{keys.map(key=>{const changed=Object.hasOwn(event.datos_anteriores,key)&&Object.hasOwn(event.datos_nuevos,key)&&JSON.stringify(event.datos_anteriores[key])!==JSON.stringify(event.datos_nuevos[key]);return <tr key={key} className={changed?'audit-changed':undefined}><th scope="row">{(Object.hasOwn(FIELDS,key)?FIELDS[key]:pretty(key.toUpperCase()))}</th><td>{cell(event.datos_anteriores,key)}</td><td>{cell(event.datos_nuevos,key)}</td></tr>;})}</tbody></table></div>:<p className="auditoria-empty">No hay valores registrados para este evento.</p>}</section></div>;
}
const RESOURCE_TYPES = ['PRESUPUESTO','OBRA','PARTICIPANTE','CATEGORIA_SERVICIO','TURNO','GASTO','CONTROL_COSTOS','CORTESIA','DOCUMENTO','CIERRE_SIN_COBRO','PAGO','USUARIO'];
function validEvent(event) {
  const keys = ['id','evento_id','fuente','modulo','recurso_tipo','recurso_id','tipo','actor','actor_etiqueta','motivo','creado_en','datos_anteriores','datos_nuevos'];
  if (!event || Object.keys(event).some((key) => !keys.includes(key)) || keys.some((key) => !Object.hasOwn(event,key))
      || typeof event.id !== 'string' || !Number.isSafeInteger(event.evento_id) || !Number.isSafeInteger(event.actor) || !Number.isSafeInteger(event.recurso_id)
      || !SOURCES.includes(event.fuente) || typeof event.modulo !== 'string' || typeof event.recurso_tipo !== 'string' || typeof event.tipo !== 'string'
      || (event.actor_etiqueta !== null && typeof event.actor_etiqueta !== 'string') || typeof event.motivo !== 'string' || typeof event.creado_en !== 'string'
      || !event.datos_anteriores || !event.datos_nuevos || typeof event.datos_anteriores !== 'object' || typeof event.datos_nuevos !== 'object') throw new Error('Evento de auditoría inválido.');
  return event;
}
function query(filters) { const p = new URLSearchParams(); for (const [key,value] of Object.entries(filters)) if (value !== '' && !(key==='limit'&&value==='25')) p.set(key,value); return p.size ? `?${p}` : ''; }
export default function Auditoria() {
  const { user } = useAuth();
  return <AuditScreen key={`${user.id}:${user.role}`} />;
}
function AuditScreen() {
  const { user } = useAuth(), api = useApi();
  const [filters,setFilters] = useState(INITIAL);
  const [draft,setDraft] = useState(filters), [data,setData] = useState(null), [cursor,setCursor] = useState(null), [cursorStack,setCursorStack] = useState([]), [validation,setValidation] = useState('');
  const [revision, setRevision] = useState(0),[open,setOpen]=useState(false),[selected,setSelected]=useState(null);
  const listButton=useRef(null),restoreFocus=useRef(false);
  useEffect(()=>{if(!selected&&restoreFocus.current){restoreFocus.current=false;listButton.current?.focus();}},[selected]);
  const allowed = ROLES[user.role] || [];
  const filteredSources = useMemo(() => auditSources(user.role, draft.modulo), [draft.modulo,user.role]);
  const path = `/api/auditoria/eventos/${cursor ? `?cursor=${encodeURIComponent(cursor)}` : query(filters)}`;
  const types=[...new Set((draft.fuente?[draft.fuente]:filteredSources).flatMap(source=>TYPES[source]||[]))].sort((a,b)=>pretty(a).localeCompare(pretty(b),'es'));
  function changeDraft(key,value) { setValidation('');setDraft((old)=>({...old,[key]:value,...(key==='modulo'?{fuente:'',tipo:''}:key==='fuente'?{tipo:''}:{})})); }
  function clear(){api.cancelRead('audit');api.setError(null);setData(null);setSelected(null);setDraft(INITIAL);setFilters(INITIAL);setValidation('');setCursor(null);setCursorStack([]);setRevision(v=>v+1);}
  function refresh() { api.cancelRead('audit');api.setError(null);setData(null);setSelected(null);setDraft(filters);setValidation('');setCursor(null);setCursorStack([]);setRevision((v)=>v+1); }
  async function load(nextPath = path) {
    setData(null);
    return api.load('audit',nextPath,(value)=>{
      if (!value || Object.keys(value).some((key)=>!['results','next_cursor','has_more','fecha_corte','zona_horaria'].includes(key)) || !Array.isArray(value.results)
        || typeof value.has_more!=='boolean' || (value.next_cursor!==null&&typeof value.next_cursor!=='string') || value.zona_horaria!=='America/Santiago' || typeof value.fecha_corte!=='string') throw new Error('Respuesta de auditoría inválida.');
      const results=value.results.map(validEvent); if(results.length>Number(filters.limit) || results.some((event)=>!auditSources(user.role,filters.modulo).includes(event.fuente))) throw new Error('Página de auditoría inválida.'); setData({...value,results});
    });
  }
  useEffect(()=>{ if(allowed.length) void load(path); },[path,revision,user?.id,user?.role]);
  useEffect(()=>{ if(filters.modulo && !allowed.includes(filters.modulo)){setFilters((p)=>({...p,modulo:'',fuente:''}));setDraft((p)=>({...p,modulo:'',fuente:''}));} },[user?.role]);
  function apply(event){event.preventDefault();const f={...draft};for(const key of Object.keys(f))f[key]=f[key].trim();if(!validAuditRange(f) || (!!f.recurso_id&&!f.recurso_tipo) || (f.actor&&!/^[1-9][0-9]{0,18}$/.test(f.actor)) || (f.recurso_id&&!/^[1-9][0-9]{0,18}$/.test(f.recurso_id))){setValidation('Revisa filtros, IDs positivos y un rango civil válido de hasta 366 días.');return;} if(f.modulo&&!allowed.includes(f.modulo))return;if(f.fuente&&!filteredSources.includes(f.fuente))return;api.cancelRead('audit');setData(null);setValidation('');setCursor(null);setCursorStack([]);setFilters(f);setSelected(null);setOpen(false);setRevision((v)=>v+1);}
  if(!allowed.length)return <section><PageHead title="Auditoría"/><p role="alert">No tienes acceso a la auditoría global.</p></section>;
  const detail=data?.results.find(event=>event.id===selected);
  if(detail)return <section className="commercial-page auditoria-page"><EventDetail event={detail} onBack={()=>{restoreFocus.current=true;setSelected(null);}}/></section>;
  return <section className="commercial-page auditoria-page"><PageHead title="Auditoría global" sub="Consulta el historial de cambios del sistema."><button type="button" className="btn btn-outline-secondary audit-icon-button" disabled={api.loading} onClick={refresh}><Icon name="refresh"/>Actualizar</button></PageHead>
  <section className="card-fyag audit-filter-card"><div className="audit-list-head"><div><h2>Consulta de eventos</h2><span className="commercial-help">{Object.entries(filters).filter(([k,val])=>k!=='limit'&&val).length?'Filtros aplicados':'Últimos 30 días'}</span></div><button ref={listButton} type="button" className="btn btn-outline-secondary audit-icon-button" aria-expanded={open} aria-controls="audit-filters" onClick={()=>setOpen(x=>!x)}><Icon name="filter"/>Filtros</button></div>
  {Object.entries(filters).some(([k,val])=>val&&(k!=='limit'||val!=='25'))&&<div className="audit-applied"><span>{Object.entries(filters).filter(([k,val])=>val&&(k!=='limit'||val!=='25')).map(([k,val])=>({modulo:'Módulo',fuente:'Fuente',tipo:'Evento',actor:'Usuario ID',recurso_tipo:'Recurso',recurso_id:'Recurso ID',desde:'Desde',hasta:'Hasta',limit:'Por página'})[k]+': '+(['desde','hasta'].includes(k)?formatCivilDate(val):['modulo','fuente','tipo','recurso_tipo'].includes(k)?pretty(val):val)).join(' · ')}</span><button type="button" className="btn btn-outline-secondary btn-sm" disabled={api.loading} onClick={clear}>Quitar filtros</button></div>}
  <form id="audit-filters" className="commercial-form auditoria-form" hidden={!open} onSubmit={apply}><fieldset className="auditoria-group"><legend>Qué buscar</legend><div className="auditoria-grid">
    <label className="form-label">Módulo<select className="form-select" value={draft.modulo} onChange={(e)=>changeDraft('modulo',e.target.value)}><option value="">Todos</option>{allowed.map((m)=><option key={m} value={m}>{pretty(m)}</option>)}</select></label>
    <label className="form-label">Fuente<select className="form-select" value={draft.fuente} onChange={(e)=>changeDraft('fuente',e.target.value)}><option value="">Todas</option>{filteredSources.map((s)=><option key={s} value={s}>{pretty(s)}</option>)}</select></label>
    <label className="form-label">Tipo<select className="form-select" value={draft.tipo} onChange={(e)=>changeDraft('tipo',e.target.value)}><option value="">Todos los eventos</option>{types.map(type=><option key={type} value={type}>{pretty(type)}</option>)}</select></label>
  </div></fieldset>
  <fieldset className="auditoria-group"><legend>Quién y sobre qué</legend><div className="auditoria-grid">
    <label className="form-label">Actor ID<input className="form-control" inputMode="numeric" placeholder="Ej.: 1" value={draft.actor} onChange={(e)=>changeDraft('actor',e.target.value)}/></label>
    <label className="form-label">Tipo de recurso<select className="form-select" value={draft.recurso_tipo} onChange={(e)=>changeDraft('recurso_tipo',e.target.value)}><option value="">Todos</option>{RESOURCE_TYPES.map((t)=><option key={t} value={t}>{pretty(t)}</option>)}</select></label>
    <label className="form-label">Recurso ID<input className="form-control" inputMode="numeric" placeholder="Ej.: 12" value={draft.recurso_id} onChange={(e)=>changeDraft('recurso_id',e.target.value)}/></label>
  </div></fieldset>
  <fieldset className="auditoria-group"><legend>Cuándo y cuántos</legend><div className="auditoria-grid">
    <label className="form-label">Desde<input className="form-control" type="date" value={draft.desde} onChange={(e)=>changeDraft('desde',e.target.value)}/></label><label className="form-label">Hasta<input className="form-control" type="date" value={draft.hasta} onChange={(e)=>changeDraft('hasta',e.target.value)}/></label>
    <label className="form-label">Eventos por página<select className="form-select" value={draft.limit} onChange={(e)=>changeDraft('limit',e.target.value)}>{[10,25,50].map((n)=><option key={n}>{n}</option>)}</select></label>
  </div></fieldset><div className="auditoria-actions"><button className="btn btn-fyag-primary" type="submit" disabled={api.loading}>Aplicar filtros</button><button className="btn btn-outline-secondary" type="button" disabled={api.loading} onClick={clear}>Limpiar filtros</button></div></form></section>
  {validation&&<p className="alert alert-warning" role="alert">{validation}</p>}{api.error&&<p className="alert alert-warning" role="alert">{api.error.status===403?'Acceso denegado para este filtro.':api.error.status===400?'Cursor o filtros inválidos; inicia una consulta nueva.':api.error.message}</p>}{api.loading&&<p role="status">Consultando eventos…</p>}
  {data&&<section className="card-fyag audit-results"><div className="audit-list-head"><div><h2>Historial de eventos</h2><span className="commercial-help">{data.results.length} eventos en esta página · Actualizado: {stamp(data.fecha_corte)}</span></div></div>
  {data.results.length?<div className="table-responsive" role="region" aria-label="Eventos de auditoría" tabIndex={0}><table className="table table-hover align-middle commercial-table"><thead><tr>{['Fecha y hora','Actor','Evento','Recurso','Detalle'].map(v=><th scope="col" key={v}>{v}</th>)}</tr></thead><tbody>{data.results.map(event=><tr key={event.id}><td><time dateTime={event.creado_en} title={event.creado_en}>{stamp(event.creado_en)}</time></td><td>{event.actor_etiqueta||'Usuario #'+event.actor}</td><td><strong>{pretty(event.tipo)}</strong><span className="audit-secondary">{pretty(event.modulo)}</span></td><td>{pretty(event.recurso_tipo)} #{event.recurso_id}</td><td><button type="button" className="audit-detail-link" aria-label={'Ver detalle de '+pretty(event.tipo)+' '+pretty(event.recurso_tipo)+' #'+event.recurso_id} onClick={()=>setSelected(event.id)}>Ver detalle<Icon name="chevron"/></button></td></tr>)}</tbody></table></div>:<p className="auditoria-empty">No hay eventos para estos filtros.</p>}
    {(data.has_more||cursorStack.length>0)&&    <nav className="commercial-pager" aria-label="Paginación de auditoría"><button type="button" className="btn btn-outline-secondary btn-sm" disabled={!cursorStack.length||api.loading} onClick={()=>{setData(null);const stack=[...cursorStack];const prev=stack.pop();setCursorStack(stack);setCursor(prev);}}>Anterior</button><span>{data.results.length} eventos · límite {filters.limit}</span><button type="button" className="btn btn-outline-secondary btn-sm" disabled={!data.has_more||!data.next_cursor||api.loading} onClick={()=>{setData(null);setCursorStack([...cursorStack,cursor]);setCursor(data.next_cursor);}}>Siguiente</button></nav>}</section>}
  </section>;
}
