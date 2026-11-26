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
function FinanceAdminScreen({ onChanged = async () => true, onMutationStart = () => {}, openRequest, onBlockedChange, initialObra = null }) {
  const { user } = useAuth(), api = useApi();
  const [page,setPage] = useState(1), [data,setData] = useState(null), [create,setCreate] = useState(false);
  const [form,setForm] = useState(INITIAL), [selected,setSelected] = useState(null), [message,setMessage] = useState('');
  const [eligiblePage,setEligiblePage] = useState(1), [eligible,setEligible] = useState(null), [chosen,setChosen] = useState(null);
  const [obraInput,setObraInput] = useState(''), [obraId,setObraId] = useState(initialObra ? String(initialObra) : ''), [state,setState] = useState(null), [reason,setReason] = useState('');
  const [childBlocked,setChildBlocked] = useState(false);
  const [paymentFirst,setPaymentFirst]=useState(false);
  const [detailVersion,setDetailVersion]=useState(0);
  const [searchDraft,setSearchDraft]=useState(''),[search,setSearch]=useState('');
  const [eligibleDraft,setEligibleDraft]=useState(''),[eligibleSearch,setEligibleSearch]=useState('');
  const pending = useRef(false);
  const canWrite = user.role === 'ADMINISTRATIVO_FINANZAS';
  const blocked = api.busy || api.locked || childBlocked;
  const path = `${DOCUMENTS}?page=${page}`+(search?'&buscar='+encodeURIComponent(search):'');
  const reload = () => { setData(null); return api.load('all-docs',path,(v)=>setData(financialPage(v,DOCUMENTS,financialDocument,search?{buscar:search}:{}))); };
  const loadEligible = () => { setEligible(null); return api.load('eligible',`${ELIGIBLE}?page=${eligiblePage}`+(eligibleSearch?'&buscar='+encodeURIComponent(eligibleSearch):''),(v)=>setEligible(financialPage(v,ELIGIBLE,financialOrigin,eligibleSearch?{buscar:eligibleSearch}:{}))); };
  const loadState = (id = obraId) => {
    setState(null);
    return id ? api.load('financial-state',`/api/finanzas/obras/${id}/estado-financiero/`,(v)=>setState(financialState(v,id))) : Promise.resolve(true);
  };
  useEffect(()=>{ void reload(); },[path]);
  useEffect(()=>{ if (canWrite && create) void loadEligible(); },[create,eligiblePage,eligibleSearch]);
  useEffect(()=>{if(initialObra){void loadState(String(initialObra));}},[initialObra]);
  useEffect(()=>{if(openRequest&&!blocked){setSelected(openRequest.doc);setPaymentFirst(openRequest.payment);setDetailVersion(v=>v+1);setCreate(false);}},[openRequest]);
  useEffect(()=>{onBlockedChange?.(blocked);return ()=>onBlockedChange?.(false);},[blocked,onBlockedChange]);
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
    const match = /^OB-([0-9]{1,19})$/i.exec(obraInput.trim());
    const id = match ? String(Number(match[1])) : '';
    if (!safeFinancialId(id)) { setMessage('Ingresa el código de la obra, por ejemplo OB-000009.'); return; }
    setMessage(''); setReason(''); setObraId(id); void loadState(id);
  }
  async function closeWithoutCharge(event) {
    event.preventDefault(); if (!canWrite || blocked || pending.current || !canRegisterWithoutCharge(state)) return;
    if (!reason.trim()) { setMessage('El motivo de registro es obligatorio.'); return; }
    if (!confirm(`¿Registrar el cierre administrativo sin cobro de la ${state.origen.codigo_obra}? No modifica la cortesía ni crea un pago.`)) return;
    pending.current = true; invalidate();
    try {
      await api.write(`/api/finanzas/obras/${obraId}/registrar-sin-cobro/`,'POST',{motivo_registro:reason.trim()},async(result)=>{
        if (!result || result.obra !== Number(obraId) || result.estado_financiero !== 'SIN_COBRO' || !safeFinancialId(result.id)) throw new ApiError(502,'Respuesta de cierre sin cobro inválida.');
        await refreshAffected(); setReason(''); setMessage('Cierre administrativo sin cobro registrado y estado reconsultado.');
      });
    } finally { pending.current = false; }
  }
  if(selected)return <FinanceDocument key={detailVersion} document={selected} initialPayment={paymentFirst} onClose={()=>{setSelected(null);setPaymentFirst(false);}} onChanged={refreshAffected} onMutationStart={invalidate} onBlockedChange={setChildBlocked} />;
  return <section className="card-fyag p-3 my-3" aria-label="Administración de documentos financieros">
    <div className="d-flex flex-wrap justify-content-between gap-2"><h3>Facturas registradas</h3><div className="d-flex gap-2">
      <button type="button" className="btn btn-outline-secondary btn-sm" disabled={api.loading || api.busy || childBlocked} onClick={()=>{setMessage('');void refreshAffected().catch(api.setError);}}>Actualizar</button>
      {canWrite && <button type="button" className="btn btn-fyag-primary btn-sm" disabled={blocked||create} onClick={()=>{setCreate(true);setEligiblePage(1);setEligibleSearch('');setEligibleDraft('');setSelected(null);}}>Registrar factura</button>}
    </div></div>
    {api.error && <p className="alert alert-warning" role="alert">{({400:'Revisa los datos financieros ingresados.',403:'No tienes permiso para esta operación.',404:'La obra, documento o página ya no está disponible.',409:'Conflicto financiero: vuelve a consultar antes de decidir.'})[api.error.status] || api.error.message}</p>}
    {api.locked && <p role="alert">Escritura bloqueada: falta confirmar el resultado. Reconsultar no reenvía ni desbloquea una operación administrativa incierta.</p>}
    {message && <p className="alert alert-info" role="status">{message}</p>}
    <form className="commercial-form my-3" hidden={create} onSubmit={lookup} aria-label="Consulta del estado financiero de una obra">
      <label className="form-label">Código de obra<input className="form-control" placeholder="OB-000009" value={obraInput} disabled={blocked} onChange={(e)=>{setObraInput(e.target.value);setObraId('');setState(null);api.cancelRead('financial-state');}} /></label>
      <button className="btn btn-outline-secondary mt-2" disabled={blocked || api.loading}>Consultar estado financiero</button>
    </form>
    {state && !create && <section aria-label="Estado financiero de la obra"><h4>{state.origen.codigo_obra} · {({PENDIENTE_FACTURACION:'Pendiente de facturación',PENDIENTE_REGISTRO_SIN_COBRO:'Pendiente de cierre sin cobro',SIN_COBRO:'Sin cobro',DOCUMENTADO:'Facturada'})[state.estado_financiero]}</h4>
      <p>Presupuesto {state.origen.codigo_presupuesto} · Cliente {state.origen.cliente.nombre_legal} · Neto aprobado {state.origen.monto_neto_aprobado} {state.origen.moneda}</p>
      <p>Finalización: {state.origen.finalizado_en || 'No informada'} · Cortesía: {state.origen.cortesia?.tipo || 'Sin cortesía'}</p>
      {state.documento_vigente && <><p>Factura {state.documento_vigente.folio_externo} · {state.documento_vigente.monto_total} CLP</p><button type="button" className="btn btn-outline-secondary" disabled={blocked} onClick={()=>{setSelected(state.documento_vigente);setPaymentFirst(false);}}>Ver factura</button></>}
      {state.cierre_sin_cobro && <p>Cierre sin cobro #{state.cierre_sin_cobro.id}: {state.cierre_sin_cobro.motivo_registro} · registrado {state.cierre_sin_cobro.registrado_en}</p>}
      {canWrite && canRegisterWithoutCharge(state) && <form className="commercial-form" onSubmit={closeWithoutCharge} aria-label="Registro administrativo sin cobro"><h4>Registrar cierre administrativo sin cobro</h4>
        <label className="form-label">Motivo de registro sin cobro<textarea className="form-control" required maxLength={2000} value={reason} disabled={blocked} onChange={(e)=>setReason(e.target.value)} /></label>
        <button className="btn btn-fyag-primary mt-2" disabled={blocked || api.loading || !reason.trim()}>Confirmar cierre sin cobro</button>
      </form>}
    </section>}
    {create && canWrite && <form className="commercial-form my-3 finance-register-form" onSubmit={submit} aria-label="Registro de documento externo"><h4>Registrar factura externa ya emitida</h4>
      <p>Ingresa los datos de la factura ya emitida.</p>
      <label className="form-label">Buscar obra elegible por código o cliente</label><div className="finance-search-row"><input aria-label="Buscar obra elegible" className="form-control" maxLength={150} value={eligibleDraft} onChange={e=>setEligibleDraft(e.target.value)} onKeyDown={e=>{if(e.key==='Enter'){e.preventDefault();setEligiblePage(1);setEligibleSearch(eligibleDraft.trim());}}} placeholder="Código de obra o cliente"/><button type="button" className="btn btn-outline-secondary" disabled={blocked||api.loading} onClick={()=>{setEligiblePage(1);setEligibleSearch(eligibleDraft.trim());}}>Buscar</button></div>
      <label className="form-label">Obra elegible para facturación<select className="form-select" value={form.obra} disabled={blocked || api.loading} onChange={(e)=>{const next=eligible?.results.find((row)=>row.obra===Number(e.target.value)) || (chosen?.obra===Number(e.target.value)?chosen:null);setChosen(next);setForm({...form,obra:e.target.value});}}>
        <option value="">Selecciona una obra elegible</option>{eligible?.results.map((row)=><option key={row.obra} value={String(row.obra)}>{row.codigo_obra} · {row.cliente.nombre_legal}</option>)}
        {chosen && !eligible?.results.some((row)=>row.obra===chosen.obra) && <option value={String(chosen.obra)}>{chosen.codigo_obra} · {chosen.cliente.nombre_legal}</option>}
      </select></label>
      {eligible && (eligible.previous||eligible.next) && <nav className="commercial-pager" aria-label="Paginación de obras elegibles"><button type="button" className="btn btn-outline-secondary btn-sm" disabled={blocked||api.loading||!eligible.previous} onClick={()=>setEligiblePage(safePage(eligible.previous,ELIGIBLE,eligibleSearch?{buscar:eligibleSearch}:{}))}>Anterior</button><span>Página {eligiblePage} · {eligible.count} obras elegibles</span><button type="button" className="btn btn-outline-secondary btn-sm" disabled={blocked||api.loading||!eligible.next} onClick={()=>setEligiblePage(safePage(eligible.next,ELIGIBLE,eligibleSearch?{buscar:eligibleSearch}:{}))}>Siguiente</button></nav>}
      {eligible && !eligible.count && <p>No hay obras elegibles para facturación en esta consulta.</p>}
      <button type="button" className="btn btn-outline-secondary btn-sm" disabled={blocked||api.loading} onClick={()=>void loadEligible()}>Reconsultar obras elegibles</button>
      {chosen && <p>Neto aprobado: {formatCompactCLP(chosen.monto_neto_aprobado)} CLP.</p>}
      <div className="finance-fields">{[['folio_externo','Folio de factura'],['fecha_emision','Fecha de emisión'],['fecha_vencimiento','Fecha de vencimiento'],['monto_neto','Monto neto (CLP)'],['monto_impuesto','Impuesto (CLP)'],['monto_total','Monto total (CLP)'],['referencia_respaldo','Referencia del respaldo']].map(([key,label])=><label className="form-label" key={key}>{label}<input className="form-control" type={key.startsWith('fecha_')?'date':'text'} disabled={blocked} value={form[key]} onChange={(e)=>setForm({...form,[key]:e.target.value})}/></label>)}
        <label className="form-label">Tipo<select className="form-select" value={form.tipo_documento} disabled={blocked} onChange={(e)=>setForm({...form,tipo_documento:e.target.value})}><option value="FACTURA_AFECTA">Factura afecta</option><option value="FACTURA_EXENTA">Factura exenta</option></select></label></div>
      <div className="finance-form-footer"><button className="btn btn-outline-secondary" type="button" disabled={blocked} onClick={()=>setCreate(false)}>Cancelar</button><button className="btn btn-fyag-primary" disabled={blocked||api.loading}>Registrar factura</button></div>
    </form>}
    {!create&&<><form className="finance-search-row" aria-label="Buscar documentos" onSubmit={e=>{e.preventDefault();setPage(1);setSearch(searchDraft.trim());}}><input className="form-control" aria-label="Buscar factura histórica" placeholder="Folio, código de obra o cliente" maxLength={150} value={searchDraft} onChange={e=>setSearchDraft(e.target.value)}/><button className="btn btn-outline-secondary" disabled={blocked||api.loading}>Buscar</button>{search&&<button type="button" className="btn btn-outline-secondary" onClick={()=>{setSearchDraft('');setSearch('');setPage(1);}}>Limpiar</button>}</form><div className="table-responsive" role="region" aria-label="Documentos financieros incluidos históricos" tabIndex={0}><table className="table table-hover commercial-table"><thead><tr>{['Factura / Cliente','Obra','Emisión','Vencimiento','Total CLP','Estado','Detalle'].map((label)=><th scope="col" key={label}>{label}</th>)}</tr></thead><tbody>{data?.results.map((doc)=><tr key={doc.id}><td><strong>Factura {doc.folio_externo}</strong><span className="cobranzas-client">{doc.origen.cliente.nombre_legal}</span></td><td>{doc.origen.codigo_obra}</td><td>{formatCivilDate(doc.fecha_emision)}</td><td>{formatCivilDate(doc.fecha_vencimiento)}</td><td className="num">{formatCompactCLP(doc.monto_total)}</td><td><span className="cobranzas-estado" data-estado={doc.estado}>{doc.estado==='VIGENTE'?'Vigente':'Revertida'}</span></td><td><button className="btn btn-outline-secondary btn-sm" type="button" disabled={blocked} onClick={()=>{setSelected(doc);setPaymentFirst(false);setCreate(false);}}>Ver detalle</button></td></tr>)}</tbody></table></div>
    {data && !data.count && <p>No hay documentos financieros registrados.</p>}
    {data && (data.previous||data.next) && <nav className="commercial-pager" aria-label="Paginación de documentos"><button type="button" className="btn btn-outline-secondary btn-sm" disabled={blocked||api.loading||!data.previous} onClick={()=>setPage(safePage(data.previous,DOCUMENTS,search?{buscar:search}:{}))}>Anterior</button><span>Página {page} · {data.count} documentos</span><button type="button" className="btn btn-outline-secondary btn-sm" disabled={blocked||api.loading||!data.next} onClick={()=>setPage(safePage(data.next,DOCUMENTS,search?{buscar:search}:{}))}>Siguiente</button></nav>}
    </>}
  </section>;
}
