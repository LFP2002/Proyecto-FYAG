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
  return (await Promise.all(entries.map((entry) => entry.isDirectory() ? allSource(join(directory, entry.name)) : /\.[jt]sx?$/.test(entry.name) ? readFile(join(directory, entry.name), 'utf8') : ''))).join('\n');
}

test('fuentes productivas sin credenciales demo ni almacenamiento de credenciales/tokens', async () => {
  const text = await allSource(root);
  assert.doesNotMatch(text, /DEMO_USERS|demo1234|Perfil de prueba|sessionStorage|indexedDB|document\.cookie/);
  assert.doesNotMatch(text, /localStorage\.(?:getItem|setItem)\([^)]*(?:access|refresh|token|password)/i);
  const pages = await Promise.all(['Alertas.jsx','Cobranzas.jsx','Dashboard.jsx','Reportes.jsx'].map((name) => source(`pages/${name}`)));
  assert.ok(pages.every((page) => !/useApp|obrasC|alertasAll|Exportación generada|estado de desviación/.test(page)));
  assert.doesNotMatch(pages[0], /markAtendida/); assert.doesNotMatch(pages[1], /pagoChange|showPagoForm|savePago/);
  assert.doesNotMatch(pages[2], /pctTxt|margen proyectado|Math\.round\([^)]*(?:presupuesto|costo)/); assert.doesNotMatch(pages[3], /flash\(|generado[.!]/);
});

test('imports respetan exactamente las mayúsculas de app y login en Linux', async () => {
  assert.match(await source('main.jsx'), /from '\.\/app\.jsx'/); assert.match(await source('app.jsx'), /from '\.\/components\/login\.jsx'/);
  assert.ok((await readdir(root)).includes('app.jsx')); assert.ok((await readdir(join(root, 'components'))).includes('login.jsx'));
});

test('login vacío sin selector y con estados de envío y error accesibles', async () => {
  const login = await source('components/login.jsx');
  assert.match(login, /useState\(''\)/); assert.match(login, /type="email"/); assert.match(login, /type="password"/); assert.match(login, /role="alert"/); assert.match(login, /disabled=\{busy\}/);
  assert.doesNotMatch(login, /<select|selectedRole/); assert.doesNotMatch(await source('components/Shell/RoleSwitch.jsx'), /<select|switchRole/);
});

test('sesión separada de navegación y sin acciones de negocio locales', async () => {
  const app = await source('app.jsx');
  for (const pattern of [/status === 'restoring'/,/status !== 'authenticated'/,/PendingIntegration/,/pages\/Clientes/,/pages\/Presupuestos/,/canRead\(user\.role\)/,/pages\/Obras/,/canReadObras\(user\.role\)/,/pages\/Cobranzas/,/pages\/Alertas/,/pages\/Dashboard/,/pages\/Reportes/,/mod === 'usuarios' && user\.role === 'ADMINISTRADOR_TI'/,/pages\/Inventario/]) assert.match(app, pattern);
  const context = await source('context/AppContext.jsx'); assert.doesNotMatch(context, /savePre|saveCli|crearObra|applyEstado|addCosto|pagoChange|savePago|switchRole|loginRole/);
  assert.match(await source('components/PendingIntegration.jsx'), /Pendiente de integración/);
  assert.match(app, /mod === 'alertas'.*GERENCIA.*SUPERVISOR_OBRAS/s); assert.match(app, /mod === 'dashboard'.*GERENCIA/s);
  assert.match(app, /mod === 'reportes'.*GERENCIA.*ADMINISTRATIVO_FINANZAS/s); assert.match(app, /mod === 'cobranzas'.*GERENCIA.*ADMINISTRATIVO_FINANZAS/s);
  assert.doesNotMatch(await source('pages/TecnicoApp.jsx'), /saveNota|addAvance|Guardar registro/);
});

test('menús usan seis roles; solo TI ofrece Usuarios y Técnico no ofrece módulos privilegiados', () => {
  assert.deepEqual(Object.keys(NAV).sort(), ['ADMINISTRADOR_TI', 'ADMINISTRATIVO_FINANZAS', 'BODEGUERO', 'GERENCIA', 'SUPERVISOR_OBRAS', 'TECNICO']);
  assert.deepEqual(NAV.ADMINISTRADOR_TI, ['usuarios', 'auditoria']); assert.equal(NAV.GERENCIA.includes('usuarios'), false);
  assert.deepEqual(NAV.TECNICO, ['obras']); assert.deepEqual(NAV.SUPERVISOR_OBRAS, ['obras', 'alertas', 'auditoria', 'inventario']);
  assert.deepEqual(NAV.BODEGUERO, ['inventario']); assert.ok(NAV.GERENCIA.includes('clientes'));
  for (const role of Object.keys(NAV)) assert.ok(NAV[role].includes(DEFMOD[role]));
});

test('preferencias de apariencia limitadas a tema y tipografía, nunca a credenciales', async () => {
  const appearance = await source('context/AppearanceContext.jsx');
  assert.match(appearance, /fyag:appearance:/); assert.match(appearance, /\['light','dark'\]/); assert.match(appearance, /FONTS/); assert.match(appearance, /SCALES/);
  assert.doesNotMatch(appearance, /accessToken|refreshToken|password|sessionStorage/);
  assert.match(await source('components/Shell/AppearanceControls.jsx'), /Tema de color/); assert.match(await source('components/Shell/AppearanceControls.jsx'), /Tamaño del texto/);
});

test('módulo Bodega permanece acotado por endpoint y escritura explícita', async () => {
  const inventory = await source('pages/Inventario.jsx');
  assert.match(inventory, /\/api\/inventario\//); assert.match(inventory, /SUPERVISOR_OBRAS/); assert.match(inventory, /BODEGUERO/);
  assert.match(inventory, /api\.write/); assert.match(inventory, /clave_idempotencia/);
});

test('proxy conserva Host y Origin para CSRF sin reescribir cookies', () => {
  const proxy = viteConfig.server.proxy['/api']; assert.equal(proxy.changeOrigin, false); assert.equal(proxy.cookieDomainRewrite, undefined); assert.equal(proxy.cookiePathRewrite, undefined); assert.equal(proxy.headers, undefined);
});
