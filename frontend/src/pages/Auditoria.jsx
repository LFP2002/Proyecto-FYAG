import React, { useEffect, useMemo, useState } from 'react';
import { useAuth } from '../auth/AuthContext.jsx';
import { PageHead } from '../components/ui';
import { useApi } from '../integrations/useApi.js';
import { AUDIT_MODULES as ROLES, AUDIT_SOURCES as SOURCES, auditSources, validAuditRange } from '../integrations/audit.js';

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
  const [filters,setFilters] = useState({modulo:'',fuente:'',tipo:'',actor:'',recurso_tipo:'',recurso_id:'',desde:'',hasta:'',limit:'25'});
  const [draft,setDraft] = useState(filters), [data,setData] = useState(null), [cursor,setCursor] = useState(null), [cursorStack,setCursorStack] = useState([]), [validation,setValidation] = useState('');
  const [revision, setRevision] = useState(0);
  const allowed = ROLES[user.role] || [];
  const filteredSources = useMemo(() => auditSources(user.role, draft.modulo), [draft.modulo,user.role]);
  const path = `/api/auditoria/eventos/${cursor ? `?cursor=${encodeURIComponent(cursor)}` : query(filters)}`;
  function changeDraft(key,value) { api.cancelRead('audit');setData(null);setValidation('');setDraft((old)=>({...old,[key]:value,...(key==='modulo'?{fuente:''}:{})})); }
  function refresh() { api.cancelRead('audit');api.setError(null);setData(null);setDraft(filters);setCursor(null);setCursorStack([]);setRevision((v)=>v+1); }
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
  function apply(event){event.preventDefault();const f={...draft};for(const key of Object.keys(f))f[key]=f[key].trim();if(!validAuditRange(f) || (!!f.recurso_id&&!f.recurso_tipo) || (f.actor&&!/^[1-9][0-9]{0,18}$/.test(f.actor)) || (f.recurso_id&&!/^[1-9][0-9]{0,18}$/.test(f.recurso_id))){setValidation('Revisa filtros, IDs positivos y un rango civil válido de hasta 366 días.');return;} if(f.modulo&&!allowed.includes(f.modulo))return;if(f.fuente&&!filteredSources.includes(f.fuente))return;api.cancelRead('audit');setData(null);setValidation('');setCursor(null);setCursorStack([]);setFilters(f);setRevision((v)=>v+1);}
  if(!allowed.length)return <section><PageHead title="Auditoría"/><p role="alert">No tienes acceso a la auditoría global.</p></section>;
  return <section className="commercial-page"><PageHead title="Auditoría global"/><form className="card-fyag commercial-form mb-3" onSubmit={apply}><div className="obras-form-grid">
    <label className="form-label">Módulo<select className="form-select" value={draft.modulo} onChange={(e)=>changeDraft('modulo',e.target.value)}><option value="">Todos los permitidos</option>{allowed.map((m)=><option key={m}>{m}</option>)}</select></label>
    <label className="form-label">Fuente<select className="form-select" value={draft.fuente} onChange={(e)=>changeDraft('fuente',e.target.value)}><option value="">Todas las permitidas</option>{filteredSources.map((s)=><option key={s}>{s}</option>)}</select></label>
    <label className="form-label">Tipo<input className="form-control" maxLength={24} value={draft.tipo} onChange={(e)=>changeDraft('tipo',e.target.value)}/></label>
    <label className="form-label">Actor ID<input className="form-control" inputMode="numeric" value={draft.actor} onChange={(e)=>changeDraft('actor',e.target.value)}/></label>
    <label className="form-label">Tipo de recurso<select className="form-select" value={draft.recurso_tipo} onChange={(e)=>changeDraft('recurso_tipo',e.target.value)}><option value="">Todos</option>{RESOURCE_TYPES.map((t)=><option key={t}>{t}</option>)}</select></label>
    <label className="form-label">Recurso ID<input className="form-control" inputMode="numeric" value={draft.recurso_id} onChange={(e)=>changeDraft('recurso_id',e.target.value)}/></label>
    <label className="form-label">Desde<input className="form-control" type="date" value={draft.desde} onChange={(e)=>changeDraft('desde',e.target.value)}/></label><label className="form-label">Hasta<input className="form-control" type="date" value={draft.hasta} onChange={(e)=>changeDraft('hasta',e.target.value)}/></label>
    <label className="form-label">Eventos por página<select className="form-select" value={draft.limit} onChange={(e)=>changeDraft('limit',e.target.value)}>{[10,25,50].map((n)=><option key={n}>{n}</option>)}</select></label>
  </div><button className="btn btn-fyag-primary mt-2" type="submit" disabled={api.loading}>Aplicar filtros</button><button className="btn btn-outline-secondary mt-2 ms-2" type="button" disabled={api.loading} onClick={refresh}>Actualizar</button></form>
  {validation&&<p className="alert alert-warning" role="alert">{validation}</p>}{api.error&&<p className="alert alert-warning" role="alert">{api.error.status===403?'Acceso denegado para este filtro.':api.error.status===400?'Cursor o filtros inválidos; inicia una consulta nueva.':api.error.message}</p>}{api.loading&&<p role="status">Consultando eventos…</p>}
  {data&&<><p className="commercial-help">Corte {new Date(data.fecha_corte).toLocaleString('es-CL',{timeZone:'America/Santiago'})} · America/Santiago</p>{!data.results.length&&<p>No hay eventos para estos filtros.</p>}
   <div className="table-responsive" role="region" aria-label="Eventos de auditoría" tabIndex={0}><table className="table table-hover align-middle commercial-table"><thead><tr>{['Fecha y hora','Actor','Módulo / tipo','Recurso','Detalle permitido'].map((v)=><th scope="col" key={v}>{v}</th>)}</tr></thead><tbody>{data.results.map((event)=> <tr key={event.id}><td>{new Date(event.creado_en).toLocaleString('es-CL',{timeZone:'America/Santiago'})}</td><td>{event.actor_etiqueta||`Usuario #${event.actor}`}</td><td>{event.modulo} · {event.tipo}</td><td>{event.recurso_tipo} #{event.recurso_id}</td><td><details><summary>Ver detalle</summary><p>{event.motivo||'Sin motivo'}</p><dl>{Object.entries(event.datos_anteriores).map(([key,value])=><div key={`old-${key}`}><dt>{key} anterior</dt><dd>{String(value)}</dd></div>)}{Object.entries(event.datos_nuevos).map(([key,value])=><div key={`new-${key}`}><dt>{key} nuevo</dt><dd>{String(value)}</dd></div>)}</dl></details></td></tr>)}</tbody></table></div>
    <nav className="commercial-pager" aria-label="Paginación de auditoría"><button type="button" className="btn btn-outline-secondary btn-sm" disabled={!cursorStack.length||api.loading} onClick={()=>{setData(null);const stack=[...cursorStack];const prev=stack.pop();setCursorStack(stack);setCursor(prev);}}>Anterior</button><span>{data.results.length} eventos · límite {filters.limit}</span><button type="button" className="btn btn-outline-secondary btn-sm" disabled={!data.has_more||!data.next_cursor||api.loading} onClick={()=>{setData(null);setCursorStack([...cursorStack,cursor]);setCursor(data.next_cursor);}}>Siguiente</button></nav></>}
  </section>;
}
