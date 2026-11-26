import {formatCompactCLP} from '../utils/format.js';
export const units=v=>{
 if(typeof v!=='string'||!/^-?\d+(?:\.\d{1,2})?$/.test(v))return null;
 const negative=v.startsWith('-'),[a,b='']=(negative?v.slice(1):v).split('.');
 return BigInt(a+b.padEnd(2,'0'))*(negative?-1n:1n);
};
export function asDecimal(n){
 const a=(n<0n?-n:n).toString().padStart(3,'0');
 return (n<0n?'-':'')+a.slice(0,-2)+'.'+a.slice(-2);
}
export function economicDifference(budget,cost,final=false){
 const b=units(budget),c=units(cost);
 if(b===null||c===null||b<0n||c<0n)return null;
 const d=b-c,over=d<0n,abs=over?-d:d;
 const pct=b>0n?(abs*1000n+b/2n)/b:null;
 const rate=pct===null?null:(pct/10n).toLocaleString('es-CL')+(pct%10n?','+pct%10n:'')+' %';
 return {label:over?'Sobrecosto':final?'Margen neto':'Presupuesto restante',value:(over?'+':'')+formatCompactCLP(asDecimal(abs)),tone:over?'red':final&&d>0n?'green':'neutral',detail:over?(rate?rate+' sobre presupuesto':'Sin presupuesto neto'):(c===0n&&!final?'Sin costos registrados':rate?rate+(final?' de margen':' disponible'):'Sin presupuesto neto'),deviation:rate===null?null:(over?'+':d>0n?'−':'')+rate};
}
export const managerDateTime=value=>typeof value==='string'&&Number.isFinite(Date.parse(value))?new Intl.DateTimeFormat('es-CL',{timeZone:'America/Santiago',day:'2-digit',month:'2-digit',year:'numeric',hour:'2-digit',minute:'2-digit',hour12:false}).format(new Date(value)).replaceAll('-','/'):'—';
