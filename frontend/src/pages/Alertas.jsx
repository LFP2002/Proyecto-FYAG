import React from 'react';
import { useAuth } from '../auth/AuthContext.jsx';
import { PageHead } from '../components/ui';
import GerenciaAlertas from '../integrations/GerenciaAlertas.jsx';

export default function Alertas() {
  const {user}=useAuth();
  if (!['GERENCIA','ADMINISTRATIVO_FINANZAS','SUPERVISOR_OBRAS'].includes(user.role)) {
    return <section><PageHead title="Alertas"/><div className="alert alert-warning" role="alert">No tienes permiso para consultar alertas.</div></section>;
  }
  return <GerenciaAlertas role={user.role} key={user.id+':'+user.role}/>;
}
