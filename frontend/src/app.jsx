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
import Obras from './pages/Obras';
import Usuarios from './pages/Usuarios';
import { canReadObras } from './obras/domain.js';
import Alertas from './pages/Alertas.jsx';
import Cobranzas from './pages/Cobranzas.jsx';
import Dashboard from './pages/Dashboard.jsx';
import Reportes from './pages/Reportes.jsx';
import Auditoria from './pages/Auditoria.jsx';
import Inventario from './pages/Inventario.jsx';
import Solicitudes from './pages/Solicitudes.jsx';
import Mermas from './pages/Mermas.jsx';
import BodegaMermas from './pages/BodegaMermas.jsx';
import Egresos from './pages/Egresos.jsx';
import Chat from './pages/Chat.jsx';
import Bodega from './pages/Bodega.jsx';
import { modules as warehouseModules } from './bodega/domain.js';

export default function App() {
  const { status, user } = useAuth();
  const { mod } = useApp();
  if (status === 'restoring') {
    return <main className="login-page"><div className="login-card" role="status">Restaurando sesión…</div></main>;
  }
  if (status !== 'authenticated' || !user) return <Login />;

  const warehouse = user.role==='BODEGUERO'&&Object.hasOwn(warehouseModules,mod);
  const Page = warehouse ? Bodega : mod === 'inventario' ? Inventario
    : mod === 'solicitudes' ? Solicitudes
      : mod === 'mermas' ? (user.role==='BODEGUERO'?BodegaMermas:Mermas)
        : mod === 'egresos' ? Egresos
          : mod === 'chat' ? Chat
            : mod === 'auditoria' ? Auditoria
    : mod === 'usuarios' && user.role === 'ADMINISTRADOR_TI' ? Usuarios
    : mod === 'obras' && canReadObras(user.role) ? Obras
      : mod === 'alertas' && ['GERENCIA', 'SUPERVISOR_OBRAS', 'ADMINISTRATIVO_FINANZAS'].includes(user.role) ? Alertas
        : mod === 'dashboard' && user.role === 'GERENCIA' ? Dashboard
          : mod === 'reportes' && ['GERENCIA', 'ADMINISTRATIVO_FINANZAS'].includes(user.role) ? Reportes
            : mod === 'cobranzas' && ['GERENCIA', 'ADMINISTRATIVO_FINANZAS'].includes(user.role) ? Cobranzas
              : canRead(user.role, mod) ? ({ clientes: Clientes, presupuestos: Presupuestos })[mod] : null;
  return <div className="app-root"><DesktopLayout>{Page ? <Page key={`${user.id}:${user.role}:${warehouse?'bodega':mod}`} /> : <PendingIntegration />}</DesktopLayout></div>;
}
