import { useApp } from '../../context/AppContext';
import { MODS, NAV, ROLES, ROLE_NOTE } from '../../data/constants';
import { Icon } from '../ui';
import React from 'react';
export default function SideNav() {
  const { role, mod, go, presPend, alertasPend, sinObra } = useApp();
  const badge = (k) => {
    if (k === 'presupuestos' && role === 'gerencia') return presPend.length;
    if (k === 'alertas') return alertasPend.length;
    if (k === 'obras' && role === 'supervisor') return sinObra.length;
    return 0;
  };
  return (
    <nav className="fyag-side" aria-label="Módulos">
      {NAV[role].map((k) => (
        <button key={k} className={`navbtn${k === mod ? ' on' : ''}`} onClick={() => go(k)}>
          <Icon d={MODS[k].icon} />
          <span>{MODS[k].label}</span>
          {badge(k) > 0 && <span className="badge-pill">{badge(k)}</span>}
        </button>
      ))}
      <div className="side-note">
        <strong>{ROLES[role].short}</strong>
        {ROLE_NOTE[role]}
      </div>
    </nav>
  );
}