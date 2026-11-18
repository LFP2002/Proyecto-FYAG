import test from 'node:test';
import assert from 'node:assert/strict';
import React from 'react';
import Renderer, { act } from 'react-test-renderer';
import { createServer } from 'vite';
import { document as financialDocument, paginated } from './helpers/finance-contract.js';

const API = 'https://api.example.test', WEB = 'https://web.example.test';
const flush = () => new Promise((resolve) => setImmediate(resolve));
const text = (node) => typeof node === 'string' ? node : (node?.children || []).map(text).join('');
let server, safePage, AuthProvider, EvidenceMetadata, Cobranzas, Reportes;
test.before(async () => {
  globalThis.location = { origin: WEB };
  server = await createServer({ configFile: false, define: { 'import.meta.env.VITE_API_BASE_URL': JSON.stringify(API) }, esbuild: { jsx: 'automatic' }, server: { middlewareMode: true, ws: false, hmr: false }, appType: 'custom', optimizeDeps: { noDiscovery: true, include: [] } });
  ({ safePage } = await server.ssrLoadModule('/src/integrations/useApi.js'));
  ({ AuthProvider } = await server.ssrLoadModule('/src/auth/AuthContext.jsx'));
  ({ default: EvidenceMetadata } = await server.ssrLoadModule('/src/integrations/EvidenceMetadata.jsx'));
  ({ default: Cobranzas } = await server.ssrLoadModule('/src/pages/Cobranzas.jsx'));
  ({ default: Reportes } = await server.ssrLoadModule('/src/pages/Reportes.jsx'));
});
test.after(async () => { delete globalThis.location; await server.close(); });

test('Paginación split-origin: enlaces relativos, query y absolutos de API/web explícitos; filtros independientes del orden', () => {
  const path = '/api/finanzas/cobranzas/', filters = { obra: '7', estado: 'PENDIENTE' };
  for (const link of [`${path}?page=2&estado=PENDIENTE&obra=7`, '?estado=PENDIENTE&obra=7&page=2', `${API}${path}?obra=7&page=2&estado=PENDIENTE`, `${WEB}${path}?page=2&obra=7&estado=PENDIENTE`]) assert.equal(safePage(link, path, filters), 2);
  assert.equal(safePage(`${API}${path}?estado=PENDIENTE&obra=7`, path, filters), 1, 'DRF puede omitir page=1 en previous');
  assert.equal(safePage(`${API}/api/documentos-metadata/?page=2&obra=7`, '/api/documentos-metadata/', { obra: 7 }), 2);
  assert.equal(safePage(`${API}/api/reportes/cobranzas/?cliente=15&page=2`, '/api/reportes/cobranzas/', { cliente: '15' }), 2);
});

test('Paginación rechaza orígenes ajenos, credenciales, fragmentos, ruta/query manipuladas y páginas inválidas', () => {
  const path = '/api/finanzas/cobranzas/';
  for (const link of [
    `https://evil.example${path}?obra=7&page=2`, `http://api.example.test${path}?obra=7&page=2`,
    `https://api.example.test.evil.example${path}?obra=7&page=2`, `https://user:password@api.example.test${path}?obra=7&page=2`,
    `${API}${path}?obra=7&page=2#data`, `${API}/api/reportes/cobranzas/?obra=7&page=2`,
    `${API}${path}?obra=7&page=2&page=3`, `${API}${path}?obra=7&obra=8&page=2`,
    `${API}${path}?obra=8&page=2`, `${API}${path}?page=2`, `${API}${path}?obra=7&page=2&redirect=https://evil.example`,
    ...['0','-1','01','1.5','1e2','9007199254740992',''].map((page) => `${API}${path}?obra=7&page=${page}`),
  ]) assert.throws(() => safePage(link, path, { obra: '7' }), (error) => error.name === 'ApiError', link);
  for(const query of ['obra=9223372036854775808','fecha_emision_desde=0000-01-01&fecha_emision_hasta=0000-01-02','fecha_emision_desde=2026-02-30&fecha_emision_hasta=2026-03-01','estado=OTRO']) assert.throws(()=>safePage(`${API}${path}?${query}&page=2`,path));
  assert.throws(()=>safePage(`${API}/api/reportes/obras/?fecha_base=FINALIZACION&page=2`,'/api/reportes/obras/'));
});

test('Proxy same-origin sin VITE_API_BASE_URL conserva páginas relativas y absolutas propias', async () => {
  const proxy = await createServer({ configFile: false, define: { 'import.meta.env.VITE_API_BASE_URL': JSON.stringify('') }, server: { middlewareMode: true, ws: false, hmr: false }, appType: 'custom', optimizeDeps: { noDiscovery: true, include: [] } });
  try {
    const { paginationURL } = await proxy.ssrLoadModule('/src/integrations/pagination.js');
    assert.equal(paginationURL('/api/alertas/?page=2', '/api/alertas/').origin, WEB);
    assert.equal(paginationURL(`${WEB}/api/alertas/?page=2`, '/api/alertas/').origin, WEB);
    assert.throws(() => paginationURL(`${API}/api/alertas/?page=2`, '/api/alertas/'));
  } finally { await proxy.close(); }
});

async function mount(Page, request, role, props) {
  const session = { status: 'authenticated', user: { id: 9, username: 'Cuenta QA sintética', email: 'qa@example.test', role } };
  const client = { getSnapshot: () => session, subscribe: () => () => {}, restore: async () => {}, request };
  let renderer;
  await act(async () => { renderer = Renderer.create(React.createElement(AuthProvider, { client }, React.createElement(Page, props))); await flush(); });
  return renderer;
}
function absolutePage(rows, url) {
  const value = paginated(rows, url);
  for (const key of ['next', 'previous']) if (value[key]) value[key] = API + value[key];
  return value;
}

