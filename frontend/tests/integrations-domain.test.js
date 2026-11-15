import test from 'node:test';
import assert from 'node:assert/strict';
import { createAuthClient, ApiError } from '../src/auth/client.js';
import { createServer } from 'vite';
import React from 'react';
import Renderer, { act } from 'react-test-renderer';

let server, AuthProvider, Alertas, Cobranzas, Dashboard, Reportes;
test.before(async () => {
  server = await createServer({ configFile: false, esbuild: { jsx: 'automatic' }, server: { middlewareMode: true, ws: false, hmr: false }, appType: 'custom', optimizeDeps: { noDiscovery: true, include: [] } });
  ({ AuthProvider } = await server.ssrLoadModule('/src/auth/AuthContext.jsx'));
  ({ default: Alertas } = await server.ssrLoadModule('/src/pages/Alertas.jsx'));
  ({ default: Cobranzas } = await server.ssrLoadModule('/src/pages/Cobranzas.jsx'));
  ({ default: Dashboard } = await server.ssrLoadModule('/src/pages/Dashboard.jsx'));
  ({ default: Reportes } = await server.ssrLoadModule('/src/pages/Reportes.jsx'));
  globalThis.window = { location: { origin: 'http://localhost' } };
  globalThis.document = { body: { appendChild() {} }, createElement: () => ({ click() {}, remove() {} }) };
});
test.after(async () => { delete globalThis.window; delete globalThis.document; await server.close(); });
const flush = () => new Promise((resolve) => setImmediate(resolve));
const text = (node) => typeof node === 'string' ? node : (node.children || []).map(text).join('');

function apiFor(role, calls) {
  const alert = { id: 3, tipo: 'OBRA_SUSPENDIDA', estado: 'PENDIENTE', severidad: 'ALTA', rol_destinatario: role, recurso_tipo: 'OBRA', recurso_id: 4, recurso_codigo: 'OB-000004', obra: 4, titulo: 'Obra suspendida', descripcion: 'La obra se encuentra suspendida.', creado_en: '2026-11-14T10:00:00-03:00', atendida_por: null, atendida_en: null, motivo_atencion: null, resuelta_en: null, acciones_permitidas: ['ATENDER'] };
  const send = async (path, options = {}) => {
    calls.push({ path, options });
    if (path === '/api/alertas/resumen/') return { generado_en: '2026-11-14T10:00:00-03:00', zona_horaria: 'America/Santiago', por_estado: { PENDIENTE: 1, ATENDIDA: 0, RESUELTA: 0 }, activas: 1, por_tipo: { OBRA_SUSPENDIDA: { PENDIENTE: 1, ATENDIDA: 0, RESUELTA: 0 } }, sincronizacion: { ultima_correcta_en: null, desactualizada: false } };
    if (path === '/api/alertas/' || path === '/api/alertas/?page=1') return { count: 1, next: null, previous: null, results: [alert] };
    if (path === '/api/alertas/3/') return alert;
    if (path.startsWith('/api/alertas/3/historial/')) return { count: 0, next: null, previous: null, results: [] };
    if (path === '/api/finanzas/cobranzas/' || path === '/api/finanzas/cobranzas/?page=1') return { count: 0, next: null, previous: null, results: [] };
    if (path.startsWith('/api/finanzas/cobranzas/resumen/')) return { moneda: 'CLP', documentos: 0, conteos: { PENDIENTE: 0, PARCIAL: 0, PAGADA: 0, VENCIDA: 0 }, monto_documentado_total: '0.00', abonado_total: '0.00', saldo_total: '0.00', saldo_vencido: '0.00' };
    if (path === '/api/dashboard/resumen/') return { generado_en: '2026-11-14T10:00:00-03:00', zona_horaria: 'America/Santiago', moneda: 'CLP', periodo: { desde: '2026-06-01', hasta: '2026-11-14' }, operacion: { obras_por_estado_actual: { PLANIFICADA: 0, EN_PROCESO: 0, SUSPENDIDA: 0, FINALIZADA: 0, CANCELADA: 0 }, presupuestos_pendientes_gerencia_actual: 0, obras_finalizadas_periodo: 0 }, rentabilidad_cerrada_periodo: { obras_con_cierre: 0, presupuesto_neto: '0.00', costo_real_neto: '0.00', margen_real_neto: '0.00' }, cobranza_actual: { documentos_vigentes: 0, monto_documentado_bruto: '0.00', abonado: '0.00', saldo: '0.00', saldo_vencido: '0.00' } };
    if (path.startsWith('/api/dashboard/serie-obras/')) { const months = Number(new URL(path, 'http://localhost').searchParams.get('meses') || 6); return { metrica: 'OBRAS_FINALIZADAS', zona_horaria: 'America/Santiago', puntos: Array.from({ length: months }, (_, i) => ({ mes: `2026-${String(i + 1).padStart(2, '0')}`, cantidad: 0 })) }; }
    if (path.startsWith('/api/dashboard/obras-activas/')) return { count: 0, next: null, previous: null, results: [] };
    if (path === '/api/reportes/catalogo/') return { moneda: 'CLP', zona_horaria: 'America/Santiago', formatos: ['csv', 'xlsx', 'pdf'], reportes: (role === 'GERENCIA' ? ['obras', 'rentabilidad', 'cobranzas'] : ['cobranzas']).map((tipo) => ({ tipo, titulo: tipo, filtros: ['desde', 'hasta', 'cliente', ...(tipo === 'obras' ? ['estado', 'fecha_base'] : tipo === 'cobranzas' ? ['estado'] : [])], formatos: ['csv', 'xlsx', 'pdf'] })) };
    if (path.startsWith('/api/reportes/')) { const tipo = path.split('/')[3]; return { count: 0, next: null, previous: null, results: [], totales: tipo === 'obras' ? { obras: 0, presupuesto_neto: '0.00' } : tipo === 'rentabilidad' ? { obras: 0, presupuesto_neto: '0.00', costo_real_neto: '0.00', margen_neto: '0.00' } : { documentos: 0, monto_documentado_bruto: '0.00', abonado: '0.00', saldo: '0.00', saldo_vencido: '0.00' }, periodo: { desde: '2026-11-01', hasta: '2026-11-14' }, moneda: 'CLP', fecha_corte: '2026-11-14T10:00:00-03:00' }; }
    throw new Error(`Unexpected API request ${path}`);
  };
  return send;
}
async function mount(Page, role) {
  const calls = [], request = apiFor(role, calls);
  const session = { status: 'authenticated', user: { id: 9, username: role, email: 'account@example.test', role } };
  const client = { getSnapshot: () => session, subscribe: () => () => {}, restore: async () => {}, request };
  let renderer;
  await act(async () => { renderer = Renderer.create(React.createElement(AuthProvider, { client }, React.createElement(Page))); await flush(); });
  return { renderer, calls };
}

