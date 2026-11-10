import React from 'react';
import { useAuth } from '../../auth/AuthContext';
import { ROLES } from '../../data/constants';
import { Icon } from '../ui';

export default function TopBar({ menuOpen = false, onToggleMenu, menuButtonRef }) {
  const { user, logout } = useAuth();
  return (
    <header className="fyag-top">
      <div className="brand">
        <Icon d="M12 2v20M4.2 7l15.6 10M4.2 17L19.8 7M9 3.5l3 2.5 3-2.5M9 20.5l3-2.5 3 2.5" />
        <span>FYAG · Sistema de Gestión</span>
      </div>
      <button
        type="button"
        ref={menuButtonRef}
        className="btn btn-sm btn-fyag-white fyag-menu-toggle"
        aria-controls="fyag-modules-nav"
        aria-expanded={menuOpen}
        onClick={onToggleMenu}
      >
        <svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" fill="currentColor" className="bi bi-list" viewBox="0 0 16 16" aria-hidden="true" focusable="false">
          <path fillRule="evenodd" d="M2.5 12a.5.5 0 0 1 .5-.5h10a.5.5 0 0 1 0 1H3a.5.5 0 0 1-.5-.5m0-4a.5.5 0 0 1 .5-.5h10a.5.5 0 0 1 0 1H3a.5.5 0 0 1-.5-.5m0-4a.5.5 0 0 1 .5-.5h10a.5.5 0 0 1 0 1H3a.5.5 0 0 1-.5-.5" />
        </svg>
        {menuOpen ? 'Cerrar menú' : 'Menú'}
      </button>
      <div className="top-right">
        <span className="d-inline-flex align-items-center gap-2">
          <Icon d="M20 21v-1a5 5 0 0 0-5-5H9a5 5 0 0 0-5 5v1M12 11a4 4 0 1 0 0-8 4 4 0 0 0 0 8z" />
          {user.username} · {ROLES[user.role].short}
        </span>
        <button className="btn btn-sm btn-fyag-white" onClick={() => void logout()}>
          <Icon d="M9 4H5v16h4M16 8l4 4-4 4M20 12H9" /> Salir
        </button>
      </div>
    </header>
  );
}
