import React, { useEffect, useRef, useState } from 'react';
import TecIcon from '../obras/TecIcon.jsx';
import { civilDate } from '../obras/tecnicoDomain.js';
import '../styles/pages/tecnico.css';
import '../styles/pages/supervisor-obras.css';
import {SupervisorEmpty} from '../obras/SupervisorCostReview.jsx';
import { useAuth } from '../auth/AuthContext';
import { collectionPath, obraPath, readPage } from '../obras/api.js';
import { canReadObras, G, emptyFilters, filterErrors, OBRA_STATES, orderingOptions, projectObra, S, T } from '../obras/domain.js';
import Categories from '../obras/Categories.jsx';
import NewObra from '../obras/ObraForm.jsx';
import ObraDetail from '../obras/ObraDetail.jsx';
import FinanzasObras from '../obras/FinanzasObras.jsx';
import GerenciaPanel from '../obras/GerenciaPanel.jsx';
import { Feedback, Field, focusError, ObraStatus, Pager, useOperational } from '../obras/ui.jsx';

export default function Obras() {
  const {user}=useAuth();
  return user.role===G?<GerenciaPanel key={user.id}/>:user.role==='ADMINISTRATIVO_FINANZAS'?<FinanzasObras key={user.id}/>:<ObrasOperativas key={user.id+':'+user.role}/>;
}
function ObrasOperativas() {
  const { user } = useAuth(), api = useOperational();
  const [query, setQuery] = useState({ filters: { ...emptyFilters }, page: 1 });
  const [draft, setDraft] = useState({ ...emptyFilters }), [errors, setErrors] = useState({});
  const [search,setSearch]=useState('');
  const technician=user.role===T,supervisor=user.role===S;
  const extraFilters=Object.entries(query.filters).some(([k,v])=>k!=='estado'&&Boolean(v));
  const emptyWorkTitles={EN_PROCESO:'No tienes obras en ejecución',PLANIFICADA:'No tienes obras programadas',SUSPENDIDA:'No tienes obras suspendidas',FINALIZADA:'No tienes obras finalizadas',CANCELADA:'No tienes obras canceladas'};
  const [data, setData] = useState(null), [selected, setSelected] = useState(null), [selectedSection, setSelectedSection] = useState('resumen'), [creating, setCreating] = useState(false), [categories, setCategories] = useState(false), [expanded, setExpanded] = useState(false);
  const refreshFlight = useRef(false);
  function openObra(id){setSelectedSection('resumen');setSelected(id);}
  const path = user.role === T ? `${obraPath()}mis-obras/` : obraPath();
  const read = () => { setData(null); return api.load('list', collectionPath(path, query.page, query.filters), (result) => {
    const page = readPage(result, path); setData({ ...page, results: page.results.map((row) => projectObra(row, user.role)) });
  }); };
  useEffect(() => { setData(null); if (canReadObras(user.role)) void read(); }, [query]);
  async function refresh() {
    if (refreshFlight.current || api.busy || api.loading) return;
    refreshFlight.current = true;
    try { await api.reconcile(read); } finally { refreshFlight.current = false; }
  }
  function apply(event) {
    event.preventDefault();
    const invalid = filterErrors(draft); if(supervisor&&(/[\x00-\x1f]/.test(search.trim())||search.trim().length>150))invalid.buscar='Búsqueda no válida.'; setErrors(invalid); focusError(event, invalid);
    if (!Object.keys(invalid).length) { api.setError(null); setQuery({ filters: { ...draft, ...((technician||supervisor)&&search.trim()?{buscar:search.trim()}: {}) }, page: 1 }); if(technician||supervisor)setExpanded(false); }
  }
  const blocked = api.busy || api.loading || api.locked;
  if (!canReadObras(user.role)) return <p role="alert">No tienes acceso a Obras.</p>;
  if (categories && user.role === S) return <section className="commercial-page obras-page supervisor-obras"><Categories onBack={() => setCategories(false)} /></section>;
  if (selected) return <section className={'commercial-page obras-page'+(technician?' tecnico-page':supervisor?' supervisor-obras':'')}><ObraDetail key={`${user.id}:${user.role}:${selected}`} id={selected} initialTab={selectedSection} onBack={() => { setSelected(null); setSelectedSection('resumen'); void read(); }} /></section>;
  if(technician) return <section className="commercial-page obras-page tecnico-page">
    <header className="tec-heading"><div><h1>Mis obras</h1><p>Consulta tus trabajos asignados.</p></div><button type="button" className="btn btn-outline-secondary tec-button" aria-label="Actualizar datos" disabled={api.busy||api.loading} onClick={refresh}><TecIcon name="refresh"/>Actualizar</button></header>
    <div className="tec-tabs" role="group" aria-label="Estado de mis obras">{[['','Todas'],['EN_PROCESO','En ejecución'],['PLANIFICADA','Programadas'],['SUSPENDIDA','Suspendidas'],['FINALIZADA','Finalizadas'],['CANCELADA','Canceladas']].map(([key,label])=><button key={key} type="button" aria-pressed={query.filters.estado===key} disabled={blocked} onClick={()=>{setDraft(old=>({...old,estado:key}));setQuery({filters:{...query.filters,estado:key},page:1});}}>{label}</button>)}</div>
    <section className="card-fyag tec-panel"><form className="tec-search" onSubmit={apply}><input className="form-control" aria-label="Buscar obra o cliente" placeholder="Código de obra, cliente o categoría" value={search} maxLength={150} disabled={blocked} onChange={e=>setSearch(e.target.value)}/><button className="btn btn-outline-secondary tec-button" disabled={blocked}><TecIcon name="search"/>Buscar</button><button type="button" className="btn btn-outline-secondary tec-button" aria-expanded={expanded} disabled={blocked} onClick={()=>setExpanded(v=>!v)}><TecIcon name="filter"/>Filtros</button></form>
    {expanded&&<form className="tec-filters" onSubmit={apply}><Field name="fecha_programada_desde" label="Programada desde" type="date" value={draft.fecha_programada_desde} onChange={value=>setDraft({...draft,fecha_programada_desde:value})} error={errors.fecha_programada_desde}/><Field name="fecha_programada_hasta" label="Programada hasta" type="date" value={draft.fecha_programada_hasta} onChange={value=>setDraft({...draft,fecha_programada_hasta:value})} error={errors.fecha_programada_hasta}/><Field name="ordering" label="Ordenar por" value={draft.ordering} options={orderingOptions.map(([k,v])=>[k,k?v:'Prioridad operativa'])} onChange={ordering=>setDraft({...draft,ordering})}/><button className="btn btn-fyag-primary" disabled={blocked}>Aplicar filtros</button></form>}
    {extraFilters&&<div className="tec-row"><small>Filtros aplicados</small><button type="button" className="btn btn-outline-secondary btn-sm" disabled={blocked} onClick={()=>{setSearch('');setDraft({...emptyFilters,estado:query.filters.estado});setErrors({});setQuery({filters:{...emptyFilters,estado:query.filters.estado},page:1});}}>Limpiar filtros</button></div>}
    <Feedback api={api}/>
    {data?.results.length>0&&<div className="tec-work-grid">{data.results.map(obra=><article key={obra.id} className="tec-work"><div className="tec-row"><strong className="tec-code">{obra.codigo}</strong><ObraStatus state={obra.estado}/></div><div><h2>{obra.cliente_nombre}</h2><small>{obra.categoria_nombre}</small></div><p className="tec-description">{obra.descripcion}</p><div className="tec-facts"><div><small><TecIcon name="calendar"/> Programación</small><strong>{civilDate(obra.fecha_programada)}</strong></div><div><small><TecIcon name="person"/> Responsable</small><strong>{obra.tecnico_nombre||'Sin asignar'}</strong></div></div><div className="tec-card-actions"><button type="button" className="btn btn-outline-secondary tec-button" disabled={blocked} onClick={()=>{setSelectedSection('turnos');setSelected(obra.id);}}>Ver mis turnos</button><button type="button" className="btn btn-fyag-primary tec-button" disabled={blocked} onClick={()=>openObra(obra.id)}>Ver obra<TecIcon name="chevron"/></button></div></article>)}</div>}
    {data&&!data.count&&!api.error&&!api.loading&&<div className="tec-empty" role="status"><TecIcon name="inbox"/><strong>{extraFilters?'No hay resultados':emptyWorkTitles[query.filters.estado]||'No tienes obras asignadas.'}</strong><p>{extraFilters?'Prueba con otros filtros.':query.filters.estado?'Las obras con este estado aparecerán aquí.':'Las obras asignadas aparecerán aquí.'}</p></div>}
    {data&&(data.next||data.previous)&&<Pager label="Paginación de obras" data={data} page={query.page} setPage={page=>setQuery({...query,page})} disabled={blocked}/>}
    {api.error?.status===404&&query.page!==1&&<button className="btn btn-outline-secondary" onClick={()=>setQuery({...query,page:1})}>Volver a la primera página</button>}
    </section></section>;
  if(supervisor&&creating)return <section className="commercial-page obras-page supervisor-obras"><div className="so-section-head"><h1 className="so-module-title">Nueva obra</h1></div><NewObra onClose={()=>setCreating(false)} onCreated={id=>{setCreating(false);setSelectedSection('resumen');setSelected(id);}}/></section>;
  return <section className="commercial-page obras-page supervisor-obras">
    <header className="so-heading"><div><h1>Obras</h1><p className="commercial-help">Planifica, coordina y supervisa la ejecución de los trabajos.</p></div><div className="so-actions"><button type="button" className="btn btn-outline-secondary" disabled={blocked} onClick={refresh} aria-label="Actualizar datos"><TecIcon name="refresh"/> Actualizar</button><button type="button" className="btn btn-fyag-primary" disabled={blocked} onClick={()=>{setExpanded(false);setCreating(true);}}><TecIcon name="plus"/> Nueva obra</button></div></header>
    <div className="so-section-head"><button type="button" className="btn btn-outline-secondary" disabled={blocked} onClick={()=>setCategories(true)}>Categorías de servicio</button></div>
    <nav className="so-tabs" aria-label="Estado de las obras">{[['','Todas'],['EN_PROCESO','En proceso'],['PLANIFICADA','Planificadas'],['SUSPENDIDA','Suspendidas'],['FINALIZADA','Finalizadas'],['CANCELADA','Canceladas']].map(([state,label])=><button key={state} type="button" aria-pressed={query.filters.estado===state} disabled={blocked} onClick={()=>{setDraft(old=>({...old,estado:state}));setQuery({filters:{...query.filters,estado:state},page:1});}}>{label}</button>)}</nav>
    <section className="card-fyag so-list">
      <form className="so-list-filter" noValidate onSubmit={apply}>
        <div className="so-search-row"><Field name="buscar" label="Buscar obra" value={search} maxLength={150} disabled={blocked} error={errors.buscar} onChange={setSearch}/><button className="btn btn-fyag-primary" type="submit" disabled={blocked}><TecIcon name="search"/> Buscar</button><button type="button" className="btn btn-outline-secondary" aria-expanded={expanded} aria-controls="obras-filters" disabled={blocked} onClick={()=>setExpanded(v=>!v)}><TecIcon name="filter"/> Filtros</button></div>
        <p className="commercial-help">Busca por código de obra, cliente, categoría o responsable.</p>
        {expanded&&<div id="obras-filters" className="so-filter-fields"><Field name="fecha_programada_desde" label="Programada desde" type="date" value={draft.fecha_programada_desde} onChange={v=>setDraft({...draft,fecha_programada_desde:v})} error={errors.fecha_programada_desde}/><Field name="fecha_programada_hasta" label="Programada hasta" type="date" value={draft.fecha_programada_hasta} onChange={v=>setDraft({...draft,fecha_programada_hasta:v})} error={errors.fecha_programada_hasta}/><Field name="ordering" label="Ordenar por" value={draft.ordering} options={orderingOptions.map(([key,label])=>[key,key?label:'Prioridad operativa'])} onChange={ordering=>setDraft({...draft,ordering})} error={errors.ordering}/><button type="submit" className="btn btn-fyag-primary" disabled={blocked}>Aplicar filtros</button></div>}
        {extraFilters||search||Object.values(draft).some(Boolean)&&draft.estado!==query.filters.estado?<div className="so-section-head"><small className="commercial-help">{extraFilters?'Filtros aplicados':''}</small><button type="button" className="btn btn-outline-secondary btn-sm" disabled={blocked} onClick={()=>{setSearch('');setDraft({...emptyFilters,estado:query.filters.estado});setErrors({});api.setError(null);setQuery({filters:{...emptyFilters,estado:query.filters.estado},page:1});}}>Limpiar filtros</button></div>:null}
      </form>
      <Feedback api={api}/>
      {data?.results.length>0&&<div className="table-responsive" role="region" aria-label="Listado de obras" tabIndex={0}><table className="table table-hover align-middle commercial-table so-works-table"><thead><tr>{['Obra / Cliente','Responsable','Estado','Programación','Detalle'].map(label=><th scope="col" key={label}>{label}</th>)}</tr></thead><tbody>{data.results.map(obra=><tr key={obra.id}><td><strong>{obra.codigo}</strong><span className="so-client">{obra.cliente_nombre}</span><small className="commercial-help">{obra.categoria_nombre}</small></td><td>{obra.tecnico_nombre||<span className="so-warning-text">Sin asignar</span>}</td><td><ObraStatus state={obra.estado}/></td><td>{obra.fecha_programada?civilDate(obra.fecha_programada):<span className="so-warning-text">Sin programar</span>}</td><td><button type="button" className="btn btn-outline-secondary btn-sm" disabled={blocked} onClick={()=>openObra(obra.id)}>Ver obra</button></td></tr>)}</tbody></table></div>}
      {data&&!data.count&&!api.error&&<SupervisorEmpty title="No hay obras para esta consulta" description="Prueba con otros filtros o crea una obra desde un presupuesto aceptado."/>}
      {data&&(data.next||data.previous)&&<Pager label="Paginación de obras" data={data} page={query.page} setPage={page=>setQuery({...query,page})} disabled={blocked}/>}
      {api.error?.status===404&&query.page!==1&&<button className="btn btn-outline-secondary m-3" onClick={()=>setQuery({...query,page:1})}>Volver a la primera página</button>}
    </section>
  </section>;
}