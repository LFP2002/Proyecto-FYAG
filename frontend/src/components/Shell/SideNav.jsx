import { useApp } from '../../context/AppContext';
import { MODS, NAV, ROLES, ROLE_NOTE } from '../../data/constants';
import { Icon } from '../ui';
import React from 'react';
export default function SideNav({ mobileOpen = false, onNavigate, onEscape }) {
  const { role, mod, go } = useApp();
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
          onClick={() => { go(k); onNavigate?.(); }}
        >
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
