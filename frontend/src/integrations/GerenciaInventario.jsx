import React,{useEffect,useState} from 'react';
import {PageHead} from '../components/ui/index.js';
import {Errors,Pager} from '../comercial/ui.jsx';
import {useApi,readPage} from './useApi.js';
import {civilRange,todayInSantiago} from './dates.js';
import '../styles/pages/inventario-gerencia.css';
import {formatCompactCLP,formatCivilDate} from '../utils/format.js';

const ROOT='/api/inventario/supervision-gerencial/';
const INITIAL={seccion:'existencias',filtro:'',buscar:'',articulo:'',estado:'',desde:'',hasta:'',page:1};
const count=v=>Number.isSafeInteger(v)&&v>=0;
const money=v=>typeof v==='string'&&/^\d+\.\d{2}$/.test(v);
const quantity=v=>typeof v==='string'&&/^\d+\.\d{3}$/.test(v);
const civil=v=>typeof v==='string'&&/^\d{4}-\d{2}-\d{2}$/.test(v);
const qty=v=>quantity(v)?v.replace(/0+$/,'').replace(/\.$/,'').replace('.',','):'—';
const types={DANO:'Daño',VENCIMIENTO:'Vencimiento',EXTRAVIO:'Extravío',DIFERENCIA_CONTEO:'Diferencia de conteo',OTRA:'Otra',CORTE_NO_REUTILIZABLE:'Corte no reutilizable',DANO_EN_OBRA:'Daño en obra',EXTRAVIO_EN_OBRA:'Extravío en obra'};
const cents=v=>BigInt(v.replace('.',''));
const percentage=(v,t)=>t===0n?'0%':(Number((v*1000n+t/2n)/t)/10).toLocaleString('es-CL',{maximumFractionDigits:1})+'%';
function validate(data,section,filters){
 readPage(data,ROOT,25,filters);
 const s=data?.resumen;
 if(!s||!count(data.count)||!Array.isArray(data.results)||data.results.length>25||!['sin_stock','pendientes_valoracion','mermas_bodega','mermas_obra','mermas_sin_valor','mermas_pendientes'].every(k=>count(s[k]))||!['valor_stock_valorado','mermas_bodega_neto','mermas_obra_informativo'].every(k=>money(s[k]))||!civil(s.desde)||!civil(s.hasta))throw Error('No se pudieron confirmar los indicadores de inventario.');
 if(!Array.isArray(s.composicion)||s.composicion.length>7||!s.composicion.every(x=>money(x.valor_neto)&&cents(x.valor_neto)>0n&&typeof x.nombre==='string'&&count(x.materiales)&&x.materiales>0&&(x.id===null?x.codigo===null:Number.isSafeInteger(x.id)&&x.id>0&&typeof x.codigo==='string'&&x.materiales===1))||new Set(s.composicion.map(x=>x.id)).size!==s.composicion.length||s.composicion.reduce((a,x)=>a+cents(x.valor_neto),0n)!==cents(s.valor_stock_valorado))throw Error('No se pudo confirmar la composición del inventario.');
 if(section==='mermas'&&filters.estado!=='PENDIENTE'&&(!civil(data.periodo_mermas?.desde)||!civil(data.periodo_mermas?.hasta)))throw Error('Período de mermas inválido.');
 for(const row of data.results){
  if(!Number.isSafeInteger(row.id)||row.id<1||typeof row.nombre!=='string'||typeof row.codigo!=='string'||typeof row.unidad!=='string'||!(row.valor_neto===null||money(row.valor_neto))||(section==='existencias'?!(row.saldo===null||quantity(row.saldo))||typeof row.activo!=='boolean'||typeof row.pendiente_valoracion!=='boolean':!quantity(row.cantidad)||!['BODEGA','OBRA'].includes(row.ambito)||typeof row.fecha!=='string'||!Number.isFinite(Date.parse(row.fecha))||!['APROBADA','PENDIENTE','RECHAZADA'].includes(row.estado)||row.estado!==(filters.estado||'APROBADA')||typeof row.motivo!=='string'||typeof row.motivo_decision!=='string'||(row.estado!=='APROBADA'&&row.valor_neto!==null)))throw Error('No se pudieron confirmar los registros de inventario.');
 }
 return data;
}
function Metric({label,value,detail,tone,onClick,active,disabled}){
 const content=<><span>{label}</span><strong>{value}</strong>{detail&&<small>{detail}</small>}</>;
 return onClick?<button type="button" className={'portfolio-kpi portfolio-'+tone} aria-pressed={active} disabled={disabled} onClick={onClick}>{content}</button>:<div className={'portfolio-kpi portfolio-'+tone}>{content}</div>;
}
// Partición binaria por área: no se agranda artificialmente ningún valor.
function tiles(items,x=0,y=0,w=600,h=260){
 if(!items.length)return [];
 if(items.length===1)return [{...items[0],x,y,w,h}];
 const total=items.reduce((a,r)=>a+cents(r.valor_neto),0n);
 let sum=0n,split=1,best=total;
 for(let i=1;i<items.length;i++){sum+=cents(items[i-1].valor_neto);const delta=sum*2n>total?sum*2n-total:total-sum*2n;if(delta<best){best=delta;split=i;}}
 const fraction=Number(items.slice(0,split).reduce((a,r)=>a+cents(r.valor_neto),0n))/Number(total);
 return w>=h?[...tiles(items.slice(0,split),x,y,w*fraction,h),...tiles(items.slice(split),x+w*fraction,y,w*(1-fraction),h)]:[...tiles(items.slice(0,split),x,y,w,h*fraction),...tiles(items.slice(split),x,y+h*fraction,w,h*(1-fraction))];
}
const colors=['#24598E','#3478DC','#427D8D','#326D7C','#526F94','#386B9E','#64748B'];
function Treemap({s,onMaterial}){
 const entries=s?.composicion||[],total=s?cents(s.valor_stock_valorado):0n;
 return <section className="card-fyag inventory-insight"><div className="portfolio-list-head"><div><h2>Composición del inventario valorizado</h2><span>Valor económico de los materiales</span></div><strong>{formatCompactCLP(s?.valor_stock_valorado)}</strong></div>
 {!s?<p className="commercial-empty">Sin datos disponibles.</p>:!entries.length?<p className="commercial-empty">No hay stock valorizado.</p>:<>
 <div className="inventory-treemap" role="group" aria-label="Composición del valor de inventario">{tiles(entries).map((r,i)=>{const style={left:r.x/6+'%',top:r.y/2.6+'%',width:r.w/6+'%',height:r.h/2.6+'%',background:colors[i]};const label=r.nombre+' · '+formatCompactCLP(r.valor_neto)+' · '+percentage(cents(r.valor_neto),total);const content=r.w>=105&&r.h>=42?<><strong>{r.nombre}</strong><span>{formatCompactCLP(r.valor_neto)}</span></>:null;return r.id===null?<div key="other" className="inventory-tile" style={style} title={label}>{content}</div>:<button type="button" key={r.id} className="inventory-tile" style={style} title={label} aria-label={'Localizar '+label} onClick={()=>onMaterial(r)}>{content}</button>;})}</div>
 <div className="inventory-treemap-legend">{entries.map((r,i)=><div key={r.id??'otros'}><i style={{background:colors[i]}}/>{r.id===null?<span>{r.nombre} ({r.materiales})</span>:<button type="button" onClick={()=>onMaterial(r)}>{r.nombre}</button>}<strong>{formatCompactCLP(r.valor_neto)}</strong><small>{percentage(cents(r.valor_neto),total)}</small></div>)}</div></>}
 {s?.pendientes_valoracion>0&&<p className="commercial-help">Solo incluye cantidades valorizadas.</p>}</section>;
}
function Attention({s,onSelect}){
 const icons=['M8.186 1.113a.5.5 0 0 0-.372 0l-6 2.4A.5.5 0 0 0 1.5 4v8a.5.5 0 0 0 .314.464l6 2.4a.5.5 0 0 0 .372 0l6-2.4A.5.5 0 0 0 14.5 12V4a.5.5 0 0 0-.314-.464zM8 2.116 12.654 4 8 5.862 3.346 4zM2.5 4.74 7.5 6.74v6.92l-5-2zm6 8.92V6.74l5-2v6.92z','M2 2a2 2 0 0 1 2-2h8a2 2 0 0 1 2 2v12a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2zm2-1a1 1 0 0 0-1 1v12a1 1 0 0 0 1 1h8a1 1 0 0 0 1-1V2a1 1 0 0 0-1-1zM5 3h6v3H5zm0 5h2v2H5zm4 0h2v2H9zm-4 4h2v1H5zm4 0h2v1H9z','M8 15A7 7 0 1 1 8 1a7 7 0 0 1 0 14m0 1A8 8 0 1 0 8 0a8 8 0 0 0 0 16M7.1 4.995a.9.9 0 1 1 1.8 0l-.35 3.507a.55.55 0 0 1-1.1 0zM8 10a1 1 0 1 0 0 2 1 1 0 0 0 0-2'];
 return <section className="card-fyag inventory-insight"><h2>Situaciones que requieren atención</h2><div className="inventory-attention">{[['Materiales agotados','Comprobar disponibilidad',s?.sin_stock,'sin_stock'],['Valoraciones pendientes','Revisar costos de adquisición',s?.pendientes_valoracion,'pendiente'],['Mermas pendientes','Pendientes de decisión',s?.mermas_pendientes,'PENDIENTE']].map(([label,desc,n,filter],i)=><button type="button" key={filter} disabled={!s||n===0} onClick={()=>onSelect(filter)}><span className={'inventory-attention-icon '+(i===0?'stock':'')}><svg width="22" height="22" viewBox="0 0 16 16" fill="currentColor" aria-hidden="true"><path d={icons[i]}/></svg></span><span><strong>{label}</strong><small>{desc}</small></span><b>{n??'—'}</b><span aria-hidden="true">›</span></button>)}</div>
 <div className="inventory-losses"><div><span>Mermas de bodega del mes</span><strong>{formatCompactCLP(s?.mermas_bodega_neto)}</strong></div><div><span>Mermas de obra del mes</span><strong>{formatCompactCLP(s?.mermas_obra_informativo)}</strong><small>Incluidas en los costos de obra</small></div></div>{s?.mermas_sin_valor>0&&<p className="commercial-help">{s.mermas_sin_valor} mermas aprobadas sin importe disponible.</p>}</section>;
}
export default function GerenciaInventario(){
 const api=useApi(),[query,setQuery]=useState(INITIAL),[draft,setDraft]=useState({buscar:'',filtro:'',desde:'',hasta:''}),[open,setOpen]=useState(false),[snapshot,setSnapshot]=useState(null),[error,setError]=useState('');
 const {page,...filters}=query,path=ROOT+'?'+new URLSearchParams(Object.entries(query).filter(([,v])=>v!==''));
 const read=()=>{setSnapshot(null);return api.load('inventory-manager',path,v=>setSnapshot({path,data:validate(v,query.seccion,filters)}));};
 useEffect(()=>{api.setError(null);void read();},[path]);
 const data=snapshot?.path===path?snapshot.data:null,s=data?.resumen,stock=query.seccion==='existencias',pending=query.estado==='PENDIENTE';
 const change=patch=>setQuery(prev=>({...prev,...patch,page:1}));
 const scroll=()=>{const node=globalThis.document?.getElementById?.('inventory-manager-list');node?.focus?.({preventScroll:true});node?.scrollIntoView?.({block:'start',behavior:'auto'});};
 function select(section,filter='',state='',material=''){
  setDraft({buscar:'',filtro:filter,desde:'',hasta:''});setError('');
  change({seccion:section,filtro:filter,estado:state,buscar:'',articulo:material,desde:'',hasta:''});scroll();
 }
 function clear(){setDraft({buscar:'',filtro:'',desde:'',hasta:''});setError('');change({buscar:'',filtro:'',articulo:'',desde:'',hasta:''});}
 function apply(e){e.preventDefault();if(!stock&&!pending&&(draft.desde||draft.hasta)&&(!civilRange(draft.desde,draft.hasta)||draft.hasta>todayInSantiago())){setError('Selecciona un período válido de hasta 366 días, sin fechas futuras.');return;}setError('');change({buscar:draft.buscar.trim(),filtro:draft.filtro,articulo:'',desde:stock||pending?'':draft.desde,hasta:stock||pending?'':draft.hasta});}
 const dateLocal=v=>new Intl.DateTimeFormat('es-CL',{timeZone:'America/Santiago',day:'2-digit',month:'2-digit',year:'numeric'}).format(new Date(v)).replaceAll('-','/');
 return <section className="commercial-page manager-portfolio cobranzas-page manager-cobranzas inventory-manager">
  <PageHead title="Inventario" sub="Supervisa las existencias, valoración y pérdidas de materiales."><button type="button" className="btn btn-outline-secondary cobranzas-refresh" aria-label="Actualizar datos" disabled={api.loading} onClick={()=>void api.reconcile(read)}><svg width="16" height="16" viewBox="0 0 16 16" fill="currentColor" aria-hidden="true"><path fillRule="evenodd" d="M8 3a5 5 0 1 1-4.546 2.914.5.5 0 0 0-.908-.417A6 6 0 1 0 8 2z"/><path d="M8 4.466V.534a.25.25 0 0 0-.41-.192L5.23 2.308a.25.25 0 0 0 0 .384l2.36 1.966A.25.25 0 0 0 8 4.466"/></svg>Actualizar</button></PageHead>
  <Errors error={api.error}/>{api.loading&&<p role="status">Cargando inventario…</p>}
  <div className="portfolio-kpis">
   <Metric label="Valor del stock valorizado" value={formatCompactCLP(s?.valor_stock_valorado)} detail="CLP · neto" tone="blue"/>
   <Metric label="Materiales sin stock" value={s?.sin_stock??'—'} detail="Materiales activos" tone="red" active={stock&&query.filtro==='sin_stock'} disabled={!s} onClick={()=>select('existencias','sin_stock')}/>
   <Metric label="Mermas de bodega del mes" value={formatCompactCLP(s?.mermas_bodega_neto)} detail={s?s.mermas_bodega+' aprobadas · CLP neto':'CLP · neto'} tone="amber" active={!stock&&query.filtro==='bodega'&&!query.estado&&!query.desde} disabled={!s} onClick={()=>select('mermas','bodega')}/>
   <Metric label="Pendientes de valoración" value={s?.pendientes_valoracion??'—'} detail="Materiales" tone="gray" active={stock&&query.filtro==='pendiente'} disabled={!s} onClick={()=>select('existencias','pendiente')}/>
  </div>
  <div className="commercial-insights"><Treemap s={s} onMaterial={r=>select('existencias','','',String(r.id))}/><Attention s={s} onSelect={f=>f==='PENDIENTE'?select('mermas','',f):select('existencias',f)}/></div>
  <section id="inventory-manager-list" tabIndex={-1} className="card-fyag portfolio-list">
    <div className="portfolio-list-head"><div><h2>{stock?'Existencias y valoración':'Mermas'}</h2><span>{data?data.count+' registros · ':''}{stock?'Estado actual':pending?'Pendientes de todos los períodos':data?.periodo_mermas?formatCivilDate(data.periodo_mermas.desde)+' – '+formatCivilDate(data.periodo_mermas.hasta):'Período seleccionado'}</span></div><button type="button" className="btn btn-outline-secondary btn-sm manager-cob-filter-toggle" aria-expanded={open} aria-controls="inv-filters" onClick={()=>setOpen(x=>!x)}><svg width="16" height="16" viewBox="0 0 16 16" fill="currentColor" aria-hidden="true"><path d="M6 11.5a.5.5 0 0 1 .5-.5h3a.5.5 0 0 1 0 1h-3a.5.5 0 0 1-.5-.5m-2-4a.5.5 0 0 1 .5-.5h7a.5.5 0 0 1 0 1h-7a.5.5 0 0 1-.5-.5m-2-4a.5.5 0 0 1 .5-.5h11a.5.5 0 0 1 0 1h-11a.5.5 0 0 1-.5-.5"/></svg>Filtros</button></div>
    <form id="inv-filters" className="commercial-period manager-cob-filter-form" hidden={!open} onSubmit={apply}><div className="commercial-search"><label htmlFor="inv-search">Buscar material</label><input id="inv-search" className="form-control" placeholder="Código o nombre" maxLength={100} value={draft.buscar} onChange={e=>setDraft({...draft,buscar:e.target.value})}/></div><div><label htmlFor="inv-filter">{stock?'Situación':'Ámbito'}</label><select id="inv-filter" className="form-select" value={draft.filtro} onChange={e=>setDraft({...draft,filtro:e.target.value})}><option value="">Todos</option>{(stock?[['sin_stock','Sin stock'],['pendiente','Pendientes de valoración']]:[['bodega','Bodega'],['obra','Obras']]).map(([k,l])=><option key={k} value={k}>{l}</option>)}</select></div>
    {!stock&&!pending&&[['desde','Decisión desde'],['hasta','Decisión hasta']].map(([k,l])=><div key={k}><label htmlFor={'inv-'+k}>{l}</label><input id={'inv-'+k} className="form-control" type="date" value={draft[k]} onChange={e=>setDraft({...draft,[k]:e.target.value})}/></div>)}<button type="submit" className="btn btn-fyag-primary">Aplicar filtros</button><button type="button" className="btn btn-outline-secondary" onClick={clear}>Limpiar filtros</button>{error&&<p role="alert">{error}</p>}</form>
    {(query.articulo||query.buscar||query.filtro||query.desde)&&<div className="inventory-active-filter"><span>{query.articulo?'Material: '+(s?.composicion.find(r=>String(r.id)===query.articulo)?.nombre||query.articulo):[query.buscar,({sin_stock:'Sin stock',pendiente:'Pendientes de valoración',bodega:'Bodega',obra:'Obras'})[query.filtro],query.desde&&formatCivilDate(query.desde)+' – '+formatCivilDate(query.hasta)].filter(Boolean).join(' · ')}</span><button type="button" className="btn btn-outline-secondary btn-sm" onClick={clear}>Quitar filtros</button></div>}
    <div className="manager-work-tabs" role="group" aria-label="Secciones de inventario">{[['existencias','Existencias'],['mermas','Mermas']].map(([k,l])=><button type="button" key={k} aria-pressed={query.seccion===k} onClick={()=>select(k)}>{l}</button>)}</div>
    {!stock&&<div className="inventory-state-tabs" role="group" aria-label="Estado de mermas">{[['','Aprobadas'],['PENDIENTE','Pendientes'],['RECHAZADA','Rechazadas']].map(([k,l])=><button type="button" className="btn btn-outline-secondary btn-sm" key={k} aria-pressed={query.estado===k} onClick={()=>{setDraft(prev=>({...prev,desde:'',hasta:''}));setError('');change({estado:k,desde:'',hasta:''});}}>{l}</button>)}</div>}
    {data&&<div className="table-responsive" role="region" aria-label={stock?'Existencias y valoración':pending?'Mermas pendientes':query.estado==='RECHAZADA'?'Mermas rechazadas':'Mermas aprobadas'} tabIndex={0}>
      <table className="table commercial-table inventory-manager-table"><thead><tr>{(stock?['Material','Stock disponible','Valor neto CLP','Situación']:['Material','Ámbito','Cantidad','Motivo','Fecha','Estado','Importe CLP']).map((x,i)=><th scope="col" key={x} className={stock?(i===2?'text-end':undefined):(i===6?'text-end':i===4?'inventory-merma-date':i===5?'inventory-merma-state':undefined)}>{x}</th>)}</tr></thead>
      <tbody>{data.results.map(row=><tr key={row.id}><td><strong>{row.nombre}</strong><span className="commercial-help d-block">{row.codigo}</span></td>{stock?<><td>{qty(row.saldo)} {row.unidad}</td><td className="text-end commercial-money">{row.pendiente_valoracion&&row.valor_neto==='0.00'&&row.saldo!=='0.000'?'—':formatCompactCLP(row.valor_neto)}{row.pendiente_valoracion&&<small className="d-block commercial-help">{row.valor_neto&&cents(row.valor_neto)>0n?'Valor parcial':'Sin valoración completa'}</small>}</td><td>{!row.activo&&<span className="chip gray">Inactivo</span>}{row.activo&&row.saldo==='0.000'&&<span className="chip red">Sin stock</span>}{row.pendiente_valoracion?<span className="chip amber">Pendiente de valoración</span>:row.activo&&row.saldo!=='0.000'&&<span className="chip green">Valorizado</span>}</td></>:<><td>{row.ambito==='BODEGA'?'Bodega':row.obra||'Obra'}</td><td>{qty(row.cantidad)} {row.unidad}</td><td><strong>{types[row.tipo]||'Otra'}</strong><small className="d-block commercial-help">{row.motivo}</small>{row.motivo_decision&&<small className="d-block commercial-help">Decisión: {row.motivo_decision}</small>}</td><td className="inventory-merma-date">{dateLocal(row.fecha)}</td><td className="inventory-merma-state"><span className={'chip '+(row.estado==='APROBADA'?'green':row.estado==='PENDIENTE'?'amber':'red')}>{({APROBADA:'Aprobada',PENDIENTE:'Pendiente',RECHAZADA:'Rechazada'})[row.estado]}</span></td><td className="text-end commercial-money">{formatCompactCLP(row.valor_neto)}{row.estado==='APROBADA'&&row.ambito==='OBRA'&&<small className="d-block commercial-help">Informativo</small>}</td></>}</tr>)}</tbody></table>
      {!data.count&&<p className="commercial-empty">No hay registros para estos filtros.</p>}
    </div>}
    {data&&(data.next||data.previous)&&<Pager label="Paginación de inventario" data={data} page={query.page} setPage={page=>setQuery(prev=>({...prev,page}))} disabled={api.loading}/>}
    {api.error?.status===404&&query.page!==1&&<button type="button" className="btn btn-outline-secondary" onClick={()=>change({})}>Volver a la primera página</button>}
  </section>
 </section>;
}
