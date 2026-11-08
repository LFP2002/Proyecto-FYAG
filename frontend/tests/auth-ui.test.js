import test, { before, after } from 'node:test';
import assert from 'node:assert/strict';
import React from 'react';
import { renderToString } from 'react-dom/server';
import { createServer } from 'vite';

// Render real de componentes JSX mediante Vite, sin navegador ni nuevas
// dependencias. Los ciclos y carreras de red se prueban en auth-client.test.js.
let server;
let App;
let AuthProvider;
let AppProvider;

before(async () => {
  server = await createServer({
    configFile: false, esbuild: { jsx: 'automatic' },
    server: { middlewareMode: true, hmr: false, ws: false }, appType: 'custom',
    optimizeDeps: { noDiscovery: true, include: [] },
  });
  ({ default: App } = await server.ssrLoadModule('/src/app.jsx'));
  ({ AuthProvider } = await server.ssrLoadModule('/src/auth/AuthContext.jsx'));
  ({ AppProvider } = await server.ssrLoadModule('/src/context/AppContext.jsx'));
});
after(async () => { await server?.close(); });

function render(session) {
  const client = {
    getSnapshot: () => session, subscribe: () => () => {},
    restore: async () => null, login: async () => null, logout: async () => true,
  };
  return renderToString(React.createElement(AuthProvider, { client },
    React.createElement(AppProvider, null, React.createElement(App))));
}

test('restauración no muestra ningún contenido protegido ni formulario prematuro', () => {
  const html = render({ status: 'restoring', user: null, notice: null });
  assert.match(html, /Restaurando sesión/);
  assert.doesNotMatch(html, /Pendiente de integración|<form|Dashboard/);
});

test('login real vacío y sin selector ni credenciales precargadas', () => {
  const html = render({ status: 'anonymous', user: null, notice: null });
  assert.match(html, /Correo electrónico/);
  assert.match(html, /type="password"/);
  assert.match(html, /value=""/);
  assert.doesNotMatch(html, /<select|demo|Ver como|Perfil de prueba/);
});

test('envío deshabilita formulario y muestra progreso', () => {
  const html = render({ status: 'authenticating', user: null, notice: null });
  assert.match(html, /Ingresando/);
  assert.match(html, /disabled=""/);
  assert.match(html, /aria-busy="true"/);
});

test('logout fallido muestra aviso y opción de reintentar revocación', () => {
  const html = render({ status: 'anonymous', user: null, notice: 'No se pudo confirmar la revocación remota.' });
  assert.match(html, /role="alert"/);
  assert.match(html, /Reintentar cierre de sesión/);
});

for (const [role, label] of [
  ['GERENCIA', 'Gerencia'], ['ADMINISTRATIVO_FINANZAS', 'Administrativo / Finanzas'],
  ['SUPERVISOR_OBRAS', 'Supervisor de Obras'], ['TECNICO', 'Técnico'],
]) {
  test(`interfaz ${role}: alias real, menú acotado y módulos sin escrituras simuladas`, () => {
    const html = render({ status: 'authenticated', notice: null,
      user: { id: 7, username: 'Alias de la cuenta real', email: 'cuenta@example.test', role } });
    assert.match(html, /Alias de la cuenta real/);
    assert.ok(html.includes(label));
    if (role === 'ADMINISTRATIVO_FINANZAS') assert.match(html, /Nuevo borrador/);
    else assert.match(html, /Pendiente de integración/);
    assert.match(html, /Salir/);
    assert.doesNotMatch(html, /Guardar|Aprobar|Registrar pago|Registrar en bitácora/);
    if (role === 'TECNICO') assert.doesNotMatch(html, /Gerencia|Cobranzas|Presupuestos|Usuarios y roles/);
    if (role === 'SUPERVISOR_OBRAS') assert.doesNotMatch(html, /Cobranzas|Usuarios y roles/);
  });
}
