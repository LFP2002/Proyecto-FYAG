import React from 'react';
import { useApp } from '../context/AppContext';
import { MODS } from '../data/constants';

export default function PendingIntegration() {
  const { mod } = useApp();
  return (
    <section className="p-3" aria-labelledby="pending-title">
      <h1 id="pending-title">{MODS[mod]?.label || 'Mis obras'}</h1>
      <div className="alert alert-info mt-3" role="status">
        <strong>Pendiente de integración</strong>
        <p className="mb-0 mt-2">Este módulo todavía no está conectado a su API. No se muestran registros ni se guardan modificaciones desde esta pantalla.</p>
      </div>
      <p>Tu sesión está autenticada. Las funciones de negocio se habilitarán en una entrega posterior.</p>
    </section>
  );
}
