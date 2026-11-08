import React, { useState } from 'react';
import { isCatalogUnit, OTHER_UNIT, UNIT_GROUPS } from './units.js';

export default function UnitField({ value, onChange, disabled, error }) {
  const [explicitOther, setExplicitOther] = useState(false);
  const other = explicitOther || (!!value && !isCatalogUnit(value));
  return <div className="fgrid commercial-fields">
    <div>
      <label className="form-label" htmlFor="com-unidad">Unidad de medida</label>
      <select id="com-unidad" className={`form-select${error && !other ? ' is-invalid' : ''}`} required disabled={disabled}
        aria-invalid={!!error && !other} aria-describedby={error && !other ? 'com-unidad-error' : undefined}
        value={other ? OTHER_UNIT : value} onChange={(event) => {
          const unit = event.target.value;
          setExplicitOther(unit === OTHER_UNIT);
          onChange(unit === OTHER_UNIT ? '' : unit);
        }}>
        <option value="">Selecciona una unidad</option>
        {UNIT_GROUPS.map((group) => <optgroup key={group.label} label={group.label}>
          {group.options.map(([unit, label]) => <option key={unit} value={unit}>{label}</option>)}
        </optgroup>)}
        <option value={OTHER_UNIT}>Otra (especificar)</option>
      </select>
      {error && !other && <div id="com-unidad-error" className="invalid-feedback">{error}</div>}
    </div>
    {other && <div>
      <label className="form-label" htmlFor="com-unidad-otra">Especifica la unidad</label>
      <input id="com-unidad-otra" className={`form-control${error ? ' is-invalid' : ''}`} required maxLength={30}
        aria-invalid={!!error} aria-describedby={error ? 'com-unidad-error' : undefined}
        disabled={disabled} value={value} onChange={(event) => onChange(event.target.value)} />
      {error && <div id="com-unidad-error" className="invalid-feedback">{error}</div>}
    </div>}
  </div>;
}
