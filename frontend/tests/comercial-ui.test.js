import test, { before, after } from 'node:test';
import assert from 'node:assert/strict';
import React from 'react';
import Renderer, { act } from 'react-test-renderer';
import { createServer } from 'vite';
import { ApiError } from '../src/auth/client.js';
import { OTHER_UNIT } from '../src/comercial/units.js';
import { PRE_E } from '../src/data/constants.js';
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
async function mount(Page, request, role = 'ADMINISTRATIVO_FINANZAS', rendererOptions) {
  const session = { status: 'authenticated', notice: null, user: { id: 1, username: 'Usuario', email: 'test@example.test', role } };
  const client = { getSnapshot: () => session, subscribe: () => () => {}, restore: async () => {}, request };
  let renderer;
  await act(async () => { renderer = Renderer.create(React.createElement(AuthProvider, { client }, React.createElement(Page)), rendererOptions); await flush(); });
  return renderer;
}
async function click(renderer, label, index = 0) {
  const button = renderer.root.findAllByType('button').filter((b) => text(b) === label || b.props['aria-label'] === label)[index];
  assert.ok(button, `Falta botón ${label}`); assert.ok(!button.props.disabled, `${label} está deshabilitado`);
  await act(async () => { await button.props.onClick({ preventDefault() {} }); await flush(); });
}
async function input(renderer, name, value) {
  await act(async () => { renderer.root.findByProps({ id: `com-${name}` }).props.onChange({ target: { value } }); });
}
async function submit(renderer) {
  await act(async () => {
    const row = renderer.root.findAllByProps({ 'aria-label': 'Edición de ítem' })[0];
    if (row) row.props.onKeyDown({ key: 'Enter', target: { tagName: 'INPUT' }, preventDefault() {} });
    else await renderer.root.findByType('form').props.onSubmit({ preventDefault() {} });
    await flush();
  });
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
      if (method === 'POST') budget.items.push({ ...options.body, id: Math.max(0, ...budget.items.map((i) => i.id)) + 1, subtotal: '1234.56' });
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
    await click(renderer, '+ Agregar nuevo ítem');
    for (const [k, v] of Object.entries({ descripcion: 'Trabajo', cantidad: '0.001', unidad: 'h', precio_unitario: '9999999999999.99', orden: '1' })) await input(renderer, k, v);
    await submit(renderer); assert.match(text(renderer.root), /1\.234,56 CLP/);
    const itemPost = b.calls.find((c) => c.path.endsWith('/items/') && c.method === 'POST'); assert.equal(itemPost.body.cantidad, '0.001'); assert.equal(itemPost.body.precio_unitario, '9999999999999.99'); assert.equal(itemPost.body.orden, 1);
    await click(renderer, 'Editar ítem'); await input(renderer, 'unidad', 'u'); await submit(renderer);
    assert.deepEqual(b.calls.find((c) => c.method === 'PATCH').body, { unidad: 'u' });
    await click(renderer, 'Enviar a Gerencia'); await submit(renderer); assert.equal(b.budgets[0].estado, 'PENDIENTE_GERENCIA');
    assert.equal(renderer.root.findAllByType('button').some((n) => text(n) === 'Editar cabecera'), false);
    await act(async () => renderer.unmount()); renderer = await mount(Presupuestos, b.request, 'GERENCIA');
    await click(renderer, 'Ver presupuesto'); assert.equal(renderer.root.findAllByProps({ 'aria-label': 'Nuevo borrador' }).length, 0);
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
    await click(renderer, 'Actualizar datos'); assert.equal(b.calls.filter((c) => c.method !== 'GET').length, before);
    b.setFailure(null); await submit(renderer); assert.equal(b.budgets[0].estado, 'ANULADO');
  } finally { await act(async () => renderer.unmount()); }
});
test('unidad de medida en alta/edición: catálogo, Otra, límite, valor histórico y payload sin campos auxiliares', async () => {
  const b = fakeBackend(), renderer = await mount(Presupuestos, b.request);
  try {
    await createBudget(renderer); await click(renderer, '+ Agregar nuevo ítem');
    const select = renderer.root.findByProps({ id: 'com-unidad' });
    assert.equal(select.type, 'select'); assert.equal(select.props.value, ''); assert.ok(select.props.required);
    assert.match(text(renderer.root), /Unidad de medida/);
    assert.equal(renderer.root.findAllByProps({ id: 'com-unidad-otra' }).length, 0);
    for (const [key, value] of Object.entries({ descripcion: 'Servicio', cantidad: '1', precio_unitario: '100', orden: '1' })) await input(renderer, key, value);
    await submit(renderer);
    assert.equal(text(renderer.root.findByProps({ id: 'com-unidad-error' })), 'Campo obligatorio');
    assert.equal(b.calls.filter((c) => c.method === 'POST' && c.path.endsWith('/items/')).length, 0);
    await input(renderer, 'unidad', OTHER_UNIT);
    const custom = renderer.root.findByProps({ id: 'com-unidad-otra' });
    assert.equal(custom.type, 'input'); assert.equal(custom.props.maxLength, 30); assert.ok(custom.props.required);
    await input(renderer, 'unidad-otra', 'x'.repeat(31)); await submit(renderer);
    assert.match(text(renderer.root), /Máximo 30 caracteres/);
    assert.equal(b.budgets[0].items.length, 0);
    const historical = 'x'.repeat(30);
    await input(renderer, 'unidad-otra', historical); await submit(renderer);
    const post = b.calls.find((c) => c.method === 'POST' && c.path.endsWith('/items/'));
    assert.equal(post.body.unidad, historical);
    assert.deepEqual(Object.keys(post.body).sort(), ['cantidad', 'descripcion', 'orden', 'precio_unitario', 'unidad']);
    await click(renderer, 'Editar ítem');
    assert.equal(renderer.root.findByProps({ id: 'com-unidad' }).props.value, OTHER_UNIT);
    assert.equal(renderer.root.findByProps({ id: 'com-unidad-otra' }).props.value, historical);
    await input(renderer, 'descripcion', 'Servicio editado'); await submit(renderer);
    assert.deepEqual(b.calls.filter((c) => c.method === 'PATCH').at(-1).body, { descripcion: 'Servicio editado' });
    await click(renderer, 'Editar ítem'); await input(renderer, 'unidad', 'kg');
    assert.equal(renderer.root.findAllByProps({ id: 'com-unidad-otra' }).length, 0);
    await submit(renderer);
    assert.deepEqual(b.calls.filter((c) => c.method === 'PATCH').at(-1).body, { unidad: 'kg' });
    await click(renderer, 'Editar ítem');
    assert.equal(renderer.root.findByProps({ id: 'com-unidad' }).props.value, 'kg');
    assert.equal(renderer.root.findAllByProps({ id: 'com-unidad-otra' }).length, 0);
    await input(renderer, 'unidad', OTHER_UNIT);
    assert.equal(renderer.root.findByProps({ id: 'com-unidad-otra' }).props.value, '');
    await input(renderer, 'unidad-otra', '  visita técnica  '); await submit(renderer);
    assert.deepEqual(b.calls.filter((c) => c.method === 'PATCH').at(-1).body, { unidad: 'visita técnica' });
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
    await click(renderer, 'Actualizar datos'); await click(renderer, 'Editar cabecera');
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
    assert.ok(calls.slice(0, 2).every((c) => c.options.signal.aborted));
    assert.equal(calls.at(-1).path, '/api/obras/?page=1');
    await act(async () => { pending.splice(0).forEach((resolve) => resolve()); await flush(); });
    assert.doesNotMatch(text(renderer.root), /Nuevo borrador/); assert.equal(calls.length, 3);
    await act(async () => { session = { status: 'authenticated', user: { id: 3, username: 'Técnico', role: 'TECNICO' } }; listeners.forEach((fn) => fn()); });
    assert.equal(calls.length, 4); assert.equal(calls.at(-1).path, '/api/obras/mis-obras/?page=1');
    await act(async () => { session = { status: 'anonymous', user: null }; listeners.forEach((fn) => fn()); });
    assert.match(text(renderer.root), /Correo electrónico/); assert.doesNotMatch(text(renderer.root), /Supervisor|Nuevo borrador/);
  } finally { await act(async () => renderer.unmount()); }
});
test('presentación Comercial: controles Bootstrap, estados con texto, tablas accesibles y acciones diferenciadas', async () => {
  const b = fakeBackend();
  const checkButtons = (renderer) => {
    for (const button of renderer.root.findAllByType('button')) assert.match(button.props.className, /\bbtn\b/);
  };
  let renderer = await mount(Clientes, b.request);
  try {
    checkButtons(renderer);
    assert.equal(renderer.root.findByProps({ 'aria-label': 'Listado de clientes' }).props.tabIndex, 0);
    assert.ok(renderer.root.findAllByType('span').some((n) => n.props.className === 'chip green' && text(n) === 'Activo'));
    await click(renderer, 'Ver cliente');
    const deactivate = renderer.root.findAllByType('button').find((n) => text(n) === 'Desactivar');
    assert.match(deactivate.props.className, /btn-outline-danger/);
    await click(renderer, 'Editar cliente'); checkButtons(renderer);
    for (const field of [...renderer.root.findAllByType('input'), ...renderer.root.findAllByType('select')]) {
      assert.ok(renderer.root.findAllByType('label').some((label) => label.props.htmlFor === field.props.id));
    }
  } finally { await act(async () => renderer.unmount()); }
  renderer = await mount(Presupuestos, b.request);
  try {
    assert.equal(renderer.root.findByProps({ id: 'budget-filter' }).props.className, 'form-select');
    const pager = renderer.root.findByProps({ 'aria-label': 'Paginación' });
    assert.ok(pager.findAllByType('button').every((n) => n.props.disabled));
    assert.match(pager.props.className, /commercial-pager/);
    await createBudget(renderer); checkButtons(renderer);
    assert.ok(renderer.root.findAllByType('span').some((n) => n.props.className === 'chip gray' && text(n) === 'Borrador'));
    assert.equal(renderer.root.findByProps({ 'aria-label': 'Listado de presupuestos' }).props.tabIndex, 0);
    assert.ok(renderer.root.findAllByType('td').some((n) => n.props.className === 'commercial-money'));
    assert.ok(renderer.root.findByProps({ 'aria-label': 'Paginación del historial' }));
    await click(renderer, '+ Agregar nuevo ítem'); checkButtons(renderer);
    assert.equal(renderer.root.findByProps({ id: 'com-unidad' }).type, 'select');
    await click(renderer, 'Cancelar edición de ítem'); await click(renderer, 'Anular'); checkButtons(renderer);
    const confirm = renderer.root.findAllByType('button').find((n) => text(n) === 'Confirmar Anular');
    assert.match(confirm.props.className, /btn-outline-danger/);
  } finally { await act(async () => renderer.unmount()); }
});
const itemSaveButton = (renderer) => renderer.root.findByProps({ 'aria-label': 'Guardar ítem' });
async function fillItem(renderer) {
  for (const [key, value] of Object.entries({ descripcion: 'Instalación', cantidad: '1.001', unidad: 'h', precio_unitario: '25.50', orden: '1' })) await input(renderer, key, value);
}
async function rowKey(renderer, key, extra = {}) {
  let prevented = false;
  await act(async () => {
    renderer.root.findByProps({ 'aria-label': 'Edición de ítem' }).props.onKeyDown({ key, target: { tagName: 'INPUT' }, preventDefault() { prevented = true; }, ...extra });
    await flush();
  });
  return prevented;
}
test('fila fantasma: alta limpia, orden vacío en cada creación, guardado explícito y validación al guardar', async () => {
  const b = fakeBackend(), renderer = await mount(Presupuestos, b.request);
  try {
    await createBudget(renderer); await click(renderer, '+ Agregar nuevo ítem');
    assert.equal(renderer.root.findAllByType('form').length, 0);
    assert.equal(renderer.root.findByProps({ id: 'com-orden' }).props.value, '');
    assert.equal(itemSaveButton(renderer).props.disabled, false);
    assert.equal(renderer.root.findAllByProps({ 'aria-invalid': true }).length, 0);
    assert.equal(renderer.root.findAllByProps({ id: 'item-row-feedback' }).length, 0);
    assert.doesNotMatch(text(renderer.root), /Revisa el ítem|Tab: siguiente|se consultan a Django|Se calculará al guardar|puede ser rechazada/);
    await fillItem(renderer); assert.equal(itemSaveButton(renderer).props.disabled, false);
    await input(renderer, 'cantidad', '0'); await click(renderer, 'Guardar ítem');
    assert.equal(text(renderer.root.findByProps({ id: 'com-cantidad-error' })), 'Ingresa una cantidad válida');
    await input(renderer, 'cantidad', '1.001'); await input(renderer, 'orden', '4');
    // Escribir no crea registros ni cambia el neto localmente.
    assert.equal(b.budgets[0].items.length, 0); assert.match(text(renderer.root), /0,00 CLP/);
    await click(renderer, 'Guardar ítem');
    assert.equal(b.budgets[0].items.length, 1); assert.equal(b.budgets[0].items[0].orden, 4);
    assert.equal(renderer.root.findAllByProps({ 'aria-label': 'Edición de ítem' }).length, 0);
    assert.match(text(renderer.root), /1\.234,56 CLP/);
    await click(renderer, '+ Agregar nuevo ítem'); assert.equal(renderer.root.findByProps({ id: 'com-orden' }).props.value, '');
    await fillItem(renderer); await input(renderer, 'orden', '4');
    await click(renderer, 'Guardar ítem'); assert.match(text(renderer.root), /Orden ya utilizado/);
    assert.equal(b.budgets[0].items.length, 1);
    await input(renderer, 'orden', '5'); await click(renderer, 'Guardar ítem');
    assert.equal(b.budgets[0].items.length, 2);
    assert.equal(b.budgets[0].items[0].orden, 4);
    await click(renderer, 'Editar ítem');
    assert.equal(renderer.root.findByProps({ id: 'com-orden' }).props.value, 4);
    assert.equal(renderer.root.findAllByProps({ 'aria-invalid': true }).length, 0);
    await click(renderer, 'Cancelar edición de ítem'); await click(renderer, '+ Agregar nuevo ítem');
    assert.equal(renderer.root.findByProps({ id: 'com-orden' }).props.value, '');
  } finally { await act(async () => renderer.unmount()); }
});
test('teclado inline: Tab nativo, Enter guarda, Escape cancela; composición y select no guardan', async () => {
  const b = fakeBackend(), renderer = await mount(Presupuestos, b.request);
  try {
    await createBudget(renderer); await click(renderer, '+ Agregar nuevo ítem'); await fillItem(renderer);
    assert.equal(await rowKey(renderer, 'Tab'), false);
    assert.equal(await rowKey(renderer, 'Enter', { isComposing: true }), false);
    assert.equal(await rowKey(renderer, 'Enter', { target: { tagName: 'SELECT' } }), false);
    assert.equal(b.budgets[0].items.length, 0);
    assert.equal(await rowKey(renderer, 'Enter'), true); assert.equal(b.budgets[0].items.length, 1);
    await click(renderer, 'Editar ítem'); await input(renderer, 'descripcion', 'No guardar');
    await rowKey(renderer, 'Escape'); assert.equal(b.budgets[0].items[0].descripcion, 'Instalación');
    assert.equal(b.calls.filter((c) => c.method === 'PATCH').length, 0);
    await click(renderer, '+ Agregar nuevo ítem'); await rowKey(renderer, 'Escape');
    assert.equal(b.budgets[0].items.length, 1);
  } finally { await act(async () => renderer.unmount()); }
});
test('guardando inline: indicador, controles bloqueados y un solo POST ante doble envío', async () => {
  const b = fakeBackend(); let release, attempts = 0;
  const gate = new Promise((resolve) => { release = resolve; });
  const request = async (path, options) => {
    if (options?.method === 'POST' && path.endsWith('/items/')) { attempts++; await gate; }
    return b.request(path, options);
  };
  const renderer = await mount(Presupuestos, request);
  try {
    await createBudget(renderer); await click(renderer, '+ Agregar nuevo ítem'); await fillItem(renderer);
    const save = itemSaveButton(renderer).props.onClick;
    let first, second;
    await act(async () => {
      first = save({ preventDefault() {} }); second = save({ preventDefault() {} }); await flush();
    });
    assert.equal(attempts, 1); assert.ok(itemSaveButton(renderer).props.disabled);
    assert.match(text(renderer.root), /Guardando…/);
    assert.ok(renderer.root.findByProps({ 'aria-label': 'Cancelar edición de ítem' }).props.disabled);
    await rowKey(renderer, 'Escape'); assert.ok(renderer.root.findByProps({ 'aria-label': 'Edición de ítem' }));
    await act(async () => { release(); await Promise.all([first, second]); await flush(); });
    assert.equal(b.budgets[0].items.length, 1);
    assert.equal(renderer.root.findAllByProps({ 'aria-label': 'Edición de ítem' }).length, 0);
  } finally { release(); await act(async () => renderer.unmount()); }
});
test('error API inline conserva valores y muestra el mensaje junto a la fila; permite corregir', async () => {
  const b = fakeBackend(), renderer = await mount(Presupuestos, b.request);
  try {
    await createBudget(renderer); await click(renderer, '+ Agregar nuevo ítem'); await fillItem(renderer);
    b.setFailure(new ApiError(400, 'No fue posible guardar.', null, { fieldErrors: { descripcion: ['Revisa esta descripción.'] } }));
    await click(renderer, 'Guardar ítem');
    assert.equal(renderer.root.findByProps({ id: 'com-descripcion' }).props.value, 'Instalación');
    assert.match(text(renderer.root.findByProps({ id: 'item-row-feedback' })), /Revisa esta descripción/);
    assert.equal(b.budgets[0].items.length, 0);
    b.setFailure(null); await input(renderer, 'descripcion', 'Corregida'); await click(renderer, 'Guardar ítem');
    assert.equal(b.budgets[0].items[0].descripcion, 'Corregida');
  } finally { await act(async () => renderer.unmount()); }
});
test('409 inline obliga a reconsultar y no permite editar cuando deja de ser BORRADOR', async () => {
  const b = fakeBackend(), renderer = await mount(Presupuestos, b.request);
  try {
    await createBudget(renderer); await click(renderer, '+ Agregar nuevo ítem'); await fillItem(renderer);
    b.setFailure(new ApiError(409, 'Estado incompatible.')); await click(renderer, 'Guardar ítem');
    assert.ok(itemSaveButton(renderer).props.disabled); assert.equal(b.budgets[0].items.length, 0);
    const writes = b.calls.filter((c) => c.method !== 'GET').length;
    b.budgets[0].estado = 'PENDIENTE_GERENCIA'; await click(renderer, 'Actualizar datos');
    assert.equal(b.calls.filter((c) => c.method !== 'GET').length, writes);
    assert.ok(itemSaveButton(renderer).props.disabled);
    assert.equal(renderer.root.findByProps({ id: 'com-descripcion' }).props.value, 'Instalación');
    assert.ok(renderer.root.findByProps({ id: 'com-descripcion' }).props.disabled);
    await click(renderer, 'Cancelar edición de ítem');
    assert.equal(renderer.root.findAllByType('button').some((n) => text(n) === '+ Agregar nuevo ítem'), false);
  } finally { await act(async () => renderer.unmount()); }
});
test('validación inline bajo demanda: mensajes por campo y foco en el primer dato incorrecto', async () => {
  const b = fakeBackend(), focused = [];
  let customUnit = false;
  const renderer = await mount(Presupuestos, b.request, 'ADMINISTRATIVO_FINANZAS', {
    createNodeMock(element) {
      if (element.props['aria-label'] !== 'Edición de ítem') return null;
      return { querySelector(selector) {
        if (selector === '#com-unidad-otra' && !customUnit) return null;
        return { focus() { focused.push(selector); } };
      } };
    },
  });
  try {
    await createBudget(renderer); await click(renderer, '+ Agregar nuevo ítem');
    assert.equal(renderer.root.findAllByProps({ 'aria-invalid': true }).length, 0);
    assert.equal(renderer.root.findAllByProps({ className: 'invalid-feedback' }).length, 0);
    await click(renderer, 'Guardar ítem');
    assert.equal(focused.at(-1), '#com-descripcion');
    assert.equal(text(renderer.root.findByProps({ id: 'com-descripcion-error' })), 'Campo obligatorio');
    assert.equal(renderer.root.findAllByProps({ id: 'item-row-feedback' }).length, 0);
    assert.equal(b.budgets[0].items.length, 0);
    await input(renderer, 'descripcion', 'Descripción conservada'); await rowKey(renderer, 'Enter');
    assert.equal(focused.at(-1), '#com-cantidad');
    assert.equal(renderer.root.findByProps({ id: 'com-descripcion' }).props['aria-invalid'], false);
    await input(renderer, 'cantidad', '1'); await input(renderer, 'unidad', OTHER_UNIT); customUnit = true;
    await click(renderer, 'Guardar ítem'); assert.equal(focused.at(-1), '#com-unidad-otra');
    assert.ok(renderer.root.findByProps({ id: 'com-unidad-otra' }).props['aria-invalid']);
    assert.equal(renderer.root.findByProps({ id: 'com-unidad' }).props['aria-invalid'], false);
    await input(renderer, 'unidad-otra', 'Visita'); await input(renderer, 'precio_unitario', '0.00');
    await input(renderer, 'orden', '0'); await rowKey(renderer, 'Enter');
    assert.equal(focused.at(-1), '#com-orden');
    assert.equal(text(renderer.root.findByProps({ id: 'com-orden-error' })), 'Ingresa un entero positivo válido');
    await input(renderer, 'orden', '7'); await rowKey(renderer, 'Enter');
    assert.equal(b.budgets[0].items.length, 1); assert.equal(b.budgets[0].items[0].orden, 7);
  } finally { await act(async () => renderer.unmount()); }
});
test('barra compacta AF/G: controles agrupados, etiquetas legibles y creación solo para AF', async () => {
  for (const role of ['ADMINISTRATIVO_FINANZAS', 'GERENCIA']) {
    const b = fakeBackend(), renderer = await mount(Presupuestos, b.request, role);
    try {
      const toolbar = renderer.root.findByProps({ 'aria-label': 'Herramientas de presupuestos' });
      assert.equal(toolbar.props.className, 'budget-toolbar');
      const create = toolbar.findAllByProps({ 'aria-label': 'Nuevo borrador' });
      assert.equal(create.length, role === 'ADMINISTRATIVO_FINANZAS' ? 1 : 0);
      if (create.length) assert.equal(text(create[0]), '+ Nuevo borrador');
      assert.equal(renderer.root.findByProps({ className: 'page-head' }).findAllByType('button').length, 0);
      const filter = toolbar.findByProps({ id: 'budget-filter' });
      assert.equal(filter.props.value, '');
      assert.equal(text(toolbar.findByProps({ htmlFor: 'budget-filter' })), 'Filtrar por');
      assert.deepEqual(filter.findAllByType('option').map((o) => [o.props.value, text(o)]), [['', 'Todos'], ...Object.entries(PRE_E).map(([value, [label]]) => [value, label])]);
      assert.doesNotMatch(text(toolbar), /solo esta página/);
      const refresh = toolbar.findByProps({ 'aria-label': 'Actualizar datos' });
      assert.equal(refresh.type, 'button'); assert.equal(refresh.props.title, 'Actualizar datos');
      assert.equal(refresh.findByType('svg').props['aria-hidden'], 'true');
      const before = b.calls.length;
      await act(async () => filter.props.onChange({ target: { value: 'ANULADO' } }));
      assert.equal(b.calls.length, before); // El filtro sigue siendo local.
      await click(renderer, 'Actualizar datos');
      assert.equal(b.calls.length, before + 2);
      assert.equal(renderer.root.findByProps({ id: 'budget-filter' }).props.value, 'ANULADO');
    } finally { await act(async () => renderer.unmount()); }
  }
});
test('recarga de barra: spinner accesible, pulsaciones repetidas deduplicadas y página/filtro conservados', async () => {
  const b = fakeBackend(), requests = [];
  let hold = false, release;
  const gate = new Promise((resolve) => { release = resolve; });
  const request = async (path, options) => {
    requests.push(path);
    if (path.startsWith('/api/presupuestos/?')) {
      if (hold) await gate;
      const second = path.endsWith('page=2');
      return { count: 26, results: [], next: second ? null : '/api/presupuestos/?page=2', previous: second ? '/api/presupuestos/' : null };
    }
    return b.request(path, options);
  };
  const renderer = await mount(Presupuestos, request);
  try {
    await click(renderer, 'Siguiente');
    await act(async () => renderer.root.findByProps({ id: 'budget-filter' }).props.onChange({ target: { value: 'PENDIENTE_GERENCIA' } }));
    const before = requests.length;
    hold = true;
    const refresh = renderer.root.findByProps({ 'aria-label': 'Actualizar datos' }).props.onClick;
    let first, repeated;
    await act(async () => { first = refresh(); repeated = refresh(); await flush(); });
    assert.deepEqual(requests.slice(before), ['/api/presupuestos/?page=2']);
    const button = renderer.root.findByProps({ 'aria-label': 'Actualizar datos' });
    assert.equal(button.props['aria-busy'], true); assert.ok(button.props.disabled);
    assert.equal(button.findByProps({ className: 'spinner-border spinner-border-sm' }).props['aria-hidden'], 'true');
    await act(async () => { release(); await Promise.all([first, repeated]); await flush(); });
    assert.deepEqual(requests.slice(before), ['/api/presupuestos/?page=2', '/api/clientes/']);
    assert.equal(renderer.root.findByProps({ id: 'budget-filter' }).props.value, 'PENDIENTE_GERENCIA');
    assert.match(text(renderer.root.findByProps({ 'aria-label': 'Paginación' })), /Página 2/);
    assert.equal(renderer.root.findByProps({ 'aria-label': 'Actualizar datos' }).props['aria-busy'], false);
    assert.equal(renderer.root.findByProps({ 'aria-label': 'Actualizar datos' }).props.disabled, false);
  } finally { release(); await act(async () => renderer.unmount()); }
});
