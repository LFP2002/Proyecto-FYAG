import React from 'react';

export function ModuleLoading() {
  return <div className="card-fyag p-4" role="status" aria-live="polite">Cargando módulo…</div>;
}

// Mantiene el menú disponible. React.lazy cachea un rechazo de descarga;
// ofrecer recarga explícita, nunca automática (podría haber datos en edición).
export default class ModuleBoundary extends React.Component {
  state = { failed: false };
  static getDerivedStateFromError() { return { failed: true }; }
  render() {
    if (!this.state.failed) return this.props.children;
    return <section className="card-fyag p-4" role="alert">
      <h2>No fue posible cargar este módulo</h2>
      <p>Intenta recargar la aplicación. También puedes volver a otro módulo desde el menú.</p>
      <button type="button" className="btn btn-fyag-primary" onClick={() => globalThis.location.reload()}>Recargar aplicación</button>
    </section>;
  }
}
