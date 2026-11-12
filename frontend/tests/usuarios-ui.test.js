import test, { before, after } from 'node:test';
import assert from 'node:assert/strict';
import React from 'react';
import Renderer, { act } from 'react-test-renderer';
import { createServer } from 'vite';
import { ApiError } from '../src/auth/client.js';

let server, AuthProvider, AppProvider, App, Usuarios;
before(async () => {
  server = await createServer({ configFile: false, esbuild: { jsx: 'automatic' }, server: { middlewareMode: true, hmr: false, ws: false }, appType: 'custom', optimizeDeps: { noDiscovery: true, include: [] } });
  ({ AuthProvider } = await server.ssrLoadModule('/src/auth/AuthContext.jsx'));
  ({ AppProvider } = await server.ssrLoadModule('/src/context/AppContext.jsx'));
  ({ default: App } = await server.ssrLoadModule('/src/app.jsx'));
  ({ default: Usuarios } = await server.ssrLoadModule('/src/pages/Usuarios.jsx'));
});
after(async () => { await server.close(); });
const flush = () => new Promise((resolve) => setImmediate(resolve));
const text = (node) => typeof node === 'string' ? node : (node.children || []).map(text).join('');
const account = (id, rol = 'TECNICO', active = false) => ({ id, username: `alias${id}`, email: `cuenta${id}@example.test`, first_name: '', last_name: '', rol, is_active: active, date_joined: '2026-11-11T12:00:00Z' });
const page = (results) => ({ count: results.length, results: structuredClone(results), next: null, previous: null });
function backend() {
  const calls = [], accounts = [account(1, 'ADMINISTRADOR_TI', true), account(2)], events = [];
  let failure = null;
  async function request(path, options = {}) {
    const method = options.method || 'GET';
    calls.push({ path, method, body: options.body, signal: options.signal });
    if (method !== 'GET' && failure) throw failure;
    if (path.startsWith('/api/usuarios/?')) {
      const query = new URL(path, 'http://localhost').searchParams;
      return page(accounts.filter((a) => (!query.has('rol') || a.rol === query.get('rol')) && (!query.has('activo') || String(a.is_active) === query.get('activo'))));
    }
    if (path === '/api/usuarios/' && method === 'POST') {
      const { password, ...profile } = options.body;
      const obj = { ...account(accounts.length + 1), ...profile };
      accounts.push(obj); return structuredClone(obj);
    }
    const match = path.match(/^\/api\/usuarios\/(\d+)\/(.*)$/);
    if (!match) throw new Error(`Ruta inesperada ${path}`);
    const obj = accounts.find((a) => a.id === Number(match[1]));
    const action = match[2];
    if (action.startsWith('historial/')) return page(events.filter((e) => e.usuario_objetivo === obj.id));
    if (method === 'PATCH') Object.assign(obj, options.body);
    if (action === 'activar/') obj.is_active = true;
    if (action === 'desactivar/') obj.is_active = false;
    if (action === 'cambiar-rol/') obj.rol = options.body.rol;
    if (method !== 'GET') events.push({ id: events.length + 1, usuario_objetivo: obj.id, actor: 1, tipo: action === 'establecer-clave/' ? 'ESTABLECER_CLAVE' : 'EDICION', motivo: options.body.motivo || '', datos_anteriores: {}, datos_nuevos: action === 'establecer-clave/' ? {} : { is_active: obj.is_active }, creado_en: '2026-11-11T12:00:00Z' });
    return structuredClone(obj);
  }
  return { request, calls, accounts, setFailure: (value) => { failure = value; } };
}
async function mount(request, role = 'ADMINISTRADOR_TI', full = false) {
  let session = { status: 'authenticated', user: { id: 1, username: 'Institucional', email: 'sesion@example.test', role } };
  const listeners = new Set();
  const client = { getSnapshot: () => session, subscribe: (fn) => { listeners.add(fn); return () => listeners.delete(fn); }, restore: async () => {}, request,
    sessionInvalidatedByEmailChange: () => { session = { status: 'anonymous', user: null, notice: 'Correo actualizado correctamente. Inicia sesión con tu nuevo correo electrónico.' }; listeners.forEach((fn) => fn()); } };
  const content = full ? React.createElement(AppProvider, null, React.createElement(App)) : React.createElement(Usuarios);
  let renderer;
  await act(async () => { renderer = Renderer.create(React.createElement(AuthProvider, { client }, content)); await flush(); });
  return { renderer, changeRole: (next) => { session = { ...session, user: { ...session.user, role: next } }; listeners.forEach((fn) => fn()); } };
}
async function click(renderer, label) {
  const button = renderer.root.findAllByType('button').find((b) => text(b) === label);
  assert.ok(button, `Falta botón ${label}`); assert.ok(!button.props.disabled, `${label} deshabilitado`);
  await act(async () => { await button.props.onClick(); await flush(); });
}
async function input(renderer, name, value) {
  await act(async () => { renderer.root.findByProps({ id: `usuario-${name}` }).props.onChange({ target: { value } }); });
}
async function submit(renderer) {
  await act(async () => { await renderer.root.findByType('form').props.onSubmit({ preventDefault() {} }); await flush(); });
}

