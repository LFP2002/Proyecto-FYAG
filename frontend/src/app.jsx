import React, { lazy, Suspense } from 'react';
import ModuleBoundary, { ModuleLoading } from './components/ModuleBoundary.jsx';
import { useAuth } from './auth/AuthContext';
import Login from './components/login.jsx';
import DesktopLayout from './components/layouts/DesktopLayout';
import PendingIntegration from './components/PendingIntegration';
import { useApp } from './context/AppContext';
import { canRead } from './comercial/domain.js';
import { canReadObras } from './obras/domain.js';
import { modules as warehouseModules } from './bodega/domain.js';

// Una instancia lazy estable por pantalla; se importa tras elegir el módulo.
const Clientes = lazy(() => import('./pages/Clientes.jsx'));
const Presupuestos = lazy(() => import('./pages/Presupuestos.jsx'));
const Obras = lazy(() => import('./pages/Obras.jsx'));
const MisTurnos = lazy(() => import('./pages/MisTurnos.jsx'));
const Usuarios = lazy(() => import('./pages/Usuarios.jsx'));
const Alertas = lazy(() => import('./pages/Alertas.jsx'));
const Cobranzas = lazy(() => import('./pages/Cobranzas.jsx'));
const Dashboard = lazy(() => import('./pages/Dashboard.jsx'));
const Reportes = lazy(() => import('./pages/Reportes.jsx'));
const Auditoria = lazy(() => import('./pages/Auditoria.jsx'));
const Inventario = lazy(() => import('./pages/Inventario.jsx'));
const Solicitudes = lazy(() => import('./pages/Solicitudes.jsx'));
const Mermas = lazy(() => import('./pages/Mermas.jsx'));
const BodegaMermas = lazy(() => import('./pages/BodegaMermas.jsx'));
const TecnicoMateriales = lazy(() => import('./pages/TecnicoMateriales.jsx'));
const Egresos = lazy(() => import('./pages/Egresos.jsx'));
const Chat = lazy(() => import('./pages/Chat.jsx'));
const Bodega = lazy(() => import('./pages/Bodega.jsx'));

const TecnicoMermas=()=> <TecnicoMateriales loss/>;

export default function App() {
  const { status, user } = useAuth();
  const { mod } = useApp();
  if (status === 'restoring') {
    return <main className="login-page"><div className="login-card" role="status">Restaurando sesión…</div></main>;
  }
  if (status !== 'authenticated' || !user) return <Login />;

  const warehouse = user.role==='BODEGUERO'&&Object.hasOwn(warehouseModules,mod);
  const Page = warehouse ? Bodega : mod==='mis_turnos'&&user.role==='TECNICO'?MisTurnos: mod === 'inventario' ? Inventario
    : mod === 'solicitudes' ? (user.role==='TECNICO'?TecnicoMateriales:Solicitudes)
      : mod === 'mermas' ? (user.role==='BODEGUERO'?BodegaMermas:user.role==='TECNICO'?TecnicoMermas:Mermas)
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
  // Bodega conserva su identidad entre secciones.
  const pageKey = `${user.id}:${user.role}:${warehouse?'bodega':mod}`;
  return <div className="app-root"><DesktopLayout>{Page ? <ModuleBoundary key={pageKey}><Suspense fallback={<ModuleLoading/>}><Page key={pageKey}/></Suspense></ModuleBoundary> : <PendingIntegration />}</DesktopLayout></div>;
}
