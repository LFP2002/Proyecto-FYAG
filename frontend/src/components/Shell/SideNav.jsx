import { useApp } from '../../context/AppContext';
import { MODS, NAV, ROLES, ROLE_NOTE } from '../../data/constants';
import { Icon } from '../ui';
import React from 'react';
export default function SideNav() {
  const { role, mod, go } = useApp();
  return (
    <nav className="fyag-side" aria-label="Módulos">
      {NAV[role].map((k) => (
        <button key={k} className={`navbtn${k === mod ? ' on' : ''}`} onClick={() => go(k)}>
          <Icon d={MODS[k].icon} />
          <span>{MODS[k].label}</span>
        </button>
      ))}
      <div className="side-note">
        <strong>{ROLES[role].short}</strong>
        {ROLE_NOTE[role]}
      </div>
    </nav>
  );
}
