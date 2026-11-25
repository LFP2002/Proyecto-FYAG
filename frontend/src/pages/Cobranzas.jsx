import React, { useEffect, useMemo, useState } from 'react';
import { useAuth } from '../auth/AuthContext.jsx';
import { PageHead } from '../components/ui';
import { Pager } from '../comercial/ui.jsx';
import { decimalString, positiveInteger, readPage, safePage, strictObject, useApi } from '../integrations/useApi.js';
import Adjuntos from '../integrations/Adjuntos.jsx';
import FinanceAdmin from '../integrations/FinanceAdmin.jsx';
import { formatCompactCLP, formatCivilDate } from '../utils/format.js';

const STATES = ['PENDIENTE', 'PARCIAL', 'PAGADA', 'VENCIDA'];
const COLLECTION_URL = '/api/finanzas/cobranzas/';
const SUMMARY = '/api/finanzas/cobranzas/resumen/';
const EMPTY_FILTERS = { estado:'', cliente:'', obra:'', fecha_vencimiento_desde:'', fecha_vencimiento_hasta:'', fecha_emision_desde:'', fecha_emision_hasta:'' };
const hasInvalidId = filters => ['cliente','obra'].some(key=>filters[key]&&!/^[1-9][0-9]{0,18}$/.test(filters[key]));
const hasInvalidDates = filters => ['fecha_emision','fecha_vencimiento'].some(field=>!!filters[`${field}_desde`]!==!!filters[`${field}_hasta`]||(filters[`${field}_desde`]&&filters[`${field}_hasta`]&&filters[`${field}_desde`]>filters[`${field}_hasta`]));
function queryString(filters, page, includePage) {
  const params = new URLSearchParams();
  for (const [key, value] of Object.entries(filters)) if (value !== '' && value != null) params.set(key, value);
  if (includePage && page > 1) params.set('page', String(page));
  return params.size ? `?${params}` : '';
}
function safeNext(value, filters) {
  if (!value) return null;
  return safePage(value, COLLECTION_URL, filters);
}
function rowShape(row) {
  strictObject(row, ['id','naturaleza','origen','tipo_documento','folio_externo','fecha_emision','fecha_vencimiento','monto_neto','monto_impuesto','monto_total','referencia_respaldo','estado','registrado_por','registrado_en','revertido_por','revertido_en','motivo_reversion','referencia_rectificacion_externa','cobranza']);
  if (!positiveInteger(row.id) || typeof row.folio_externo !== 'string' || !/^\d+$/.test(row.folio_externo)
    || !['FACTURA_AFECTA','FACTURA_EXENTA'].includes(row.tipo_documento) || row.estado !== 'VIGENTE'
    || !decimalString(row.monto_neto) || !decimalString(row.monto_impuesto) || !decimalString(row.monto_total)) throw new Error('Documento financiero inválido.');
  strictObject(row.cobranza, ['moneda','abonado','saldo','estado']);
  if (row.cobranza.moneda !== 'CLP' || !decimalString(row.cobranza.abonado) || !decimalString(row.cobranza.saldo) || !STATES.includes(row.cobranza.estado)) throw new Error('Cobranza inválida.');
  strictObject(row.origen, ['obra','codigo_obra','presupuesto','codigo_presupuesto','cliente','moneda','monto_neto_aprobado','finalizado_en','cortesia']);
  if (row.origen.moneda !== 'CLP' || !decimalString(row.origen.monto_neto_aprobado) || !row.origen.cliente || typeof row.origen.cliente.nombre_legal !== 'string') throw new Error('Origen financiero inválido.');
  return row;
}
function summaryShape(data) {
  strictObject(data, ['moneda','documentos','conteos','monto_documentado_total','abonado_total','saldo_total','saldo_vencido']);
  strictObject(data.conteos, STATES);
  if (data.moneda !== 'CLP' || !Number.isSafeInteger(data.documentos) || data.documentos < 0
    || Object.values(data.conteos).some((x) => !Number.isSafeInteger(x) || x < 0)
    || ['monto_documentado_total','abonado_total','saldo_total','saldo_vencido'].some((k) => !decimalString(data[k]))) throw new Error('Resumen de cobranza inválido.');
  return data;
}
function FilterField({ title, value, onChange, type = 'text' }) {
  return <label className="form-label">{title}<input className="form-control" type={type} inputMode={type==='text'?'numeric':undefined} value={value} onChange={(e)=>onChange(e.target.value)} /></label>;
}
export default function Cobranzas() {
  const { user } = useAuth(); const api = useApi();
  const canRead = ['GERENCIA','ADMINISTRATIVO_FINANZAS'].includes(user.role);
  const [data, setData] = useState(null), [summary, setSummary] = useState(null), [snapshotKey,setSnapshotKey]=useState(null), [filters, setFilters] = useState(EMPTY_FILTERS), [page,setPage]=useState(1), [selectedDocument,setSelectedDocument]=useState(null);
  const [activeView,setActiveView]=useState('cartera'), [filtersOpen,setFiltersOpen]=useState(false), [draft,setDraft]=useState(EMPTY_FILTERS);
  const generation=React.useRef(0);
  const url=useMemo(()=>COLLECTION_URL+queryString(filters,page,true),[filters,page]);
  const summaryUrl=useMemo(()=>SUMMARY+queryString(filters,1,false),[filters]);
  const currentSnapshotKey=`${user.id}:${user.role}\n${url}\n${summaryUrl}`;
  const reload=async()=>{
    const current=++generation.current;
    setData(null);setSummary(null);setSnapshotKey(null);
    if(!canRead||invalidId||invalidDates)return false;
    let listSnapshot=null,summarySnapshot=null;
    const [listOk,summaryOk]=await Promise.all([
      api.load('cobranzas',url,(result)=>{const next=safeNext(result.next,filters),previous=safeNext(result.previous,filters);listSnapshot={...readPage(result,COLLECTION_URL),results:result.results.map(rowShape),next:next?`?page=${next}`:null,previous:previous?`?page=${previous}`:null};}),
      api.load('resumen',summaryUrl,(result)=>{summarySnapshot=summaryShape(result);})
    ]);
    if(current!==generation.current)return false;
    if(!listOk||!summaryOk||!listSnapshot||!summarySnapshot){setData(null);setSummary(null);return false;}
    setData(listSnapshot);setSummary(summarySnapshot);setSnapshotKey(currentSnapshotKey);return true;
  };
  useEffect(()=>{void reload();},[url,summaryUrl,user.id,user.role]);
  function invalidateFinancial() { generation.current+=1;api.cancelRead('cobranzas');api.cancelRead('resumen');setData(null);setSummary(null);setSnapshotKey(null);setSelectedDocument(null); }
  const blocked=api.loading||api.busy;
  const invalidId=hasInvalidId(filters), invalidDates=hasInvalidDates(filters);
  const draftInvalidId=hasInvalidId(draft), draftInvalidDates=hasInvalidDates(draft);
  const activeFilters=Object.values(filters).filter(Boolean).length;
  function change(key,value){setDraft(prev=>({...prev,[key]:value}));}
  function applyFilters(event){
    event.preventDefault();
    if(blocked||draftInvalidId||draftInvalidDates)return;
    setPage(1);setFilters({...draft});setSelectedDocument(null);setFiltersOpen(false);
  }
  async function refresh(){const ok=await reload();if(ok)api.reconcile(async()=>true);}
  if (!['GERENCIA','ADMINISTRATIVO_FINANZAS'].includes(user.role)) return <section><PageHead title="Cobranzas"/><p role="alert">No tienes permiso para consultar cobranzas.</p></section>;
  return <section className="commercial-page cobranzas-page">
    <PageHead title="Cobranzas" sub="Seguimiento de documentos, pagos y saldos.">
      {activeView==='cartera'&&<button type="button" className="btn btn-outline-secondary cobranzas-refresh" disabled={blocked} onClick={()=>void refresh()}>
        <svg width="16" height="16" viewBox="0 0 16 16" fill="currentColor" className="bi bi-arrow-counterclockwise" aria-hidden="true"><path fillRule="evenodd" d="M8 3a5 5 0 1 1-4.546 2.914.5.5 0 0 0-.908-.417A6 6 0 1 0 8 2z"/><path d="M8 4.466V.534a.25.25 0 0 0-.41-.192L5.23 2.308a.25.25 0 0 0 0 .384l2.36 1.966A.25.25 0 0 0 8 4.466"/></svg>Actualizar
      </button>}
    </PageHead>
    <div className="cobranzas-tabs" role="group" aria-label="Secciones de cobranzas">
      <button type="button" aria-pressed={activeView==='cartera'} aria-controls="cobranzas-cartera" onClick={()=>setActiveView('cartera')}>Cobranzas vigentes</button>
      <button type="button" aria-pressed={activeView==='documentos'} aria-controls="cobranzas-documentos" onClick={()=>setActiveView('documentos')}>Documentos y pagos</button>
    </div>
    <div id="cobranzas-cartera" className="cobranzas-view" hidden={activeView!=='cartera'}>
    {api.error&&<div className="alert alert-warning" role="alert">{api.error.status===403?'Acceso denegado.':api.error.message}</div>}
    {snapshotKey===currentSnapshotKey&&summary&&<div className="kpis">{[['Documentos',String(summary.documentos)],['Documentado bruto CLP',summary.monto_documentado_total],['Abonado CLP',summary.abonado_total],['Saldo CLP',summary.saldo_total],['Saldo vencido CLP',summary.saldo_vencido]].map(([label,value])=><div key={label} className={`kpi${label==='Saldo vencido CLP'&&Number(value)>0?' kpi-alert':''}`}><div className="kpi-l">{label}</div><div className="kpi-v">{label==='Documentos'?value:formatCompactCLP(value)}</div></div>)}</div>}
    {api.loading&&<p role="status">Cargando cartera…</p>}
    <div className="card-fyag commercial-table-card">
      <div className="cobranzas-panel-head">
        <div><h2>Documentos vigentes</h2><p>{snapshotKey===currentSnapshotKey&&data?`${data.count} registros · CLP`:'CLP'}</p></div>
        <div className="cobranzas-panel-actions">
          {selectedDocument&&<button type="button" className="btn btn-outline-secondary btn-sm" onClick={()=>setSelectedDocument(null)}>Cerrar detalle</button>}
          <button type="button" className="btn btn-outline-secondary btn-sm" aria-expanded={filtersOpen} aria-controls="cobranzas-filtros" onClick={()=>setFiltersOpen(open=>!open)}>
            <svg width="16" height="16" viewBox="0 0 16 16" fill="currentColor" className="bi bi-filter" aria-hidden="true"><path d="M6 10.5a.5.5 0 0 1 .5-.5h3a.5.5 0 0 1 0 1h-3a.5.5 0 0 1-.5-.5m-2-3a.5.5 0 0 1 .5-.5h7a.5.5 0 0 1 0 1h-7a.5.5 0 0 1-.5-.5m-2-3a.5.5 0 0 1 .5-.5h11a.5.5 0 0 1 0 1h-11a.5.5 0 0 1-.5-.5"/></svg>Filtros{activeFilters>0?` (${activeFilters})`:''}
            <svg width="12" height="12" viewBox="0 0 16 16" fill="currentColor" className="bi bi-chevron-down" aria-hidden="true"><path fillRule="evenodd" d="M1.646 4.646a.5.5 0 0 1 .708 0L8 10.293l5.646-5.647a.5.5 0 0 1 .708.708l-6 6a.5.5 0 0 1-.708 0l-6-6a.5.5 0 0 1 0-.708"/></svg>
          </button>
        </div>
      </div>
      <form id="cobranzas-filtros" className="cobranzas-filtros" aria-label="Filtros de cobranzas" hidden={!filtersOpen} onSubmit={applyFilters}>
        <label className="form-label">Estado<select className="form-select" value={draft.estado} onChange={(e)=>change('estado',e.target.value)}><option value="">Todos</option>{STATES.map(s=><option key={s}>{s}</option>)}</select></label>
        {['cliente','obra'].map(key=><FilterField key={key} title={`ID de ${key==='cliente'?'cliente':'obra'}`} value={draft[key]} onChange={v=>change(key,v)} />)}
        {['fecha_emision','fecha_vencimiento'].map(field=><React.Fragment key={field}><FilterField title={`${field==='fecha_emision'?'Emisión':'Vencimiento'} desde`} type="date" value={draft[`${field}_desde`]} onChange={v=>change(`${field}_desde`,v)} /><FilterField title={`${field==='fecha_emision'?'Emisión':'Vencimiento'} hasta`} type="date" value={draft[`${field}_hasta`]} onChange={v=>change(`${field}_hasta`,v)} /></React.Fragment>)}
        {draftInvalidId&&<p className="text-danger" role="alert">Los IDs de Cliente y Obra deben ser enteros positivos sin ceros iniciales.</p>}
        {draftInvalidDates&&<p className="text-danger" role="alert">Completa cada par de fechas y conserva el orden desde/hasta.</p>}
        <div className="cobranzas-filter-actions"><button type="button" className="btn btn-outline-secondary btn-sm" onClick={()=>setDraft({...EMPTY_FILTERS})}>Limpiar</button><button type="submit" className="btn btn-fyag-primary btn-sm" disabled={blocked||draftInvalidId||draftInvalidDates}>Aplicar filtros</button></div>
      </form>
      <div className="table-responsive" role="region" aria-label="Cartera de cobranzas" tabIndex={0}><table className="table table-hover align-middle commercial-table"><thead><tr>{['Folio externo','Obra','Cliente','Emisión','Vencimiento','Neto CLP','Impuesto CLP','Bruto CLP','Abonado CLP','Saldo CLP','Estado','Adjuntos'].map((x)=><th scope="col" key={x}>{x}</th>)}</tr></thead><tbody>{(snapshotKey===currentSnapshotKey?data?.results:null)?.map((row)=><tr key={row.id}><td><button className="btn btn-link p-0" type="button" onClick={()=>setSelectedDocument(row.id)}>{row.folio_externo}</button></td><td>{row.origen.codigo_obra} · #{row.origen.obra}</td><td>{row.origen.cliente.nombre_legal}</td><td>{formatCivilDate(row.fecha_emision)}</td><td>{formatCivilDate(row.fecha_vencimiento)}</td><td className="num">{formatCompactCLP(row.monto_neto)}</td><td className="num">{formatCompactCLP(row.monto_impuesto)}</td><td className="num">{formatCompactCLP(row.monto_total)}</td><td className="num">{formatCompactCLP(row.cobranza.abonado)}</td><td className="num saldo">{formatCompactCLP(row.cobranza.saldo)}</td><td><span className="cobranzas-estado" data-estado={row.cobranza.estado}>{row.cobranza.estado}</span></td><td><button type="button" className="btn btn-outline-secondary btn-sm" onClick={()=>setSelectedDocument(row.id)}>Adjuntos</button></td></tr>)}</tbody></table></div>
      {snapshotKey===currentSnapshotKey&&data&&!data.count&&<div className="commercial-empty"><svg width="30" height="30" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.4" aria-hidden="true"><rect x="5" y="3" width="14" height="18" rx="2"/><path d="M8 8h8M8 12h8M8 16h4"/></svg><strong>Sin documentos vigentes</strong><span>No hay documentos vigentes para esos filtros.</span></div>}
      <Pager data={snapshotKey===currentSnapshotKey?data:null} page={page} setPage={setPage} disabled={blocked||invalidId||invalidDates} label="Paginación de cobranzas" />
    </div>
    {selectedDocument && <Adjuntos type="RESPALDO_FACTURA" destinationId={selectedDocument} canUpload={user.role==='ADMINISTRATIVO_FINANZAS'&&data?.results.some((row)=>row.id===selectedDocument&&row.estado==='VIGENTE')} />}
    </div>
    <div id="cobranzas-documentos" className="cobranzas-view" hidden={activeView!=='documentos'}>
      <FinanceAdmin onChanged={reload} onMutationStart={invalidateFinancial} />
    </div>
    <p className="commercial-help">FYAG registra documentos externos y pagos ya informados; no emite DTE, no procesa cobros ni realiza transferencias. Totales y estados vienen del backend.</p>
  </section>;
}
