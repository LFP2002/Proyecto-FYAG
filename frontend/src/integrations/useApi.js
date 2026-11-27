import { useEffect, useRef, useState } from 'react';
import { ApiError } from '../auth/client.js';
import { createScope } from '../comercial/scope.js';
import { useAuth } from '../auth/AuthContext.jsx';
import { paginationURL, samePageFilters } from './pagination.js';
import { civilRange } from './dates.js';

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

export function readPage(value, path, max = 25, filters = null) {
  if (!value || !Number.isSafeInteger(value.count) || value.count < 0 || !Array.isArray(value.results)
      || value.results.length > max || !('next' in value) || !('previous' in value)) {
    throw new ApiError(502, 'El servidor devolvió una página inesperada.');
  }
  for (const key of ['next', 'previous']) {
    if (value[key] !== null && typeof value[key] !== 'string') throw new ApiError(502, 'El servidor devolvió una página inesperada.');
    if (value[key]) safePage(value[key], path, filters);
  }
  return value;
}

export function safePage(link, path, filters = null) {
  try {
    const url = paginationURL(link, path);
    const pathFilters = path === '/api/alertas/'
      ? ['estado','tipo','recurso_tipo','recurso_id','desde','hasta']
      : path === '/api/reportes/obras/'
        ? ['desde','hasta','cliente','estado','fecha_base']
        : path === '/api/reportes/rentabilidad/'
          ? ['desde','hasta','cliente']
          : path === '/api/reportes/cobranzas/'
            ? ['desde','hasta','cliente','estado']
            : path === '/api/finanzas/cobranzas/'
            ? ['estado','cliente','obra','fecha_vencimiento_desde','fecha_vencimiento_hasta','fecha_emision_desde','fecha_emision_hasta','buscar']
             : ['/api/finanzas/documentos/','/api/finanzas/obras-elegibles/'].includes(path) ? ['buscar']
             : path==='/api/finanzas/obras-resumen/' ? ['buscar','estado','situacion_financiera','cliente_nombre','categoria_nombre','responsable_nombre','fecha_programada_desde','fecha_programada_hasta','ordering']
             : path === '/api/finanzas/cobranzas/supervision-gerencial/' ? ['vista','buscar','desde','hasta']
             : path === '/api/finanzas/egresos/' ? ['buscar','categoria','medio','obra','activo','desde','hasta','resumen']
             : path === '/api/finanzas/egresos/supervision-gerencial/' ? ['vista','buscar','categoria','medio','desde','hasta']
             : path === '/api/inventario/mermas-bodega/' ? ['vista','buscar','estado','tipo','articulo']
             : path === '/api/inventario/solicitudes-supervisor/' ? ['estado','buscar']
             : path === '/api/inventario/disponibilidad/' ? ['seccion','buscar','stock','vista']
             : path === '/api/inventario/finanzas/' ? ['seccion','buscar','filtro','tipo','desde','hasta']
             : path === '/api/inventario/supervision-gerencial/' ? ['seccion','filtro','buscar','estado','desde','hasta','articulo']
             : path === '/api/documentos-metadata/' ? ['obra'] : [];
    const allowed = new Set(['page', ...pathFilters]);
    if ([...url.searchParams.keys()].some((key) => !allowed.has(key))
        || [...url.searchParams.keys()].some((key) => url.searchParams.getAll(key).length !== 1 || url.searchParams.get(key) === '')) throw new Error('invalid');
    if (filters !== null && !samePageFilters(url, filters)) throw new Error('Filtros incompatibles.');
    const pageText=url.searchParams.get('page')||'1',page=Number(pageText);
    if(!/^[1-9][0-9]*$/.test(pageText)||!Number.isSafeInteger(page)||page<1)throw new Error('invalid');
    const value=(key)=>url.searchParams.get(key);
    const validId=(input)=>/^[1-9][0-9]{0,18}$/.test(input||'')&&BigInt(input)<=9223372036854775807n;
    const datePair=(from,to)=>{const a=value(from),b=value(to);if(!!a!==!!b)return false;return !a||civilRange(a,b);};
    if(path==='/api/alertas/'){
      if(value('estado')&&!['PENDIENTE','ATENDIDA','RESUELTA','TODAS'].includes(value('estado')))throw new Error('invalid');
      if(value('tipo')&&!['PRESUPUESTO_PENDIENTE_FINANZAS','OBRA_SUSPENDIDA','TURNO_PENDIENTE_REVISION','COBRANZA_VENCIDA'].includes(value('tipo')))throw new Error('invalid');
      if(value('recurso_tipo')&&!['PRESUPUESTO','OBRA','TURNO','DOCUMENTO'].includes(value('recurso_tipo')))throw new Error('invalid');
      if((value('recurso_id')&&!value('recurso_tipo'))||(value('recurso_id')&&!validId(value('recurso_id')))||!datePair('desde','hasta'))throw new Error('invalid');
    }
    if(path.startsWith('/api/reportes/')){
      if(!datePair('desde','hasta')||(value('cliente')&&!validId(value('cliente'))))throw new Error('invalid');
      if(value('estado')){const states=path.endsWith('/obras/')?['PLANIFICADA','EN_PROCESO','SUSPENDIDA','FINALIZADA','CANCELADA']:path.endsWith('/cobranzas/')?['PENDIENTE','PARCIAL','PAGADA','VENCIDA']:[];if(!states.includes(value('estado')))throw new Error('invalid');}
      if(value('fecha_base')&&!['CREACION','FINALIZACION'].includes(value('fecha_base')))throw new Error('invalid');
      if(path.endsWith('/rentabilidad/')&&(value('estado')||value('fecha_base')))throw new Error('invalid');
      if(path.endsWith('/cobranzas/')&&value('fecha_base'))throw new Error('invalid');
      if(path.endsWith('/obras/')&&value('fecha_base')==='FINALIZACION'&&value('estado')!=='FINALIZADA')throw new Error('invalid');
    }
    if(path==='/api/finanzas/cobranzas/'){
      if((value('cliente')&&!validId(value('cliente')))||(value('obra')&&!validId(value('obra')))||!datePair('fecha_emision_desde','fecha_emision_hasta')||!datePair('fecha_vencimiento_desde','fecha_vencimiento_hasta'))throw new Error('invalid');
      if(value('estado')&&!['PENDIENTE','PARCIAL','PAGADA','VENCIDA'].includes(value('estado')))throw new Error('invalid');
    }
    if(path==='/api/finanzas/cobranzas/supervision-gerencial/'){
      if(!datePair('desde','hasta')||(value('vista')&&!['atencion','vigentes','documentos'].includes(value('vista')))||(value('buscar')||'').length>100)throw new Error('invalid');
    }
    if(path==='/api/finanzas/egresos/'){
      if(!datePair('desde','hasta')||(value('buscar')||'').length>100||(value('obra')&&!validId(value('obra')))||(value('activo')&&!['true','false'].includes(value('activo')))||(value('resumen')&&value('resumen')!=='true')||(value('categoria')&&!['MATERIALES','TRANSPORTE','SERVICIOS','ARRIENDO','OTROS'].includes(value('categoria')))||(value('medio')&&!['TRANSFERENCIA','EFECTIVO','TARJETA','OTRO'].includes(value('medio'))))throw new Error('invalid');
    }
    if(path==='/api/finanzas/egresos/supervision-gerencial/'){
      if(!value('desde')||!datePair('desde','hasta')||(value('vista')&&!['activos','anulados','todos'].includes(value('vista')))||(value('buscar')||'').length>100||(value('categoria')&&!['MATERIALES','TRANSPORTE','SERVICIOS','ARRIENDO','OTROS'].includes(value('categoria')))||(value('medio')&&!['TRANSFERENCIA','EFECTIVO','TARJETA','OTRO'].includes(value('medio'))))throw new Error('invalid');
    }
    if(path==='/api/inventario/mermas-bodega/'){
      if((value('vista')&&value('vista')!=='finanzas')||(value('buscar')&&(value('vista')!=='finanzas'||value('buscar').length>150))||(value('estado')&&!['PENDIENTE','APROBADA','RECHAZADA'].includes(value('estado')))||(value('tipo')&&!['DANO','VENCIMIENTO','EXTRAVIO','DIFERENCIA_CONTEO','OTRA'].includes(value('tipo')))||(value('articulo')&&!validId(value('articulo'))))throw new Error('invalid');
    }
    if(path==='/api/inventario/solicitudes-supervisor/' && ((value('estado')&&!['PENDIENTE','APROBADA','RECHAZADA'].includes(value('estado')))||(value('buscar')||'').length>150))throw new Error('invalid');
    if(path==='/api/inventario/disponibilidad/'){
      const section=value('seccion')||'disponibilidad';
      if(!['disponibilidad','pendientes','historial'].includes(section)||(value('buscar')||'').length>150||(value('stock')&&(section!=='disponibilidad'||!['con_stock','sin_stock'].includes(value('stock'))))||(value('vista')&&(section!=='historial'||!['entregas','devoluciones','por_recibir'].includes(value('vista')))))throw new Error('invalid');
    }
    if(path==='/api/inventario/finanzas/'){
      const section=value('seccion')||'inventario';
      if(!['inventario','movimientos','valoraciones','regularizaciones','ingresos','historicos'].includes(section)||(value('buscar')||'').length>150||!datePair('desde','hasta')||(value('filtro')&&(section!=='inventario'||!['sin_stock','pendiente'].includes(value('filtro'))))||((value('tipo')||value('desde'))&&section!=='movimientos')||(value('tipo')&&!['INGRESO','SALIDA','DEVOLUCION','MERMA'].includes(value('tipo'))))throw new Error('invalid');
    }
    if(path==='/api/inventario/supervision-gerencial/'){
      const stock=(value('seccion')||'existencias')==='existencias',state=value('estado');
      if(!['existencias','mermas'].includes(value('seccion')||'existencias')||(value('buscar')||'').length>100||(value('filtro')&&!(stock?['sin_stock','pendiente']:['bodega','obra']).includes(value('filtro')))||(state&&!['APROBADA','PENDIENTE','RECHAZADA'].includes(state))||!datePair('desde','hasta')||(stock&&(state||value('desde')))||(!stock&&value('articulo'))||(value('articulo')&&!validId(value('articulo')))||(state==='PENDIENTE'&&value('desde')))throw new Error('invalid');
    }
    if((value('buscar')||'').length>150 && ['/api/finanzas/cobranzas/','/api/finanzas/documentos/','/api/finanzas/obras-elegibles/','/api/finanzas/obras-resumen/'].includes(path))throw new Error('invalid');
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
