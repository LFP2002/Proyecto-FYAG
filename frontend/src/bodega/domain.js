import {normalizeDecimalInput} from '../utils/decimalInput.js';
export const ROOT='/api/inventario/';
export const modules={bodega_resumen:'resumen',inventario:'inventario',bodega_movimientos:'movimientos',bodega_entregas:'entregas',bodega_devoluciones:'devoluciones'};
export const milli=v=>{const normalized=normalizeDecimalInput(v,9,3,{fixed:true});return normalized===null?null:BigInt(normalized.replace('.',''));};
export const decimal=n=>String(n/1000n)+'.'+String(n%1000n).padStart(3,'0');
export const quantity=v=>{const n=milli(v);return n===null?'—':(n/1000n).toLocaleString('es-CL')+(n%1000n?','+String(n%1000n).padStart(3,'0').replace(/0+$/,''):'');};
export const amount=(v,unit)=>quantity(v)+(milli(v)===null||!unit?'':' '+unit);
// Display-only abbreviations; preserve original unit in the API and forms.
const movementUnits=new Map([['litro','L'],['litros','L'],['l','L'],['unidad','un.'],['unidades','un.'],['un','un.'],['un.','un.'],['metro','m'],['metros','m'],['kilogramo','kg'],['kilogramos','kg']]);
export const shortUnit=unit=>movementUnits.get(unit?.trim().toLowerCase())??unit;
export const movementAmount=(v,unit)=>amount(v,shortUnit(unit));
const dateParts=v=>typeof v==='string'&&Number.isFinite(Date.parse(v))?new Intl.DateTimeFormat('es-CL',{timeZone:'America/Santiago',day:'2-digit',month:'2-digit',year:'numeric',hour:'2-digit',minute:'2-digit',hourCycle:'h23'}).formatToParts(new Date(v)).reduce((a,p)=>({...a,[p.type]:p.value}),{}):null;
export const timestamp=v=>{const p=dateParts(v);return p?`${p.day}/${p.month}/${p.year} · ${p.hour}:${p.minute}`:'—';};
export const recordCount=n=>n===1?'1 registro':`${n} registros`;
export function authorizationStatus(row){
 const pending=milli(row.pendiente),executed=milli(row.ejecutada),total=milli(row.cantidad);
 if(pending===null||executed===null||total===null)return ['No disponible','neutral'];
 if(pending===0n)return executed>=total?['Completada','good']:['Sin saldo pendiente','neutral'];
 if(row.bloqueo)return ['Bloqueada','warn'];
 return executed>0n?['Parcial','warn']:['Pendiente','warn'];
}
export function pathFor(section,filters={},page=1){
 const p=new URLSearchParams({seccion:section});
 if(!['resumen','confirmacion','merma_detalle'].includes(section))p.set('page',String(page));
 for(const [k,v] of Object.entries(filters))if(v!==''&&v!==null&&v!==undefined)p.set(k,String(v));
 return ROOT+'bodega/?'+p;
}
export function readPage(v){
 if(!v||!Number.isSafeInteger(v.count)||v.count<0||!Array.isArray(v.results)||v.results.length>25||v.results.some(r=>!Number.isSafeInteger(r.id)||r.id<1||typeof r.nombre!=='string'||typeof r.codigo!=='string'||typeof r.unidad!=='string')||!['next','previous'].every(k=>v[k]===null||typeof v[k]==='string'))throw Error('Respuesta de Bodega inesperada.');
 return v;
}
export function readSummary(v){
 if(!v||!['materiales','sin_stock','entregas','devoluciones'].every(k=>Number.isSafeInteger(v[k])&&v[k]>=0)||!['faltantes','pendientes','retornos'].every(k=>Array.isArray(v[k])&&v[k].length<=5))throw Error('Resumen de Bodega inesperado.');
 for(const k of ['faltantes','pendientes','retornos'])readPage({count:v[k].length,results:v[k],next:null,previous:null});
 return v;
}
export function preview(form){
 const current=milli(form.row?.saldo),q=milli(form.cantidad),max=form.kind==='ENTREGA'||form.kind==='DEVOLUCION'?milli(form.row?.maximo):current===null?null:999999999999n-current;
 if(current===null||q===null||max===null||q<=0n||q>max||form.row?.bloqueo)return null;
 const next=form.kind==='ENTREGA'?current-q:current+q;
 return next<0n||next>999999999999n?null:{cantidad:decimal(q),saldo:decimal(next)};
}
