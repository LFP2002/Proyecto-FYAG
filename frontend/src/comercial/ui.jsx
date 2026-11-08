import React, { useEffect, useRef, useState } from 'react';
import { useAuth } from '../auth/AuthContext';
import { createScope } from './scope.js';
import { ApiError } from '../auth/client.js';

export function useCommercial() {
  const { request, user } = useAuth();
  const ref = useRef(null);
  const reads = useRef(0);
  const [error, setError] = useState(null);
  const [busy, setBusy] = useState(false);
  const [loading, setLoading] = useState(false);
  const [locked, setLocked] = useState(false);
  useEffect(() => {
    const scope = createScope(); ref.current = scope;
    return () => { scope.dispose(); if (ref.current === scope) ref.current = null; };
  }, [user.id, user.role]);
  async function load(key, path, apply) {
    const scope = ref.current;
    if (!scope) return false;
    reads.current += 1; setLoading(true);
    try { return await scope.read(key, (signal) => request(path, { signal }), apply); }
    catch (e) { if (ref.current === scope) setError(e); return false; }
    finally { reads.current -= 1; if (ref.current === scope) setLoading(reads.current > 0); }
  }
  async function requiredLoad(key, path, apply) {
    if (!await load(key, path, apply)) throw new ApiError(502, 'La escritura pudo aplicarse, pero falta confirmar los datos. Reconsulta antes de continuar.');
  }
  async function write(path, method, body, apply) {
    const scope = ref.current;
    if (!scope || scope.locked) return false;
    setBusy(true); setError(null);
    try { return await scope.write((signal) => request(path, { method, body, signal }), apply); }
    catch (e) { if (ref.current === scope) setError(e); return false; }
    finally { if (ref.current === scope) { setBusy(false); setLocked(scope.locked); } }
  }
  async function reconcile(operation) {
    setError(null);
    if (await operation()) { ref.current?.reconciled(); setLocked(false); }
  }
  return { load, requiredLoad, write, error, setError, busy, loading, locked, reconcile };
}
export function Errors({ error }) {
  if (!error) return null;
  return <div role="alert" className="alert alert-warning"><p>{error.message || 'Revisa los campos.'}</p>
    {error.code === 'presupuesto_utilizado' && <p>El presupuesto está utilizado por una Obra y no puede anularse.</p>}
    {Object.entries(error.fieldErrors || {}).map(([field, values]) => <p key={field}>{field}: {values.join(' ')}</p>)}
    {error.retryAfter && <p>Espera indicada por el servidor: {error.retryAfter}.</p>}
  </div>;
}
export function Fields({ form, setForm, fields, disabled = false }) {
  return <div className="fgrid">{fields.map(([name, label, options]) => <div key={name}>
    <label htmlFor={`com-${name}`}>{label}</label>
    {options ? <select id={`com-${name}`} className="form-select" disabled={disabled} value={form[name] ?? ''} onChange={(e) => setForm({ ...form, [name]: e.target.value })}>
      {options.map(([value, text]) => <option key={value} value={value}>{text}</option>)}
    </select> : <input id={`com-${name}`} className="form-control" disabled={disabled} value={form[name] ?? ''} onChange={(e) => setForm({ ...form, [name]: e.target.value })} />}
  </div>)}</div>;
}
export function Pager({ data, page, setPage, disabled }) {
  return <nav aria-label="Paginación" className="d-flex gap-3 my-3">
    <button disabled={disabled || !data?.previous} onClick={() => setPage(page - 1)}>Anterior</button>
    <span>Página {page} · {data?.count ?? 0} registros</span>
    <button disabled={disabled || !data?.next} onClick={() => setPage(page + 1)}>Siguiente</button>
  </nav>;
}
