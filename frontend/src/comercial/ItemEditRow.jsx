import React, { useRef, useState } from 'react';
import UnitField from './UnitField.jsx';
import MaterialPicker from './MaterialPicker.jsx';
import { money, validateItem } from './domain.js';
import { Errors } from './ui.jsx';

export function itemRowErrors(form, items, original) {
  const errors = validateItem(form);
  const messages = { descripcion: 'Máximo 2000 caracteres', cantidad: 'Ingresa una cantidad válida', unidad: 'Máximo 30 caracteres', precio_unitario: 'Ingresa un precio válido', orden: 'Ingresa un entero positivo válido' };
  for (const name of Object.keys(errors)) errors[name] = [String(form[name]).trim() ? messages[name] : 'Campo obligatorio'];
  if (items.some((item) => item.id !== original?.id && item.orden === Number(form.orden))) errors.orden = ['Orden ya utilizado'];
  return errors;
}

export default function ItemEditRow({ line, items, onChange, onSave, onCancel, disabled, busy, editable, error }) {
  const [attempted, setAttempted] = useState(false);
  const [picker, setPicker] = useState(line.mode === 'material');
  const [advanced,setAdvanced] = useState(false);
  const linked = line.form.articulo != null;
  const selectMaterial = (material) => {
    const changed = line.form.articulo !== material.id;
    onChange({ ...line.form, articulo: material.id, codigo_articulo: material.codigo, descripcion: material.nombre, unidad: material.unidad, ...(changed ? {cantidad:'', precio_unitario:''} : {}) });
    setPicker(false);
  };
  const row = useRef(null);
  const errors = attempted ? itemRowErrors(line.form, items, line.original) : {};
  const blocked = disabled || !editable;
  const save = (event) => {
    if (blocked || picker || (line.mode === 'material' && line.form.articulo === undefined)) return;
    setAttempted(true);
    const validation = itemRowErrors(line.form, items, line.original);
    const first = ['descripcion', 'cantidad', 'unidad', 'precio_unitario', 'orden'].find((name) => validation[name]);
    if (first) {
      if (first === 'orden') setAdvanced(true);
      const control = first === 'unidad' && row.current?.querySelector('#com-unidad-otra')
        || row.current?.querySelector(`#com-${first}`);
      control?.focus();
      return;
    }
    return onSave(event);
  };
  const change = (name, value) => onChange({ ...line.form, [name]: value });
  const field = (name, label, options = {}) => <>
    <label className="form-label commercial-cell-label" htmlFor={`com-${name}`}>{label}</label>
    <input id={`com-${name}`} className={`form-control form-control-sm${errors[name] ? ' is-invalid' : ''}`} required
      disabled={busy || !editable} value={line.form[name]} aria-invalid={!!errors[name]} aria-describedby={errors[name] ? `com-${name}-error` : undefined}
      onChange={(event) => change(name, event.target.value)} {...options} />
    {errors[name] && <div id={`com-${name}-error`} className="invalid-feedback">{errors[name][0]}</div>}
  </>;
  return <>
    <tr ref={row} className="commercial-item-editor" aria-label="Edición de ítem" aria-busy={busy} onKeyDown={(event) => {
      if (event.isComposing || event.nativeEvent?.isComposing) return;
      if (event.key === 'Escape') { event.preventDefault(); if (!busy) onCancel(); }
      // Enter en select conserva la interacción nativa; Tab nunca se intercepta.
      if (event.key === 'Enter' && event.target.tagName === 'INPUT') {
        event.preventDefault(); if (!event.repeat) void save(event);
      }
    }}>
      <td colSpan={7}><div className="budget-item-form">
        <h3>{line.original?'Editar ítem':line.mode==='material'?'Agregar material de bodega':'Agregar ítem manual'}</h3>
        {line.mode==='material'&&line.form.articulo===undefined&&<p className="commercial-help">Selecciona primero un material de bodega para completar su descripción y unidad.</p>}
        {(!picker||linked)&&<div className="budget-item-fields">
          <div className="budget-item-full">{field('descripcion', 'Descripción', { autoFocus: !linked&&line.mode!=='material', maxLength: 2000, readOnly: linked||(line.mode==='material'&&line.form.articulo===undefined), placeholder:'Describe el material o servicio' })}{linked&&<span className="commercial-help d-block">Material de catálogo · {line.form.codigo_articulo}</span>}
            <div className="d-flex flex-wrap gap-1 mt-2"><button type="button" className="btn btn-outline-secondary btn-sm" disabled={blocked} aria-expanded={picker} onClick={()=>setPicker(!picker)}>{linked?'Cambiar material':'Seleccionar material de bodega'}</button>{linked&&<button type="button" className="btn btn-outline-secondary btn-sm" disabled={blocked} onClick={()=>{setPicker(false);onChange({...line.form,articulo:null,codigo_articulo:''});}}>Convertir en ítem libre</button>}</div></div>
          <div>{field('cantidad', 'Cantidad', { inputMode: 'decimal', placeholder:'Ej.: 2.5' })}</div>
          <div>{linked?<><span className="form-label">Unidad de medida</span><span className="form-control bg-transparent">{line.form.unidad}</span></>:<UnitField value={line.form.unidad} onChange={value=>change('unidad',value)} disabled={busy||!editable} error={errors.unidad?.[0]}/>}</div>
          <div>{field('precio_unitario', 'Precio de venta unitario (CLP)', { inputMode: 'decimal', placeholder:'Ej.: 55000' })}</div>
          <div className="budget-item-subtotal"><span className="commercial-help">{line.original?'Subtotal guardado':'Subtotal'}</span><strong>{line.original?money(line.original.subtotal):'Se calcula al guardar'}</strong></div>
        </div>}
        <button type="button" className="btn btn-outline-secondary btn-sm mt-2" disabled={blocked} aria-expanded={advanced||!!errors.orden} onClick={()=>setAdvanced(!advanced)}>{advanced||errors.orden?'Ocultar orden':'Cambiar orden'}</button>
        <div className="budget-order-field" hidden={!advanced&&!errors.orden}>{field('orden', 'Posición del ítem', { inputMode:'numeric' })}</div>
        <div className="budget-item-footer">
          <button className="btn btn-outline-secondary" type="button" aria-label="Cancelar edición de ítem" title="Cancelar (Escape)" disabled={busy} onClick={onCancel}>Cancelar</button>
          <button className="btn btn-fyag-primary" type="button" aria-label="Guardar ítem" title="Guardar ítem (Enter)" disabled={blocked||picker||(line.mode==='material'&&line.form.articulo===undefined)} onClick={save}>Guardar ítem</button>
        </div>{busy&&<span role="status" className="commercial-help">Guardando…</span>}
      </div></td>
    </tr>
    {picker && editable && <tr><td colSpan={7}><MaterialPicker disabled={blocked} onSelect={selectMaterial} onCancel={()=>setPicker(false)} currentId={line.form.articulo}/></td></tr>}
    {(error || !editable) && <tr className="commercial-item-feedback"><td colSpan={7} id="item-row-feedback">
      <Errors error={error} />
      {!editable && <p className="alert alert-warning">El presupuesto ya no es BORRADOR o el ítem ya no está disponible. Cancela la edición para continuar.</p>}
    </td></tr>}
  </>;
}
