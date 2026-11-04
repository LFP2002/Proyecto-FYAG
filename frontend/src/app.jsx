import React from 'react';
import { useApp } from './context/AppContext';
import Login from './components/Login';
import { Toast } from './components/Shell';
import DesktopLayout from './components/layouts/DesktopLayout';
import TecnicoApp from './pages/TecnicoApp';
import Dashboard from './pages/Dashboard';
import Presupuestos from './pages/Presupuestos';
import Clientes from './pages/Clientes';
import Obras from './pages/Obras';
import Cobranzas from './pages/Cobranzas';
import Alertas from './pages/Alertas';
import Reportes from './pages/Reportes';
import Usuarios from './pages/Usuarios';

const PAGES = { dashboard: Dashboard, presupuestos: Presupuestos, clientes: Clientes, obras: Obras, cobranzas: Cobranzas, alertas: Alertas, reportes: Reportes, usuarios: Usuarios };

export default function App() {
  const { screen, role, mod } = useApp();
  let body;
  if (screen === 'login') body = <Login />;
  else if (role === 'tecnico') body = <TecnicoApp />;
  else {
    const Page = PAGES[mod];
    body = <DesktopLayout><Page /></DesktopLayout>;
  }
  return <div className="app-root">{body}<Toast /></div>;
}