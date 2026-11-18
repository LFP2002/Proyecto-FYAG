import React, { useEffect, useRef, useState } from 'react';
import { useAuth } from '../auth/AuthContext.jsx';
import { ApiError } from '../auth/client.js';
import { safePage, useApi } from './useApi.js';
import { financialDocument, financialEvent, financialPage, financialPayment } from './finance.js';
import { isoDate, todayInSantiago } from './dates.js';
import Adjuntos from './Adjuntos.jsx';

const confirm = (text) => (globalThis.confirm || globalThis.window?.confirm)?.(text) === true;
const EMPTY = { monto:'',fecha_pago:'',medio:'TRANSFERENCIA',referencia_respaldo:'',observacion:'' };
export default function FinanceDocument(props) {
  const { user } = useAuth();
  if (!['GERENCIA','ADMINISTRATIVO_FINANZAS'].includes(user.role)) return null;
  return <DocumentScreen key={`${user.id}:${user.role}:${props.document.id}`} {...props} />;
}
function DocumentScreen({ document: doc, onClose, onChanged = async () => true, onMutationStart = () => {}, onBlockedChange }) {
  const { user } = useAuth(), api = useApi();
  const [detail,setDetail] = useState(null), [payments,setPayments] = useState(null), [docEvents,setDocEvents] = useState(null), [payEvents,setPayEvents] = useState(null);
  const [paymentPage,setPaymentPage] = useState(1), [docPage,setDocPage] = useState(1), [historyPage,setHistoryPage] = useState(1);
  const [showAttachments,setShowAttachments] = useState(false);
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
      await api.write(path,'POST',body,async()=>{await afterWrite();setReason('');setReference('');setMessage('Operación confirmada con relecturas de documento, historiales y cartera.');});
    } finally {submitting.current=false;setPending(false);}
  }
  async function performPayment(current) {
    invalidate();
    return api.write(paymentsBase,'POST',current.body,async(value)=>{
      const payment = financialPayment(value);
      if(payment.documento!==doc.id)throw new ApiError(502,'El pago no corresponde al documento.');
      await afterWrite();intention.current=null;setIntent(null);setForm(EMPTY);setMessage('Pago informado registrado; relecturas confirmadas.');
    },{headers:{'Idempotency-Key':current.key}});
  }
  async function submitPayment(event) {
    event.preventDefault();if(!writable||blocked||submitting.current||intention.current)return;
    if(!/^(?:0|[1-9][0-9]*)(?:\.[0-9]{1,2})?$/.test(form.monto)||!isoDate(form.fecha_pago)||form.fecha_pago>todayInSantiago()||!form.referencia_respaldo.trim()) {setMessage('Monto decimal, fecha válida y referencia externa son obligatorios.');return;}
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
  return <section className="card-fyag p-3 my-3" aria-label={`Administración del documento ${doc.id}`}>
    <div className="d-flex flex-wrap justify-content-between gap-2"><h3>Documento externo #{doc.id} · folio {doc.folio_externo}</h3>
      <button className="btn btn-outline-secondary btn-sm" type="button" disabled={pending||api.locked||!!intent} onClick={onClose}>Cerrar detalle</button>
      <button className="btn btn-outline-secondary btn-sm" type="button" disabled={pending||api.loading} onClick={()=>{setMessage('');void afterWrite().catch(api.setError);}}>Actualizar detalle financiero</button>
    </div>
    {api.error&&<p className="alert alert-warning" role="alert">{api.error.status===409?'Conflicto financiero: reconsulta antes de decidir; no se repitió la operación.':api.error.status===403?'Operación financiera no autorizada.':api.error.message}</p>}
    {api.locked&&<p role="alert">Falta confirmar el resultado. No se habilitan nuevas escrituras; los pagos solo admiten un reintento explícito de la misma intención.</p>}
    {message&&<p className="alert alert-info" role="status">{message}</p>}
    {intent&&<div role="status"><p>Intención de pago conservada sin cambios: {intent.body.monto} CLP · {intent.body.fecha_pago}. No se presume éxito ni fallo.</p>
      <button type="button" className="btn btn-outline-secondary" disabled={pending||api.loading} onClick={()=>void retryPayment()}>Reintentar misma intención de pago</button>
      {!api.locked&&[400,403,404,405,422].includes(api.error?.status)&&<button type="button" className="btn btn-outline-secondary" disabled={pending} onClick={()=>{intention.current=null;setIntent(null);api.setError(null);setMessage('Intención rechazada descartada. Corrige el contenido antes de un nuevo registro explícito.');}}>Nueva intención tras rechazo</button>}
    </div>}
    {detail&&<dl className="commercial-facts"><div><dt>Estado</dt><dd>{detail.estado}</dd></div><div><dt>Total documento externo</dt><dd>{detail.monto_total} CLP</dd></div><div><dt>Registrado</dt><dd>{detail.registrado_en}</dd></div><div><dt>Saldo / estado</dt><dd>{detail.cobranza?.saldo??'No aplica'} · {detail.cobranza?.estado??'—'}</dd></div></dl>}
    {detail&&<section aria-label="Respaldos documentales del documento financiero" className="my-3">
      <button type="button" className="btn btn-outline-secondary btn-sm" disabled={pending||api.busy} onClick={()=>setShowAttachments((visible)=>!visible)}>{showAttachments?'Ocultar respaldos documentales':'Consultar respaldos documentales'}</button>
      {showAttachments&&<>
        {detail.estado==='REVERTIDO'&&<p className="commercial-help">Documento revertido: sus respaldos permanecen disponibles para consulta histórica, sin nuevas cargas ni edición de anotaciones.</p>}
        <Adjuntos type="RESPALDO_FACTURA" destinationId={doc.id} canUpload={writable&&detail.estado==='VIGENTE'&&!blocked} readOnly={detail.estado==='REVERTIDO'}/>
      </>}
    </section>}
    {writable&&detail?.estado==='VIGENTE'&&<form className="commercial-form" onSubmit={submitPayment} aria-label="Registro de pago informado"><h4>Registrar pago real informado externamente</h4><p>No transfiere dinero. Una intención conserva exactamente su clave y contenido hasta confirmar sus relecturas.</p>
      <div className="obras-form-grid">{[['monto','Monto decimal'],['fecha_pago','Fecha de pago'],['referencia_respaldo','Referencia externa del pago'],['observacion','Observación del pago']].map(([key,label])=><label className="form-label" key={key}>{label}<input className="form-control" type={key==='fecha_pago'?'date':'text'} value={form[key]} disabled={blocked} onChange={(e)=>setForm({...form,[key]:e.target.value})}/></label>)}
      <label className="form-label">Medio<select className="form-select" value={form.medio} disabled={blocked} onChange={(e)=>setForm({...form,medio:e.target.value})}>{['TRANSFERENCIA','EFECTIVO','TARJETA','OTRO'].map((value)=><option key={value}>{value}</option>)}</select></label></div>
      <button className="btn btn-fyag-primary mt-2" disabled={blocked}>Registrar pago informado</button>
    </form>}
    <section aria-label="Lista de pagos"><h4 className="mt-3">Pagos del documento</h4>{payments&&<ul>{payments.results.map((payment)=><li key={payment.id}>Pago #{payment.id}: {payment.monto} CLP · {payment.fecha_pago} · {payment.medio} · {payment.activo?'Activo':'Anulado'}
      {writable&&payment.activo&&<button type="button" className="btn btn-outline-danger btn-sm ms-2" disabled={blocked} onClick={()=>{if(justification()&&confirm(`¿Anular el registro de pago #${payment.id}? No se genera un reembolso.`))void mutate(`${paymentsBase}${payment.id}/anular/`,{motivo:reason.trim(),referencia_reversion_externa:reference.trim()});}}>Anular pago #{payment.id}</button>}
    </li>)}</ul>}<FinancialPager data={payments} path={paymentsBase} page={paymentPage} onPage={setPaymentPage} disabled={pending||api.loading} label="Paginación de pagos" /></section>
    <EventHistory title="Historial del documento" data={docEvents} path={docHistory} page={docPage} onPage={setDocPage} disabled={pending||api.loading}/>
    <EventHistory title="Historial de pagos" data={payEvents} path={payHistory} page={historyPage} onPage={setHistoryPage} disabled={pending||api.loading}/>
    {writable&&<div className="commercial-form mt-3"><label className="form-label">Motivo de reversión o anulación<input className="form-control" maxLength={2000} value={reason} disabled={blocked} onChange={(e)=>setReason(e.target.value)}/></label><label className="form-label">Referencia externa de rectificación o reversión<input className="form-control" maxLength={500} value={reference} disabled={blocked} onChange={(e)=>setReference(e.target.value)}/></label>
      {detail?.estado==='VIGENTE'&&<button type="button" className="btn btn-outline-danger mt-2" disabled={blocked} onClick={()=>{if(justification()&&confirm(`¿Revertir administrativamente el documento externo #${doc.id}? Resuelve primero los pagos activos.`))void mutate(`${base}revertir/`,{motivo:reason.trim(),referencia_rectificacion_externa:reference.trim()});}}>Revertir documento externo</button>}
    </div>}
  </section>;
}
function FinancialPager({data,path,page,onPage,disabled,label}) {
  return <nav className="commercial-pager" aria-label={label}><button type="button" className="btn btn-outline-secondary btn-sm" disabled={disabled||!data?.previous} onClick={()=>onPage(safePage(data.previous,path))}>Anterior</button><span>Página {page}{data?` · ${data.count} registros`:' · lectura no confirmada'}</span><button type="button" className="btn btn-outline-secondary btn-sm" disabled={disabled||!data?.next} onClick={()=>onPage(safePage(data.next,path))}>Siguiente</button></nav>;
}
function EventHistory({title,data,...pager}) {
  return <section aria-label={title}><h4>{title}</h4><p>Se muestra únicamente la página indicada, no el historial completo.</p><ol>{data?.results.map((event)=><li key={event.id}>{event.tipo} · {event.creado_en} · actor #{event.actor} · {event.motivo||'Sin motivo'}</li>)}</ol><FinancialPager {...pager} data={data} label={`Paginación: ${title}`}/></section>;
}
