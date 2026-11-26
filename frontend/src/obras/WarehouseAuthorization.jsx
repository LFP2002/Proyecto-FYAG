import React,{useRef,useState} from 'react';
import InventoryPicker from '../integrations/InventoryPicker.jsx';
import {useApi} from '../integrations/useApi.js';
import {quantityInput,quantityHint,normalizeDecimalInput} from '../utils/decimalInput.js';
import {OperationalErrors} from './ui.jsx';

export default function WarehouseAuthorization({obra,delivery,onClose,onConfirmed}){
 const api=useApi(), pending=useRef(false), frozen=useRef(null);
 const [material,setMaterial]=useState(''),[quantity,setQuantity]=useState(''),[reference,setReference]=useState(''),[reason,setReason]=useState(''),[intent,setIntent]=useState(null),[issue,setIssue]=useState('');
 const returning=!!delivery, endpoint='/api/inventario/'+(returning?'autorizaciones-devolucion/':'autorizaciones-entrega/');
 const blocked=api.busy||!!intent;
 const definitive=[400,401,403,404,422].includes(api.error?.status)&&!api.locked;
 async function send(body,retry=false){
  if(!body||pending.current)return;
  pending.current=true;setIssue('');
  try{
   if(retry&&api.locked)await api.reconcile(async()=>true); // Only exact replay with the original UUID can resolve an uncertain authorization.
   const ok=await api.write(endpoint,'POST',body,async result=>{
    if(!result||!Number.isSafeInteger(result.id)||result.id<1||result.obra!==obra.id||
       result.tipo!==(returning?'AUTORIZACION_DEVOLUCION':'AUTORIZACION_ENTREGA')||
       result.clave_idempotencia!==body.clave_idempotencia||
       normalizeDecimalInput(result.cantidad,9,3,{fixed:true,positive:true})!==normalizeDecimalInput(body.cantidad,9,3,{fixed:true,positive:true})||
       (returning?result.entrega!==body.entrega:result.articulo!==body.articulo))throw Error('No se pudo confirmar la autorización.');
   });
   if(ok){frozen.current=null;setIntent(null);onConfirmed(returning?'Devolución autorizada. Bodega debe confirmar la recepción física.':'Entrega autorizada. Bodega debe confirmar el despacho; todavía no se modifica el costo de la obra.');}
  }finally{pending.current=false;}
 }
 async function submit(e){
  e.preventDefault();if(frozen.current||pending.current||api.busy||api.locked)return;
  const q=quantityInput(quantity);
  if(q===null||(!returning&&(!/^[1-9]\d*$/.test(material)||!Number.isSafeInteger(Number(material))))){setIssue('Selecciona el material e ingresa una cantidad mayor que cero.');return;}
  if(returning&&(!Number.isSafeInteger(delivery.entrega_bodega)||delivery.entrega_bodega<1)){setIssue('No se pudo identificar la entrega original.');return;}
  const key=globalThis.crypto?.randomUUID?.();
  if(!key){setIssue('No se pudo generar una clave segura.');return;}
  const body={...(returning?{entrega:delivery.entrega_bodega}:{obra:obra.id,articulo:Number(material)}),cantidad:q,clave_idempotencia:key,...(reference.trim()?{referencia:reference.trim()}:{}),...(reason.trim()?{motivo:reason.trim()}: {})};
  frozen.current=body;setIntent(body);await send(body);
 }
 return <form className="card-fyag so-panel commercial-form" aria-label={returning?'Autorizar devolución de Bodega':'Autorizar material de Bodega'} onSubmit={submit}>
  <h3>{returning?'Autorizar devolución':'Autorizar entrega de material'}</h3>
  <p className="commercial-help">{returning?'La cantidad y el costo se ajustarán cuando Bodega reciba físicamente el material.':'La obra ya está seleccionada. El costo se registrará automáticamente al confirmar el despacho; no debes ingresar un precio.'}</p>
  {!returning?<InventoryPicker kind="articulo" label="Material de Bodega" required activeOnly disabled={blocked} value={material} onChange={setMaterial}/>:<p><strong>{delivery.descripcion}</strong> · Entrega #{delivery.entrega_bodega}</p>}
  <div className="obras-form-grid">
   <label className="form-label">Cantidad<input className="form-control" required inputMode="decimal" placeholder={quantityHint} value={quantity} disabled={blocked} onChange={e=>setQuantity(e.target.value)}/></label>
   <label className="form-label">Referencia (opcional)<input className="form-control" maxLength={150} value={reference} disabled={blocked} onChange={e=>setReference(e.target.value)}/></label>
   <label className="form-label">Motivo (opcional)<textarea className="form-control" maxLength={2000} rows={2} value={reason} disabled={blocked} onChange={e=>setReason(e.target.value)}/></label>
  </div>
  <OperationalErrors error={api.error}/>{issue&&<p role="alert">{issue}</p>}
  {intent?<><p className="commercial-help" role="status">{api.busy?'Confirmando autorización…':'Se conserva la autorización original. No se enviará una distinta hasta confirmar el resultado.'}</p><div className="so-actions">
    <button type="button" className="btn btn-outline-secondary" disabled={api.busy} onClick={()=>void send(frozen.current,true)}>Reintentar misma autorización</button>
    {definitive&&<button type="button" className="btn btn-outline-secondary" disabled={api.busy} onClick={()=>{frozen.current=null;setIntent(null);api.setError(null);}}>Corregir datos rechazados</button>}
  </div></>:<div className="so-actions"><button type="button" className="btn btn-outline-secondary" onClick={onClose}>Cancelar</button><button type="submit" className="btn btn-fyag-primary">{returning?'Autorizar devolución':'Autorizar entrega'}</button></div>}
 </form>;
}
