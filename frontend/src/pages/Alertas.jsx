import React, { useEffect, useMemo, useState } from 'react';
import { useAuth } from '../auth/AuthContext.jsx';
import { PageHead } from '../components/ui';
import { useApi, readPage, strictObject, positiveInteger } from '../integrations/useApi.js';
import { Pager } from '../comercial/ui.jsx';

const RULES = {
  PRESUPUESTO_PENDIENTE_FINANZAS: { responsable:'ADMINISTRATIVO_FINANZAS', lectores:['ADMINISTRATIVO_FINANZAS'], recurso:'PRESUPUESTO', severidad:'MEDIA', label:'Presupuesto pendiente de Finanzas' },
  OBRA_SUSPENDIDA: { responsable:'SUPERVISOR_OBRAS', lectores:['SUPERVISOR_OBRAS','GERENCIA'], recurso:'OBRA', severidad:'ALTA', label:'Obra suspendida' },
  TURNO_PENDIENTE_REVISION: { responsable:'SUPERVISOR_OBRAS', lectores:['SUPERVISOR_OBRAS'], recurso:'TURNO', severidad:'MEDIA', label:'Turno pendiente de revisión' },
  COBRANZA_VENCIDA: { responsable:'ADMINISTRATIVO_FINANZAS', lectores:['ADMINISTRATIVO_FINANZAS','GERENCIA'], recurso:'DOCUMENTO', severidad:'ALTA', label:'Cobranza vencida' },
};
const typesFor = role => Object.keys(RULES).filter(type=>RULES[type].lectores.includes(role));
const STATES = ['PENDIENTE', 'ATENDIDA', 'RESUELTA', 'TODAS'];
const alertKeys = ['id','tipo','estado','severidad','rol_destinatario','rol_responsable','destinatarios','es_legada','generacion','recurso_tipo','recurso_id','recurso_codigo','obra','titulo','descripcion','creado_en','atendida_por','atendida_en','motivo_atencion','resuelta_en','acciones_permitidas'];
function alertRow(row, role) {
  strictObject(row, alertKeys);
  const rule = Object.hasOwn(RULES,row.tipo) ? RULES[row.tipo] : null;
  if (!positiveInteger(row.id) || !positiveInteger(row.recurso_id) || !positiveInteger(row.generacion)
    || !rule || !rule.lectores.includes(role) || row.es_legada !== false
    || !['PENDIENTE','ATENDIDA','RESUELTA'].includes(row.estado) || row.severidad !== rule.severidad
    || row.recurso_tipo !== rule.recurso || row.rol_destinatario !== role || row.rol_responsable !== rule.responsable
    || !Array.isArray(row.destinatarios) || row.destinatarios.length !== rule.lectores.length
    || new Set(row.destinatarios).size !== rule.lectores.length || row.destinatarios.some(r=>!rule.lectores.includes(r))
    || typeof row.titulo !== 'string' || typeof row.descripcion !== 'string' || !Array.isArray(row.acciones_permitidas)
    || row.acciones_permitidas.length > 1 || row.acciones_permitidas.some(action=>action!=='ATENDER')
    || (row.acciones_permitidas.length && (role!==rule.responsable || row.estado!=='PENDIENTE'))) throw new Error('Alerta inválida o no autorizada.');
  if (row.recurso_codigo !== null && typeof row.recurso_codigo !== 'string') throw new Error('Código de recurso inválido.');
  if (row.obra !== null && !positiveInteger(row.obra)) throw new Error('Obra inválida.');
  return row;
}
function safePage(path, page, filters = {}) {
  const query = new URLSearchParams();
  for (const [key, value] of Object.entries(filters)) if (value !== '' && value != null) query.set(key, value);
  if (page > 1) query.set('page', String(page));
  return `${path}${query.size ? `?${query}` : ''}`;
}
function summaryShape(value, role) {
  strictObject(value, ['generado_en','zona_horaria','por_estado','activas','por_tipo','sincronizacion']);
  strictObject(value.por_estado, ['PENDIENTE','ATENDIDA','RESUELTA']);
  strictObject(value.sincronizacion, ['ultima_correcta_en','desactualizada']);
  if (value.zona_horaria !== 'America/Santiago' || !Number.isSafeInteger(value.activas)
      || Object.values(value.por_estado).some((count) => !Number.isSafeInteger(count) || count < 0)
      || typeof value.sincronizacion.desactualizada !== 'boolean' || !value.por_tipo || typeof value.por_tipo !== 'object') throw new Error('Resumen de alertas inválido.');
  const allowed = typesFor(role);
  if (Object.keys(value.por_tipo).some((type) => !allowed.includes(type))) throw new Error('El resumen contiene tipos fuera del rol.');
  for (const item of Object.values(value.por_tipo)) { strictObject(item, ['PENDIENTE','ATENDIDA','RESUELTA']); if (Object.values(item).some((count) => !Number.isSafeInteger(count) || count < 0)) throw new Error('Conteo inválido.'); }
  return value;
}

