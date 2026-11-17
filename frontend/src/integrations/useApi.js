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

  async function write(path, method, body, apply, requestOptions = {}) {
    const scope = scopeRef.current;
    if (!scope || scope.locked) return false;
    setBusy(true); setError(null);
    try { return await scope.write((signal) => request(path, { ...requestOptions, method, body, signal }), apply); }
    catch (cause) { if (scopeRef.current === scope) setError(cause); return false; }
    finally { if (scopeRef.current === scope) { setBusy(false); setLocked(scope.locked); } }
  }

  async function reconcile(operation) {
    const scope = scopeRef.current;
    setError(null);
    if (await operation() && scope && scopeRef.current === scope) { scope.reconciled(); setLocked(false); return true; }
    return false;
  }

  const cancelRead = (key) => scopeRef.current?.cancelRead(key);
  return { load, requiredLoad, write, reconcile, cancelRead, error, setError, busy, loading, locked };
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
    const origin = globalThis.location?.origin || 'http://localhost';
    const url = new URL(link, origin);
    const pathFilters = path === '/api/alertas/'
      ? ['estado','tipo','recurso_tipo','recurso_id','desde','hasta']
      : path === '/api/reportes/obras/'
        ? ['desde','hasta','cliente','estado','fecha_base']
        : path === '/api/reportes/rentabilidad/'
          ? ['desde','hasta','cliente']
          : path === '/api/reportes/cobranzas/'
            ? ['desde','hasta','cliente','estado']
            : path === '/api/finanzas/cobranzas/'
            ? ['estado','cliente','obra','fecha_vencimiento_desde','fecha_vencimiento_hasta','fecha_emision_desde','fecha_emision_hasta']
             : path === '/api/documentos-metadata/' ? ['obra'] : [];
    const allowed = new Set(['page', ...pathFilters]);
    if (url.origin !== origin || url.pathname !== path || [...url.searchParams.keys()].some((key) => !allowed.has(key))
        || [...url.searchParams.keys()].some((key) => url.searchParams.getAll(key).length !== 1 || url.searchParams.get(key) === '')) throw new Error('invalid');
    const pageText=url.searchParams.get('page')||'1',page=Number(pageText);
    if(!/^[1-9][0-9]*$/.test(pageText)||!Number.isSafeInteger(page)||page<1)throw new Error('invalid');
    const value=(key)=>url.searchParams.get(key);
    const validId=(input)=>/^[1-9][0-9]{0,18}$/.test(input||'');
    const validDate=(input)=>{if(!/^\d{4}-\d{2}-\d{2}$/.test(input||''))return false;const date=new Date(`${input}T00:00:00Z`);return !Number.isNaN(date.getTime())&&date.toISOString().slice(0,10)===input;};
    const datePair=(from,to)=>{const a=value(from),b=value(to);if(!!a!==!!b)return false;if(!a)return true;if(!validDate(a)||!validDate(b)||a>b)return false;return (Date.parse(`${b}T00:00:00Z`)-Date.parse(`${a}T00:00:00Z`))/86400000+1<=366;};
    if(path==='/api/alertas/'){
      if(value('estado')&&!['PENDIENTE','ATENDIDA','RESUELTA','TODAS'].includes(value('estado')))throw new Error('invalid');
      if(value('tipo')&&!['PRESUPUESTO_PENDIENTE_GERENCIA','OBRA_SUSPENDIDA','TURNO_PENDIENTE_REVISION','COBRANZA_VENCIDA'].includes(value('tipo')))throw new Error('invalid');
      if(value('recurso_tipo')&&!['PRESUPUESTO','OBRA','TURNO','DOCUMENTO'].includes(value('recurso_tipo')))throw new Error('invalid');
      if((value('recurso_id')&&!value('recurso_tipo'))||(value('recurso_id')&&!validId(value('recurso_id')))||!datePair('desde','hasta'))throw new Error('invalid');
    }
    if(path.startsWith('/api/reportes/')){
      if(!datePair('desde','hasta')||(value('cliente')&&!validId(value('cliente'))))throw new Error('invalid');
      if(value('estado')){const states=path.endsWith('/obras/')?['PLANIFICADA','EN_PROCESO','SUSPENDIDA','FINALIZADA','CANCELADA']:path.endsWith('/cobranzas/')?['PENDIENTE','PARCIAL','PAGADA','VENCIDA']:[];if(!states.includes(value('estado')))throw new Error('invalid');}
      if(value('fecha_base')&&!['CREACION','FINALIZACION'].includes(value('fecha_base')))throw new Error('invalid');
      if(path.endsWith('/rentabilidad/')&&(value('estado')||value('fecha_base')))throw new Error('invalid');
      if(path.endsWith('/cobranzas/')&&value('fecha_base'))throw new Error('invalid');
      if(path.endsWith('/obras/')&&value('fecha_base')==='FINALIZACION'&&value('estado')&&value('estado')!=='FINALIZADA')throw new Error('invalid');
    }
    if(path==='/api/finanzas/cobranzas/'){
      if((value('cliente')&&!validId(value('cliente')))||(value('obra')&&!validId(value('obra')))||!datePair('fecha_emision_desde','fecha_emision_hasta')||!datePair('fecha_vencimiento_desde','fecha_vencimiento_hasta'))throw new Error('invalid');
      if(value('estado')&&!['PENDIENTE','PARCIAL','PAGADA','VENCIDA'].includes(value('estado')))throw new Error('invalid');
    }
    if(path==='/api/documentos-metadata/'&&!validId(value('obra')))throw new Error('invalid');
    return page;
  } catch { throw new ApiError(502, 'El servidor devolvió una página no segura.'); }
}

export const strictObject = (value, keys, optional = []) => {
  if (!value || typeof value !== 'object' || Array.isArray(value) || value instanceof Date || keys.some((key) => !optional.includes(key) && !Object.hasOwn(value, key))
      || Object.keys(value).some((key) => !keys.includes(key))) throw new ApiError(502, 'El servidor devolvió datos inesperados.');
  return value;
};
export const positiveInteger = (value) => Number.isSafeInteger(value) && value > 0;
export const decimalString = (value, signed = false) => typeof value === 'string' && new RegExp(signed ? '^-?(?:0|[1-9][0-9]*)\\.[0-9]{2}$' : '^(?:0|[1-9][0-9]*)\\.[0-9]{2}$').test(value);
