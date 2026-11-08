import React, { createContext, useContext, useEffect, useSyncExternalStore } from 'react';
import { authClient } from './client';

const AuthContext = createContext(null);

export function AuthProvider({ children, client = authClient }) {
  const session = useSyncExternalStore(client.subscribe, client.getSnapshot, client.getSnapshot);
  useEffect(() => { void client.restore(); }, [client]);
  return (
    <AuthContext.Provider value={{ ...session, login: client.login, logout: client.logout, request: client.request }}>
      {children}
    </AuthContext.Provider>
  );
}

export const useAuth = () => useContext(AuthContext);
