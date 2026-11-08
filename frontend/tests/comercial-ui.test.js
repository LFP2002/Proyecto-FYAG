import test, { before, after } from 'node:test';
import assert from 'node:assert/strict';
import React from 'react';
import Renderer, { act } from 'react-test-renderer';
import { createServer } from 'vite';
import { ApiError } from '../src/auth/client.js';
let server, AuthProvider, AppProvider, App, Clientes, Presupuestos;
before(async () => {
  server = await createServer({ configFile: false, esbuild: { jsx: 'automatic' }, server: { middlewareMode: true, hmr: false, ws: false }, appType: 'custom', optimizeDeps: { noDiscovery: true, include: [] } });
  ({ AuthProvider } = await server.ssrLoadModule('/src/auth/AuthContext.jsx'));
  ({ AppProvider } = await server.ssrLoadModule('/src/context/AppContext.jsx'));
  ({ default: App } = await server.ssrLoadModule('/src/app.jsx'));
  ({ default: Clientes } = await server.ssrLoadModule('/src/pages/Clientes.jsx'));
  ({ default: Presupuestos } = await server.ssrLoadModule('/src/pages/Presupuestos.jsx'));
  globalThis.window = { confirm: () => true };
});
after(async () => { delete globalThis.window; await server.close(); });
const flush = () => new Promise((resolve) => setImmediate(resolve));
const text = (node) => typeof node === 'string' ? node : (node.children || []).map(text).join('');
async function mount(Page, request, role = 'ADMINISTRATIVO_FINANZAS') {
  const session = { status: 'authenticated', notice: null, user: { id: 1, username: 'Usuario', email: 'test@example.test', role } };
  const client = { getSnapshot: () => session, subscribe: () => () => {}, restore: async () => {}, request };
  let renderer;
  await act(async () => { renderer = Renderer.create(React.createElement(AuthProvider, { client }, React.createElement(Page))); await flush(); });
  return renderer;
}
async function click(renderer, label, index = 0) {
  const button = renderer.root.findAllByType('button').filter((b) => text(b) === label)[index];
  assert.ok(button, `Falta botón ${label}`); assert.ok(!button.props.disabled, `${label} está deshabilitado`);
  await act(async () => { await button.props.onClick(); await flush(); });
}
async function input(renderer, name, value) {
  await act(async () => { renderer.root.findByProps({ id: `com-${name}` }).props.onChange({ target: { value } }); });
}
async function submit(renderer) {
  await act(async () => { await renderer.root.findByType('form').props.onSubmit({ preventDefault() {} }); await flush(); });
}
const page = (results) => ({ count: results.length, results, next: null, previous: null });
function fakeBackend() {
  const calls = [];
  const clients = [{ id: 1, tipo_cliente: 'PERSONA', tipo_identificacion: 'SIN_IDENTIFICACION', numero_identificacion: null, pais_identificacion: null, tipo_documento_extranjero: null, nombre_legal: 'Cliente activo', nombre_contacto: '', correo: '', telefono: '123', activo: true }];
  const budgets = [], events = [];
  let fail = null;
  async function request(path, options = {}) {
    const method = options.method || 'GET'; calls.push({ path, method, body: options.body });
    if (method !== 'GET' && fail) throw fail;
    if (path === '/api/clientes/') {
      if (method === 'GET') return structuredClone(clients);
      const client = { ...options.body, id: clients.length + 1, activo: true }; clients.push(client); return structuredClone(client);
    }
    const matchClient = path.match(/^\/api\/clientes\/(\d+)\/(activar\/|desactivar\/)?$/);
    if (matchClient) {
      const client = clients.find((c) => c.id === Number(matchClient[1]));
      if (method === 'PATCH') Object.assign(client, options.body);
      if (matchClient[2]) client.activo = matchClient[2] === 'activar/';
      return structuredClone(client);
    }
    if (path.startsWith('/api/presupuestos/?')) return page(structuredClone(budgets));
    if (path === '/api/presupuestos/' && method === 'POST') {
      const budget = { ...options.body, id: budgets.length + 1, codigo: `PRE-${budgets.length + 1}`, estado: 'BORRADOR', monto_neto: '0.00', items: [], creado_por: 1, creado_en: '2026-11-08T12:00:00Z', presupuesto_origen: null }; budgets.push(budget); return structuredClone(budget);
    }
    const match = path.match(/^\/api\/presupuestos\/(\d+)\/(.*)$/);
    if (!match) throw new Error(`Ruta inesperada: ${path}`);
    const budget = budgets.find((b) => b.id === Number(match[1])), suffix = match[2];
    if (suffix.startsWith('historial/')) return page(structuredClone(events.filter((e) => e.presupuesto === budget.id)));
    if (method === 'GET') return structuredClone(budget);
    if (!suffix) { Object.assign(budget, options.body); return structuredClone(budget); }
    if (suffix.startsWith('items/')) {
      const itemId = Number(suffix.split('/')[1]);
      if (method === 'POST') budget.items.push({ ...options.body, id: 1, subtotal: '1234.56' });
      if (method === 'PATCH') Object.assign(budget.items.find((i) => i.id === itemId), options.body);
      if (method === 'DELETE') budget.items = budget.items.filter((i) => i.id !== itemId);
      budget.monto_neto = budget.items.length ? '1234.56' : '0.00';
      return method === 'DELETE' ? null : structuredClone(budget.items[0]);
    }
    if (suffix === 'crear-revision/') {
      const revision = { ...structuredClone(budget), id: budgets.length + 1, codigo: `PRE-${budgets.length + 1}`, presupuesto_origen: budget.id, estado: 'BORRADOR' }; budgets.push(revision); return structuredClone(revision);
    }
    const states = { 'enviar-gerencia/': 'PENDIENTE_GERENCIA', 'aprobar-gerencia/': 'APROBADO_GERENCIA', 'rechazar-gerencia/': 'RECHAZADO_GERENCIA', 'enviar-cliente/': 'ENVIADO_CLIENTE', 'registrar-aprobacion-cliente/': 'APROBADO_CLIENTE', 'registrar-rechazo-cliente/': 'RECHAZADO_CLIENTE', 'anular/': 'ANULADO' };
    events.push({ id: events.length + 1, presupuesto: budget.id, estado_anterior: budget.estado, estado_nuevo: states[suffix], registrado_por: 1, motivo: options.body.motivo, creado_en: '2026-11-08T12:00:00Z' });
    budget.estado = states[suffix]; return structuredClone(budget);
  }
  return { request, calls, clients, budgets, events, setFailure: (e) => { fail = e; } };
}
test('Clientes montado: GET, alta, PATCH, detalle, desactivar/reactivar y errores sin perder formulario', async () => {
  const backend = fakeBackend(), renderer = await mount(Clientes, backend.request);
  try {
    assert.match(text(renderer.root), /Cliente activo/);
    await click(renderer, 'Nuevo cliente');
    await input(renderer, 'tipo_identificacion', 'SIN_IDENTIFICACION');
    await input(renderer, 'nombre_legal', 'Cliente nuevo'); await input(renderer, 'telefono', '456');
    backend.setFailure(new ApiError(400, 'Datos inválidos', null, { fieldErrors: { nombre_legal: ['Duplicado.'] } }));
    await submit(renderer); assert.equal(renderer.root.findByProps({ id: 'com-nombre_legal' }).props.value, 'Cliente nuevo'); assert.match(text(renderer.root), /Duplicado/);
    backend.setFailure(null); await submit(renderer);
    assert.equal(backend.clients.length, 2);
    const post = backend.calls.find((c) => c.method === 'POST'); assert.equal(post.body.numero_identificacion, null);
    await click(renderer, 'Desactivar'); assert.equal(backend.clients[1].activo, false);
    await click(renderer, 'Editar cliente'); await input(renderer, 'nombre_legal', 'Inactivo editado'); await submit(renderer);
    assert.deepEqual(backend.calls.find((c) => c.method === 'PATCH').body, { nombre_legal: 'Inactivo editado' });
    await click(renderer, 'Activar'); assert.equal(backend.clients[1].activo, true);
    await click(renderer, 'Volver al listado'); await click(renderer, 'Ver cliente', 1); assert.match(text(renderer.root), /Inactivo editado/);
  } finally { await act(async () => renderer.unmount()); }
});
async function createBudget(renderer) {
  await click(renderer, 'Nuevo borrador'); await input(renderer, 'cliente', '1'); await input(renderer, 'descripcion', 'Servicio'); await submit(renderer);
}
async function execute(renderer, label, reason = '') {
  await click(renderer, label);
  const field = renderer.root.findAllByProps({ id: 'budget-reason' })[0];
  if (field) await act(async () => field.props.onChange({ target: { value: reason } }));
  await submit(renderer);
}
test('Presupuestos montado: borrador, CRUD líneas, Gerencia, cliente, historial, anulación y revisión', async () => {
  const b = fakeBackend(); let renderer = await mount(Presupuestos, b.request);
  try {
    await createBudget(renderer);
    const post = b.calls.find((c) => c.path === '/api/presupuestos/' && c.method === 'POST'); assert.deepEqual(post.body, { cliente: 1, descripcion: 'Servicio' });
    await click(renderer, 'Agregar ítem');
    for (const [k, v] of Object.entries({ descripcion: 'Trabajo', cantidad: '0.001', unidad: 'h', precio_unitario: '9999999999999.99', orden: '1' })) await input(renderer, k, v);
    await submit(renderer); assert.match(text(renderer.root), /1\.234,56 CLP/);
    const itemPost = b.calls.find((c) => c.path.endsWith('/items/') && c.method === 'POST'); assert.equal(itemPost.body.cantidad, '0.001'); assert.equal(itemPost.body.precio_unitario, '9999999999999.99'); assert.equal(itemPost.body.orden, 1);
    await click(renderer, 'Editar ítem'); await input(renderer, 'unidad', 'u'); await submit(renderer);
    assert.deepEqual(b.calls.find((c) => c.method === 'PATCH').body, { unidad: 'u' });
    await click(renderer, 'Enviar a Gerencia'); await submit(renderer); assert.equal(b.budgets[0].estado, 'PENDIENTE_GERENCIA');
    assert.equal(renderer.root.findAllByType('button').some((n) => text(n) === 'Editar cabecera'), false);
    await act(async () => renderer.unmount()); renderer = await mount(Presupuestos, b.request, 'GERENCIA');
    await click(renderer, 'Ver presupuesto'); assert.equal(renderer.root.findAllByType('button').some((n) => text(n) === 'Nuevo borrador'), false);
    await execute(renderer, 'Aprobar por Gerencia'); assert.equal(b.budgets[0].estado, 'APROBADO_GERENCIA');
    await act(async () => renderer.unmount()); renderer = await mount(Presupuestos, b.request);
    await click(renderer, 'Ver presupuesto'); await execute(renderer, 'Enviar al cliente'); await execute(renderer, 'Registrar aprobación del cliente');
    assert.equal(b.budgets[0].estado, 'APROBADO_CLIENTE'); assert.match(text(renderer.root), /Usuario #1/);
    await execute(renderer, 'Anular', 'Corrección'); assert.equal(b.budgets[0].estado, 'ANULADO');
    await execute(renderer, 'Crear revisión'); assert.equal(b.budgets.length, 2); assert.equal(b.budgets[1].presupuesto_origen, 1); assert.equal(b.budgets[0].estado, 'ANULADO');
    assert.deepEqual(b.calls.find((c) => c.path.endsWith('/crear-revision/')).body, {});
    await click(renderer, 'Eliminar ítem'); assert.equal(b.budgets[1].items.length, 0); assert.match(text(renderer.root), /0,00 CLP/);
    assert.ok(b.calls.some((c) => c.method === 'DELETE' && c.path === '/api/presupuestos/2/items/1/'));
  } finally { await act(async () => renderer.unmount()); }
});
test('409 utilizado bloquea reenvío; relectura no repite POST y conserva motivo', async () => {
  const b = fakeBackend(), renderer = await mount(Presupuestos, b.request);
  try {
    await createBudget(renderer); await click(renderer, 'Anular');
    await act(async () => renderer.root.findByProps({ id: 'budget-reason' }).props.onChange({ target: { value: 'Motivo conservado' } }));
    b.setFailure(new ApiError(409, 'Conflicto', null, { code: 'presupuesto_utilizado' })); await submit(renderer);
    assert.match(text(renderer.root), /utilizado por una Obra/); assert.equal(renderer.root.findByProps({ id: 'budget-reason' }).props.value, 'Motivo conservado');
    const before = b.calls.filter((c) => c.method !== 'GET').length;
    await click(renderer, 'Reconsultar datos'); assert.equal(b.calls.filter((c) => c.method !== 'GET').length, before);
    b.setFailure(null); await submit(renderer); assert.equal(b.budgets[0].estado, 'ANULADO');
  } finally { await act(async () => renderer.unmount()); }
});
test('rechazos Gerencia/cliente requieren motivo y solo habilitan revisión', async () => {
  for (const [state, role, label, expected] of [
    ['PENDIENTE_GERENCIA', 'GERENCIA', 'Rechazar por Gerencia', 'RECHAZADO_GERENCIA'],
    ['ENVIADO_CLIENTE', 'ADMINISTRATIVO_FINANZAS', 'Registrar rechazo del cliente', 'RECHAZADO_CLIENTE'],
  ]) {
    const b = fakeBackend(); let renderer = await mount(Presupuestos, b.request);
    await createBudget(renderer); await act(async () => renderer.unmount()); b.budgets[0].estado = state;
    renderer = await mount(Presupuestos, b.request, role);
    try {
      await click(renderer, 'Ver presupuesto'); await click(renderer, label); await submit(renderer);
      assert.equal(b.budgets[0].estado, state); assert.match(text(renderer.root), /motivo es obligatorio/);
      await act(async () => renderer.root.findByProps({ id: 'budget-reason' }).props.onChange({ target: { value: 'No aceptado' } }));
      await submit(renderer); assert.equal(b.budgets[0].estado, expected);
      assert.equal(renderer.root.findAllByType('button').some((n) => text(n) === 'Anular'), false);
    } finally { await act(async () => renderer.unmount()); }
  }
});
test('cabecera: cliente histórico inactivo se conserva sin reenviar su ID; alta no lo ofrece', async () => {
  const b = fakeBackend(), renderer = await mount(Presupuestos, b.request);
  try {
    await createBudget(renderer); b.clients[0].activo = false;
    await click(renderer, 'Reconsultar datos'); await click(renderer, 'Editar cabecera');
    await input(renderer, 'descripcion', 'Descripción nueva'); await submit(renderer);
    assert.deepEqual(b.calls.find((c) => c.method === 'PATCH').body, { descripcion: 'Descripción nueva' });
    await click(renderer, 'Nuevo borrador');
    const select = renderer.root.findByProps({ id: 'com-cliente' });
    assert.equal(select.findAllByType('option').some((n) => n.props.value === '1'), false);
  } finally { await act(async () => renderer.unmount()); }
});
test('listado e historial navegan por página real sin seguir directamente next/previous', async () => {
  const b = fakeBackend(); let renderer = await mount(Presupuestos, b.request);
  await createBudget(renderer); await act(async () => renderer.unmount());
  const calls = [];
  const request = async (path, options) => {
    calls.push(path);
    const result = await b.request(path, options);
    if (path.includes('?page=')) {
      const second = path.endsWith('page=2'), base = path.split('?')[0];
      return { ...result, count: 26, next: second ? null : `${base}?page=2`, previous: second ? base : null };
    }
    return result;
  };
  renderer = await mount(Presupuestos, request);
  try {
    await click(renderer, 'Siguiente'); assert.ok(calls.includes('/api/presupuestos/?page=2'));
    await click(renderer, 'Ver presupuesto'); await click(renderer, 'Siguiente', 1);
    assert.ok(calls.includes('/api/presupuestos/1/historial/?page=2'));
  } finally { await act(async () => renderer.unmount()); }
});
test('cambio de usuario/rol y logout desmontan Comercial y abortan respuestas tardías; S/T no consultan', async () => {
  let session = { status: 'authenticated', user: { id: 1, username: 'AF', role: 'ADMINISTRATIVO_FINANZAS' } };
  const listeners = new Set(), calls = [], pending = [];
  const client = { getSnapshot: () => session, subscribe: (fn) => { listeners.add(fn); return () => listeners.delete(fn); }, restore: async () => {}, request: (path, options) => {
    calls.push({ path, options }); return new Promise((resolve) => pending.push(() => resolve(path === '/api/clientes/' ? [] : page([]))));
  } };
  let renderer;
  await act(async () => { renderer = Renderer.create(React.createElement(AuthProvider, { client }, React.createElement(AppProvider, null, React.createElement(App)))); });
  try {
    assert.equal(calls.length, 2);
    await act(async () => { session = { status: 'authenticated', user: { id: 2, username: 'Supervisor', role: 'SUPERVISOR_OBRAS' } }; listeners.forEach((fn) => fn()); });
    assert.ok(calls.every((c) => c.options.signal.aborted));
    await act(async () => { pending.splice(0).forEach((resolve) => resolve()); await flush(); });
    assert.doesNotMatch(text(renderer.root), /Nuevo borrador/); assert.equal(calls.length, 2);
    await act(async () => { session = { status: 'authenticated', user: { id: 3, username: 'Técnico', role: 'TECNICO' } }; listeners.forEach((fn) => fn()); });
    assert.equal(calls.length, 2);
    await act(async () => { session = { status: 'anonymous', user: null }; listeners.forEach((fn) => fn()); });
    assert.match(text(renderer.root), /Correo electrónico/); assert.doesNotMatch(text(renderer.root), /Supervisor|Nuevo borrador/);
  } finally { await act(async () => renderer.unmount()); }
});
