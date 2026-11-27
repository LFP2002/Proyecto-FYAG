import React, { createContext, useContext, useEffect, useSyncExternalStore } from 'react';
import { authClient } from './client';

const AuthContext = createContext(null);

export function AuthProvider({ children, client = authClient, restoreSession = true }) {
  const session = useSyncExternalStore(client.subscribe, client.getSnapshot, client.getSnapshot);
  useEffect(() => { if (restoreSession) void client.restore(); }, [client, restoreSession]);
  const status = !restoreSession && session.status === 'restoring' ? 'anonymous' : session.status;
  return (
    <AuthContext.Provider value={{ ...session, status, login: client.login, logout: client.logout, request: client.request,
        completeFirstPasswordChange: client.completeFirstPasswordChange,
        sessionInvalidatedByEmailChange: client.sessionInvalidatedByEmailChange }}>
      {children}
    </AuthContext.Provider>
  );
}

export const useAuth = () => useContext(AuthContext);
