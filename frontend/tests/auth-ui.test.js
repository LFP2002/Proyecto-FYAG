import test, { before, after } from 'node:test';
import assert from 'node:assert/strict';
import React from 'react';
import { renderToString, renderToPipeableStream } from 'react-dom/server';
import { PassThrough } from 'node:stream';
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

function tree(session) {
  const client = {
    getSnapshot: () => session, subscribe: () => () => {},
    restore: async () => null, login: async () => null, logout: async () => true,
  };
  return React.createElement(AuthProvider, { client }, React.createElement(AppProvider, null, React.createElement(App)));
}
function render(session) { return renderToString(tree(session)); }
// Espera el contenido real de Suspense antes de comprobar los permisos.
function renderReady(session) {
  return new Promise((resolve,reject)=>{
    const output=new PassThrough();let html='';let timer;
    output.setEncoding('utf8');output.on('data',chunk=>html+=chunk);
    output.on('end',()=>{clearTimeout(timer);resolve(html);});
    output.on('error',error=>{clearTimeout(timer);reject(error);});
    const stream=renderToPipeableStream(tree(session),{
      onAllReady(){stream.pipe(output);},
      onError(error){clearTimeout(timer);reject(error);},
      onShellError(error){clearTimeout(timer);reject(error);}
    });
    timer=setTimeout(()=>{stream.abort();reject(new Error('Tiempo agotado al cargar módulo SSR'));},10000);
  });
}

test('restauración no muestra ningún contenido protegido ni formulario prematuro', () => {
  const html = render({ status: 'restoring', user: null, notice: null });
  assert.match(html, /Restaurando sesión/);
  assert.doesNotMatch(html, /Pendiente de integración|<form|Dashboard/);
});

test('desafío de primer acceso monta solo el formulario para contraseña personal', () => {
  const html = render({ status: 'password-change-required', user: null, notice: null });
  assert.match(html, /Crear contraseña personal/);
  assert.match(html, /id="first-password"/);
  assert.match(html, /Confirmar contraseña/);
  assert.doesNotMatch(html, /Dashboard|Módulos|Ingresar</);
});

test('primer acceso temporal no monta negocio y solicita definir y confirmar clave personal', () => {
  const html = render({ status: 'password-change-required', user: null, notice: null });
  assert.match(html, /Crear contraseña personal/);
  assert.match(html, /id="first-password"/);
  assert.match(html, /id="first-password-confirm"/);
  assert.match(html, /Guardar contraseña personal/);
  assert.doesNotMatch(html, /fyag-modules-nav|Dashboard gerencial|Mis obras|type="email"/);
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
  test(`interfaz ${role}: alias real, menú acotado y módulos sin escrituras simuladas`, async () => {
    const html = await renderReady({ status: 'authenticated', notice: null,
      user: { id: 7, username: 'Alias de la cuenta real', email: 'cuenta@example.test', role } });
    assert.match(html, /Alias de la cuenta real/);
    assert.ok(html.includes(label));
    if (role === 'ADMINISTRATIVO_FINANZAS') assert.match(html, /Nuevo presupuesto/);
    else if (role === 'SUPERVISOR_OBRAS') assert.match(html, /Nueva obra/);
    else if (role === 'GERENCIA') assert.match(html, /Dashboard gerencial/);
    else if (role === 'TECNICO') assert.match(html, /Mis obras/);
    assert.match(html, /Salir/);
    assert.doesNotMatch(html, /Guardar|Aprobar|Registrar pago|Registrar en bitácora/);
    if (role === 'TECNICO') assert.doesNotMatch(html, /Gerencia|Cobranzas|Presupuestos|Usuarios y roles/);
    if (role === 'SUPERVISOR_OBRAS') assert.doesNotMatch(html, /Cobranzas|Usuarios y roles/);
  });
}
