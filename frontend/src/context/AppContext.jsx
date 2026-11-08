import React, { createContext, useContext, useEffect, useState } from 'react';
import { useAuth } from '../auth/AuthContext';
import { DEFMOD, NAV } from '../data/constants';

const Ctx = createContext(null);
export const useApp = () => useContext(Ctx);

// Solo navegación. La identidad pertenece a AuthContext y los módulos de
// negocio aún no tienen estado de datos ni acciones de persistencia simulada.
export function AppProvider({ children }) {
  const { user } = useAuth();
  const [selection, setSelection] = useState(null);
  useEffect(() => { setSelection(null); }, [user?.id, user?.role]);
  const role = user?.role;
  const allowed = NAV[role] || [];
  const mod = allowed.includes(selection) ? selection : DEFMOD[role];
  const go = (next) => {
    if (user && allowed.includes(next)) setSelection(next);
  };
  return <Ctx.Provider value={{ role, mod, go }}>{children}</Ctx.Provider>;
}
