import React from 'react';
import {useAuth} from '../auth/AuthContext.jsx';
import GerenciaEgresos from '../integrations/GerenciaEgresos.jsx';
import FinanzasEgresos from '../integrations/FinanzasEgresos.jsx';

export default function Egresos(){
  const {user}=useAuth();
  if(user.role==='GERENCIA')return <GerenciaEgresos key={user.id}/>;
  if(user.role==='ADMINISTRATIVO_FINANZAS')return <FinanzasEgresos key={user.id}/>;
  return <p role="alert">No tienes acceso a Egresos.</p>;
}
