import React, { useEffect, useRef, useState } from 'react';
import { useAuth } from '../auth/AuthContext.jsx';
import { ApiError } from '../auth/client.js';
import { safePage, useApi } from './useApi.js';
import { financialDocument, financialEvent, financialPage, financialPayment } from './finance.js';
import { isoDate, todayInSantiago } from './dates.js';
import Adjuntos from './Adjuntos.jsx';
import { formatCompactCLP, formatCivilDate } from '../utils/format.js';

const confirm = (text) => (globalThis.confirm || globalThis.window?.confirm)?.(text) === true;
const EVENT_LABELS = { DOCUMENTO_REGISTRADO:'Documento registrado', DOCUMENTO_REVERTIDO:'Documento revertido', PAGO_REGISTRADO:'Pago registrado', PAGO_ANULADO:'Pago anulado' };
const formatTimestamp = value => {
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? value : new Intl.DateTimeFormat('es-CL',{timeZone:'America/Santiago',dateStyle:'medium',timeStyle:'short'}).format(date);
};
const EMPTY = { monto:'',fecha_pago:'',medio:'TRANSFERENCIA',referencia_respaldo:'',observacion:'' };
export default function FinanceDocument(props) {
  const { user } = useAuth();
  if (!['GERENCIA','ADMINISTRATIVO_FINANZAS'].includes(user.role)) return null;
  return <DocumentScreen key={`${user.id}:${user.role}:${props.document.id}`} {...props} />;
}
function DocumentScreen({ document: doc, onClose, onChanged = async () => true, onMutationStart = () => {}, onBlockedChange, initialPayment=false }) {
  const { user } = useAuth(), api = useApi();
  const [detail,setDetail] = useState(null), [payments,setPayments] = useState(null), [docEvents,setDocEvents] = useState(null), [payEvents,setPayEvents] = useState(null);
  const [paymentPage,setPaymentPage] = useState(1), [docPage,setDocPage] = useState(1), [historyPage,setHistoryPage] = useState(1);
  const [activeTab,setActiveTab] = useState(doc.estado==='REVERTIDO'?'history':'payments');
  const [showAttachments,setShowAttachments] = useState(false);
  const [showPayment,setShowPayment]=useState(initialPayment);
  const [correction,setCorrection]=useState(null);
  function openTab(tab){setActiveTab(tab);if(tab==='files')setShowAttachments(true);}
  const [form,setForm] = useState(EMPTY), [reason,setReason] = useState(''), [reference,setReference] = useState('');
  const [message,setMessage] = useState(''), [intent,setIntent] = useState(null), [pending,setPending] = useState(false);
  const intention = useRef(null), submitting = useRef(false);
  const base = `/api/finanzas/documentos/${doc.id}/`, paymentsBase = `${base}pagos/`, docHistory = `${base}historial/`, payHistory = `${base}pagos/historial/`;
  const writable = user.role === 'ADMINISTRATIVO_FINANZAS';
  const blocked = pending || api.busy || api.loading || api.locked || !!intent;
  const readDetail = () => {setDetail(null);return api.load('fin-doc',base,(v)=>{const value=financialDocument(v);if(value.id!==doc.id)throw new ApiError(502,'Documento inesperado.');setDetail(value);});};
  const readPayments = () => {setPayments(null);return api.load('fin-payments',`${paymentsBase}?page=${paymentPage}`,(v)=>{const data=financialPage(v,paymentsBase,financialPayment);if(data.results.some((p)=>p.documento!==doc.id))throw new ApiError(502,'Pago de otro documento.');setPayments(data);});};
  const readDocHistory = () => {setDocEvents(null);return api.load('fin-doc-history',`${docHistory}?page=${docPage}`,(v)=>setDocEvents(financialPage(v,docHistory,financialEvent)));};
  const readPayHistory = () => {setPayEvents(null);return api.load('fin-pay-history',`${payHistory}?page=${historyPage}`,(v)=>setPayEvents(financialPage(v,payHistory,financialEvent)));};
  async function readAll() {
    const results = await Promise.all([readDetail(),readPayments(),readDocHistory(),readPayHistory()]);
    if (!results.every(Boolean)) throw new ApiError(502,'Faltan relecturas del documento, pagos o historiales. No repitas una operación incierta.');
    return true;
  }
  useEffect(()=>{void readDetail();},[]);
  useEffect(()=>{void readPayments();},[paymentPage]);
  useEffect(()=>{void readDocHistory();},[docPage]);
  useEffect(()=>{void readPayHistory();},[historyPage]);
  useEffect(()=>{onBlockedChange?.(pending || api.locked || !!intent);},[pending,api.locked,intent,onBlockedChange]);
  useEffect(()=>()=>onBlockedChange?.(false),[onBlockedChange]);
  async function afterWrite() {
    await readAll();
    if (await onChanged() !== true) throw new ApiError(502,'No se confirmó la actualización de documentos y cartera.');
  }
  function invalidate() {
    setMessage(''); setDetail(null);setPayments(null);setDocEvents(null);setPayEvents(null);
    ['fin-doc','fin-payments','fin-doc-history','fin-pay-history'].forEach(api.cancelRead);
    onMutationStart();
  }
  async function mutate(path, body) {
    if (!writable || blocked || submitting.current) return;
    submitting.current = true;setPending(true);invalidate();
    try {
      await api.write(path,'POST',body,async()=>{await afterWrite();setReason('');setReference('');setCorrection(null);setMessage('Operación confirmada con relecturas de documento, historiales y cartera.');});
    } finally {submitting.current=false;setPending(false);}
  }
  async function performPayment(current) {
    invalidate();
    return api.write(paymentsBase,'POST',current.body,async(value)=>{
      const payment = financialPayment(value);
      if(payment.documento!==doc.id)throw new ApiError(502,'El pago no corresponde al documento.');
      await afterWrite();intention.current=null;setIntent(null);setForm(EMPTY);setShowPayment(false);setMessage('Pago informado registrado; relecturas confirmadas.');
    },{headers:{'Idempotency-Key':current.key}});
  }
  async function submitPayment(event) {
    event.preventDefault();if(!writable||blocked||submitting.current||intention.current||detail?.estado!=='VIGENTE'||!detail.cobranza||detail.cobranza.saldo==='0.00')return;
    if(!/^(?:0|[1-9][0-9]*)(?:\.[0-9]{1,2})?$/.test(form.monto)||!isoDate(form.fecha_pago)||form.fecha_pago>todayInSantiago()||!form.referencia_respaldo.trim()) {setMessage('Monto recibido, fecha válida y referencia del pago son obligatorios.');return;}
    const key=globalThis.crypto?.randomUUID?.();if(!key){setMessage('No se pudo generar una clave segura de idempotencia.');return;}
    if(!confirm('¿Registrar el pago ya recibido e informado externamente? FYAG no transfiere dinero.'))return;
    const current={key,body:{...form,referencia_respaldo:form.referencia_respaldo.trim(),observacion:form.observacion.trim()}};
    intention.current=current;setIntent(current);submitting.current=true;setPending(true);
    try{await performPayment(current);}finally{submitting.current=false;setPending(false);}
  }
  async function retryPayment() {
    if(!writable||submitting.current||!intention.current||!confirm('¿Reconsultar y reintentar explícitamente la misma intención de pago, sin cambiar su clave ni contenido?'))return;
    submitting.current=true;setPending(true);setMessage('');
    try{
      if(api.locked && !await api.reconcile(async()=>{await afterWrite();return true;}))return;
      await performPayment(intention.current);
    }catch(error){api.setError(error);}finally{submitting.current=false;setPending(false);}
  }
  const justification = () => {
    if(!reason.trim()||!reference.trim()){setMessage('Motivo y referencia externa son obligatorios.');return false;}return true;
  };
  return <section className="finance-detail" aria-label={`Administración del documento ${doc.id}`}>
    <div className="finance-detail-toolbar">
      <button className="btn btn-outline-secondary btn-sm" type="button" disabled={pending||api.locked||!!intent} onClick={onClose}><svg width="16" height="16" viewBox="0 0 16 16" fill="currentColor" className="bi bi-arrow-left" aria-hidden="true"><path fillRule="evenodd" d="M15 8a.5.5 0 0 0-.5-.5H2.707l3.647-3.646a.5.5 0 1 0-.708-.708l-4.5 4.5a.5.5 0 0 0 0 .708l4.5 4.5a.5.5 0 0 0 .708-.708L2.707 8.5H14.5A.5.5 0 0 0 15 8"/></svg>Volver a facturas</button>
      <button className="btn btn-outline-secondary btn-sm" type="button" disabled={pending||api.loading} onClick={()=>{setMessage('');void afterWrite().catch(api.setError);}}>Actualizar</button>
    </div>
    <div className="finance-detail-title"><h2>Factura {doc.folio_externo}</h2>{detail&&<span className="cobranzas-estado" data-estado={detail.estado}>{detail.estado==='REVERTIDO'?'Revertido':'Vigente'}</span>}</div>
    <p className="finance-detail-sub">{doc.origen.cliente.nombre_legal} · {doc.origen.codigo_obra} · {doc.tipo_documento==='FACTURA_AFECTA'?'Factura afecta':'Factura exenta'}</p>
    {api.error&&<p className="alert alert-warning" role="alert">{api.error.status===409?'Conflicto financiero: reconsulta antes de decidir; no se repitió la operación.':api.error.status===403?'Operación financiera no autorizada.':api.error.message}</p>}
    {api.locked&&<p role="alert">Falta confirmar el resultado. No se habilitan nuevas escrituras; los pagos solo admiten un reintento explícito de la misma intención.</p>}
    {message&&<p className="alert alert-info" role="status">{message}</p>}
    {intent&&<div role="status"><p>Intención de pago conservada sin cambios: {intent.body.monto} CLP · {intent.body.fecha_pago}. No se presume éxito ni fallo.</p>
      <button type="button" className="btn btn-outline-secondary" disabled={pending||api.loading} onClick={()=>void retryPayment()}>Reintentar misma intención de pago</button>
      {!api.locked&&[400,403,404,405,422].includes(api.error?.status)&&<button type="button" className="btn btn-outline-secondary" disabled={pending} onClick={()=>{intention.current=null;setIntent(null);api.setError(null);setMessage('Intención rechazada descartada. Corrige el contenido antes de un nuevo registro explícito.');}}>Nueva intención tras rechazo</button>}
    </div>}
    {detail&&<dl className="finance-summary card-fyag">
      <div><dt>Total del documento</dt><dd className="finance-amount">{formatCompactCLP(detail.monto_total)}</dd><small>CLP</small></div>
      <div><dt>Total recibido</dt><dd className="finance-amount">{detail.cobranza?formatCompactCLP(detail.cobranza.abonado):'—'}</dd></div>
      <div><dt>Saldo pendiente</dt><dd className="finance-amount">{detail.cobranza?formatCompactCLP(detail.cobranza.saldo):'—'}</dd><small>{({PENDIENTE:'Pendiente',PARCIAL:'Pago parcial',PAGADA:'Pagada',VENCIDA:'Vencida'})[detail.cobranza?.estado]??'No aplica'}</small></div>
      <div><dt>Emisión</dt><dd>{formatCivilDate(detail.fecha_emision)}</dd><dt>Vencimiento</dt><dd>{formatCivilDate(detail.fecha_vencimiento)}</dd></div>
      <div><dt>Neto / impuesto (CLP)</dt><dd>{formatCompactCLP(detail.monto_neto)} / {formatCompactCLP(detail.monto_impuesto)}</dd><dt>Registrado</dt><dd><time dateTime={detail.registrado_en} title={detail.registrado_en}>{formatTimestamp(detail.registrado_en)}</time></dd></div>
    </dl>}
    <div className="cobranzas-tabs finance-tabs" role="group" aria-label="Secciones del documento">
      {[['payments','Pagos'],['history','Historial del documento'],['payhistory','Historial de pagos'],['files','Respaldos']].map(([id,label])=><button key={id} type="button" aria-pressed={activeTab===id} aria-controls={`finance-${doc.id}-${id}`} onClick={()=>openTab(id)}>{label}</button>)}
    </div>
    <div id={`finance-${doc.id}-payments`} className="finance-tab-content card-fyag" hidden={activeTab!=='payments'}>
    {detail?.estado==='REVERTIDO'&&<p className="commercial-help">Factura revertida. Los datos y respaldos se conservan solo para consulta.</p>}
    <div className="finance-payments-heading"><h4>Pagos del documento</h4>{writable&&detail?.estado==='VIGENTE'&&detail.cobranza&&detail.cobranza.saldo!=='0.00'&&!showPayment&&!correction&&<button className="btn btn-fyag-primary" type="button" disabled={blocked} onClick={()=>{setShowPayment(true);setCorrection(null);}}>Registrar pago</button>}</div>
    {writable&&detail?.estado==='VIGENTE'&&detail.cobranza&&detail.cobranza.saldo!=='0.00'&&showPayment&&<form className="commercial-form finance-register-form" onSubmit={submitPayment} aria-label="Registro de pago informado"><h4>Registrar pago recibido</h4><p className="commercial-help">Registra un pago que ya recibiste. Saldo pendiente: {formatCompactCLP(detail.cobranza.saldo)} CLP.</p>
      <div className="finance-fields">
        <label className="form-label">Monto recibido (CLP)<input className="form-control" inputMode="decimal" placeholder="Ej.: 150000" value={form.monto} disabled={blocked} onChange={e=>setForm({...form,monto:e.target.value})}/></label>
        <label className="form-label">Fecha de pago<input className="form-control" type="date" value={form.fecha_pago} disabled={blocked} onChange={e=>setForm({...form,fecha_pago:e.target.value})}/></label>
        <label className="form-label">Medio de pago<select className="form-select" value={form.medio} disabled={blocked} onChange={e=>setForm({...form,medio:e.target.value})}>{Object.entries({TRANSFERENCIA:'Transferencia',EFECTIVO:'Efectivo',TARJETA:'Tarjeta',OTRO:'Otro'}).map(([key,label])=><option key={key} value={key}>{label}</option>)}</select></label>
        <label className="form-label">Referencia del pago<input className="form-control" placeholder="Número de comprobante" value={form.referencia_respaldo} disabled={blocked} onChange={e=>setForm({...form,referencia_respaldo:e.target.value})}/></label>
        <label className="form-label finance-full">Observaciones<textarea className="form-control" rows={2} value={form.observacion} disabled={blocked} onChange={e=>setForm({...form,observacion:e.target.value})}/></label>
      </div><div className="finance-form-footer"><button type="button" className="btn btn-outline-secondary" disabled={blocked} onClick={()=>setShowPayment(false)}>Cancelar</button><button className="btn btn-fyag-primary" disabled={blocked}>Registrar pago informado</button></div>
    </form>}
    <section className="finance-payments-list" aria-label="Lista de pagos">
      {payments&&!payments.count&&<div className="finance-empty"><strong>No hay pagos registrados</strong><span>Este documento no tiene pagos informados.</span></div>}
      {payments&&!!payments.count&&<ul className="finance-payments">{payments.results.map((payment)=><li key={payment.id}><div><strong>{formatCompactCLP(payment.monto)}</strong><span>{formatCivilDate(payment.fecha_pago)} · {({TRANSFERENCIA:'Transferencia',EFECTIVO:'Efectivo',TARJETA:'Tarjeta',OTRO:'Otro'})[payment.medio]} · {payment.referencia_respaldo}</span></div><span className="cobranzas-estado" data-estado={payment.activo?'PAGADA':'REVERTIDO'}>{payment.activo?'Activo':'Anulado'}</span>
      {writable&&detail?.estado==='VIGENTE'&&payment.activo&&!showPayment&&!correction&&<button type="button" className="btn btn-outline-danger btn-sm ms-2" disabled={blocked} onClick={()=>{setCorrection({payment:payment.id});setReason('');setReference('');setShowPayment(false);}}>Anular pago</button>}
    </li>)}</ul>}<FinancialPager data={payments} path={paymentsBase} page={paymentPage} onPage={setPaymentPage} disabled={pending||api.loading} label="Paginación de pagos" /></section>

    {writable&&detail?.estado==='VIGENTE'&&detail.cobranza&&!showPayment&&!correction&&<div className="finance-reversal-action">{detail.cobranza.abonado==='0.00'?<button className="btn btn-outline-danger btn-sm" type="button" disabled={blocked} onClick={()=>{setCorrection({payment:null});setReason('');setReference('');setShowPayment(false);}}>Revertir factura</button>:<p className="commercial-help">La factura tiene pagos activos. Para revertirla, primero debes resolver esos pagos.</p>}</div>}
    {writable&&detail?.estado==='VIGENTE'&&correction&&<div className="commercial-form finance-correction finance-register-form"><h4>{correction.payment?'Anular registro de pago':'Revertir factura'}</h4><p className="commercial-help">No se realiza un reembolso ni se modifica un DTE externo.</p><label className="form-label">Motivo de reversión o anulación<textarea className="form-control" rows={2} maxLength={2000} value={reason} disabled={blocked} onChange={e=>setReason(e.target.value)}/></label><label className="form-label">Referencia externa de rectificación o reversión<input className="form-control" maxLength={500} value={reference} disabled={blocked} onChange={e=>setReference(e.target.value)}/></label>
      <div className="finance-form-footer"><button className="btn btn-outline-secondary" type="button" disabled={blocked} onClick={()=>setCorrection(null)}>Cancelar</button><button className="btn btn-outline-danger" type="button" disabled={blocked} onClick={()=>{if(!justification()||!confirm(correction.payment?'¿Anular el registro de pago? No se genera un reembolso.':'¿Revertir administrativamente la factura externa?'))return;if(correction.payment)void mutate(`${paymentsBase}${correction.payment}/anular/`,{motivo:reason.trim(),referencia_reversion_externa:reference.trim()});else void mutate(`${base}revertir/`,{motivo:reason.trim(),referencia_rectificacion_externa:reference.trim()});}}>{correction.payment?'Confirmar anulación':'Confirmar reversión'}</button></div></div>}
    </div>
    <div id={`finance-${doc.id}-history`} className="finance-tab-content card-fyag" hidden={activeTab!=='history'}>
      <EventHistory title="Historial del documento" data={docEvents} path={docHistory} page={docPage} onPage={setDocPage} disabled={pending||api.loading}/>
    </div>
    <div id={`finance-${doc.id}-payhistory`} className="finance-tab-content card-fyag" hidden={activeTab!=='payhistory'}>
      <EventHistory title="Historial de pagos" data={payEvents} path={payHistory} page={historyPage} onPage={setHistoryPage} disabled={pending||api.loading}/>
    </div>
    <div id={`finance-${doc.id}-files`} className="finance-tab-content card-fyag" hidden={activeTab!=='files'}>
      <section aria-label="Respaldos documentales del documento financiero">
        {detail&&showAttachments&&<Adjuntos embedded type="RESPALDO_FACTURA" destinationId={doc.id} canUpload={writable&&detail.estado==='VIGENTE'&&!blocked} readOnly={detail.estado==='REVERTIDO'}/>}
        {!detail&&activeTab==='files'&&<p role="status" className="commercial-help">Información del documento aún no confirmada.</p>}
      </section>
    </div>
  </section>;
}
function FinancialPager({data,path,page,onPage,disabled,label}) {
  if(data&&!data.previous&&!data.next)return null;
  if(!data)return null;
  return <nav className="commercial-pager" aria-label={label}><button type="button" className="btn btn-outline-secondary btn-sm" disabled={disabled||!data?.previous} onClick={()=>onPage(safePage(data.previous,path))}>Anterior</button><span>Página {page}{data?` · ${data.count} registros`:' · lectura no confirmada'}</span><button type="button" className="btn btn-outline-secondary btn-sm" disabled={disabled||!data?.next} onClick={()=>onPage(safePage(data.next,path))}>Siguiente</button></nav>;
}
function EventHistory({title,data,...pager}) {
  const events=data?[...data.results].sort((a,b)=>Date.parse(b.creado_en)-Date.parse(a.creado_en)||b.id-a.id):[];
  return <section aria-label={title}>
    <div className="finance-history-head"><h4>{title==='Historial del documento'?'Actividad del documento':title}</h4>{data&&<span>{data.count} registros</span>}</div>
    {!data&&<p className="commercial-help">Lectura no confirmada.</p>}
    {data&&!data.count&&<div className="finance-empty"><strong>{title==='Historial de pagos'?'Sin historial de pagos':'Sin actividad registrada'}</strong><span>No existen movimientos registrados.</span></div>}
    {!!events.length&&<ol className="finance-timeline">{events.map(event=><li key={event.id} data-type={event.tipo}>
      <strong>{EVENT_LABELS[event.tipo]||event.tipo.replaceAll('_',' ')}</strong>
      <div className="finance-event-meta"><time dateTime={event.creado_en} title={event.creado_en}>{formatTimestamp(event.creado_en)}</time> · Usuario #{event.actor}</div>
      {event.motivo&&<div className="finance-event-reason"><strong>Motivo</strong><p>{event.motivo}</p></div>}
    </li>)}</ol>}
    {data&&(data.previous||data.next)&&<p className="commercial-help">Se muestran los registros de esta página.</p>}
    <FinancialPager {...pager} data={data} label={`Paginación: ${title}`}/>
  </section>;
}
