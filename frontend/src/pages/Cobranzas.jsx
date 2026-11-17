import React, { useEffect, useMemo, useState } from 'react';
import { useAuth } from '../auth/AuthContext.jsx';
import { PageHead } from '../components/ui';
import { Pager } from '../comercial/ui.jsx';
import { decimalString, positiveInteger, readPage, strictObject, useApi } from '../integrations/useApi.js';
import Adjuntos from '../integrations/Adjuntos.jsx';
import FinanceDocument from '../integrations/FinanceDocument.jsx';
import FinanceAdmin from '../integrations/FinanceAdmin.jsx';

const STATES = ['PENDIENTE', 'PARCIAL', 'PAGADA', 'VENCIDA'];
const COLLECTION_URL = '/api/finanzas/cobranzas/';
const SUMMARY = '/api/finanzas/cobranzas/resumen/';
function queryString(filters, page, includePage) {
  const params = new URLSearchParams();
  for (const [key, value] of Object.entries(filters)) if (value !== '' && value != null) params.set(key, value);
  if (includePage && page > 1) params.set('page', String(page));
  return params.size ? `?${params}` : '';
}
function safeNext(value, filters) {
  if (!value) return null;
  try {
    const origin = globalThis.location?.origin || 'http://localhost';
    const url = new URL(value, origin);
    const allowed = new Set(['page','estado','cliente','obra','fecha_vencimiento_desde','fecha_vencimiento_hasta','fecha_emision_desde','fecha_emision_hasta']);
    const actualFilters = new URLSearchParams(url.search); actualFilters.delete('page');
    const expectedFilters = new URLSearchParams(queryString(filters, 1, false));
    const page = url.searchParams.get('page');
    if (url.origin !== origin || url.pathname !== COLLECTION_URL || [...url.searchParams.keys()].some((key) => !allowed.has(key))
        || [...url.searchParams.keys()].some((key) => url.searchParams.getAll(key).length !== 1 || !url.searchParams.get(key))
        || actualFilters.toString() !== expectedFilters.toString() || (page && !/^[1-9][0-9]*$/.test(page))) throw new Error('invalid');
    return Number(page || 1);
  } catch { throw new Error('La paginación del servidor no es segura.'); }
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
function FilterField({ name, title, value, onChange, type = 'text' }) {
  return <label className="form-label">{title}<input className="form-control" type={type} value={value} onChange={(e)=>onChange(e.target.value)} /></label>;
}
export default function Cobranzas() {
  const { user } = useAuth(); const api = useApi();
  const [data, setData] = useState(null), [summary, setSummary] = useState(null), [snapshotKey,setSnapshotKey]=useState(null), [filters, setFilters] = useState({ estado:'', cliente:'', obra:'', fecha_vencimiento_desde:'', fecha_vencimiento_hasta:'', fecha_emision_desde:'', fecha_emision_hasta:'' }), [page,setPage]=useState(1), [selectedDocument,setSelectedDocument]=useState(null);
  const generation=React.useRef(0);
  const url=useMemo(()=>COLLECTION_URL+queryString(filters,page,true),[filters,page]);
  const summaryUrl=useMemo(()=>SUMMARY+queryString(filters,1,false),[filters]);
  const currentSnapshotKey=`${url}\n${summaryUrl}`;
  const reload=async()=>{
    const current=++generation.current;
    setData(null);setSummary(null);setSnapshotKey(null);
    if(invalidId||invalidDates)return false;
    let listSnapshot=null,summarySnapshot=null;
    const [listOk,summaryOk]=await Promise.all([
      api.load('cobranzas',url,(result)=>{const next=safeNext(result.next,filters),previous=safeNext(result.previous,filters);listSnapshot={...readPage(result,COLLECTION_URL),results:result.results.map(rowShape),next:next?`?page=${next}`:null,previous:previous?`?page=${previous}`:null};}),
      api.load('resumen',summaryUrl,(result)=>{summarySnapshot=summaryShape(result);})
    ]);
    if(current!==generation.current)return false;
    if(!listOk||!summaryOk||!listSnapshot||!summarySnapshot){setData(null);setSummary(null);return false;}
    setData(listSnapshot);setSummary(summarySnapshot);setSnapshotKey(currentSnapshotKey);return true;
  };
  useEffect(()=>{void reload();},[url,summaryUrl]);
  const blocked=api.loading||api.busy;
  const invalidId = ['cliente','obra'].some((key)=>filters[key]&&!/^[1-9][0-9]{0,18}$/.test(filters[key]));
  const invalidDates = ['fecha_emision','fecha_vencimiento'].some((field)=>!!filters[`${field}_desde`]!==!!filters[`${field}_hasta`]||(filters[`${field}_desde`]&&filters[`${field}_hasta`]&&filters[`${field}_desde`]>filters[`${field}_hasta`]));
  function change(key,value){setPage(1);setFilters((prev)=>({...prev,[key]:value}));}
  async function refresh(){const ok=await reload();if(ok)api.reconcile(async()=>true);}
  if (!['GERENCIA','ADMINISTRATIVO_FINANZAS'].includes(user.role)) return <section><PageHead title="Cobranzas"/><p role="alert">No tienes permiso para consultar cobranzas.</p></section>;
  return <section className="commercial-page">
    <PageHead title="Cobranzas" sub="Cartera y saldos calculados por el backend; las operaciones administrativas se registran solo para Finanzas." />
    {api.error&&<div className="alert alert-warning" role="alert">{api.error.status===403?'Acceso denegado.':api.error.message}</div>}
    <div className="d-flex flex-wrap gap-2 mb-3 align-items-end">
      <button type="button" className="btn btn-outline-secondary" disabled={blocked} onClick={()=>void refresh()}>Actualizar</button>
      {selectedDocument&&<button type="button" className="btn btn-outline-secondary" onClick={()=>setSelectedDocument(null)}>Cerrar detalle</button>}
      <label className="form-label">Estado<select className="form-select" value={filters.estado} disabled={blocked} onChange={(e)=>change('estado',e.target.value)}><option value="">Todos</option>{STATES.map((s)=><option key={s}>{s}</option>)}</select></label>
      {['cliente','obra'].map((key)=><FilterField key={key} name={key} title={`${key==='cliente'?'Cliente':'Obra'} ID`} value={filters[key]} onChange={(v)=>change(key,v)} />)}
      {['fecha_emision','fecha_vencimiento'].map((field)=><React.Fragment key={field}><FilterField name={`${field}_desde`} title={`${field==='fecha_emision'?'Emisión':'Vencimiento'} desde`} type="date" value={filters[`${field}_desde`]} onChange={(v)=>change(`${field}_desde`,v)} /><FilterField name={`${field}_hasta`} title="hasta" type="date" value={filters[`${field}_hasta`]} onChange={(v)=>change(`${field}_hasta`,v)} /></React.Fragment>)}
    </div>
    {invalidId&&<p className="text-danger" role="alert">Los IDs de Cliente y Obra deben ser enteros positivos sin ceros iniciales.</p>}{invalidDates&&<p className="text-danger" role="alert">Completa cada par de fechas y conserva el orden desde/hasta.</p>}
    {snapshotKey===currentSnapshotKey&&summary&&<div className="kpis">{[['Documentos',String(summary.documentos)],['Documentado bruto CLP',summary.monto_documentado_total],['Abonado CLP',summary.abonado_total],['Saldo CLP',summary.saldo_total],['Saldo vencido CLP',summary.saldo_vencido]].map(([label,value])=><div key={label} className="kpi"><div className="kpi-l">{label}</div><div className="kpi-v">{value}</div></div>)}</div>}
    {api.loading&&<p role="status">Cargando cartera…</p>}
    <div className="card-fyag commercial-table-card"><div className="table-responsive" role="region" aria-label="Cartera de cobranzas" tabIndex={0}><table className="table table-hover align-middle commercial-table"><thead><tr>{['Folio externo','Obra','Cliente','Emisión','Vencimiento','Neto CLP','Impuesto CLP','Bruto CLP','Abonado CLP','Saldo CLP','Estado','Adjuntos'].map((x)=><th scope="col" key={x}>{x}</th>)}</tr></thead><tbody>{(snapshotKey===currentSnapshotKey?data?.results:null)?.map((row)=><tr key={row.id}><td><button className="btn btn-link p-0" type="button" onClick={()=>setSelectedDocument(row.id)}>{row.folio_externo}</button></td><td>{row.origen.codigo_obra} · #{row.origen.obra}</td><td>{row.origen.cliente.nombre_legal}</td><td>{row.fecha_emision}</td><td>{row.fecha_vencimiento}</td><td>{row.monto_neto}</td><td>{row.monto_impuesto}</td><td>{row.monto_total}</td><td>{row.cobranza.abonado}</td><td>{row.cobranza.saldo}</td><td>{row.cobranza.estado}</td><td><button type="button" className="btn btn-outline-secondary btn-sm" onClick={()=>setSelectedDocument(row.id)}>Adjuntos</button></td></tr>)}</tbody></table></div>
      {snapshotKey===currentSnapshotKey&&data&&!data.count&&<p className="commercial-empty">No hay documentos vigentes para esos filtros.</p>}
      <Pager data={snapshotKey===currentSnapshotKey?data:null} page={page} setPage={setPage} disabled={blocked||invalidId||invalidDates} label="Paginación de cobranzas" />
    </div>
    {selectedDocument && <Adjuntos type="RESPALDO_FACTURA" destinationId={selectedDocument} canUpload={user.role==='ADMINISTRATIVO_FINANZAS'} />}
    <FinanceAdmin />
    <p className="commercial-help">FYAG registra documentos externos y pagos ya informados; no emite DTE, no procesa cobros ni realiza transferencias. Totales y estados vienen del backend.</p>
  </section>;
}
