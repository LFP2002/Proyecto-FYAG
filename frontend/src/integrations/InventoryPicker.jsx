import React, { useEffect, useState } from 'react';
import { useApi, positiveInteger } from './useApi.js';
import { Errors, Pager } from '../comercial/ui.jsx';
import { validatePage } from '../comercial/api.js';

const ROOT='/api/inventario/';
const sources={
  articulo:{path:ROOT+'articulos/',text:r=>r.nombre+' · '+r.codigo+' · '+r.unidad},
  ingreso:{path:ROOT+'movimientos/',params:{tipo:'INGRESO'},text:r=>'Ingreso #'+r.id+' · Artículo #'+r.articulo+' · '+r.cantidad+(r.referencia?' · '+r.referencia:'')},
  obra:{path:'/api/obras/',text:r=>(r.codigo||'Obra #'+r.id)+(r.cliente_nombre?' · '+r.cliente_nombre:'')},
  entrega:{path:ROOT+'entregas/',text:r=>'Entrega #'+r.id+' · Obra #'+r.obra+' · '+r.cantidad+' '+r.unidad+(r.referencia?' · '+r.referencia:'')},
  autorizacionEntrega:{path:ROOT+'autorizaciones-entrega/',text:r=>'Autorización #'+r.id+' · Obra #'+r.obra+' · '+r.cantidad+' '+r.unidad+(r.referencia?' · '+r.referencia:'')},
  autorizacionDevolucion:{path:ROOT+'autorizaciones-devolucion/',text:r=>'Devolución #'+r.id+' · Obra #'+r.obra+' · '+r.cantidad+' '+r.unidad+(r.referencia?' · '+r.referencia:'')},
};

export default function InventoryPicker({ kind='articulo', label, value, onChange, disabled=false, required=false, activeOnly=false, compact=false, onSelect }) {
  const api=useApi(), source=sources[kind];
  const [page,setPage]=useState(1),[data,setData]=useState(null),[search,setSearch]=useState(''),[chosen,setChosen]=useState(null),[reload,setReload]=useState(0);
  useEffect(()=>{
    setData(null);api.setError(null);
    const query=new URLSearchParams({page:String(page),...source.params});
    if(kind==='articulo'){
      if(activeOnly)query.set('activo','true');
      if(search.trim())query.set('buscar',search.trim());
    }
    void api.load('choices',source.path+'?'+query,v=>{
      const result=validatePage(v,source.path);
      if(result.results.length>25||result.results.some(r=>!positiveInteger(r.id)))throw new Error('Opciones inválidas.');
      setData(result);
    });
    return ()=>api.cancelRead('choices');
  },[kind,page,search,activeOnly,reload]);
  const rows=data?.results||[];
  const selected=String(value||'');
  return <div className={compact?"obras-selector so-material-picker":"obras-selector"}>
    {kind==='articulo'&&<label className="form-label">Buscar material<input className="form-control" type="search" maxLength={150} value={search} disabled={disabled} onChange={e=>{setPage(1);setSearch(e.target.value);}} placeholder="Nombre o código"/></label>}
    <label className="form-label">{label}<select className="form-select" required={required} disabled={disabled||api.loading} value={selected} onChange={e=>{
      const next=e.target.value;const row=rows.find(r=>String(r.id)===next)||null;setChosen(row);onChange(next);onSelect?.(row);
    }}><option value="">{required?'Selecciona una opción':'Todos'}</option>
      {rows.map(r=><option key={r.id} value={String(r.id)}>{source.text(r)}</option>)}
      {selected&&!rows.some(r=>String(r.id)===selected)&&<option value={selected}>{chosen&&String(chosen.id)===selected?source.text(chosen):'Seleccionado #'+selected}</option>}
    </select></label>
    <Errors error={api.error}/>
    {api.error&&<button type="button" className="btn btn-outline-secondary btn-sm" disabled={disabled||api.loading} onClick={()=>setReload(n=>n+1)}>Reintentar consulta</button>}
    {api.loading&&<p role="status" className="commercial-help">Cargando opciones…</p>}
    {data&&(!compact||data.previous||data.next)&&<Pager data={data} page={page} setPage={setPage} disabled={disabled||api.loading} label={'Páginas de '+label.toLowerCase()}/>}
    {data&&data.count===0&&<p className="commercial-help">No hay opciones disponibles.</p>}
  </div>;
}
