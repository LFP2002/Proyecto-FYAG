import test, { before, after } from 'node:test';
import assert from 'node:assert/strict';
import React from 'react';
import Renderer, { act } from 'react-test-renderer';
import { createServer } from 'vite';
import { AF, G, S } from '../src/obras/domain.js';
import { obrasBackend } from './helpers/obras-backend.js';

let server, AuthProvider, Obras;
before(async () => {
  server = await createServer({ configFile: false, esbuild: { jsx: 'automatic' }, server: { middlewareMode: true, ws: false, hmr: false }, appType: 'custom', optimizeDeps: { noDiscovery: true, include: [] } });
  ({ AuthProvider } = await server.ssrLoadModule('/src/auth/AuthContext.jsx'));
  ({ default: Obras } = await server.ssrLoadModule('/src/pages/Obras.jsx'));
  globalThis.window = { confirm: () => true };
  globalThis.confirm = () => true;
});
after(async () => { delete globalThis.window; delete globalThis.confirm; await server.close(); });
const flush = () => new Promise((resolve) => setImmediate(resolve));
const text = (node) => typeof node === 'string' ? node : (node.children || []).map(text).join('');
async function mount(backend) {
  const session = { status: 'authenticated', user: { id: backend.role === 'TECNICO' ? 8 : 2, username: 'Cuenta de prueba', email: 'test@example.test', role: backend.role } };
  const client = { getSnapshot: () => session, subscribe: () => () => {}, restore: async () => {}, request: backend.request };
  let renderer;
  await act(async () => { renderer = Renderer.create(React.createElement(AuthProvider, { client }, React.createElement(Obras))); await flush(); });
  return renderer;
}
const buttons = (renderer, label) => renderer.root.findAllByType('button').filter((button) => text(button) === label || button.props['aria-label'] === label);
async function click(renderer, label) {
  const button = buttons(renderer, label)[0]; assert.ok(button, `Falta el botón ${label}`); assert.ok(!button.props.disabled, `${label} deshabilitado`);
  await act(async () => { await button.props.onClick({ preventDefault() {} }); await flush(); });
}
async function input(renderer, id, value) { await act(async () => renderer.root.findByProps({ id }).props.onChange({ target: { value } })); }
async function openCosts(renderer) { await click(renderer, 'Ver obra'); await click(renderer, 'Costos'); }
async function openExpenses(renderer) { await click(renderer, 'Ver obra'); await click(renderer, 'Materiales y gastos'); }
async function unmount(renderer) { await act(async () => renderer.unmount()); }

const gasto = { id: 4, obra: 1, tipo: 'MATERIAL', descripcion: 'Cable', unidad: 'metro', cantidad: '2.000', cantidad_devuelta: '0.000', costo_unitario_neto: '12.50', subtotal: '25.00', fecha_gasto: '2026-11-12', referencia_respaldo: '', observacion: '', vigente: true, anulado_por: null, anulado_en: null, motivo_anulacion: '', registrado_por: 2, creado_en: '2026-11-12T12:00:00Z', actualizado_en: '2026-11-12T12:00:00Z' };

test('005C-3 Supervisor registra gasto con decimales string y actualiza datos remotos', async () => {
  const backend = obrasBackend(S); backend.obras[0].estado = 'EN_PROCESO';
  const renderer = await mount(backend);
  try {
    await openExpenses(renderer);
    await input(renderer, 'obras-gasto-descripcion', 'Cable'); await input(renderer, 'obras-gasto-unidad', 'metro');
    await input(renderer, 'obras-gasto-cantidad', '2.000'); await input(renderer, 'obras-gasto-costo_unitario_neto', '12.50'); await input(renderer, 'obras-gasto-fecha_gasto', '2026-11-12');
    await act(async () => { await renderer.root.findAllByType('form').find((form) => text(form).includes('Registrar material'))?.props.onSubmit({ preventDefault() {} }); await flush(); });
    const call = backend.calls.find((entry) => entry.path === '/api/obras/1/gastos/' && entry.method === 'POST');
    assert.ok(call); assert.equal(call.body.cantidad, '2.000'); assert.equal(call.body.costo_unitario_neto, '12.50');
    assert.ok(backend.calls.some((entry) => entry.path === '/api/obras/1/costos/resumen/'));
    assert.ok(backend.calls.some((entry) => entry.path === '/api/obras/1/costos/control/'));
    assert.equal(backend.expenses.length, 1);
  } finally { await unmount(renderer); }
});

test('Gerencia separa la pestaña Materiales y gastos de Costos y solo consulta', async () => {
  const backend = obrasBackend(G); backend.obras[0].estado = 'EN_PROCESO'; backend.expenses = [gasto];
  const renderer = await mount(backend);
  try {
    await openExpenses(renderer);
    assert.ok(backend.calls.some((entry) => entry.path === '/api/obras/1/gastos/?page=1'));
    assert.match(text(renderer.root), /\$25\.00 CLP/);
    assert.doesNotMatch(text(renderer.root), /Resumen económico|Control de rubros|Historial de costos/);
    assert.equal(buttons(renderer, 'Registrar gasto').length, 0);
    await click(renderer, 'Costos');
    assert.ok(backend.calls.some((entry) => entry.path === '/api/obras/1/costos/resumen/'));
    assert.ok(backend.calls.some((entry) => entry.path === '/api/obras/1/costos/historial/?page=1'));
    assert.match(text(renderer.root), /Resumen económico/);
    assert.ok(backend.calls.some((entry) => entry.path === '/api/obras/1/costos/resumen/'));
    assert.doesNotMatch(text(renderer.root), /Gastos de la obra|Cable/);
    assert.equal(buttons(renderer, 'Validar costos').length, 0);
    assert.equal(buttons(renderer, 'Finalizar obra').length, 0);
  } finally { await unmount(renderer); }
});

test('Administrativo ve solo el resumen económico mínimo, sin consultas de gastos/control/historial', async () => {
  const backend = obrasBackend(AF); backend.obras[0].estado = 'EN_PROCESO';
  const renderer = await mount(backend);
  try {
    await openCosts(renderer);
    assert.ok(backend.calls.some((entry) => entry.path === '/api/obras/1/costos/resumen/'));
    assert.ok(backend.calls.every((entry) => !/gastos|costos\/control|costos\/historial/.test(entry.path)));
    assert.doesNotMatch(text(renderer.root), /Materiales y gastos|Control de rubros|Validar costos|Finalizar obra|Version/);
  } finally { await unmount(renderer); }
});

test('Supervisor finaliza solo con validación remota, confirmación y motivo; refresca ficha', async () => {
  const backend = obrasBackend(S); backend.obras[0].estado = 'EN_PROCESO';
  backend.control.costos_validados = true; backend.control.version_validada = 0;
  const renderer = await mount(backend);
  try {
    await openCosts(renderer);
    await input(renderer, 'obras-finalizar-motivo', 'Trabajo terminado y revisado');
    await click(renderer, 'Finalizar obra');
    const call = backend.calls.find((entry) => entry.path === '/api/obras/1/finalizar/' && entry.method === 'POST');
    assert.deepEqual(call.body, { motivo: 'Trabajo terminado y revisado' });
    assert.equal(backend.obras[0].estado, 'FINALIZADA');
    assert.ok(backend.calls.filter((entry) => entry.path === '/api/obras/1/').length >= 2);
    assert.equal(buttons(renderer, 'Finalizar obra').length, 0);
  } finally { await unmount(renderer); }
});
