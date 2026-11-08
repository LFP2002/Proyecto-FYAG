import React from 'react';
import { useAuth } from '../auth/AuthContext';
import PendingIntegration from '../components/PendingIntegration';

export default function TecnicoApp() {
  const { user, logout } = useAuth();
  return (
    <div className="tec-bg">
      <header className="protobar">
        <span className="fw-bold">FYAG · Técnico</span>
        <button className="btn btn-sm btn-fyag-white ms-auto" onClick={() => void logout()}>Salir</button>
      </header>
      <main className="tec-container">
        <div className="tec-top"><h1 className="tec-name">{user.username}</h1></div>
        <PendingIntegration />
      </main>
    </div>
  );
}
