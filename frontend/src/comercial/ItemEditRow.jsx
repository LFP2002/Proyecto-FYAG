import React, { useRef, useState } from 'react';
import UnitField from './UnitField.jsx';
import MaterialPicker from './MaterialPicker.jsx';
import { money, validateItem, validDecimal, nextItemOrder } from './domain.js';
import { Errors } from './ui.jsx';

// Estimación exacta en centavos; el servidor confirma los importes definitivos.
export function estimateSubtotal(quantity, price) {
  if (!validDecimal(quantity, 9, 3, true) || !validDecimal(price, 13, 2)) return '—';
  const scaled = (value, scale) => {
    const [whole, fraction = ''] = value.split('.');
    return BigInt(whole + fraction.padEnd(scale, '0'));
  };
  const cents = (scaled(quantity, 3) * scaled(price, 2) + 500n) / 1000n;
  return money((cents / 100n).toString() + '.' + (cents % 100n).toString().padStart(2, '0')).replace(/,00 CLP$/, '').replace(/ CLP$/, '');
}

export function itemRowErrors(form, items, original) {
  const order = original ? original.orden : nextItemOrder(items);
  const errors = validateItem({ ...form, orden: order });
  const messages = { descripcion: 'Máximo 2000 caracteres', cantidad: 'Ingresa una cantidad válida', unidad: 'Máximo 30 caracteres', precio_unitario: 'Ingresa un precio válido', orden: 'Ingresa un entero positivo válido' };
  for (const name of Object.keys(errors)) errors[name] = [String(form[name]).trim() ? messages[name] : 'Campo obligatorio'];
  if (items.some((item) => item.id !== original?.id && item.orden === Number(order))) errors.orden = ['Orden ya utilizado'];
  return errors;
}

export default function ItemEditRow({ line, items, onChange, onSave, onCancel, disabled, busy, editable, error }) {
  const [attempted, setAttempted] = useState(false);
  const [picker, setPicker] = useState(line.mode === 'material');
  const linked = line.form.articulo != null;
  const needsMaterial = line.mode === 'material' && line.form.articulo === undefined;
  const selectMaterial = (material) => {
    const changed = line.form.articulo !== material.id;
    onChange({ ...line.form, articulo: material.id, codigo_articulo: material.codigo, descripcion: material.nombre, unidad: material.unidad, ...(changed ? {cantidad:'', precio_unitario:''} : {}) });
    setPicker(false);
  };
  const row = useRef(null);
  const errors = attempted ? itemRowErrors(line.form, items, line.original) : {};
  const blocked = disabled || !editable;
  const save = (event) => {
    if (blocked || picker || needsMaterial) return;
    setAttempted(true);
    const validation = itemRowErrors(line.form, items, line.original);
    const first = ['descripcion', 'cantidad', 'unidad', 'precio_unitario'].find((name) => validation[name]);
    if (first) {
      const control = first === 'unidad' && row.current?.querySelector('#com-unidad-otra')
        || row.current?.querySelector(`#com-${first}`);
      control?.focus();
      return;
    }
    if (validation.orden) return;
    return onSave(event);
  };
  const change = (name, value) => onChange({ ...line.form, [name]: value });
  const field = (name, label, options = {}) => <>
    <label className="form-label commercial-cell-label" htmlFor={`com-${name}`}>{label}</label>
    <input id={`com-${name}`} className={`form-control form-control-sm${errors[name] ? ' is-invalid' : ''}`} required
      disabled={blocked} value={line.form[name]} aria-invalid={!!errors[name]} aria-describedby={errors[name] ? `com-${name}-error` : undefined}
      onChange={(event) => change(name, event.target.value)} {...options} />
    {errors[name] && <div id={`com-${name}-error`} className="invalid-feedback">{errors[name][0]}</div>}
  </>;
  return <>
    <tr ref={row} className="commercial-item-editor" aria-label="Edición de ítem" aria-busy={busy} onKeyDown={(event) => {
      if (picker || event.isComposing || event.nativeEvent?.isComposing) return;
      if (event.key === 'Escape') { event.preventDefault(); if (!busy) onCancel(); }
      // Enter en select conserva la interacción nativa; Tab nunca se intercepta.
      if (event.key === 'Enter' && event.target.tagName === 'INPUT') {
        event.preventDefault(); if (!event.repeat) void save(event);
      }
    }}>
      <td colSpan={editable?6:5}><div className="budget-item-form">
        {picker && editable ? <MaterialPicker disabled={blocked} compact onSelect={selectMaterial} onCancel={()=>needsMaterial?onCancel():setPicker(false)} currentId={line.form.articulo}/> : <>
          <h3>{line.original?'Editar ítem':linked?'Agregar material de bodega':'Agregar ítem manual'}</h3>
          <div className="budget-item-fields">
            <div className="budget-item-full">
              {linked ? <div className="budget-material-selected"><div><strong>{line.form.descripcion}</strong><span className="commercial-help d-block">Material de bodega · {line.form.codigo_articulo}</span></div><button type="button" className="btn btn-outline-secondary btn-sm" disabled={blocked} onClick={()=>setPicker(true)}>Cambiar material</button></div> : field('descripcion','Descripción',{autoFocus:true,maxLength:2000,placeholder:'Nombre del material o servicio'})}
            </div>
            <div>{field('cantidad','Cantidad',{inputMode:'decimal',placeholder:'Ej.: 2.5'})}</div>
            <div>{linked?<><label className="form-label commercial-cell-label" htmlFor="com-unidad">Unidad de medida</label><input id="com-unidad" className="form-control form-control-sm" readOnly value={line.form.unidad}/></>:<UnitField value={line.form.unidad} onChange={value=>change('unidad',value)} disabled={blocked} error={errors.unidad?.[0]}/>}</div>
            <div>{field('precio_unitario','Precio unitario (CLP)',{inputMode:'decimal',placeholder:'Ej.: 55000'})}</div>
          </div>
          <div className="budget-item-subtotal"><span className="commercial-help">Subtotal estimado</span><strong data-testid="item-estimated-subtotal">{estimateSubtotal(line.form.cantidad,line.form.precio_unitario)}</strong></div>
          {errors.orden&&<p role="alert" className="commercial-help">No se pudo asignar una posición. Actualiza los datos y vuelve a intentar.</p>}
          <div className="budget-item-footer">
            {linked&&line.original&&<button type="button" className="btn btn-outline-secondary btn-sm me-auto" disabled={blocked} onClick={()=>onChange({...line.form,articulo:null,codigo_articulo:''})}>Convertir en ítem manual</button>}
            <button className="btn btn-outline-secondary" type="button" aria-label="Cancelar edición de ítem" title="Cancelar (Escape)" disabled={busy} onClick={onCancel}>Cancelar</button>
            <button className="btn btn-fyag-primary" type="button" aria-label="Guardar ítem" title="Guardar ítem (Enter)" disabled={blocked||needsMaterial} onClick={save}>Guardar ítem</button>
          </div>{busy&&<span role="status" className="commercial-help">Guardando…</span>}
        </>}
      </div></td>
    </tr>
    {(error || !editable) && <tr className="commercial-item-feedback"><td colSpan={editable?6:5} id="item-row-feedback">
      <Errors error={error} />
      {!editable && <p className="alert alert-warning">El presupuesto ya no es BORRADOR o el ítem ya no está disponible. Cancela la edición para continuar.</p>}
    </td></tr>}
  </>;
}