export default function Alertas() {
  const { user } = useAuth(); const api = useApi();
  const [summary, setSummary] = useState(null), [pageData, setPageData] = useState(null), [page, setPage] = useState(1);
  const [filters, setFilters] = useState({ estado: '', tipo: '', recurso_tipo: '', recurso_id: '', desde: '', hasta: '' });
  const [selected, setSelected] = useState(null), [detail, setDetail] = useState(null), [history, setHistory] = useState(null), [historyPage, setHistoryPage] = useState(1);
  const [reason, setReason] = useState(''), [attending, setAttending] = useState(false);
  const role = user.role, listPath = '/api/alertas/';
  const query = useMemo(() => ({ ...filters, ...(page > 1 ? { page: String(page) } : {}) }), [filters, page]);
  const validDate=(value)=>/^\d{4}-\d{2}-\d{2}$/.test(value)&&!Number.isNaN(Date.parse(`${value}T00:00:00Z`))&&new Date(`${value}T00:00:00Z`).toISOString().slice(0,10)===value;
  const dateRangeInvalid = (!!filters.desde !== !!filters.hasta) || (!!filters.desde && !!filters.hasta && (!validDate(filters.desde)||!validDate(filters.hasta)||filters.desde > filters.hasta));
  const dateRangeTooWide = !dateRangeInvalid&&filters.desde&&filters.hasta&&(Date.parse(`${filters.hasta}T00:00:00Z`)-Date.parse(`${filters.desde}T00:00:00Z`))/86400000>365;
  const idInvalid = !!filters.recurso_id && (!filters.recurso_tipo || !/^[1-9][0-9]{0,18}$/.test(filters.recurso_id));
  const listUrl = useMemo(() => safePage(listPath, page, filters), [page, filters]);
  const historyPath = selected ? `/api/alertas/${selected}/historial/` : '';
  const reloadSummary = () => api.load('summary', '/api/alertas/resumen/', (value) => setSummary(summaryShape(value, role)));
  const reloadList = () => {
    if (dateRangeInvalid || dateRangeTooWide || idInvalid) { setPageData(null); return Promise.resolve(false); }
    return api.load('alerts', listUrl, (value) => setPageData({ ...readPage(value, listPath), results: value.results.map((row) => alertRow(row, role)) }));
  };
  const reload = async () => { const [a,b] = await Promise.all([reloadSummary(), reloadList()]); return a && b; };
  useEffect(() => { setPageData(null); void reloadList(); }, [listUrl]);
  useEffect(() => { void reloadSummary(); }, [role]);
  useEffect(() => { if (!selected) return; setHistory(null); const suffix=historyPage>1?`?page=${historyPage}`:'';void api.load('history',`${historyPath}${suffix}`,(value)=>setHistory(readPage(value,historyPath))); }, [historyPath, historyPage]);
  const blocked = api.busy || api.loading || api.locked || attending;
  async function choose(id) {
    setSelected(id); setDetail(null); setHistory(null); setHistoryPage(1);
    await api.load('detail', `/api/alertas/${id}/`, (value) => setDetail(alertRow(value, role)));
  }
  async function reloadSelected() {
    if (!selected) return true;
    const [d,h] = await Promise.all([
      api.load('detail', `/api/alertas/${selected}/`, (value) => setDetail(alertRow(value, role))),
      api.load('history', `${historyPath}${historyPage > 1 ? `?page=${historyPage}` : ''}`, (value) => setHistory(readPage(value, historyPath)))
    ]);
    return d && h;
  }
  async function reconcile() { const ok = await reload(); const selectedOk = await reloadSelected(); if (ok && selectedOk) api.reconcile(async () => true); }
  async function attend(event) {
    event.preventDefault(); if (role==='GERENCIA' || !selected || !reason.trim() || blocked || !detail?.acciones_permitidas.includes('ATENDER')) return;
    setAttending(true);
    try {
      await api.write(`/api/alertas/${selected}/atender/`, 'POST', { motivo: reason.trim() }, async (saved) => {
        setDetail(alertRow(saved, role)); setReason('');
        await api.requiredLoad('list', listUrl, (v) => setPageData({ ...readPage(v, listPath), results: v.results.map((row) => alertRow(row, role)) }));
        await api.requiredLoad('summary', '/api/alertas/resumen/', (v) => setSummary(summaryShape(v, role)));
        await api.requiredLoad('history', `${historyPath}${historyPage > 1 ? `?page=${historyPage}` : ''}`, (v) => setHistory(readPage(v, historyPath)));
      });
    } finally { setAttending(false); }
  }
  const types = typesFor(role);
  const resources = [...new Set(types.map(t=>RULES[t].recurso))];
  if (!['GERENCIA','SUPERVISOR_OBRAS','ADMINISTRATIVO_FINANZAS'].includes(role)) return <section><PageHead title="Alertas"/><div className="alert alert-warning" role="alert">No tienes permiso para consultar alertas.</div></section>;
  return <section className="commercial-page">
    <PageHead title="Alertas" sub={role === 'SUPERVISOR_OBRAS' ? undefined : 'Bandeja de alertas operativas asignadas a tu rol.'} />
    {summary && <><div className="kpis">{[['Activas',summary.activas],['Pendientes',summary.por_estado.PENDIENTE],['Atendidas',summary.por_estado.ATENDIDA],['Resueltas (histórico)',summary.por_estado.RESUELTA]].map(([label,value])=><div key={label} className="kpi"><div className="kpi-l">{label}</div><div className="kpi-v">{value}</div></div>)}</div>
      {summary.sincronizacion.desactualizada && role !== 'SUPERVISOR_OBRAS' && <p className="alert alert-warning" role="status">La sincronización del backend está atrasada. Los datos pueden no estar actualizados.</p>}</>}
    <div className="d-flex flex-wrap gap-2 mb-3"><button className="btn btn-outline-secondary" disabled={api.loading||api.busy} onClick={() => void api.reconcile(reload)}>Actualizar</button>
      <label className="form-label">Estado<select className="form-select" value={filters.estado} disabled={blocked} onChange={(e)=>{setPage(1);setFilters({...filters,estado:e.target.value});}}><option value="">Activas</option>{STATES.map((s)=><option key={s}>{s}</option>)}</select></label>
      <label className="form-label">Tipo<select className="form-select" value={filters.tipo} disabled={blocked} onChange={(e)=>{setPage(1);setFilters({...filters,tipo:e.target.value});}}><option value="">Todos</option>{types.map((t)=><option key={t} value={t}>{RULES[t].label}</option>)}</select></label>
      <label className="form-label">Recurso tipo<select className="form-select" value={filters.recurso_tipo} disabled={blocked} onChange={(e)=>{setPage(1);setFilters({...filters,recurso_tipo:e.target.value});}}><option value="">Todos</option>{resources.map((x)=><option key={x} value={x}>{({PRESUPUESTO:'Presupuesto',OBRA:'Obra',TURNO:'Turno',DOCUMENTO:'Documento'})[x]}</option>)}</select></label>
      <label className="form-label">ID recurso<input className="form-control" inputMode="numeric" value={filters.recurso_id} disabled={blocked} onChange={(e)=>{setPage(1);setFilters({...filters,recurso_id:e.target.value});}} /></label>
      <label className="form-label">Desde<input className="form-control" type="date" value={filters.desde} disabled={blocked} onChange={(e)=>{setPage(1);setFilters({...filters,desde:e.target.value});}} /></label>
      <label className="form-label">Hasta<input className="form-control" type="date" value={filters.hasta} disabled={blocked} onChange={(e)=>{setPage(1);setFilters({...filters,hasta:e.target.value});}} /></label>
    </div>
    {dateRangeInvalid&&<p className="alert alert-warning" role="alert">Indica ambas fechas y usa un rango válido.</p>}{dateRangeTooWide&&<p className="alert alert-warning" role="alert">El rango de fechas no puede superar 366 días inclusivos.</p>}{filters.recurso_id&&!filters.recurso_tipo&&<p className="alert alert-warning" role="alert">Selecciona el tipo de recurso para filtrar por ID.</p>}{idInvalid&&filters.recurso_tipo&&<p className="alert alert-warning" role="alert">El ID del recurso debe ser un entero positivo.</p>}
    {api.error && <div className="alert alert-warning" role="alert">{api.error.status===409?({alerta_ya_atendida:'La alerta ya fue atendida.',alerta_resuelta:'La alerta ya está resuelta.',alerta_desactualizada:'La causa ya no está vigente.'}[api.error.code]||api.error.message):api.error.status===403?'Acceso denegado.':api.error.message}</div>}
    <div className="card-fyag commercial-table-card"><div className="table-responsive" role="region" aria-label="Bandeja de alertas" tabIndex={0}><table className="table table-hover align-middle commercial-table"><thead><tr>{['Alerta','Severidad','Recurso','Estado','Creada'].map((x)=><th scope="col" key={x}>{x}</th>)}</tr></thead><tbody>{pageData?.results.map((a)=><tr key={a.id}><td><button type="button" className="btn btn-link p-0 text-start" onClick={()=>void choose(a.id)}>{a.titulo}</button><span className="d-block small">{a.tipo}</span></td><td>{a.severidad}</td><td>{a.recurso_tipo} {a.recurso_codigo||`#${a.recurso_id}`}</td><td>{a.estado}</td><td>{new Date(a.creado_en).toLocaleString('es-CL')}</td></tr>)}</tbody></table></div>{pageData&&!pageData.count&&<p className="commercial-empty">No hay alertas para esos filtros.</p>}
      <Pager data={pageData} page={page} setPage={setPage} disabled={blocked||dateRangeInvalid||dateRangeTooWide||idInvalid} label="Paginación de alertas" />
    </div>
    {selected && <article className="card-fyag commercial-detail"><div className="commercial-section-head"><h2>{detail?.titulo||`Alerta #${selected}`}</h2><button className="btn btn-outline-secondary btn-sm" disabled={blocked} onClick={()=>{setSelected(null);setDetail(null);}}>Cerrar</button></div>
      {detail&&<><p>{detail.descripcion}</p><p>{detail.tipo} · {detail.severidad} · {detail.estado} · {detail.recurso_tipo} {detail.recurso_codigo||`#${detail.recurso_id}`}</p>{detail.motivo_atencion&&<p>Motivo de atención: {detail.motivo_atencion}</p>}
      {role!=='GERENCIA'&&detail.acciones_permitidas.includes('ATENDER')&&<form className="commercial-form" onSubmit={attend}><label className="form-label" htmlFor="alert-reason">Motivo para atender</label><textarea id="alert-reason" className="form-control" value={reason} maxLength={2000} required disabled={blocked} onChange={(e)=>setReason(e.target.value)} /><button className="btn btn-fyag-primary mt-2" disabled={blocked||!reason.trim()}>Atender alerta</button></form>}</>}
      <section className="commercial-history"><h3>Historial</h3><ol>{history?.results.map((event)=><li key={event.id}>{event.tipo}: {event.estado_anterior||'—'} → {event.estado_nuevo} · {new Date(event.registrado_en).toLocaleString('es-CL')} {event.motivo}</li>)}</ol><Pager data={history} page={historyPage} setPage={setHistoryPage} disabled={blocked || !history?.results?.length} label="Paginación del historial" /></section>
    </article>}
  </section>;
}
