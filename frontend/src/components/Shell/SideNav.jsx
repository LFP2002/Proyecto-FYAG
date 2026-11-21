import { useApp } from '../../context/AppContext';
import { MODS, NAV, ROLES, ROLE_NOTE } from '../../data/constants';
import BootstrapIcon from '../ui/BootstrapIcon.jsx';
import AppearanceControls from './AppearanceControls.jsx';
import React from 'react';
export default function SideNav({ mobileOpen = false, onNavigate, onEscape }) {
  const { role, mod, go } = useApp();
  return (
    <nav id="fyag-modules-nav" className={`fyag-side${mobileOpen ? ' is-open' : ''}`} aria-label="Módulos" onKeyDown={(event) => { if (event.key === 'Escape' && mobileOpen) { event.preventDefault(); onEscape?.(); } }}>
      {NAV[role].map((key) => (
        <button type="button" key={key} className={`navbtn${key === mod ? ' on' : ''}`} aria-current={key === mod ? 'page' : undefined} onClick={() => { go(key); onNavigate?.(); }}>
          <BootstrapIcon name={MODS[key].icon} /><span>{MODS[key].label}</span>
        </button>
      ))}
      <div className="side-note"><strong>{ROLES[role].short}</strong>{ROLE_NOTE[role]}</div>
      <AppearanceControls />
    </nav>
  );
}
