import React, { useEffect, useState } from 'react';
import { useApp } from '../context/AppContext.jsx';
import { Chip } from '../components/ui';
import { Errors, Pager } from '../comercial/ui.jsx';
import { useApi, strictObject, decimalString, positiveInteger } from '../integrations/useApi.js';
import { readPage, obraPath } from './api.js';
import { OBRA_STATES, shortDate, timestamp } from './domain.js';
import { ObraStatus } from './ui.jsx';
import { formatCompactCLP } from '../utils/format.js';
import TecIcon from './TecIcon.jsx';
import '../styles/pages/obras-finanzas.css';

const PATH='/api/finanzas/obras-resumen/';
const FINANCE={
  NO_HABILITADA:['No habilitada','gray'], PENDIENTE_VALIDACION:['Revisión necesaria','amber'],
  PENDIENTE_FACTURACION:['Pendiente de facturación','amber'],
  PENDIENTE_REGISTRO_SIN_COBRO:['Pendiente de cierre sin cobro','amber'],
  DOCUMENTADO:['Facturada','blue'], SIN_COBRO:['Sin cobro','gray'],
};
const COLLECTION_KEYS=['id','codigo','presupuesto','presupuesto_codigo','cliente','cliente_nombre','categoria_servicio','categoria_nombre','tecnico_responsable','tecnico_nombre','fecha_programada','iniciado_en','estado','finalizado_en','monto_neto_aprobado','situacion_financiera'];
const EMPTY={buscar:'',estado:'',situacion_financiera:'',cliente_nombre:'',categoria_nombre:'',responsable_nombre:''};
const CASH_STATES={PENDIENTE:'Pendiente de pago',PARCIAL:'Pago parcial',PAGADA:'Pagada',VENCIDA:'Vencida'};
function shape(row, detail=false){
  strictObject(row,detail?[...COLLECTION_KEYS,'documento']:COLLECTION_KEYS);
  if(!positiveInteger(row.id)||!positiveInteger(row.presupuesto)||!positiveInteger(row.cliente)||!OBRA_STATES[row.estado]||!FINANCE[row.situacion_financiera]||!decimalString(row.monto_neto_aprobado)||typeof row.cliente_nombre!=='string') throw new Error('Resumen financiero de obra inválido.');
  if(detail&&row.documento!==null){
    strictObject(row.documento,['folio','monto_total','cobranza']);
    const c=row.documento.cobranza;strictObject(c,['moneda','abonado','saldo','estado']);
    if(c.moneda!=='CLP'||!CASH_STATES[c.estado]||![row.documento.monto_total,c.abonado,c.saldo].every(v=>decimalString(v))) throw new Error('Documento financiero inválido.');
  }
  return row;
}
function costShape(data,id){
  strictObject(data,['obra','materiales_total','otros_total','mano_obra_total','costo_total','costos_validados','cortesia_sin_cobro']);
  if(data.obra!==id||!['materiales_total','otros_total','mano_obra_total','costo_total'].every(k=>decimalString(data[k]))||typeof data.costos_validados!=='boolean'||typeof data.cortesia_sin_cobro!=='boolean') throw new Error('Resumen de costos inválido.');
  return data;
}
function FinancialStatus({state}){const [label,color]=FINANCE[state];return <Chip cls={color}>{label}</Chip>;}
function Btn({icon,children,...props}){return <button type="button" className="btn btn-outline-secondary of-button" {...props}>{icon&&<TecIcon name={icon}/>} {children}</button>;}
function Fact({label,value}){return <div className="of-fact"><dt>{label}</dt><dd>{value}</dd></div>;}
function Detail({id,onBack}){
  const api=useApi(), app=useApp();
  const [row,setRow]=useState(null),[cost,setCost]=useState(null);
  async function load(){
    api.setError(null);setRow(null);setCost(null);
    let work, costs;
    const results=await Promise.all([
      api.load('obra',PATH+id+'/',v=>{work=shape(v,true);if(work.id!==id)throw new Error('Obra inesperada.');}),
      api.load('costs',obraPath(id)+'costos/resumen/',v=>{costs=costShape(v,id);}),
    ]);
    if(results.every(Boolean)&&work&&costs){setRow(work);setCost(costs);}
  }
  useEffect(()=>{void load();},[id]);
  return <section className="of-detail">
    <div className="of-heading"><Btn icon="back" onClick={onBack}>Volver a obras</Btn><Btn icon="refresh" disabled={api.loading} onClick={()=>void load()}>Actualizar</Btn></div>
    <Errors error={api.error}/>{api.loading&&<p role="status">Cargando resumen económico…</p>}
    {row&&cost&&<>
      <section className="card-fyag of-panel"><div className="of-heading"><div><h1>{row.codigo}</h1><h2>{row.cliente_nombre}</h2><p className="commercial-help">{row.categoria_nombre} · {row.presupuesto_codigo}</p></div><ObraStatus state={row.estado}/></div>
        <div className="of-metrics"><div><small>Presupuesto aprobado · Neto</small><strong>{formatCompactCLP(row.monto_neto_aprobado)}</strong></div><div><small>Costo real registrado · Neto</small><strong>{formatCompactCLP(cost.costo_total)}</strong><small>{cost.costos_validados?'Costos validados':'Importe provisional'}</small></div></div>
        {app&&<div className="of-actions"><Btn onClick={()=>app.go('presupuestos',{presupuesto:row.presupuesto})}>Ver presupuesto {row.presupuesto_codigo}</Btn></div>}
      </section>
      <div className="of-detail-grid">
        <section className="card-fyag of-panel"><h2>Desglose de costos</h2><dl>
          <Fact label="Materiales" value={formatCompactCLP(cost.materiales_total)}/><Fact label="Mano de obra" value={formatCompactCLP(cost.mano_obra_total)}/><Fact label="Otros gastos" value={formatCompactCLP(cost.otros_total)}/><Fact label="Costo real total" value={<strong>{formatCompactCLP(cost.costo_total)}</strong>}/><Fact label="Validación" value={cost.costos_validados?'Validado':'Pendiente de validación'}/></dl>
        </section>
        <section className="card-fyag of-panel"><h2>Situación financiera</h2><FinancialStatus state={row.situacion_financiera}/>
          <p className="commercial-help mt-2">{({NO_HABILITADA:'La obra aún no está habilitada para facturar.',PENDIENTE_VALIDACION:'Requiere revisar el cierre operativo o el presupuesto.',PENDIENTE_FACTURACION:'Obra habilitada para registrar la factura externa.',PENDIENTE_REGISTRO_SIN_COBRO:'Falta registrar el cierre administrativo sin cobro.',DOCUMENTADO:'Existe un documento de cobro vigente.',SIN_COBRO:'Cierre administrativo sin cobro registrado.'})[row.situacion_financiera]}</p>
          <dl><Fact label="Cortesía autorizada" value={cost.cortesia_sin_cobro?'Sí, sin cobro':'No'}/>{row.documento&&<><Fact label="Folio de factura" value={row.documento.folio}/><Fact label="Total documento (con impuestos)" value={formatCompactCLP(row.documento.monto_total)}/><Fact label="Pagado" value={formatCompactCLP(row.documento.cobranza.abonado)}/><Fact label="Saldo por cobrar" value={formatCompactCLP(row.documento.cobranza.saldo)}/><Fact label="Estado de cobranza" value={CASH_STATES[row.documento.cobranza.estado]}/></>}</dl>
          {app&&['DOCUMENTADO','PENDIENTE_FACTURACION','PENDIENTE_REGISTRO_SIN_COBRO'].includes(row.situacion_financiera)&&<Btn onClick={()=>app.go('cobranzas',{obra:row.id,documentos:row.situacion_financiera!=='DOCUMENTADO'})}>{row.situacion_financiera==='DOCUMENTADO'?'Ver cobranza de esta obra':'Ir a documentos y pagos'}</Btn>}
        </section>
      </div>
      <section className="card-fyag of-panel"><h2>Información operativa</h2><dl className="of-operational"><Fact label="Categoría" value={row.categoria_nombre}/><Fact label="Responsable" value={row.tecnico_nombre||'Sin asignar'}/><Fact label="Fecha programada" value={shortDate(row.fecha_programada)}/><Fact label="Inicio efectivo" value={timestamp(row.iniciado_en)}/><Fact label="Finalización" value={timestamp(row.finalizado_en)}/></dl></section>
    </>}
  </section>;
}
export default function FinanzasObras(){
  const api=useApi();
  const [draft,setDraft]=useState(EMPTY),[filters,setFilters]=useState(EMPTY),[page,setPage]=useState(1),[data,setData]=useState(null),[expanded,setExpanded]=useState(false),[selected,setSelected]=useState(null);
  function load(){
    api.setError(null);setData(null);
    const params=new URLSearchParams({page:String(page)});
    Object.entries(filters).forEach(([key,value])=>{if(value)params.set(key,value);});
    return api.load('list',PATH+'?'+params,result=>{const p=readPage(result,PATH);setData({...p,results:p.results.map(v=>shape(v))});});
  }
  useEffect(()=>{if(!selected)void load();},[filters,page,selected]);
  const change=(k,v)=>setDraft(previous=>({...previous,[k]:v}));
  function apply(e){e.preventDefault();setPage(1);setFilters(Object.fromEntries(Object.entries(draft).map(([k,v])=>[k,v.trim()])));}
  if(selected)return <section className="commercial-page obras-page obras-finanzas"><Detail key={selected} id={selected} onBack={()=>setSelected(null)}/></section>;
  return <section className="commercial-page obras-page obras-finanzas">
    <header className="of-heading"><div><h1>Obras</h1><p className="commercial-help">Consulta el estado económico y la facturación de cada obra.</p></div><Btn icon="refresh" disabled={api.loading} onClick={()=>void load()}>Actualizar</Btn></header>
    <section className="card-fyag of-panel of-list">
      <form onSubmit={apply}>
        <div className="of-toolbar"><label className="of-search"><span>Buscar obra</span><input className="form-control" placeholder="Código, cliente o categoría" value={draft.buscar} maxLength={150} onChange={e=>change('buscar',e.target.value)}/></label><label>Estado operativo<select className="form-select" value={draft.estado} onChange={e=>change('estado',e.target.value)}><option value="">Todos</option>{Object.entries(OBRA_STATES).map(([k,[v]])=><option key={k} value={k}>{v}</option>)}</select></label><label>Facturación<select className="form-select" value={draft.situacion_financiera} onChange={e=>change('situacion_financiera',e.target.value)}><option value="">Todas</option>{Object.entries(FINANCE).map(([k,[v]])=><option key={k} value={k}>{v}</option>)}</select></label><Btn icon="filter" aria-expanded={expanded} onClick={()=>setExpanded(v=>!v)}>Filtros</Btn><button className="btn btn-fyag-primary" disabled={api.loading} type="submit">Buscar</button></div>
        {expanded&&<div className="of-extra-filters">{[['cliente_nombre','Cliente'],['categoria_nombre','Categoría'],['responsable_nombre','Responsable']].map(([key,label])=><label key={key}>{label}<input className="form-control" value={draft[key]} maxLength={150} onChange={e=>change(key,e.target.value)} placeholder={'Nombre de '+label.toLowerCase()}/></label>)}</div>}
        {Object.values(draft).some(Boolean)||Object.values(filters).some(Boolean)?<div className="of-actions"><Btn disabled={api.loading} onClick={()=>{setDraft(EMPTY);setFilters(EMPTY);setPage(1);}}>Limpiar filtros</Btn></div>:null}
      </form>
      <Errors error={api.error}/>{api.loading&&<p role="status">Cargando obras…</p>}
      {data&&<><div className="commercial-table-frame"><div className="table-responsive" role="region" aria-label="Listado de obras" tabIndex={0}><table className="table table-hover align-middle commercial-table"><thead><tr><th scope="col">Obra / Cliente</th><th scope="col">Estado operativo</th><th scope="col" className="text-end">Presupuesto neto (CLP)</th><th scope="col">Facturación</th><th scope="col">Detalle</th></tr></thead><tbody>{data.results.map(row=><tr key={row.id}><td><strong>{row.codigo}</strong><span className="of-client">{row.cliente_nombre}</span><small className="commercial-help">{row.categoria_nombre}</small></td><td><ObraStatus state={row.estado}/></td><td className="commercial-money">{formatCompactCLP(row.monto_neto_aprobado)}</td><td><FinancialStatus state={row.situacion_financiera}/></td><td><Btn disabled={api.loading} onClick={()=>setSelected(row.id)}>Ver obra</Btn></td></tr>)}</tbody></table></div>{!data.count&&<div className="commercial-empty"><h2>No se encontraron obras</h2><p>Prueba otra búsqueda o limpia los filtros.</p></div>}</div><p className="of-count">{data.count} obras encontradas</p>{(data.next||data.previous)&&<Pager data={data} page={page} setPage={setPage} disabled={api.loading} label="Paginación de obras"/>}</>}
      {api.error?.status===404&&page!==1&&<Btn onClick={()=>setPage(1)}>Volver a la primera página</Btn>}
    </section>
  </section>;
}
