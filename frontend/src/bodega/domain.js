export const ROOT='/api/inventario/';
export const modules={bodega_resumen:'resumen',inventario:'inventario',bodega_movimientos:'movimientos',bodega_entregas:'entregas',bodega_devoluciones:'devoluciones'};
export const milli=v=>typeof v==='string'&&/^\d{1,9}(?:[.,]\d{1,3})?$/.test(v)?BigInt(v.split(/[.,]/)[0])*1000n+BigInt((v.split(/[.,]/)[1]||'').padEnd(3,'0')):null;
export const decimal=n=>String(n/1000n)+'.'+String(n%1000n).padStart(3,'0');
export const quantity=v=>{const n=milli(v);return n===null?'—':(n/1000n).toLocaleString('es-CL')+(n%1000n?','+String(n%1000n).padStart(3,'0').replace(/0+$/,''):'');};
export const amount=(v,unit)=>quantity(v)+(milli(v)===null||!unit?'':' '+unit);
export const timestamp=v=>typeof v==='string'&&Number.isFinite(Date.parse(v))?new Intl.DateTimeFormat('es-CL',{timeZone:'America/Santiago',dateStyle:'short',timeStyle:'short',hour12:false}).format(new Date(v)):'—';
export function pathFor(section,filters={},page=1){
 const p=new URLSearchParams({seccion:section});
 if(section!=='resumen'&&section!=='confirmacion')p.set('page',String(page));
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