test('TI monta exclusivamente Usuarios y Gerencia pierde menú/consultas administrativas', async () => {
  for (const role of ['ADMINISTRADOR_TI', 'GERENCIA', 'ADMINISTRATIVO_FINANZAS', 'SUPERVISOR_OBRAS', 'TECNICO']) {
    const api = backend();
    const { renderer } = await mount(async (path, options) => path.startsWith('/api/usuarios/') ? api.request(path, options) : path === '/api/clientes/' ? [] : page([]), role, true);
    try {
      if (role === 'ADMINISTRADOR_TI') {
        const nav = renderer.root.findByProps({ id: 'fyag-modules-nav' });
        assert.deepEqual(nav.findAllByType('button').map(text), ['Usuarios y roles']);
        assert.ok(api.calls.some((call) => call.path.startsWith('/api/usuarios/')));
      } else {
        assert.equal(api.calls.length, 0);
        if (role !== 'TECNICO') assert.ok(!renderer.root.findByProps({ id: 'fyag-modules-nav' }).findAllByType('button').map(text).includes('Usuarios y roles'));
      }
    } finally { await act(async () => renderer.unmount()); }
  }
});

test('Usuarios consulta, crea inactiva, edita, activa/desactiva, cambia rol y establece clave con auditoría remota', async () => {
  const api = backend(), { renderer } = await mount(api.request);
  try {
    await click(renderer, 'Nueva cuenta');
    await input(renderer, 'email', 'nueva@example.test'); await input(renderer, 'username', 'nueva'); await input(renderer, 'password', 'fixture-segura');
    await submit(renderer);
    const post = api.calls.find((c) => c.method === 'POST');
    assert.deepEqual(Object.keys(post.body).sort(), ['email', 'first_name', 'last_name', 'password', 'rol', 'username']);
    assert.equal(api.accounts[2].is_active, false);
    await click(renderer, 'Activar'); await input(renderer, 'motivo', 'Cuenta preparada'); await submit(renderer);
    assert.equal(api.accounts[2].is_active, true);
    await click(renderer, 'Editar perfil'); await input(renderer, 'first_name', 'Nombre actualizado'); await submit(renderer);
    assert.equal(api.accounts[2].first_name, 'Nombre actualizado');
    await click(renderer, 'Cambiar rol'); await input(renderer, 'rol', 'ADMINISTRADOR_TI'); await input(renderer, 'motivo', 'Nueva función'); await submit(renderer);
    assert.equal(api.accounts[2].rol, 'ADMINISTRADOR_TI');
    await click(renderer, 'Establecer contraseña'); await input(renderer, 'nueva_clave', 'fixture-nueva'); await input(renderer, 'motivo', 'Restablecimiento'); await submit(renderer);
    assert.match(text(renderer.root), /ESTABLECER CLAVE/);
    assert.doesNotMatch(text(renderer.root), /fixture-nueva/);
    await click(renderer, 'Desactivar'); await input(renderer, 'motivo', 'Baja autorizada'); await submit(renderer);
    assert.equal(api.accounts[2].is_active, false);
    assert.ok(api.calls.filter((c) => c.path.includes('/historial/')).length >= 5);
  } finally { await act(async () => renderer.unmount()); }
});

test('400 conserva perfil pero limpia contraseña; 409 bloquea reenvío hasta reconsulta sin fingir éxito', async () => {
  const api = backend(), { renderer } = await mount(api.request);
  try {
    await click(renderer, 'Nueva cuenta');
    await input(renderer, 'email', 'nueva@example.test'); await input(renderer, 'password', 'no-conservar');
    api.setFailure(new ApiError(400, 'Revisa datos', null, { fieldErrors: { username: ['Alias obligatorio.'] } }));
    await submit(renderer);
    assert.equal(renderer.root.findByProps({ id: 'usuario-email' }).props.value, 'nueva@example.test');
    assert.equal(renderer.root.findByProps({ id: 'usuario-password' }).props.value, '');
    assert.match(text(renderer.root), /Alias obligatorio/);
    await click(renderer, 'Cancelar');
    await click(renderer, 'Ver cuenta #2'); await click(renderer, 'Activar'); await input(renderer, 'motivo', 'Preparada');
    api.setFailure(new ApiError(409, 'Conflicto', null, { code: 'asignaciones_pendientes' }));
    await submit(renderer);
    assert.equal(api.accounts[1].is_active, false);
    assert.match(text(renderer.root), /Resuelva primero/);
    assert.ok(renderer.root.findByType('form').findAllByType('button')[0].props.disabled);
    const count = api.calls.filter((c) => c.method === 'POST').length;
    api.setFailure(null); await click(renderer, 'Actualizar');
    assert.equal(api.calls.filter((c) => c.method === 'POST').length, count);
    await submit(renderer);
    assert.equal(api.accounts[1].is_active, true);
  } finally { await act(async () => renderer.unmount()); }
});

