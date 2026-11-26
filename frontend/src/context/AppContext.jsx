import React, { createContext, useContext, useEffect, useState } from 'react';
import { useAuth } from '../auth/AuthContext';
import { DEFMOD, NAV } from '../data/constants';

const Ctx = createContext(null);
export const useApp = () => useContext(Ctx);

// Solo navegación. La identidad pertenece a AuthContext; los datos comerciales
// se consultan en sus pantallas, sin acciones de persistencia simulada aquí.
export function AppProvider({ children }) {
  const { user } = useAuth();
  const [selection, setSelection] = useState(null);
  const [navigationTarget,setNavigationTarget]=useState(null);
  const [navigationBlocked,setNavigationBlocked]=useState(false);
  useEffect(() => { setSelection(null); setNavigationTarget(null); setNavigationBlocked(false); }, [user?.id, user?.role]);
  const role = user?.role;
  const allowed = NAV[role] || [];
  const mod = allowed.includes(selection) ? selection : DEFMOD[role];
  const go = (next, target = null) => {
    if (user && !navigationBlocked && allowed.includes(next)) {
      setNavigationTarget(target && role==='ADMINISTRATIVO_FINANZAS' ? {module:next, ...target} : null);
      setSelection(next);
    }
  };
  return <Ctx.Provider value={{ role, mod, go, navigationTarget: navigationTarget?.module===mod?navigationTarget:null, navigationBlocked, setNavigationBlocked }}>{children}</Ctx.Provider>;
}
