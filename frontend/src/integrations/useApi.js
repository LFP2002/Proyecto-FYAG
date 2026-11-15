import { useEffect, useRef, useState } from 'react';
import { ApiError } from '../auth/client.js';
import { createScope } from '../comercial/scope.js';
import { useAuth } from '../auth/AuthContext.jsx';

export function useApi() {
  const { request, user } = useAuth();
  const scopeRef = useRef(null);
  const reads = useRef(0);
  const [error, setError] = useState(null);
  const [busy, setBusy] = useState(false);
  const [loading, setLoading] = useState(false);
  const [locked, setLocked] = useState(false);

  useEffect(() => {
    const scope = createScope();
    scopeRef.current = scope;
    return () => { scope.dispose(); if (scopeRef.current === scope) scopeRef.current = null; };
  }, [user?.id, user?.role]);

  async function load(key, path, apply, options = {}) {
    const scope = scopeRef.current;
    if (!scope) return false;
    reads.current += 1; setLoading(true);
    try { return await scope.read(key, (signal) => request(path, { ...options, signal }), apply); }
    catch (cause) { if (scopeRef.current === scope) setError(cause); return false; }
    finally { reads.current -= 1; if (scopeRef.current === scope) setLoading(reads.current > 0); }
  }

  async function requiredLoad(key, path, apply, options = {}) {
    if (!await load(key, path, apply, options)) throw new ApiError(502, 'La operación pudo completarse, pero no se confirmó la lectura. Actualiza los datos antes de continuar.');
  }

  async function write(path, method, body, apply) {
    const scope = scopeRef.current;
    if (!scope || scope.locked) return false;
    setBusy(true); setError(null);
    try { return await scope.write((signal) => request(path, { method, body, signal }), apply); }
    catch (cause) { if (scopeRef.current === scope) setError(cause); return false; }
    finally { if (scopeRef.current === scope) { setBusy(false); setLocked(scope.locked); } }
  }

  async function reconcile(operation) {
    setError(null);
    if (await operation()) { scopeRef.current?.reconciled(); setLocked(false); return true; }
    return false;
  }

  return { load, requiredLoad, write, reconcile, error, setError, busy, loading, locked };
}

export function readPage(value, path, max = 25) {
  if (!value || !Number.isSafeInteger(value.count) || value.count < 0 || !Array.isArray(value.results)
      || value.results.length > max || !('next' in value) || !('previous' in value)) {
    throw new ApiError(502, 'El servidor devolvió una página inesperada.');
  }
  for (const key of ['next', 'previous']) {
    if (value[key] !== null && typeof value[key] !== 'string') throw new ApiError(502, 'El servidor devolvió una página inesperada.');
    if (value[key]) safePage(value[key], path);
  }
  return value;
}

export function safePage(link, path) {
  try {
    const url = new URL(link, window.location.origin);
    const allowed = new Set(['page','estado','cliente','obra','fecha_vencimiento_desde','fecha_vencimiento_hasta','fecha_emision_desde','fecha_emision_hasta','desde','hasta','fecha_base']);
    if (url.origin !== window.location.origin || url.pathname !== path || [...url.searchParams.keys()].some((key) => !allowed.has(key))
        || [...url.searchParams.keys()].some((key) => url.searchParams.getAll(key).length !== 1 || url.searchParams.get(key) === '')
        || (url.searchParams.has('page') && !/^[1-9][0-9]*$/.test(url.searchParams.get('page')))) {
      throw new Error('invalid');
    }
    return Number(url.searchParams.get('page') || 1);
  } catch { throw new ApiError(502, 'El servidor devolvió una página no segura.'); }
}

export const strictObject = (value, keys, optional = []) => {
  if (!value || typeof value !== 'object' || Array.isArray(value) || value instanceof Date || keys.some((key) => !optional.includes(key) && !Object.hasOwn(value, key))
      || Object.keys(value).some((key) => !keys.includes(key))) throw new ApiError(502, 'El servidor devolvió datos inesperados.');
  return value;
};
export const positiveInteger = (value) => Number.isSafeInteger(value) && value > 0;
export const decimalString = (value, signed = false) => typeof value === 'string' && new RegExp(signed ? '^-?(?:0|[1-9][0-9]*)\\.[0-9]{2}$' : '^(?:0|[1-9][0-9]*)\\.[0-9]{2}$').test(value);
