import React, { useEffect, useRef, useState } from 'react';
import { useAuth } from '../auth/AuthContext.jsx';
import { ApiError } from '../auth/client.js';
import { safePage, useApi } from './useApi.js';
import { financialDocument, financialOrigin, financialPage, financialState, safeFinancialId, canRegisterWithoutCharge } from './finance.js';
import { isoDate, todayInSantiago } from './dates.js';
import FinanceDocument from './FinanceDocument.jsx';
import { formatCompactCLP, formatCivilDate } from '../utils/format.js';

const DOCUMENTS = '/api/finanzas/documentos/', ELIGIBLE = '/api/finanzas/obras-elegibles/';
const INITIAL = { obra:'', tipo_documento:'FACTURA_AFECTA', folio_externo:'', fecha_emision:'', fecha_vencimiento:'', monto_neto:'', monto_impuesto:'', monto_total:'', referencia_respaldo:'' };
const confirm = (text) => (globalThis.confirm || globalThis.window?.confirm)?.(text) === true;

export default function FinanceAdmin(props) {
  const { user } = useAuth();
  if (!['GERENCIA','ADMINISTRATIVO_FINANZAS'].includes(user.role)) return null;
  return <FinanceAdminScreen key={`${user.id}:${user.role}`} {...props} />;
}
function FinanceAdminScreen({ onChanged = async () => true, onMutationStart = () => {} }) {
  const { user } = useAuth(), api = useApi();
  const [page,setPage] = useState(1), [data,setData] = useState(null), [create,setCreate] = useState(false);
  const [form,setForm] = useState(INITIAL), [selected,setSelected] = useState(null), [message,setMessage] = useState('');
  const [eligiblePage,setEligiblePage] = useState(1), [eligible,setEligible] = useState(null), [chosen,setChosen] = useState(null);
  const [obraInput,setObraInput] = useState(''), [obraId,setObraId] = useState(''), [state,setState] = useState(null), [reason,setReason] = useState('');
  const [childBlocked,setChildBlocked] = useState(false);
  const pending = useRef(false);
  const canWrite = user.role === 'ADMINISTRATIVO_FINANZAS';
  const blocked = api.busy || api.locked || childBlocked;
  const path = `${DOCUMENTS}?page=${page}`;
  const reload = () => { setData(null); return api.load('all-docs',path,(v)=>setData(financialPage(v,DOCUMENTS,financialDocument))); };
  const loadEligible = () => { setEligible(null); return api.load('eligible',`${ELIGIBLE}?page=${eligiblePage}`,(v)=>setEligible(financialPage(v,ELIGIBLE,financialOrigin))); };
  const loadState = (id = obraId) => {
    setState(null);
    return id ? api.load('financial-state',`/api/finanzas/obras/${id}/estado-financiero/`,(v)=>setState(financialState(v,id))) : Promise.resolve(true);
  };
  useEffect(()=>{ void reload(); },[path]);
  useEffect(()=>{ if (canWrite && create) void loadEligible(); },[create,eligiblePage]);
  function invalidate() {
    setMessage(''); setData(null); setState(null); api.cancelRead('all-docs'); api.cancelRead('financial-state');
    onMutationStart();
  }
  async function refreshAffected() {
    const results = await Promise.all([reload(), loadState(), onChanged()]);
    if (!results.every((result)=>result === true)) throw new ApiError(502,'La escritura pudo completarse, pero faltan relecturas financieras. No la repitas; actualiza los datos.');
    return true;
  }
  async function submit(event) {
    event.preventDefault(); if (!canWrite || blocked || pending.current) return;
    if (!safeFinancialId(form.obra) || !chosen || chosen.obra !== Number(form.obra) || !/^[0-9]+$/.test(form.folio_externo)
        || !isoDate(form.fecha_emision) || !isoDate(form.fecha_vencimiento) || form.fecha_emision > todayInSantiago() || form.fecha_emision > form.fecha_vencimiento
        || !['monto_neto','monto_impuesto','monto_total'].every((k)=>/^(?:0|[1-9][0-9]*)(?:\.[0-9]{1,2})?$/.test(form[k])) || !form.referencia_respaldo.trim()) {
      setMessage('Selecciona una obra elegible y completa folio, fechas, importes decimales y referencia.'); return;
    }
    if (!confirm('¿Registrar este documento externo ya emitido? FYAG no emite un DTE ni mueve dinero.')) return;
    pending.current = true; invalidate();
    try {
      await api.write(DOCUMENTS,'POST',{...form, obra:Number(form.obra), referencia_respaldo:form.referencia_respaldo.trim()},async(result)=>{
        const created = financialDocument(result);
        if (created.origen.obra !== Number(form.obra)) throw new ApiError(502,'El documento recibido no corresponde al origen.');
        await refreshAffected();
        setForm(INITIAL); setChosen(null); setEligible(null); setCreate(false);
        setMessage('Documento externo registrado y relecturas confirmadas. No se emitió DTE ni se movió dinero.');
      });
    } finally { pending.current = false; }
  }
  function lookup(event) {
    event.preventDefault(); if (blocked) return;
    if (!safeFinancialId(obraInput)) { setMessage('Indica un ID de Obra positivo y representable sin pérdida.'); return; }
    setMessage(''); setReason(''); setObraId(obraInput); void loadState(obraInput);
  }
  async function closeWithoutCharge(event) {
    event.preventDefault(); if (!canWrite || blocked || pending.current || !canRegisterWithoutCharge(state)) return;
    if (!reason.trim()) { setMessage('El motivo de registro es obligatorio.'); return; }
    if (!confirm(`¿Registrar el cierre administrativo sin cobro de la Obra #${obraId}? No modifica la cortesía ni crea un pago.`)) return;
    pending.current = true; invalidate();
    try {
      await api.write(`/api/finanzas/obras/${obraId}/registrar-sin-cobro/`,'POST',{motivo_registro:reason.trim()},async(result)=>{
        if (!result || result.obra !== Number(obraId) || result.estado_financiero !== 'SIN_COBRO' || !safeFinancialId(result.id)) throw new ApiError(502,'Respuesta de cierre sin cobro inválida.');
        await refreshAffected(); setReason(''); setMessage('Cierre administrativo sin cobro registrado y estado reconsultado.');
      });
    } finally { pending.current = false; }
  }
  if(selected)return <FinanceDocument document={selected} onClose={()=>setSelected(null)} onChanged={refreshAffected} onMutationStart={invalidate} onBlockedChange={setChildBlocked} />;
  return <section className="card-fyag p-3 my-3" aria-label="Administración de documentos financieros">
    <div className="d-flex flex-wrap justify-content-between gap-2"><h3>Documentos y pagos informados</h3><div className="d-flex gap-2">
      <button type="button" className="btn btn-outline-secondary btn-sm" disabled={api.loading || api.busy || childBlocked} onClick={()=>{setMessage('');void refreshAffected().catch(api.setError);}}>Actualizar documentos y estado</button>
      {canWrite && <button type="button" className="btn btn-fyag-primary btn-sm" disabled={blocked} onClick={()=>{setCreate(!create);setEligiblePage(1);setSelected(null);}}>Registrar documento externo</button>}
    </div></div>
    {api.error && <p className="alert alert-warning" role="alert">{({400:'Revisa los datos financieros ingresados.',403:'No tienes permiso para esta operación.',404:'La obra, documento o página ya no está disponible.',409:'Conflicto financiero: vuelve a consultar antes de decidir.'})[api.error.status] || api.error.message}</p>}
    {api.locked && <p role="alert">Escritura bloqueada: falta confirmar el resultado. Reconsultar no reenvía ni desbloquea una operación administrativa incierta.</p>}
    {message && <p className="alert alert-info" role="status">{message}</p>}
    <form className="commercial-form my-3" onSubmit={lookup} aria-label="Consulta del estado financiero de una obra">
      <label className="form-label">ID de Obra para consulta financiera<input className="form-control" inputMode="numeric" value={obraInput} disabled={blocked} onChange={(e)=>{setObraInput(e.target.value);setObraId('');setState(null);api.cancelRead('financial-state');}} /></label>
      <button className="btn btn-outline-secondary mt-2" disabled={blocked || api.loading}>Consultar estado financiero</button>
    </form>
    {state && <section aria-label="Estado financiero de la obra"><h4>{state.origen.codigo_obra} · {state.estado_financiero}</h4>
      <p>Presupuesto {state.origen.codigo_presupuesto} · Cliente {state.origen.cliente.nombre_legal} · Neto aprobado {state.origen.monto_neto_aprobado} {state.origen.moneda}</p>
      <p>Finalización: {state.origen.finalizado_en || 'No informada'} · Cortesía: {state.origen.cortesia?.tipo || 'Sin cortesía'}</p>
      {state.documento_vigente && <><p>Documento vigente #{state.documento_vigente.id} · {state.documento_vigente.monto_total} CLP</p><button type="button" className="btn btn-outline-secondary" disabled={blocked} onClick={()=>setSelected(state.documento_vigente)}>Consultar / administrar documento vigente</button></>}
      {state.cierre_sin_cobro && <p>Cierre sin cobro #{state.cierre_sin_cobro.id}: {state.cierre_sin_cobro.motivo_registro} · registrado {state.cierre_sin_cobro.registrado_en}</p>}
      {canWrite && canRegisterWithoutCharge(state) && <form className="commercial-form" onSubmit={closeWithoutCharge} aria-label="Registro administrativo sin cobro"><h4>Registrar cierre administrativo sin cobro</h4>
        <label className="form-label">Motivo de registro sin cobro<textarea className="form-control" required maxLength={2000} value={reason} disabled={blocked} onChange={(e)=>setReason(e.target.value)} /></label>
        <button className="btn btn-fyag-primary mt-2" disabled={blocked || api.loading || !reason.trim()}>Confirmar cierre sin cobro</button>
      </form>}
    </section>}
    {create && canWrite && <form className="commercial-form my-3" onSubmit={submit} aria-label="Registro de documento externo"><h4>Registrar factura externa ya emitida</h4>
      <p>Ingresa los datos de la factura ya emitida.</p>
      <label className="form-label">Obra elegible para facturación<select className="form-select" value={form.obra} disabled={blocked || api.loading} onChange={(e)=>{const next=eligible?.results.find((row)=>row.obra===Number(e.target.value)) || (chosen?.obra===Number(e.target.value)?chosen:null);setChosen(next);setForm({...form,obra:e.target.value});}}>
        <option value="">Selecciona una obra elegible</option>{eligible?.results.map((row)=><option key={row.obra} value={String(row.obra)}>{row.codigo_obra} · {row.cliente.nombre_legal} · #{row.obra}</option>)}
        {chosen && !eligible?.results.some((row)=>row.obra===chosen.obra) && <option value={String(chosen.obra)}>{chosen.codigo_obra} · seleccionada #{chosen.obra}</option>}
      </select></label>
      {eligible && <nav className="commercial-pager" aria-label="Paginación de obras elegibles"><button type="button" className="btn btn-outline-secondary btn-sm" disabled={blocked||api.loading||!eligible.previous} onClick={()=>setEligiblePage(safePage(eligible.previous,ELIGIBLE))}>Anterior</button><span>Página {eligiblePage} · {eligible.count} obras elegibles</span><button type="button" className="btn btn-outline-secondary btn-sm" disabled={blocked||api.loading||!eligible.next} onClick={()=>setEligiblePage(safePage(eligible.next,ELIGIBLE))}>Siguiente</button></nav>}
      {eligible && !eligible.count && <p>No hay obras elegibles para facturación en esta consulta.</p>}
      <button type="button" className="btn btn-outline-secondary btn-sm" disabled={blocked||api.loading} onClick={()=>void loadEligible()}>Reconsultar obras elegibles</button>
      {chosen && <p>Neto aprobado: {formatCompactCLP(chosen.monto_neto_aprobado)} CLP.</p>}
      <div className="obras-form-grid">{[['folio_externo','Folio externo exacto'],['fecha_emision','Fecha de emisión'],['fecha_vencimiento','Fecha de vencimiento'],['monto_neto','Neto decimal'],['monto_impuesto','Impuesto decimal'],['monto_total','Total decimal'],['referencia_respaldo','Referencia externa']].map(([key,label])=><label className="form-label" key={key}>{label}<input className="form-control" type={key.startsWith('fecha_')?'date':'text'} disabled={blocked} value={form[key]} onChange={(e)=>setForm({...form,[key]:e.target.value})}/></label>)}
        <label className="form-label">Tipo<select className="form-select" value={form.tipo_documento} disabled={blocked} onChange={(e)=>setForm({...form,tipo_documento:e.target.value})}><option value="FACTURA_AFECTA">Factura afecta</option><option value="FACTURA_EXENTA">Factura exenta</option></select></label></div>
      <button className="btn btn-fyag-primary mt-2" disabled={blocked||api.loading}>Registrar documento externo</button><button className="btn btn-outline-secondary mt-2 ms-2" type="button" disabled={blocked} onClick={()=>setCreate(false)}>Cancelar</button>
    </form>}
    <div className="table-responsive" role="region" aria-label="Documentos financieros incluidos históricos" tabIndex={0}><table className="table table-hover commercial-table"><thead><tr>{['Folio externo','Obra','Fecha emisión','Vencimiento','Total CLP','Estado','Detalle / pagos'].map((label)=><th scope="col" key={label}>{label}</th>)}</tr></thead><tbody>{data?.results.map((doc)=><tr key={doc.id}><td>{doc.folio_externo}</td><td>#{doc.origen.obra}</td><td>{formatCivilDate(doc.fecha_emision)}</td><td>{formatCivilDate(doc.fecha_vencimiento)}</td><td className="num">{formatCompactCLP(doc.monto_total)}</td><td><span className="cobranzas-estado" data-estado={doc.estado}>{doc.estado}</span></td><td><button className="btn btn-outline-secondary btn-sm" type="button" disabled={blocked} onClick={()=>{setSelected(doc);setCreate(false);}}>Consultar / administrar</button></td></tr>)}</tbody></table></div>
    {data && !data.count && <p>No hay documentos financieros registrados.</p>}
    {data && (data.previous||data.next) && <nav className="commercial-pager" aria-label="Paginación de documentos"><button type="button" className="btn btn-outline-secondary btn-sm" disabled={blocked||api.loading||!data.previous} onClick={()=>setPage(safePage(data.previous,DOCUMENTS))}>Anterior</button><span>Página {page} · {data.count} documentos</span><button type="button" className="btn btn-outline-secondary btn-sm" disabled={blocked||api.loading||!data.next} onClick={()=>setPage(safePage(data.next,DOCUMENTS))}>Siguiente</button></nav>}
  </section>;
}
