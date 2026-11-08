import React from 'react';
import { useAuth } from './auth/AuthContext';
import Login from './components/login.jsx';
import DesktopLayout from './components/layouts/DesktopLayout';
import TecnicoApp from './pages/TecnicoApp';
import PendingIntegration from './components/PendingIntegration';

export default function App() {
  const { status, user } = useAuth();
  if (status === 'restoring') {
    return <main className="login-page"><div className="login-card" role="status">Restaurando sesión…</div></main>;
  }
  if (status !== 'authenticated' || !user) return <Login />;
  if (user.role === 'TECNICO') return <TecnicoApp />;
  return <div className="app-root"><DesktopLayout><PendingIntegration /></DesktopLayout></div>;
}
