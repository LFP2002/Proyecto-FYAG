import React, { useEffect, useState } from 'react';
import { useApi, positiveInteger, strictObject } from '../integrations/useApi.js';
import { ApiError } from '../auth/client.js';
import { eligibleMaterialPath, validatePage } from './api.js';
import { Errors, Pager } from './ui.jsx';

const PATH='/api/presupuestos/materiales-elegibles/';

export default function MaterialPicker({ disabled, onSelect, onCancel, currentId, compact = false }) {
  const api=useApi();
  const [query,setQuery]=useState('');
  const [search,setSearch]=useState('');
  const [page,setPage]=useState(1);
  const [data,setData]=useState(null);
  const [reload,setReload]=useState(0);
  useEffect(()=>{
    setData(null);
    api.setError(null);
    void api.load('materials',eligibleMaterialPath(page,search),(value)=>{
      const valid=validatePage(value,PATH);
      if(valid.results.length>25)throw new ApiError(502,'Página de materiales inválida.');
      for(const row of valid.results){
        strictObject(row,['id','codigo','nombre','unidad']);
        if(!positiveInteger(row.id)||typeof row.codigo!=='string'||!row.codigo||typeof row.nombre!=='string'||!row.nombre.trim()||typeof row.unidad!=='string'||!row.unidad.trim())throw new ApiError(502,'Material no válido.');
      }
      setData(valid);
    });
    return ()=>api.cancelRead('materials');
  },[page,search,reload]);
  return <section className={compact?"budget-material-picker":"card-fyag my-2"} aria-label="Selector de materiales de Bodega">
    <h3 className="h5">{compact?"Seleccionar material":"Materiales de Bodega"}</h3>
    <p className="commercial-help">Selecciona un material activo. Cotizar no descuenta existencias.</p>
    <form className="d-flex flex-wrap align-items-end gap-2" onSubmit={e=>{e.preventDefault();setPage(1);setSearch(query.trim());setReload(r=>r+1);}}>
      <label className="form-label flex-grow-1 mb-0">Buscar por código o nombre<input className="form-control" placeholder="Nombre o código" value={query} maxLength={150} disabled={disabled} onChange={e=>setQuery(e.target.value)}/></label>
      <button type="submit" className="btn btn-fyag-primary" disabled={disabled||api.loading}>Buscar</button>
      {!compact&&<button type="button" className="btn btn-outline-secondary" disabled={disabled} onClick={onCancel}>Cerrar catálogo</button>}
    </form>
    <Errors error={api.error}/>
    {api.loading&&<p role="status">Cargando materiales…</p>}
    {data&&data.count===0&&<p className="commercial-help mt-3">No hay materiales activos que coincidan.</p>}
    <div className={"list-group mt-2"+(compact?" budget-material-results":"")}>{data?.results.map(row=><div className="list-group-item d-flex flex-wrap align-items-center justify-content-between gap-2" key={row.id}>
      <div className="text-break"><strong>{row.nombre}</strong><div className="commercial-help">{row.codigo} · Unidad: {row.unidad}</div></div>
      <button type="button" className="btn btn-outline-secondary btn-sm" disabled={disabled||api.loading||row.id===currentId} aria-label={'Seleccionar '+row.nombre} onClick={()=>onSelect(row)}>{row.id===currentId?'Seleccionado':'Seleccionar'}</button>
    </div>)}</div>
    {data&&(!compact||data.previous||data.next)&&<Pager data={data} page={page} setPage={setPage} disabled={disabled||api.loading} label="Paginación de materiales"/>}
    {compact&&<div className="budget-item-footer"><button type="button" className="btn btn-outline-secondary" disabled={disabled} onClick={onCancel}>Cancelar</button></div>}
  </section>;
}
