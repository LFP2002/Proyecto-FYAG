import test from 'node:test';
import assert from 'node:assert/strict';
import { readFile, readdir } from 'node:fs/promises';
import { fileURLToPath } from 'node:url';
import { join } from 'node:path';
import { NAV, DEFMOD } from '../src/data/constants.js';
import viteConfig from '../vite.config.js';

const root = fileURLToPath(new URL('../src/', import.meta.url));
const source = (name) => readFile(join(root, name), 'utf8');

async function allSource(directory) {
  const entries = await readdir(directory, { withFileTypes: true });
  return (await Promise.all(entries.map((entry) => entry.isDirectory()
    ? allSource(join(directory, entry.name))
    : /\.[jt]sx?$/.test(entry.name) ? readFile(join(directory, entry.name), 'utf8') : ''))).join('\n');
}

test('fuentes productivas sin credenciales demo, selector de roles ni almacenamiento de tokens', async () => {
  const text = await allSource(root);
  assert.doesNotMatch(text, /DEMO_USERS|demo1234|Perfil de prueba|localStorage|sessionStorage|indexedDB|document\.cookie/);
});

test('imports respetan exactamente las mayúsculas de app y login en Linux', async () => {
  assert.match(await source('main.jsx'), /from '\.\/app\.jsx'/);
  assert.match(await source('app.jsx'), /from '\.\/components\/login\.jsx'/);
  assert.ok((await readdir(root)).includes('app.jsx'));
  assert.ok((await readdir(join(root, 'components'))).includes('login.jsx'));
});

test('login vacío sin selector y con estados de envío y error accesibles', async () => {
  const login = await source('components/login.jsx');
  assert.match(login, /useState\(''\)/);
  assert.match(login, /type="email"/);
  assert.match(login, /type="password"/);
  assert.match(login, /role="alert"/);
  assert.match(login, /disabled=\{busy\}/);
  assert.doesNotMatch(login, /<select|selectedRole/);
  assert.doesNotMatch(await source('components/Shell/RoleSwitch.jsx'), /<select|switchRole/);
});

test('sesión separada de navegación y sin acciones de negocio locales', async () => {
  const app = await source('app.jsx');
  assert.match(app, /status === 'restoring'/);
  assert.match(app, /status !== 'authenticated'/);
  assert.match(app, /PendingIntegration/);
  assert.doesNotMatch(app, /pages\/(Clientes|Presupuestos|Obras|Cobranzas|Usuarios)/);
  const context = await source('context/AppContext.jsx');
  assert.doesNotMatch(context, /savePre|saveCli|crearObra|applyEstado|addCosto|pagoChange|savePago|switchRole|loginRole/);
  assert.match(await source('components/PendingIntegration.jsx'), /Pendiente de integración/);
  assert.doesNotMatch(await source('pages/TecnicoApp.jsx'), /saveNota|addAvance|Guardar registro/);
});

test('menús usan exclusivamente los cuatro enums reales; Técnico no ofrece módulos privilegiados', () => {
  assert.deepEqual(Object.keys(NAV).sort(), ['ADMINISTRATIVO_FINANZAS', 'GERENCIA', 'SUPERVISOR_OBRAS', 'TECNICO']);
  assert.deepEqual(NAV.TECNICO, ['obras']);
  assert.deepEqual(NAV.SUPERVISOR_OBRAS, ['obras', 'alertas']);
  for (const role of Object.keys(NAV)) assert.ok(NAV[role].includes(DEFMOD[role]));
});

test('proxy conserva Host y Origin para CSRF sin reescribir cookies', () => {
  const proxy = viteConfig.server.proxy['/api'];
  assert.equal(proxy.changeOrigin, false);
  assert.equal(proxy.cookieDomainRewrite, undefined);
  assert.equal(proxy.cookiePathRewrite, undefined);
  assert.equal(proxy.headers, undefined);
});
