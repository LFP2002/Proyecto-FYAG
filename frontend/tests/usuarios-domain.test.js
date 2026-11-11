import test from 'node:test';
import assert from 'node:assert/strict';
import { createAuthClient, USER_ROLES } from '../src/auth/client.js';
import { trustedOrigin } from '../src/auth/config.js';
import { canManageUsers, readUser, readHistory, userPath, usersPath } from '../src/usuarios/api.js';

const user = { id: 7, username: 'TI institucional', email: 'ti@example.test', role: 'ADMINISTRADOR_TI' };
const json = (data, status = 200) => new Response(JSON.stringify(data), { status, headers: { 'Content-Type': 'application/json' } });
const profile = { id: 7, username: 'TI', email: 'ti@example.test', first_name: '', last_name: '', rol: 'ADMINISTRADOR_TI', is_active: true, date_joined: '2026-11-11T12:00:00Z' };

test('TI es quinto rol conocido, único administrador; proyección no revela permisos heredados', () => {
  assert.equal(USER_ROLES.length, 5);
  for (const role of USER_ROLES) assert.equal(canManageUsers(role), role === 'ADMINISTRADOR_TI');
  assert.deepEqual(readUser({ ...profile, password: 'no-mostrar', sesion_version: 9, is_superuser: true }), profile);
  assert.throws(() => readUser({ ...profile, rol: 'ROOT' }), { status: 502 });
  assert.throws(() => userPath(true), { status: 400 });
  assert.throws(() => usersPath(0), { status: 400 });
  assert.throws(() => usersPath(1, { activo: '1' }), { status: 400 });
  assert.equal(usersPath(2, { rol: 'ADMINISTRADOR_TI', activo: 'true' }), '/api/usuarios/?page=2&rol=ADMINISTRADOR_TI&activo=true');
});

test('auditoría filtra secretos y vacía snapshots de contraseñas aun si servidor entrega extras', () => {
  const data = { count: 2, next: null, previous: null, results: [
    { id: 1, tipo: 'EDICION', actor: 7, motivo: '', creado_en: '2026-11-11T12:00:00Z', datos_nuevos: { username: 'Alias', password: 'secreto', is_active: 'true' } },
    { id: 2, tipo: 'ESTABLECER_CLAVE', actor: 7, motivo: '', creado_en: '2026-11-11T12:00:00Z', datos_nuevos: { username: 'no-mostrar', password: 'secreto' } },
  ] };
  const history = readHistory(data, 7);
  assert.deepEqual(history.results[0].datos_nuevos, { username: 'Alias' });
  assert.deepEqual(history.results[1].datos_nuevos, {});
  assert.doesNotMatch(JSON.stringify(history), /secreto|no-mostrar/);
  assert.throws(() => readHistory({ count: 1, results: [{}] }, 7), { status: 502 });
});

test('login TI y API separada: origen de confianza, credentials include y CSRF rotado', async () => {
  const calls = [];
  const client = createAuthClient({ apiOrigin: 'https://api.example.test/', fetchImpl: async (url, options) => {
    calls.push({ url, ...options });
    if (url.endsWith('/csrf/')) return json({ csrfToken: 'proteccion' });
    if (url.endsWith('/login/')) return json({ csrfToken: 'rotado', access: 'access-test' });
    if (url.endsWith('/me/')) return json(user);
    return json({ count: 0, next: null, previous: null, results: [] });
  } });
  await client.login({ email: user.email, password: 'fixture-no-real' });
  assert.equal(client.getSnapshot().user.role, 'ADMINISTRADOR_TI');
  await client.request('/api/usuarios/');
  for (const call of calls) {
    assert.ok(call.url.startsWith('https://api.example.test/api/'));
    assert.equal(call.credentials, 'include');
    assert.equal(call.redirect, 'error');
  }
  assert.equal(calls[1].headers.get('X-CSRFToken'), 'proteccion');
  assert.equal(calls.at(-1).headers.get('Authorization'), 'Bearer access-test');
  await assert.rejects(client.request('https://evil.example/api/usuarios/'), { status: 400 });
  await assert.rejects(client.request('/api/../fuera/'), { status: 400 });
});

test('configuración rechaza origen inseguro, rutas, credenciales y esquemas ajenos', () => {
  for (const value of ['http://api.example.test', 'https://api.example.test/api/', 'https://u:p@api.example.test', 'https://api.example.test/?x=1', 'javascript:alert(1)']) assert.throws(() => trustedOrigin(value));
  assert.equal(trustedOrigin('http://localhost:8000'), 'http://localhost:8000');
  assert.equal(trustedOrigin(''), '');
});

test('errores Usuarios públicos por campo y conflicto; no filtra trazas ni secretos', async () => {
  const client = createAuthClient({ fetchImpl: async (path) => {
    if (path.endsWith('/csrf/')) return json({ csrfToken: 'proteccion' });
    if (path.endsWith('/login/')) return json({ csrfToken: 'rotado', access: 'access-test' });
    if (path.endsWith('/me/')) return json(user);
    return json({ code: 'ultima_ti', email: ['Correo duplicado.'], password: ['Contraseña demasiado corta.'], is_superuser: ['No mostrar'], detail: 'Traceback sensible', token: 'oculto' }, 409);
  } });
  await client.login({ email: user.email, password: 'fixture-no-real' });
  await assert.rejects(client.request('/api/usuarios/7/desactivar/', { method: 'POST', body: { motivo: 'Prueba' } }), (e) => {
    assert.equal(e.code, 'ultima_ti');
    assert.deepEqual(e.fieldErrors, { email: ['Correo duplicado.'], password: ['Contraseña demasiado corta.'] });
    return true;
  });
});
