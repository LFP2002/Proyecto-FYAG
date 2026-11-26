export function civilDate(v){return /^\d{4}-\d{2}-\d{2}$/.test(v||'')?v.split('-').reverse().join('/'):'Sin programar';}
export function civilTime(v){
 const d=new Date(v||'');if(!Number.isFinite(d.getTime()))return '—';
 const p=Object.fromEntries(new Intl.DateTimeFormat('es-CL',{timeZone:'America/Santiago',day:'2-digit',month:'2-digit',year:'numeric',hour:'2-digit',minute:'2-digit',hourCycle:'h23'}).formatToParts(d).map(x=>[x.type,x.value]));
 return p.day+'/'+p.month+'/'+p.year+' · '+p.hour+':'+p.minute;
}
export function elapsed(seconds){const n=Math.max(0,Math.floor(seconds));if(!Number.isFinite(n))return '—';return [Math.floor(n/3600),Math.floor(n%3600/60),n%60].map(v=>String(v).padStart(2,'0')).join(':');}
export function duration(row){const raw=row.duracion_ajustada_segundos??row.duracion_segundos;if(raw==null||raw==='')return '—';const n=Number(raw);if(!Number.isFinite(n)||n<0)return '—';const m=Math.floor(n/60);return Math.floor(m/60)+' h '+m%60+' min';}
