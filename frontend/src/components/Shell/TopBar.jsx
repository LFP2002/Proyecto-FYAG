import React from 'react';
import { useAuth } from '../../auth/AuthContext';
import { ROLES } from '../../data/constants';
import { Icon } from '../ui';
import BootstrapIcon from '../ui/BootstrapIcon.jsx';
import AppearanceControls from './AppearanceControls.jsx';

export default function TopBar({ menuOpen = false, onToggleMenu, menuButtonRef }) {
  const { user, logout } = useAuth();
  return (
    <header className="fyag-top">
      <div className="brand"><Icon d="M12 2v20M4.2 7l15.6 10M4.2 17L19.8 7M9 3.5l3 2.5 3-2.5M9 20.5l3-2.5 3 2.5" /><span>FYAG · Sistema de Gestión</span></div>
      <button type="button" ref={menuButtonRef} className="btn btn-sm btn-fyag-white fyag-menu-toggle" aria-controls="fyag-modules-nav" aria-expanded={menuOpen} onClick={onToggleMenu}><BootstrapIcon name="list" />{menuOpen ? 'Cerrar menú' : 'Menú'}</button>
      <div className="top-right">
        <AppearanceControls compact />
        <span className="d-inline-flex align-items-center gap-2"><BootstrapIcon name="person-circle" />{user.username} · {ROLES[user.role].short}</span>
        <button className="btn btn-sm btn-fyag-white" onClick={() => void logout()}><BootstrapIcon name="box-arrow-right" /> Salir</button>
      </div>
    </header>
  );
}
