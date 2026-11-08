import React from 'react';
import { useAuth } from './auth/AuthContext';
import Login from './components/login.jsx';
import DesktopLayout from './components/layouts/DesktopLayout';
import TecnicoApp from './pages/TecnicoApp';
import PendingIntegration from './components/PendingIntegration';
import { useApp } from './context/AppContext';
import Clientes from './pages/Clientes';
import Presupuestos from './pages/Presupuestos';
import { canRead } from './comercial/domain.js';

export default function App() {
  const { status, user } = useAuth();
  const { mod } = useApp();
  if (status === 'restoring') {
    return <main className="login-page"><div className="login-card" role="status">Restaurando sesión…</div></main>;
  }
  if (status !== 'authenticated' || !user) return <Login />;
  if (user.role === 'TECNICO') return <TecnicoApp />;
  const Page = canRead(user.role) ? ({ clientes: Clientes, presupuestos: Presupuestos })[mod] : null;
  return <div className="app-root"><DesktopLayout>{Page ? <Page key={`${user.id}:${user.role}:${mod}`} /> : <PendingIntegration />}</DesktopLayout></div>;
}
