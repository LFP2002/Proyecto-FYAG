import test from 'node:test';
import assert from 'node:assert/strict';
import { readFile, readdir } from 'node:fs/promises';
import { fileURLToPath } from 'node:url';
import { join } from 'node:path';
import { NAV, DEFMOD } from '../src/data/constants.js';
import viteConfig from '../vite.config.js';

const root = fileURLToPath(new URL('../src/', import.meta.url));
const source = (name) => readFile(join(root, name), 'utf8');

// Única excepción: persistencia de una preferencia visual no sensible.
// No excluir archivos completos ni permitir otros usos del almacenamiento.
function fontPreferenceOnly(text) {
  assert.equal((text.match(/\bFONT_KEY\b/g) || []).length, 3);
  assert.match(text, /const FONT_KEY='fyag\.font-level';/);
  const read = "globalThis.localStorage?.getItem(FONT_KEY)";
  const write = "globalThis.localStorage?.setItem(FONT_KEY,String(fontLevel))";
  for (const access of [read, write]) {
    assert.equal(text.split(access).length, 2, 'Acceso autorizado a preferencia visual');
    text = text.replace(access, '');
  }
  return text;
}

async function allSource(directory) {
  const entries = await readdir(directory, { withFileTypes: true });
  return (await Promise.all(entries.map(async (entry) => {
    const path = join(directory, entry.name);
    if (entry.isDirectory()) return allSource(path);
    if (!/\.[jt]sx?$/.test(entry.name)) return '';
    const text = await readFile(path, 'utf8');
    return path === join(root, 'components', 'layouts', 'DesktopLayout.jsx')
      ? fontPreferenceOnly(text) : text;
  }))).join('\n');
}

test('fuentes productivas sin credenciales demo, selector de roles ni almacenamiento de tokens', async () => {
  const text = await allSource(root);
  assert.doesNotMatch(text, /DEMO_USERS|demo1234|Perfil de prueba|localStorage|sessionStorage|indexedDB|document\.cookie/);
  const pages = await Promise.all(['Alertas.jsx','Cobranzas.jsx','Dashboard.jsx','Reportes.jsx'].map((name) => source(`pages/${name}`)));
  assert.ok(pages.every((page) => !/useApp|obrasC|alertasAll|Exportación generada|estado de desviación/.test(page)));
  assert.doesNotMatch(pages[0], /markAtendida/);
  assert.doesNotMatch(pages[1], /pagoChange|showPagoForm|savePago/);
  assert.doesNotMatch(pages[2], /pctTxt|margen proyectado|Math\.round\([^)]*(?:presupuesto|costo)/);
  assert.doesNotMatch(pages[3], /flash\(|generado[.!]/);
});

test('excepción de almacenamiento visual es estricta y no permite tokens', async () => {
  const layout = await source('components/layouts/DesktopLayout.jsx');
  const forbidden = /localStorage|sessionStorage|indexedDB|document\.cookie/;
  assert.doesNotMatch(fontPreferenceOnly(layout), forbidden);
  assert.match(fontPreferenceOnly(layout + "\nlocalStorage.setItem('token', accessToken);"), forbidden);
  assert.match(fontPreferenceOnly(layout + "\nsessionStorage.setItem('token', accessToken);"), forbidden);
  assert.match(fontPreferenceOnly(layout + "\nindexedDB.open('tokens');"), forbidden);
  assert.match(fontPreferenceOnly(layout + "\ndocument.cookie = token;"), forbidden);
  assert.throws(() => fontPreferenceOnly(layout.replace("'fyag.font-level'", "'accessToken'")));
  assert.throws(() => fontPreferenceOnly(layout.replace('String(fontLevel)', 'accessToken')));
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
  assert.match(app, /pages\/Clientes/);
  assert.match(app, /pages\/Presupuestos/);
  assert.match(app, /canRead\(user.role, mod\)/);
  assert.match(app, /pages\/Obras/);
  assert.match(app, /canReadObras\(user.role\)/);
  assert.match(app, /pages\/Cobranzas/);
  assert.match(app, /pages\/Alertas/);
  assert.match(app, /pages\/Dashboard/);
  assert.match(app, /pages\/Reportes/);
  assert.match(app, /mod === 'usuarios' && user.role === 'ADMINISTRADOR_TI'/);
  const context = await source('context/AppContext.jsx');
  assert.doesNotMatch(context, /savePre|saveCli|crearObra|applyEstado|addCosto|pagoChange|savePago|switchRole|loginRole/);
  assert.match(await source('components/PendingIntegration.jsx'), /Pendiente de integración/);
  assert.match(app, /mod === 'alertas'.*GERENCIA.*SUPERVISOR_OBRAS/s);
  assert.match(app, /mod === 'dashboard'.*GERENCIA/s);
  assert.match(app, /mod === 'reportes'.*GERENCIA.*ADMINISTRATIVO_FINANZAS/s);
  assert.match(app, /mod === 'cobranzas'.*GERENCIA.*ADMINISTRATIVO_FINANZAS/s);
  assert.doesNotMatch(await source('pages/TecnicoApp.jsx'), /saveNota|addAvance|Guardar registro/);
});

test('menús usan seis roles; solo TI ofrece Usuarios y Técnico no ofrece módulos privilegiados', () => {
  assert.deepEqual(Object.keys(NAV).sort(), ['ADMINISTRADOR_TI', 'ADMINISTRATIVO_FINANZAS', 'BODEGUERO', 'GERENCIA', 'SUPERVISOR_OBRAS', 'TECNICO']);
  assert.deepEqual(NAV.ADMINISTRADOR_TI, ['usuarios', 'auditoria', 'chat']);
  assert.equal(NAV.GERENCIA.includes('usuarios'), false);
  assert.deepEqual(NAV.TECNICO, ['obras', 'solicitudes', 'mermas', 'chat']);
  assert.deepEqual(NAV.SUPERVISOR_OBRAS, ['obras', 'presupuestos', 'alertas', 'auditoria', 'inventario', 'solicitudes', 'mermas', 'chat']);
  assert.deepEqual(NAV.BODEGUERO, ['inventario', 'mermas', 'chat']);
  assert.ok(NAV.ADMINISTRATIVO_FINANZAS.includes('egresos'));
  assert.equal(NAV.ADMINISTRATIVO_FINANZAS.includes('inventario'), true);
  assert.equal(NAV.ADMINISTRATIVO_FINANZAS.includes('alertas'), true);
  assert.equal(NAV.GERENCIA.includes('inventario'), true);
  assert.equal(NAV.TECNICO.includes('inventario'), false);
  assert.equal(NAV.TECNICO.includes('egresos'), false);
  assert.equal(NAV.GERENCIA.includes('clientes'), false);
  for (const role of Object.keys(NAV)) assert.ok(NAV[role].includes(DEFMOD[role]));
});

test('proxy conserva Host y Origin para CSRF sin reescribir cookies', () => {
  const proxy = viteConfig.server.proxy['/api'];
  assert.equal(proxy.changeOrigin, false);
  assert.equal(proxy.cookieDomainRewrite, undefined);
  assert.equal(proxy.cookiePathRewrite, undefined);
  assert.equal(proxy.headers, undefined);
});