test('Cobranzas, Reportes y 012A navegan URL absoluta autorizada reconstruyendo ruta interna y filtros', async () => {
  for (const module of ['cobranzas', 'reportes', 'metadata']) {
    const calls = [];
    const request = async (path) => {
      calls.push(path);
      const url = new URL(path, API);
      if (url.pathname === '/api/finanzas/documentos/') return { count: 0, next: null, previous: null, results: [] };
      if (url.pathname === '/api/finanzas/cobranzas/resumen/') return { moneda: 'CLP', documentos: 26, conteos: { PENDIENTE: 26, PARCIAL: 0, PAGADA: 0, VENCIDA: 0 }, monto_documentado_total: '2600.00', abonado_total: '0.00', saldo_total: '2600.00', saldo_vencido: '0.00' };
      if (url.pathname === '/api/finanzas/cobranzas/') return absolutePage(Array.from({ length: 26 }, (_, i) => financialDocument(i + 1, i + 7)), url);
      if (url.pathname === '/api/reportes/catalogo/') return { moneda: 'CLP', zona_horaria: 'America/Santiago', formatos: ['csv'], reportes: [{ tipo: 'cobranzas', titulo: 'Cobranzas', filtros: ['cliente'], formatos: ['csv'] }] };
      if (url.pathname === '/api/reportes/cobranzas/') {
        const row = { documento: 1, obra: 7, codigo_obra: 'OB-7', cliente: 15, cliente_nombre: 'Cliente sintético', tipo_documento: 'FACTURA_EXENTA', folio_externo: '001', fecha_emision: '2026-11-10', fecha_vencimiento: '2026-11-30', moneda: 'CLP', monto_documentado_bruto: '100.00', abonado: '0.00', saldo: '100.00', estado_cobranza: 'PENDIENTE' };
        return { ...absolutePage(Array.from({ length: 26 }, (_, i) => ({ ...row, documento: i + 1, obra: i + 7, codigo_obra: `OB-${i + 7}` })), url), moneda: 'CLP', periodo: { desde: '2026-11-01', hasta: '2026-11-17' }, fecha_corte: '2026-11-17T12:00:00Z', totales: { documentos: 26, monto_documentado_bruto: '2600.00', abonado: '0.00', saldo: '2600.00', saldo_vencido: '0.00' } };
      }
      if (url.pathname === '/api/documentos-metadata/') return { ...absolutePage(Array.from({ length: 26 }, (_, i) => ({ evidencia_id: i + 1, obra_id: 7, turno_id: 2, tipo_mime: 'image/png', tamano_bytes: 20, creado_en: '2026-11-17T12:00:00Z', sincronizado_en: '2026-11-17T12:00:00Z', descripcion: '', etiquetas: [], atributos: {}, revision: 0 })), url), proyeccion: 'EVENTUAL', fuente_autoritativa: 'POSTGRESQL' };
      throw new Error(`Ruta no prevista: ${path}`);
    };
    const Page = module === 'cobranzas' ? Cobranzas : module === 'reportes' ? Reportes : EvidenceMetadata;
    const renderer = await mount(Page, request, module === 'metadata' ? 'GERENCIA' : 'ADMINISTRATIVO_FINANZAS', { obraId: 7 });
    try {
      const root = renderer.root;
      if (module !== 'metadata') {
        const label = module === 'cobranzas' ? 'Cliente ID' : 'ID de cliente';
        const field = root.findAllByType('label').find((node) => node.children[0] === label).findByType('input');
        await act(async () => { field.props.onChange({ target: { value: module === 'cobranzas' ? '3' : '15' } }); await flush(); });
      }
      const label = module === 'cobranzas' ? 'Paginación de cobranzas' : module === 'reportes' ? 'Paginación del reporte cobranzas' : 'Paginación de metadatos';
      const next = root.findByProps({ 'aria-label': label }).findAllByType('button').find((button) => text(button) === 'Siguiente');
      assert.equal(next.props.disabled, false, text(renderer.toJSON()));
      await act(async () => { next.props.onClick(); await flush(); });
      const route = module === 'cobranzas' ? '/api/finanzas/cobranzas/' : module === 'reportes' ? '/api/reportes/cobranzas/' : '/api/documentos-metadata/';
      const last = calls.filter((path) => new URL(path, API).pathname === route).at(-1), query = new URL(last, API).searchParams;
      assert.ok(last.startsWith('/api/')); assert.equal(query.get('page'), '2');
      assert.equal(query.get(module === 'metadata' ? 'obra' : 'cliente'), module === 'reportes' ? '15' : module === 'cobranzas' ? '3' : '7');
      assert.ok(calls.every((path) => path.startsWith('/api/')), 'No se sigue ninguna URL absoluta del servidor');
      const previous = root.findByProps({ 'aria-label': label }).findAllByType('button').find((button) => text(button) === 'Anterior');
      assert.equal(previous.props.disabled, false);
      await act(async () => { previous.props.onClick(); await flush(); });
      const back = new URL(calls.filter((path) => new URL(path, API).pathname === route).at(-1), API).searchParams;
      assert.equal(back.get('page') || '1', '1');
      assert.equal(back.get(module === 'metadata' ? 'obra' : 'cliente'), module === 'reportes' ? '15' : module === 'cobranzas' ? '3' : '7');
    } finally { await act(async () => renderer.unmount()); }
  }
});