test('autooperaciones protegidas en UI y rol ajeno no consulta aun montando Usuarios directamente', async () => {
  const api = backend(), { renderer } = await mount(api.request);
  try {
    await click(renderer, 'Ver cuenta #1');
    assert.ok(renderer.root.findAllByType('button').find((b) => text(b) === 'Desactivar').props.disabled);
    assert.ok(renderer.root.findAllByType('button').find((b) => text(b) === 'Cambiar rol').props.disabled);
    assert.equal(renderer.root.findAllByType('button').some((b) => text(b) === 'Establecer contraseña'), false);
    assert.ok(renderer.root.findAllByType('button').some((b) => text(b) === 'Mi contraseña'));
  } finally { await act(async () => renderer.unmount()); }
  const denied = await mount(async () => { throw new Error('No debe consultar'); }, 'GERENCIA');
  assert.match(text(denied.renderer.root), /No tiene permiso/);
  await act(async () => denied.renderer.unmount());
});

test('cambio de rol desmonta Usuarios, aborta petición pendiente y no aplica éxito tardío', async () => {
  const api = backend();
  let resolve, captured;
  const pending = new Promise((done) => { resolve = done; });
  const request = (path, options) => {
    if (options?.method === 'PATCH') { captured = options.signal; return pending; }
    return path.startsWith('/api/usuarios/') ? api.request(path, options) : page([]);
  };
  const { renderer, changeRole } = await mount(request, 'ADMINISTRADOR_TI', true);
  try {
    await click(renderer, 'Ver cuenta #2'); await click(renderer, 'Editar perfil'); await input(renderer, 'username', 'Tardío');
    let writing;
    await act(async () => { writing = renderer.root.findByType('form').props.onSubmit({ preventDefault() {} }); await flush(); });
    await act(async () => { changeRole('GERENCIA'); await flush(); });
    assert.equal(captured.aborted, true);
    await act(async () => { resolve(account(2)); await writing; await flush(); });
    assert.doesNotMatch(text(renderer.root), /Auditoría administrativa|Tardío/);
  } finally { await act(async () => renderer.unmount()); }
});

test('filtros y páginas de usuarios son consultas remotas independientes de las páginas de auditoría', async () => {
  const calls = [];
  const request = async (path) => {
    calls.push(path);
    const url = new URL(path, 'http://localhost');
    const number = Number(url.searchParams.get('page') || 1);
    const history = url.pathname.endsWith('/historial/');
    if (url.pathname === '/api/usuarios/27/') return account(27);
    const all = history ? Array.from({ length: 26 }, (_, i) => ({ id: i + 1, tipo: 'EDICION', actor: 1, motivo: 'Cambio revisado', creado_en: '2026-11-11T12:00:00Z', datos_nuevos: {}, datos_anteriores: {} })) : Array.from({ length: 26 }, (_, i) => account(i + 2));
    return { count: 26, results: all.slice((number - 1) * 25, number * 25), next: number === 1 ? `${url.pathname}?page=2` : null, previous: number === 2 ? `${url.pathname}?page=1` : null };
  };
  const { renderer } = await mount(request);
  try {
    await act(async () => { renderer.root.findByProps({ 'aria-label': 'Filtrar estado' }).props.onChange({ target: { value: 'false' } }); await flush(); });
    await click(renderer, 'Siguiente');
    assert.ok(calls.includes('/api/usuarios/?page=2&activo=false'));
    await click(renderer, 'Ver cuenta #27');
    assert.ok(calls.includes('/api/usuarios/27/historial/?page=1'));
    await click(renderer, 'Siguiente');
    assert.ok(calls.includes('/api/usuarios/27/historial/?page=2'));
    await click(renderer, 'Volver a usuarios');
    assert.equal(calls.at(-1), '/api/usuarios/?page=2&activo=false');
  } finally { await act(async () => renderer.unmount()); }
});

test('TI edita correo propio: 200 persistido cierra sesión sin relectura ni refresh obsoleto', async () => {
  const api = backend();
  const { renderer } = await mount(api.request, 'ADMINISTRADOR_TI', true);
  try {
    await click(renderer, 'Ver cuenta #1');
    await click(renderer, 'Editar perfil');
    await input(renderer, 'first_name', 'Nombre actualizado');
    await submit(renderer);
    assert.equal(api.accounts[0].first_name, 'Nombre actualizado');
    assert.ok(renderer.root.findAllByType('button').some((b) => text(b) === 'Editar perfil'), 'editar nombre no revoca sesión');
    const historyReads = api.calls.filter((c) => c.path.includes('/historial/')).length;
    await click(renderer, 'Editar perfil');
    await input(renderer, 'email', 'nuevo@example.test');
    await submit(renderer);
    assert.equal(api.accounts[0].email, 'nuevo@example.test');
    assert.match(text(renderer.root), /Correo actualizado correctamente/);
    assert.match(text(renderer.root), /Correo electrónico/);
    assert.equal(api.calls.filter((c) => c.path.includes('/historial/')).length, historyReads, 'no reconsulta con token ya revocado');
    assert.equal(api.calls.filter((c) => c.path.startsWith('/api/auth/refresh/')).length, 0);
  } finally { await act(async () => renderer.unmount()); }
});
