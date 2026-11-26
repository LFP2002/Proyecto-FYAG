import {milli,decimal} from '../bodega/domain.js';
export const ROOT='/api/inventario/';
export const TYPES={CORTE_NO_REUTILIZABLE:'Corte no reutilizable',DANO_EN_OBRA:'Daño en obra',EXTRAVIO_EN_OBRA:'Extravío en obra',OTRA:'Otra'};
export const STATES={PENDIENTE:'Pendiente',APROBADA:'Aprobada',RECHAZADA:'Rechazada'};
export const path=(section,filters={},page=null)=>ROOT+'tecnico-materiales/?'+new URLSearchParams({seccion:section,...(page===null?{}:{page:String(page)}),...Object.fromEntries(Object.entries(filters).filter(([,v])=>v!==''&&v!=null))});
const id=v=>Number.isSafeInteger(v)&&v>0;
const str=v=>typeof v==='string';
const date=v=>str(v)&&Number.isFinite(Date.parse(v));
const work=r=>r&&id(r.id)&&['codigo','cliente','categoria','estado'].every(k=>str(r[k]));
const mat=r=>r&&id(r.id)&&['nombre','codigo','unidad'].every(k=>str(r[k]));
const qty=v=>str(v)&&milli(v)!==null;
export function record(r,loss,detail=false){
 if(!r||!id(r.id)||!work(r.obra)||!mat(r.material)||!str(r.unidad)||!qty(r.cantidad)||!Object.hasOwn(STATES,r.estado)||!date(r.creado_en)||!str(r.motivo_decision)||!(r.decidido_por===null||str(r.decidido_por))||!(r.decidido_en===null||date(r.decidido_en)))throw Error('Registro de materiales inesperado.');
 if(loss?(!id(r.entrega)||!Object.hasOwn(TYPES,r.tipo)||!['motivo','actividad','referencia'].every(k=>str(r[k]))):(!str(r.justificacion)||!(r.cantidad_aprobada===null||qty(r.cantidad_aprobada))||!(r.autorizacion===null||id(r.autorizacion))))throw Error('Datos de materiales inesperados.');
 if(detail&&(!Array.isArray(r.historial)||r.historial.some(e=>!id(e.id)||!['CREACION','APROBACION','RECHAZO'].includes(e.tipo)||!str(e.actor)||!str(e.motivo)||!date(e.creado_en))))throw Error('Historial inesperado.');
 return r;
}
export function readPage(v,section,workId){
 if(!v||!Number.isSafeInteger(v.count)||v.count<0||!Array.isArray(v.results)||v.results.length>25||!['next','previous'].every(k=>v[k]===null||str(v[k])))throw Error('Página de materiales inesperada.');
 for(const r of v.results){
  if(section==='mermas'||section==='solicitudes')record(r,section==='mermas');
  else if(!(section==='obras'?work(r)&&['EN_PROCESO','SUSPENDIDA'].includes(r.estado):section==='catalogo'?mat(r):id(r.id)&&work(r.obra)&&r.obra.id===workId&&mat(r.material)&&str(r.unidad)&&date(r.creado_en)&&['cantidad','devuelta','mermas_aprobadas','remanente'].every(k=>qty(r[k]))))throw Error('Opción de materiales inesperada.');
 }
 return v;
}
export function payload(form,loss){
 const q=milli(form.cantidad);
 if(!form.work||!form.material||!q||q<=0n)return null;
 if(loss){
  if(form.material.obra?.id!==form.work.id||q>milli(form.material.cantidad)||!Object.hasOwn(TYPES,form.tipo)||!form.motivo.trim()||!form.actividad.trim())return null;
  return {entrega:form.material.id,cantidad:decimal(q),tipo:form.tipo,motivo:form.motivo.trim(),actividad:form.actividad.trim(),referencia:form.referencia.trim(),clave_idempotencia:form.key};
 }
 if(!form.motivo.trim())return null;
 return {obra:form.work.id,articulo:form.material.id,cantidad:decimal(q),justificacion:form.motivo.trim(),clave_idempotencia:form.key};
}
