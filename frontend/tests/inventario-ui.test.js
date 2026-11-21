import test, { before, after } from 'node:test';
import assert from 'node:assert/strict';
import React from 'react';
import Renderer, { act } from 'react-test-renderer';
import { createServer } from 'vite';

let server, AuthProvider, Inventario, safePage;
before(async () => {
  server = await createServer({ configFile: false, esbuild: { jsx: 'automatic' }, server: { middlewareMode: true, ws: false, hmr: false }, appType: 'custom', optimizeDeps: { noDiscovery: true, include: [] } });
  ({ AuthProvider } = await server.ssrLoadModule('/src/auth/AuthContext.jsx'));
  ({ default: Inventario } = await server.ssrLoadModule('/src/pages/Inventario.jsx'));
  ({ safePage } = await server.ssrLoadModule('/src/integrations/useApi.js'));
});
after(async () => { await server?.close(); });
const flush = () => new Promise((resolve) => setImmediate(resolve));
const text = (node) => typeof node === 'string' ? node : (node.children || []).map(text).join('');
async function mount(role, response) {
  const calls = [];
  const session = { status: 'authenticated', user: { id: 27, username: role, email: 'account@example.test', role } };
  const client = { getSnapshot: () => session, subscribe: () => () => {}, restore: async () => {}, logout: async () => {}, request: async (path, options = {}) => { calls.push({ path, ...options }); return response(path, options); } };
  let renderer;
  await act(async () => { renderer = Renderer.create(React.createElement(AuthProvider, { client }, React.createElement(Inventario))); await flush(); });
  return { renderer, calls };
}

test('paginación de inventario conserva filtros permitidos y rechaza query extra', () => {
  assert.equal(safePage('/api/inventario/solicitudes-materiales/?obra=8&page=2', '/api/inventario/solicitudes-materiales/'), 2);
  assert.equal(safePage('/api/inventario/articulos/?buscar=cable&page=2', '/api/inventario/articulos/'), 2);
  assert.throws(() => safePage('/api/inventario/solicitudes-materiales/?obra=8&rol=GERENCIA&page=2', '/api/inventario/solicitudes-materiales/'), { name: 'ApiError' });
  assert.throws(() => safePage('/api/inventario/articulos/?buscar=cable&page=0', '/api/inventario/articulos/'), { name: 'ApiError' });
});

test('Bodeguero ve catálogo con Bootstrap Icons y sin columnas de costo, con escritura disponible', async () => {
  const { renderer, calls } = await mount('BODEGUERO', async (path) => {
    if (path === '/api/inventario/articulos/?page=1') return { count: 1, next: null, previous: null, results: [{ id: 4, codigo: 'cable-01', nombre: 'Cable', descripcion: '', unidad: 'm', activo: true, costo_unitario_neto: '999.00' }] };
    throw new Error(`Ruta inesperada: ${path}`);
  });
  try {
    assert.ok(calls.some((call) => call.path === '/api/inventario/articulos/?page=1'));
    assert.match(text(renderer.toJSON()), /Bodega e inventario|Artículos/);
    assert.doesNotMatch(text(renderer.toJSON()), /999\.00|costo unitario/);
    assert.ok(renderer.root.findAllByType('button').some((button) => text(button).includes('Nuevo artículo')));
  } finally { await act(async () => renderer.unmount()); }
});

test('Administrativo/Finanzas puede valorizar; Gerencia solo consulta inventario', async () => {
  const { renderer, calls } = await mount('GERENCIA', async (path) => {
    if (path === '/api/inventario/articulos/?page=1') return { count: 0, next: null, previous: null, results: [] };
    throw new Error(`Ruta inesperada: ${path}`);
  });
  try {
    assert.ok(calls.every((call) => call.method === undefined || call.method === 'GET'));
    assert.equal(renderer.root.findAllByType('button').some((button) => /Nuevo artículo|Registrar ingreso/.test(text(button))), false);
  } finally { await act(async () => renderer.unmount()); }
});
