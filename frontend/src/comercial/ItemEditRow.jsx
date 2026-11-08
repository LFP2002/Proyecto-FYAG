import React, { useRef, useState } from 'react';
import UnitField from './UnitField.jsx';
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
  const row = useRef(null);
  const errors = attempted ? itemRowErrors(line.form, items, line.original) : {};
  const blocked = disabled || !editable;
  const save = (event) => {
    if (blocked) return;
    setAttempted(true);
    const validation = itemRowErrors(line.form, items, line.original);
    const first = ['descripcion', 'cantidad', 'unidad', 'precio_unitario', 'orden'].find((name) => validation[name]);
    if (first) {
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
      <td>{field('descripcion', 'Descripción', { autoFocus: true, maxLength: 2000 })}</td>
      <td>{field('cantidad', 'Cantidad', { inputMode: 'decimal' })}</td>
      <td><UnitField value={line.form.unidad} onChange={(value) => change('unidad', value)} disabled={busy || !editable} error={errors.unidad?.[0]} /></td>
      <td>{field('precio_unitario', 'Precio unitario (CLP)', { inputMode: 'decimal' })}</td>
      <td>{field('orden', 'Orden', { inputMode: 'numeric' })}</td>
      <td className="commercial-item-subtotal"><span className="commercial-help">Subtotal</span><span>{line.original ? money(line.original.subtotal) : '—'}</span></td>
      <td><div className="commercial-row-actions">
        <button className="btn btn-fyag-primary btn-sm" type="button" aria-label="Guardar ítem" title="Guardar ítem (Enter)" disabled={blocked} onClick={save}>✓</button>
        <button className="btn btn-outline-secondary btn-sm" type="button" aria-label="Cancelar edición de ítem" title="Cancelar (Escape)" disabled={busy} onClick={onCancel}>×</button>
      </div>{busy && <span role="status" className="commercial-help">Guardando…</span>}</td>
    </tr>
    {(error || !editable) && <tr className="commercial-item-feedback"><td colSpan={7} id="item-row-feedback">
      <Errors error={error} />
      {!editable && <p className="alert alert-warning">El presupuesto ya no es BORRADOR o el ítem ya no está disponible. Cancela la edición para continuar.</p>}
    </td></tr>}
  </>;
}