test('dashboard consulta los tres endpoints y despliega respuestas reales, sin mock', { timeout: 15000 }, async () => {
  const { renderer, calls } = await mount(Dashboard, 'GERENCIA');
  try { assert.ok(calls.some((c) => c.path === '/api/dashboard/resumen/')); assert.ok(calls.some((c) => c.path === '/api/dashboard/serie-obras/?meses=6')); assert.ok(calls.some((c) => c.path === '/api/dashboard/obras-activas/')); assert.match(text(renderer.toJSON()), /Obras finalizadas por mes/); assert.doesNotMatch(text(renderer.toJSON()), /Margen proyectado|Exportación generada/); } finally { await act(async () => renderer.unmount()); }
});
test('cobranzas consulta cartera y resumen sin exponer acciones de mutación', { timeout: 15000 }, async () => {
  const { renderer, calls } = await mount(Cobranzas, 'ADMINISTRATIVO_FINANZAS');
  try { assert.ok(calls.some((c) => c.path.startsWith('/api/finanzas/cobranzas/'))); assert.ok(calls.some((c) => c.path.startsWith('/api/finanzas/cobranzas/resumen/'))); assert.doesNotMatch(text(renderer.toJSON()), /Nuevo pago|Anular|Facturado/); } finally { await act(async () => renderer.unmount()); }
});
test('reportes consulta catálogo autorizado y primer listado JSON', { timeout: 15000 }, async () => {
  const { renderer, calls } = await mount(Reportes, 'ADMINISTRATIVO_FINANZAS');
  try { assert.ok(calls.some((c) => c.path === '/api/reportes/catalogo/')); assert.ok(calls.some((c) => c.path.startsWith('/api/reportes/cobranzas/'))); assert.doesNotMatch(text(renderer.toJSON()), /Reporte de obras|Rentabilidad/); } finally { await act(async () => renderer.unmount()); }
});
test('alertas solicita resumen/lista e impone matriz por rol', { timeout: 15000 }, async () => {
  for (const role of ['GERENCIA', 'SUPERVISOR_OBRAS']) {
    const { renderer, calls } = await mount(Alertas, role);
    try { assert.ok(calls.some((c) => c.path === '/api/alertas/resumen/')); assert.ok(calls.some((c) => c.path === '/api/alertas/')); assert.match(text(renderer.toJSON()), /Obra suspendida/); if (role === 'SUPERVISOR_OBRAS') assert.ok(calls.every((c) => !c.path.includes('COBRANZA_VENCIDA'))); } finally { await act(async () => renderer.unmount()); }
  }
});
test('AuthClient mantiene metadata de descarga y códigos públicos de conflicto de alerta', async () => {
  const calls = []; const json = (data, status = 200, headers = {}) => new Response(JSON.stringify(data), { status, headers });
  const client = createAuthClient({ fetchImpl: async (path, options) => { calls.push({ path, options }); if (path.endsWith('/csrf/')) return json({ csrfToken: 'csrf' }); if (path.endsWith('/login/')) return json({ access: 'token', csrfToken: 'csrf' }); if (path.endsWith('/me/')) return json({ id: 9, username: 'G', email: 'g@example.test', role: 'GERENCIA' }); if (path.endsWith('/exportar/?formato=pdf')) return new Response('%PDF-test', { status: 200, headers: { 'Content-Type': 'application/pdf', 'Content-Disposition': 'attachment; filename="fyag-obras-20261114-120000.pdf"' } }); return json({ motivo: ['Revisa el motivo.'], code: 'alerta_ya_atendida', password: 'hidden' }, 409, { 'Content-Type': 'application/json' }); } });
  await client.login({ email: 'g@example.test', password: 'dummy' }); const result = await client.request('/api/reportes/obras/exportar/?formato=pdf', { responseType: 'blob-response' }); assert.equal(result.contentType, 'application/pdf'); assert.match(result.contentDisposition, /filename="fyag-obras-/); assert.equal(await result.blob.text(), '%PDF-test');
  await assert.rejects(client.request('/api/alertas/3/atender/', { method: 'POST', body: { motivo: 'Revisar' } }), (error) => error instanceof ApiError && error.code === 'alerta_ya_atendida' && !Object.hasOwn(error.fieldErrors, 'password'));
});
