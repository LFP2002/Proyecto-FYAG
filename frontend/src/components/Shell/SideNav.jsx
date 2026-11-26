import { useApp } from '../../context/AppContext';
import { MODS, NAV, ROLES, ROLE_NOTE } from '../../data/constants';
import { Icon } from '../ui';
import React from 'react';
import BodegaIcon from '../../bodega/icons.jsx';
import TecIcon from '../../obras/TecIcon.jsx';
const warehouseIcons={bodega_resumen:'summary',inventario:'inventory',bodega_movimientos:'movements',bodega_entregas:'delivery',bodega_devoluciones:'returns'};
export default function SideNav({ mobileOpen = false, onNavigate, onEscape }) {
  const { role, mod, go, navigationBlocked } = useApp();
  return (
    <nav
      id="fyag-modules-nav"
      className={`fyag-side${mobileOpen ? ' is-open' : ''}`}
      aria-label="Módulos"
      onKeyDown={(event) => {
        if (event.key === 'Escape' && mobileOpen) {
          event.preventDefault();
          onEscape?.();
        }
      }}
    >
      {NAV[role].map((k) => (
        <button
          type="button"
          key={k}
          className={`navbtn${k === mod ? ' on' : ''}`}
          aria-current={k === mod ? 'page' : undefined}
          disabled={navigationBlocked && k!==mod}
          onClick={() => { go(k); onNavigate?.(); }}
        >
          {role==='TECNICO'&&['obras','mis_turnos'].includes(k)?<TecIcon name={k==='obras'?'work':'clock'}/>:role==='BODEGUERO'&&warehouseIcons[k]?<BodegaIcon name={warehouseIcons[k]}/>:k==='auditoria'?<svg width="18" height="18" viewBox="0 0 16 16" fill="currentColor" aria-hidden="true"><path fillRule="evenodd" d="M8 3a5 5 0 1 1-4.546 2.914.5.5 0 0 0-.908-.417A6 6 0 1 0 8 2zM8 4.466V.534a.25.25 0 0 0-.41-.192L5.23 2.308a.25.25 0 0 0 0 .384l2.36 1.966A.25.25 0 0 0 8 4.466"/><path d="M7.5 5a.5.5 0 0 1 1 0v3.25l2 1.2a.5.5 0 1 1-.514.857l-2.25-1.35A.5.5 0 0 1 7.5 8.5z"/></svg>:<Icon d={MODS[k].icon} />}
          <span>{role==='TECNICO'&&k==='obras'?'Mis obras':['GERENCIA','BODEGUERO'].includes(role)&&k==='inventario'?'Inventario':MODS[k].label}</span>
        </button>
      ))}
      <div className="side-note">
        <strong>{ROLES[role].short}</strong>
        {ROLE_NOTE[role]}
      </div>
    </nav>
  );
}
