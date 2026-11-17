// Fixtures sintéticas de serializers_documentos.py / serializers_pagos.py.
// No representan una API real ni calculan saldos en el código productivo.
import { ApiError } from '../../src/auth/client.js';

export const origin = (obra = 7, cortesia = null) => ({
  obra, codigo_obra:`OB-${obra}`, presupuesto:obra, codigo_presupuesto:`PRE-${obra}`,
  cliente:{id:3,nombre_legal:'Cliente sintético',tipo_identificacion:'SIN_IDENTIFICACION',numero_identificacion:null,pais_identificacion:null,tipo_documento_extranjero:null},
  moneda:'CLP',monto_neto_aprobado:'100.00',finalizado_en:'2026-11-10T12:00:00Z',cortesia,
});
export const document = (id = 11, obra = 7) => ({
  id,naturaleza:'REGISTRO_ADMINISTRATIVO_DOCUMENTO_EXTERNO',origen:origin(obra),tipo_documento:'FACTURA_EXENTA',folio_externo:`00${id}`,
  fecha_emision:'2026-11-10',fecha_vencimiento:'2026-12-10',monto_neto:'100.00',monto_impuesto:'0.00',monto_total:'100.00',
  referencia_respaldo:'Referencia sintética',estado:'VIGENTE',registrado_por:9,registrado_en:'2026-11-10T12:00:00Z',
  revertido_por:null,revertido_en:null,motivo_reversion:null,referencia_rectificacion_externa:null,
  cobranza:{moneda:'CLP',abonado:'0.00',saldo:'100.00',estado:'PENDIENTE'},
});
export const payment = (id = 1, documento = 11) => ({
  id,naturaleza:'REGISTRO_ADMINISTRATIVO_DINERO_RECIBIDO',documento,monto:'25.00',fecha_pago:'2026-11-11',medio:'TRANSFERENCIA',
  referencia_respaldo:'Comprobante sintético',observacion:'',registrado_por:9,registrado_en:'2026-11-11T12:00:00Z',activo:true,
  anulado_por:null,anulado_en:null,motivo_anulacion:null,referencia_reversion_externa:null,
});
export const event = (id=1,doc=11) => ({id,documento:doc,cierre_sin_cobro:null,pago:null,tipo:'DOCUMENTO_REGISTRADO',actor:9,motivo:'Registro sintético',datos_anteriores:{},datos_nuevos:{estado:'VIGENTE'},creado_en:'2026-11-11T12:00:00Z'});
export function paginated(results, url) {
  const page=Number(url.searchParams.get('page')||1),size=25;
  const link=(p)=>{const next=new URL(url);next.searchParams.set('page',String(p));return next.pathname+next.search;};
  return {count:results.length,next:page*size<results.length?link(page+1):null,previous:page>1?link(page-1):null,results:structuredClone(results.slice((page-1)*size,page*size))};
}
export function financeBackend() {
  const state={calls:[],documents:[document()],payments:[],events:Array.from({length:26},(_,i)=>event(i+1)),payEvents:Array.from({length:26},(_,i)=>({...event(i+101),tipo:'PAGO_REGISTRADO',pago:i+1})),
    eligible:Array.from({length:26},(_,i)=>origin(i+7)),financial:{origen:origin(80,{id:4,tipo:'SIN_COBRO'}),estado_financiero:'PENDIENTE_REGISTRO_SIN_COBRO',documento_vigente:null,cierre_sin_cobro:null},fail:null,lostPayment:false,paid:false};
  const keys=new Map();
  state.request=async(path,options={})=>{
    const method=options.method||'GET',url=new URL(path,'http://localhost');state.calls.push({path,method,body:options.body,headers:options.headers});
    if(state.fail){const failure=state.fail(path,options);if(failure)throw failure;}
    if(url.pathname==='/api/finanzas/obras-elegibles/')return paginated(state.eligible,url);
    if(url.pathname.match(/^\/api\/finanzas\/obras\/\d+\/estado-financiero\/$/))return structuredClone(state.financial);
    if(url.pathname.match(/^\/api\/finanzas\/obras\/\d+\/registrar-sin-cobro\/$/) && method==='POST'){
      state.financial={...state.financial,estado_financiero:'SIN_COBRO',cierre_sin_cobro:{id:5,cortesia:4,motivo_registro:options.body.motivo_registro,registrado_por:9,registrado_en:'2026-11-17T12:00:00Z',eventos:[]}};
      return {id:5,obra:state.financial.origen.obra,cortesia:4,motivo_registro:options.body.motivo_registro,registrado_por:9,registrado_en:'2026-11-17T12:00:00Z',estado_financiero:'SIN_COBRO'};
    }
    if(url.pathname==='/api/finanzas/documentos/'){
      if(method==='GET')return paginated(state.documents,url);
      const doc={...document(99,options.body.obra),...options.body,origen:origin(options.body.obra)};delete doc.obra;state.documents.unshift(doc);return structuredClone(doc);
    }
    if(url.pathname==='/api/finanzas/cobranzas/')return paginated(state.documents.filter((d)=>d.estado==='VIGENTE'),url);
    if(url.pathname==='/api/finanzas/cobranzas/resumen/')return {moneda:'CLP',documentos:1,conteos:{PENDIENTE:state.paid?0:1,PARCIAL:state.paid?1:0,PAGADA:0,VENCIDA:0},monto_documentado_total:'100.00',abonado_total:state.paid?'25.00':'0.00',saldo_total:state.paid?'75.00':'100.00',saldo_vencido:'0.00'};
    const match=url.pathname.match(/^\/api\/finanzas\/documentos\/(\d+)\/(.*)$/);if(!match)throw new Error(`Ruta no contractual ${path}`);
    const id=Number(match[1]),suffix=match[2],doc=state.documents.find((d)=>d.id===id)||document(id);
    if(!suffix)return structuredClone(doc);
    if(suffix==='historial/')return paginated(state.events,url);
    if(suffix==='pagos/historial/')return paginated(state.payEvents,url);
    if(suffix==='pagos/'){
      if(method==='GET')return paginated(state.payments.filter((p)=>p.documento===id),url);
      const key=options.headers['Idempotency-Key'];
      if(keys.has(key)){const original=keys.get(key);if(JSON.stringify(original.body)!==JSON.stringify(options.body))throw new ApiError(409,'Payload distinto');return structuredClone(original.value);}
      const next={...payment(90,id),...options.body};keys.set(key,{body:structuredClone(options.body),value:next});state.payments.push(next);state.paid=true;
      doc.cobranza={moneda:'CLP',abonado:'25.00',saldo:'75.00',estado:'PARCIAL'};
      if(state.lostPayment){state.lostPayment=false;throw new ApiError(0,'Respuesta incierta');}
      return structuredClone(next);
    }
    if(suffix==='revertir/'&&method==='POST'){doc.estado='REVERTIDO';doc.cobranza=null;return structuredClone(doc);}
    if(/^pagos\/\d+\/anular\/$/.test(suffix)&&method==='POST'){
      const item=state.payments.find((p)=>p.id===Number(suffix.split('/')[1]));item.activo=false;state.paid=false;doc.cobranza={moneda:'CLP',abonado:'0.00',saldo:'100.00',estado:'PENDIENTE'};return structuredClone(item);
    }
    throw new Error(`Ruta no contractual ${method} ${path}`);
  };
  return state;
}
