import React,{useEffect,useState} from 'react';
import {PageHead} from '../components/ui/index.js';
import {useCommercial,Errors,Pager} from '../comercial/ui.jsx';
import {formatCompactCLP,formatCivilDate} from '../utils/format.js';

const ROOT='/api/inventario/supervision-gerencial/';
const INITIAL={seccion:'existencias',filtro:'',buscar:'',page:1};
const count=v=>Number.isSafeInteger(v)&&v>=0;
const money=v=>typeof v==='string'&&/^\d+\.\d{2}$/.test(v);
const quantity=v=>typeof v==='string'&&/^\d+\.\d{3}$/.test(v);
const civil=v=>typeof v==='string'&&/^\d{4}-\d{2}-\d{2}$/.test(v);
const qty=v=>quantity(v)?v.replace(/0+$/,'').replace(/\.$/,'').replace('.',','):'—';
const types={DANO:'Daño',VENCIMIENTO:'Vencimiento',EXTRAVIO:'Extravío',DIFERENCIA_CONTEO:'Diferencia de conteo',OTRA:'Otra',CORTE_NO_REUTILIZABLE:'Corte no reutilizable',DANO_EN_OBRA:'Daño en obra',EXTRAVIO_EN_OBRA:'Extravío en obra'};
function validate(data,section){
 const s=data?.resumen;
 if(!s||!count(data.count)||!Array.isArray(data.results)||data.results.length>25||!['sin_stock','pendientes_valoracion','mermas_bodega','mermas_obra','mermas_sin_valor','mermas_pendientes'].every(k=>count(s[k]))||!['valor_stock_valorado','mermas_bodega_neto','mermas_obra_informativo'].every(k=>money(s[k]))||!civil(s.desde)||!civil(s.hasta))throw Error('No se pudieron confirmar los indicadores de inventario.');
 for(const row of data.results){
  if(!Number.isSafeInteger(row.id)||row.id<1||typeof row.nombre!=='string'||typeof row.codigo!=='string'||typeof row.unidad!=='string'||!(row.valor_neto===null||money(row.valor_neto))||(section==='existencias'?!(row.saldo===null||quantity(row.saldo))||typeof row.activo!=='boolean'||typeof row.pendiente_valoracion!=='boolean':!quantity(row.cantidad)||!['BODEGA','OBRA'].includes(row.ambito)||typeof row.fecha!=='string'))throw Error('No se pudieron confirmar los registros de inventario.');
 }
 return data;
}
function Metric({label,value,detail,tone,onClick,active,disabled}){
 const content=<><span>{label}</span><strong>{value}</strong>{detail&&<small>{detail}</small>}</>;
 return onClick?<button type="button" className={'portfolio-kpi portfolio-'+tone} aria-pressed={active} disabled={disabled} onClick={onClick}>{content}</button>:<div className={'portfolio-kpi portfolio-'+tone}>{content}</div>;
}
export default function GerenciaInventario(){
 const api=useCommercial(),[query,setQuery]=useState(INITIAL),[search,setSearch]=useState(''),[data,setData]=useState(null);
 const path=ROOT+'?'+new URLSearchParams(Object.entries(query).filter(([,v])=>v!=='')).toString();
 const read=()=>{setData(null);return api.load('inventory-manager',path,v=>setData(validate(v,query.seccion)));};
 useEffect(()=>{api.setError(null);void read();},[path]);
 const s=data?.resumen,stock=query.seccion==='existencias';
 const change=patch=>setQuery(prev=>({...prev,...patch,page:1}));
 const metric=(seccion,filtro)=>{change({seccion,filtro:query.seccion===seccion&&query.filtro===filtro?'':filtro});};
 return <section className="commercial-page manager-portfolio inventory-manager">
  <PageHead title="Inventario" sub="Supervisa las existencias, valoración y pérdidas de materiales."><button type="button" className="btn btn-outline-secondary" aria-label="Actualizar datos" disabled={api.loading} onClick={()=>void api.reconcile(read)}><svg width="16" height="16" viewBox="0 0 16 16" fill="currentColor" aria-hidden="true"><path fillRule="evenodd" d="M8 3a5 5 0 1 1-4.546 2.914.5.5 0 0 0-.908-.417A6 6 0 1 0 8 2z"/><path d="M8 4.466V.534a.25.25 0 0 0-.41-.192L5.23 2.308a.25.25 0 0 0 0 .384l2.36 1.966A.25.25 0 0 0 8 4.466"/></svg> Actualizar</button></PageHead>
  <Errors error={api.error}/>{api.loading&&<p role="status" className="commercial-loading">Cargando inventario…</p>}
  <div className="portfolio-kpis">
    <Metric label="Valor del stock valorizado" value={s?formatCompactCLP(s.valor_stock_valorado):'—'} detail="CLP · neto" tone="blue"/>
    <Metric label="Materiales sin stock" value={s?.sin_stock??'—'} detail="Materiales activos" tone="red" active={stock&&query.filtro==='sin_stock'} disabled={!s} onClick={()=>metric('existencias','sin_stock')}/>
    <Metric label="Mermas de bodega del mes" value={s?formatCompactCLP(s.mermas_bodega_neto):'—'} detail={s?s.mermas_bodega+' aprobadas · CLP neto':'CLP · neto'} tone="amber" active={!stock&&query.filtro==='bodega'} disabled={!s} onClick={()=>metric('mermas','bodega')}/>
    <Metric label="Pendientes de valoración" value={s?.pendientes_valoracion??'—'} detail="Materiales" tone="gray" active={stock&&query.filtro==='pendiente'} disabled={!s} onClick={()=>metric('existencias','pendiente')}/>
  </div>
  <section className="card-fyag inventory-mermas-summary">
    <div><h2>Mermas de obra del mes</h2><strong>{s?formatCompactCLP(s.mermas_obra_informativo):'—'}</strong><small>Importe informativo, ya incluido en el costo de materiales de obra.</small></div>
    <div><h2>Mermas pendientes de decisión</h2><strong>{s?.mermas_pendientes??'—'}</strong><small>Todos los períodos · a cargo de Finanzas o Supervisión.</small></div>
    {s?.mermas_sin_valor>0&&<p className="commercial-help">Hay {s.mermas_sin_valor} mermas aprobadas del mes sin importe disponible.</p>}
  </section>
  {s?.pendientes_valoracion>0&&<p className="commercial-help">El valor del stock incluye únicamente las cantidades valorizadas.</p>}
  <section className="card-fyag portfolio-list">
    <div className="portfolio-list-head"><div><h2>{stock?'Existencias y valoración':'Mermas aprobadas'}</h2><span>{stock?'Estado actual de los materiales':s?formatCivilDate(s.desde)+' – '+formatCivilDate(s.hasta):'Mes actual'}</span></div>
    <form className="portfolio-search" role="search" onSubmit={e=>{e.preventDefault();change({buscar:search.trim()});}}><input className="form-control" aria-label="Buscar material" placeholder="Código o nombre" maxLength={100} value={search} onChange={e=>setSearch(e.target.value)}/><button type="submit" className="btn btn-outline-secondary">Buscar</button></form></div>
    <div className="portfolio-filters"><div className="manager-work-tabs" role="group" aria-label="Secciones de inventario">{[['existencias','Existencias'],['mermas','Mermas']].map(([key,label])=><button type="button" key={key} aria-pressed={query.seccion===key} onClick={()=>change({seccion:key,filtro:''})}>{label}</button>)}</div>
      <select className="form-select" aria-label="Filtrar registros de inventario" value={query.filtro} onChange={e=>change({filtro:e.target.value})}><option value="">Todos</option>{(stock?[['sin_stock','Sin stock'],['pendiente','Pendientes de valoración']]:[['bodega','Bodega'],['obra','Obras']]).map(([key,label])=><option key={key} value={key}>{label}</option>)}</select>
      {(query.filtro||query.buscar)&&<button type="button" className="btn btn-outline-secondary btn-sm" onClick={()=>{setSearch('');change({filtro:'',buscar:''});}}>Limpiar filtros</button>}
    </div>
    {data&&<div className="table-responsive" role="region" aria-label={stock?'Existencias y valoración':'Mermas aprobadas'} tabIndex={0}>
      <table className="table commercial-table"><thead><tr>{(stock?['Material','Stock disponible','Valor neto CLP','Situación']:['Material','Ámbito','Cantidad','Motivo','Aprobación','Importe CLP']).map((x,i)=><th scope="col" key={x} className={i===2&&stock||i===5?'text-end':undefined}>{x}</th>)}</tr></thead>
      <tbody>{data.results.map(row=><tr key={row.id}><td><strong>{row.nombre}</strong><span className="commercial-help d-block">{row.codigo}</span></td>{stock?<><td>{qty(row.saldo)} {row.unidad}</td><td className="text-end commercial-money">{formatCompactCLP(row.valor_neto)}</td><td>{!row.activo&&<span className="chip gray">Inactivo</span>}{row.activo&&row.saldo==='0.000'&&<span className="chip red">Sin stock</span>}{row.pendiente_valoracion?<span className="chip amber">Pendiente de valoración</span>:row.activo&&row.saldo!=='0.000'&&<span className="chip green">Valorizado</span>}</td></>:<><td>{row.ambito==='BODEGA'?'Bodega':row.obra||'Obra'}</td><td>{qty(row.cantidad)} {row.unidad}</td><td>{types[row.tipo]||'Otra'}</td><td>{new Date(row.fecha).toLocaleDateString('es-CL')}</td><td className="text-end commercial-money">{formatCompactCLP(row.valor_neto)}{row.ambito==='OBRA'&&<small className="d-block commercial-help">Informativo</small>}</td></>}</tr>)}</tbody></table>
      {!data.count&&<p className="commercial-empty">No hay registros para estos filtros.</p>}
    </div>}
    {data&&(data.next||data.previous)&&<Pager label="Paginación de inventario" data={data} page={query.page} setPage={page=>setQuery(prev=>({...prev,page}))} disabled={api.loading}/>}
    {api.error?.status===404&&query.page!==1&&<button type="button" className="btn btn-outline-secondary" onClick={()=>change({})}>Volver a la primera página</button>}
  </section>
 </section>;
}
