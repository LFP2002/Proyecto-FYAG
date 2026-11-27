import test from 'node:test';
import assert from 'node:assert/strict';
import { ApiError, createAuthClient } from '../src/auth/client.js';

const account = Object.freeze({ id: 7, username: 'Alias institucional', email: 'cuenta@example.test', role: 'TECNICO' });
const credentials = { email: '  CUENTA@example.test  ', password: 'contraseña ficticia para pruebas' };
const json = (data, status = 200, headers = {}) => new Response(JSON.stringify(data), { status, headers: { 'Content-Type': 'application/json', ...headers } });
const deferred = () => {
  let resolve;
  const promise = new Promise((done) => { resolve = done; });
  return { promise, resolve };
};

function backend(overrides = {}) {
  const calls = [];
  let csrf = 'proteccion-inicial';
  const fetchImpl = async (path, options) => {
    calls.push({ path, ...options });
    if (overrides[path]) return overrides[path](options, calls);
    if (path === '/api/auth/csrf/') return json({ csrfToken: csrf });
    if (path === '/api/auth/login/') {
      csrf = 'proteccion-rotada';
      return json({ access: 'acceso-inicial', csrfToken: csrf, user: account });
    }
    if (path === '/api/auth/refresh/') return json({ access: 'acceso-renovado' });
    if (path === '/api/auth/me/') return json(account);
    if (path === '/api/auth/logout/') return new Response(null, { status: 204 });
    return json({ ok: true });
  };
  return { client: createAuthClient({ fetchImpl }), calls };
}

test('estado de instalación consulta sin caché, sin seguir redirecciones y admite abortar', async () => {
  const path = '/api/auth/setup/estado/';
  const { client, calls } = backend({ [path]: () => json({ pendiente: true }) });
  const { signal } = new AbortController();
  assert.deepEqual(await client.initialSetupStatus({ signal }), { pendiente: true });
  assert.equal(calls.length, 1);
  assert.equal(calls[0].path, path);
  assert.equal(calls[0].method, 'GET');
  assert.equal(calls[0].cache, 'no-store');
  assert.equal(calls[0].redirect, 'error');
  assert.equal(calls[0].signal, signal);
  assert.equal(calls[0].headers.has('Authorization'), false);
});

test('alta inicial exige 201 y CSRF sin restaurar ni crear sesión', async () => {
  const path = '/api/auth/setup/';
  for (const status of [200, 201]) {
    const { client, calls } = backend({ [path]: () => json({ detail: 'Cuenta TI creada.' }, status) });
    const snapshot = client.getSnapshot();
    const result = client.submitInitialSetup({ clave_instalacion: 'A'.repeat(43) });
    if (status === 201) await result;
    else await assert.rejects(result, { status: 502 });
    assert.deepEqual(calls.map(call => call.path), ['/api/auth/csrf/', path]);
    assert.equal(calls[1].headers.get('X-CSRFToken'), 'proteccion-inicial');
    assert.equal(calls[1].headers.has('Authorization'), false);
    assert.equal(client.getSnapshot(), snapshot);
  }
});

test('verificación envía CSRF y token solo en el cuerpo, sin crear sesión', async () => {
  const { client, calls } = backend({ '/api/auth/correo/verificar/': () => new Response(null, { status: 204 }) });
  await client.submitEmailVerification('confirmar', 'A'.repeat(43));
  assert.equal(calls.length, 2);
  assert.equal(calls[1].path, '/api/auth/correo/verificar/');
  assert.equal(calls[1].headers.get('X-CSRFToken'), 'proteccion-inicial');
  assert.equal(calls[1].headers.get('Authorization'), null);
  assert.deepEqual(JSON.parse(calls[1].body), { token: 'A'.repeat(43) });
  assert.equal(client.getSnapshot().user, null);
});

test('cliente autenticado soporta multipart sin forzar Content-Type y respuesta Blob en mismas rutas API', async () => {
  const calls = [];
  const client = createAuthClient({ fetchImpl: async (path, options) => {
    calls.push({ path, options });
    if (path.endsWith('/csrf/')) return json({ csrfToken: 'csrf-test' });
    if (path.endsWith('/login/')) return json({ access: 'access-test', csrfToken: 'csrf-test' });
    if (path.endsWith('/me/')) return json(account);
    if (path.endsWith('/fotos/9/')) return new Response(new Blob(['imagen'], { type: 'image/png' }), { status: 200, headers: { 'Content-Type': 'image/png' } });
    return json({ ok: true });
  } });
  await client.login(credentials);
  const form = new FormData(); form.append('descripcion_trabajo', 'Trabajo'); form.append('fotos[]', new Blob(['foto'], { type: 'image/png' }), 'foto.png');
  await client.request('/api/obras/1/turnos/2/finalizar/', { method: 'POST', body: form });
  const image = await client.request('/api/obras/1/turnos/2/fotos/9/', { responseType: 'blob' });
  assert.equal(calls.at(-2).options.body, form);
  assert.equal(calls.at(-2).options.headers.get('Content-Type'), null);
  assert.equal(calls.at(-2).options.headers.get('Authorization'), 'Bearer access-test');
  assert.equal(image.type, 'image/png');
  assert.equal(await image.text(), 'imagen');
});

test('login con credencial temporal solo habilita primer cambio y no consulta /me', async () => {
  const challenge = 'T'.repeat(43), calls = [];
  const client = createAuthClient({ fetchImpl: async (path, options) => {
    calls.push({ path, ...options });
    if (path === '/api/auth/csrf/') return json({ csrfToken: 'csrf-inicial' });
    if (path === '/api/auth/login/') return json({ estado: 'CAMBIO_OBLIGATORIO', desafio: challenge, desafio_vence_en: '2026-11-25T12:05:00Z', csrfToken: 'csrf-rotado' });
    if (path === '/api/auth/primer-cambio-clave/') return json({ estado: 'CLAVE_PERSONAL_CONFIRMADA', login_requerido: true });
    throw new Error(`Ruta no esperada: ${path}`);
  } });
  await client.login(credentials);
  assert.equal(client.getSnapshot().status, 'password-change-required');
  assert.equal(client.getSnapshot().user, null);
  assert.deepEqual(calls.map(call => call.path), ['/api/auth/csrf/', '/api/auth/login/']);
  await client.completeFirstPasswordChange('clave-personal-de-prueba');
  assert.equal(client.getSnapshot().status, 'anonymous');
  assert.equal(client.getSnapshot().user, null);
  assert.deepEqual(calls.map(call => call.path), ['/api/auth/csrf/', '/api/auth/login/', '/api/auth/primer-cambio-clave/']);
  assert.deepEqual(JSON.parse(calls[2].body), { desafio: challenge, nueva_clave: 'clave-personal-de-prueba' });
  assert.equal(calls[2].headers.get('X-CSRFToken'), 'csrf-rotado');
  assert.equal(calls[2].headers.get('Authorization'), null);
  assert.equal(client.getSnapshot().notice, 'Contraseña personal confirmada. Inicia sesión con tu nueva contraseña.');
});

test('login real: normaliza email, no altera password y confirma identidad con /me', async () => {
  const { client, calls } = backend();
  assert.equal(client.getSnapshot().status, 'restoring');
  const user = await client.login(credentials);
  assert.deepEqual(user, account);
  assert.equal(client.getSnapshot().status, 'authenticated');
  assert.deepEqual(calls.map((call) => call.path), ['/api/auth/csrf/', '/api/auth/login/', '/api/auth/me/']);
  assert.deepEqual(JSON.parse(calls[1].body), { email: 'cuenta@example.test', password: credentials.password });
  assert.equal(calls[1].headers.get('X-CSRFToken'), 'proteccion-inicial');
  assert.equal(calls[2].headers.get('Authorization'), 'Bearer acceso-inicial');
  for (const call of calls) {
    assert.equal(call.credentials, 'same-origin');
    assert.equal(call.redirect, 'error');
    assert.equal(call.cache, 'no-store');
  }
  assert.equal(Object.hasOwn(client.getSnapshot(), 'access'), false);
});

for (const status of [400, 401, 403, 429]) {
  test(`login ${status}: no conserva identidad y ofrece error seguro`, async () => {
    const { client } = backend({ '/api/auth/login/': () => json({ detail: 'Mensaje no expuesto', token: 'no-exponer' }, status, { 'Retry-After': '60' }) });
    await assert.rejects(client.login(credentials), (error) => error.status === status && !error.message.includes('no-exponer'));
    assert.equal(client.getSnapshot().user, null);
    assert.equal(client.getSnapshot().status, 'anonymous');
    assert.ok(client.getSnapshot().notice);
    await assert.rejects(client.request('/api/obras/'), { status: 401 });
  });
}

test('no envía credenciales incompletas ni acepta un rol como identidad', async () => {
  const { client, calls } = backend();
  await assert.rejects(client.login({ email: '', password: '', role: 'GERENCIA' }), { status: 400 });
  assert.equal(calls.length, 0);
  await client.login({ ...credentials, role: 'GERENCIA', is_superuser: true });
  assert.equal(client.getSnapshot().user.role, 'TECNICO');
  assert.deepEqual(Object.keys(JSON.parse(calls.find((call) => call.path.endsWith('/login/')).body)).sort(), ['email', 'password']);
});

test('error de red en login: sesión anónima y sin credenciales en el mensaje', async () => {
  const { client } = backend({ '/api/auth/login/': () => { throw new Error('detalle técnico sensible'); } });
  await assert.rejects(client.login(credentials), { status: 0 });
  assert.equal(client.getSnapshot().user, null);
  assert.match(client.getSnapshot().notice, /conexión/);
  assert.doesNotMatch(client.getSnapshot().notice, /sensible/);
});

test('recarga: CSRF + refresh de cookie + /me, sin refresh en JSON', async () => {
  const { client, calls } = backend();
  const first = client.restore();
  assert.equal(first, client.restore());
  await first;
  assert.equal(client.getSnapshot().user.role, account.role);
  assert.deepEqual(calls.map((call) => call.path), ['/api/auth/csrf/', '/api/auth/refresh/', '/api/auth/me/']);
  assert.equal(calls[1].body, '{}');
  assert.equal(calls[1].headers.get('X-CSRFToken'), 'proteccion-inicial');
  assert.equal(calls[2].headers.get('Authorization'), 'Bearer acceso-renovado');
});

test('sin cookie de sesión: termina restauración sin entrar ni mostrar error de credenciales', async () => {
  const { client } = backend({ '/api/auth/refresh/': () => json({}, 401) });
  await client.restore();
  assert.deepEqual(client.getSnapshot(), { status: 'anonymous', user: null, notice: null, sessionEpoch: 1 });
});

test('CSRF no disponible impide enviar login y no intenta relajar protección', async () => {
  const { client, calls } = backend({ '/api/auth/csrf/': () => json({}) });
  await assert.rejects(client.login(credentials), { status: 502 });
  assert.equal(calls.length, 1);
  assert.equal(client.getSnapshot().user, null);
});

test('403 CSRF HTML se maneja sin asumir JSON ni reintentar indefinidamente', async () => {
  const { client, calls } = backend({ '/api/auth/login/': () => new Response('<h1>CSRF verification failed</h1>', { status: 403 }) });
  await assert.rejects(client.login(credentials), { status: 403 });
  assert.equal(calls.filter((call) => call.path.endsWith('/login/')).length, 1);
  assert.equal(client.getSnapshot().user, null);
});

test('401 por expiración renueva una vez, confirma perfil y reintenta con token nuevo', async () => {
  const { client, calls } = backend({ '/api/obras/': (options) => options.headers.get('Authorization') === 'Bearer acceso-inicial' ? json({}, 401) : json({ count: 0 }) });
  await client.login(credentials);
  assert.deepEqual(await client.request('/api/obras/'), { count: 0 });
  assert.equal(calls.filter((call) => call.path.endsWith('/refresh/')).length, 1);
  assert.equal(calls.filter((call) => call.path === '/api/obras/').length, 2);
  assert.equal(calls.find((call) => call.path.endsWith('/refresh/')).headers.get('X-CSRFToken'), 'proteccion-rotada');
});

test('401 simultáneos comparten una renovación y cada solicitud se repite una vez', async () => {
  const started = deferred();
  const gate = deferred();
  const { client, calls } = backend({
    '/api/auth/refresh/': () => { started.resolve(); return gate.promise; },
    '/api/obras/': (options) => options.headers.get('Authorization') === 'Bearer acceso-inicial' ? json({}, 401) : json({ ok: true }),
  });
  await client.login(credentials);
  const first = client.request('/api/obras/');
  const second = client.request('/api/obras/');
  await started.promise;
  assert.equal(calls.filter((call) => call.path.endsWith('/refresh/')).length, 1);
  gate.resolve(json({ access: 'acceso-renovado' }));
  await Promise.all([first, second]);
  assert.equal(calls.filter((call) => call.path.endsWith('/refresh/')).length, 1);
  assert.equal(calls.filter((call) => call.path === '/api/obras/').length, 4);
});

test('401 tardío reutiliza renovación ya completada, sin rotar de nuevo la cookie', async () => {
  const late = deferred();
  let protectedCalls = 0;
  const { client, calls } = backend({ '/api/obras/': (options) => {
    if (options.headers.get('Authorization') === 'Bearer acceso-inicial') {
      protectedCalls += 1;
      return protectedCalls === 1 ? json({}, 401) : late.promise;
    }
    return json({ ok: true });
  } });
  await client.login(credentials);
  const first = client.request('/api/obras/');
  const second = client.request('/api/obras/');
  await first;
  late.resolve(json({}, 401));
  await second;
  assert.equal(calls.filter((call) => call.path.endsWith('/refresh/')).length, 1);
});

test('segundo 401 termina sesión: máximo un refresh y dos intentos', async () => {
  const { client, calls } = backend({ '/api/obras/': () => json({}, 401) });
  await client.login(credentials);
  await assert.rejects(client.request('/api/obras/'), { status: 401 });
  assert.equal(calls.filter((call) => call.path === '/api/obras/').length, 2);
  assert.equal(calls.filter((call) => call.path.endsWith('/refresh/')).length, 1);
  assert.equal(client.getSnapshot().user, null);
});

for (const status of [401, 403, 429]) {
  test(`refresh rechazado ${status} limpia token y usuario`, async () => {
    const { client, calls } = backend({ '/api/auth/refresh/': () => json({}, status), '/api/obras/': () => json({}, 401) });
    await client.login(credentials);
    await assert.rejects(client.request('/api/obras/'), { status });
    assert.equal(client.getSnapshot().status, 'anonymous');
    assert.equal(client.getSnapshot().user, null);
    const count = calls.length;
    await assert.rejects(client.request('/api/obras/'), { status: 401 });
    assert.equal(calls.length, count);
  });
}

test('refresh sin conexión termina sesión, no deja rol anterior', async () => {
  const { client } = backend({ '/api/auth/refresh/': () => { throw new Error('sin red'); }, '/api/obras/': () => json({}, 401) });
  await client.login(credentials);
  await assert.rejects(client.request('/api/obras/'), { status: 0 });
  assert.equal(client.getSnapshot().user, null);
});

test('403 de autorización real no renueva ni cambia el rol', async () => {
  const { client, calls } = backend({ '/api/obras/': () => json({}, 403) });
  await client.login(credentials);
  await assert.rejects(client.request('/api/obras/'), { status: 403 });
  assert.equal(client.getSnapshot().user.role, 'TECNICO');
  assert.equal(calls.filter((call) => call.path.endsWith('/refresh/')).length, 0);
});

test('fallo de /me después de login descarta el token y la identidad', async () => {
  const { client } = backend({ '/api/auth/me/': () => json({}, 401) });
  await assert.rejects(client.login(credentials), { status: 401 });
  assert.equal(client.getSnapshot().user, null);
  await assert.rejects(client.request('/api/obras/'), { status: 401 });
});

test('rol se obtiene de /me, no de un selector, is_superuser o payload de login', async () => {
  const { client } = backend({ '/api/auth/login/': () => json({ access: 'acceso-inicial', csrfToken: 'rotado', user: { ...account, role: 'GERENCIA', is_superuser: true } }) });
  await client.login(credentials);
  assert.equal(client.getSnapshot().user.role, 'TECNICO');
  assert.equal(client.switchRole, undefined);
  assert.equal(client.getSnapshot().user.is_superuser, undefined);
});

test('perfil con rol desconocido no habilita la aplicación', async () => {
  const { client } = backend({ '/api/auth/me/': () => json({ ...account, role: 'ADMIN' }) });
  await assert.rejects(client.login(credentials), { status: 403 });
  assert.equal(client.getSnapshot().user, null);
});

test('logout limpia inmediatamente y revoca con cookie y CSRF rotado', async () => {
  const gate = deferred();
  const started = deferred();
  const { client, calls } = backend({ '/api/auth/logout/': () => { started.resolve(); return gate.promise; } });
  await client.login(credentials);
  const ending = client.logout();
  assert.equal(client.getSnapshot().user, null);
  assert.equal(client.getSnapshot().status, 'logging-out');
  await assert.rejects(client.request('/api/obras/'), { status: 401 });
  await started.promise;
  const logout = calls.find((call) => call.path.endsWith('/logout/'));
  assert.equal(logout.headers.get('X-CSRFToken'), 'proteccion-rotada');
  assert.equal(logout.headers.get('Authorization'), null);
  assert.equal(logout.body, '{}');
  gate.resolve(new Response(null, { status: 204 }));
  assert.equal(await ending, true);
  assert.equal(client.getSnapshot().status, 'anonymous');
});

test('logout fallido informa revocación no confirmada, pero retira acceso local', async () => {
  const { client } = backend({ '/api/auth/logout/': () => { throw new Error('sin red'); } });
  await client.login(credentials);
  assert.equal(await client.logout(), false);
  assert.equal(client.getSnapshot().user, null);
  assert.match(client.getSnapshot().notice, /revocación remota/);
  await assert.rejects(client.request('/api/obras/'), { status: 401 });
});

test('logout durante refresh espera la rotación, revoca y nunca restaura identidad tardía', async () => {
  const gate = deferred();
  const started = deferred();
  const { client, calls } = backend({
    '/api/auth/refresh/': () => { started.resolve(); return gate.promise; },
    '/api/obras/': () => json({}, 401),
  });
  await client.login(credentials);
  const rejected = assert.rejects(client.request('/api/obras/'), ApiError);
  await started.promise;
  const ending = client.logout();
  assert.equal(client.getSnapshot().user, null);
  gate.resolve(json({ access: 'acceso-tardio' }));
  await rejected;
  assert.equal(await ending, true);
  assert.equal(client.getSnapshot().user, null);
  assert.equal(calls.filter((call) => call.path.endsWith('/logout/')).length, 1);
  assert.equal(calls.filter((call) => call.path.endsWith('/me/')).length, 1); // solo el login original
});

test('logout durante login impide ingreso tardío y bloquea un nuevo login hasta revocar', async () => {
  const gate = deferred();
  const started = deferred();
  const { client } = backend({ '/api/auth/login/': () => { started.resolve(); return gate.promise; } });
  const rejected = assert.rejects(client.login(credentials), ApiError);
  await started.promise;
  const ending = client.logout();
  await assert.rejects(client.login(credentials), { status: 400 });
  gate.resolve(json({ access: 'acceso-tardio', csrfToken: 'rotado', user: account }));
  await rejected;
  await ending;
  assert.equal(client.getSnapshot().status, 'anonymous');
});

test('el cliente no envía token a un origen externo ni acepta Authorization del caller', async () => {
  const { client, calls } = backend();
  await client.login(credentials);
  const count = calls.length;
  await assert.rejects(client.request('https://example.test/api/obras/'), { status: 400 });
  assert.equal(calls.length, count);
  await client.request('/api/obras/', { headers: { Authorization: 'Bearer inyectado' } });
  assert.equal(calls.at(-1).headers.get('Authorization'), 'Bearer acceso-inicial');
});

test('suscriptores reciben estados de sesión y pueden darse de baja', async () => {
  const { client } = backend();
  const states = [];
  const unsubscribe = client.subscribe(() => states.push(client.getSnapshot().status));
  await client.login(credentials);
  await client.logout();
  assert.deepEqual(states, ['authenticating', 'authenticated', 'logging-out', 'anonymous']);
  unsubscribe();
  await client.login(credentials);
  assert.equal(states.length, 4);
});

test('429 conserva Retry-After para que la UI pueda informar espera sin logs sensibles', async () => {
  const { client } = backend({ '/api/auth/login/': () => json({}, 429, { 'Retry-After': '90' }) });
  await assert.rejects(client.login(credentials), (error) => error.status === 429 && error.retryAfter === '90');
});

test('identidad diferente tras renovar exige nuevo login, sin mezclar usuarios', async () => {
  let profiles = 0;
  const { client } = backend({
    '/api/auth/me/': () => json(++profiles === 1 ? account : { ...account, id: 99, role: 'GERENCIA' }),
    '/api/obras/': () => json({}, 401),
  });
  await client.login(credentials);
  await assert.rejects(client.request('/api/obras/'), { status: 401 });
  assert.equal(client.getSnapshot().user, null);
});

test('respuesta tardía de petición autenticada no entrega datos después de logout', async () => {
  const gate = deferred();
  const { client } = backend({ '/api/obras/': () => gate.promise });
  await client.login(credentials);
  const rejected = assert.rejects(client.request('/api/obras/'), { status: 401 });
  await client.logout();
  gate.resolve(json({ datos: 'del usuario anterior' }));
  await rejected;
  assert.equal(client.getSnapshot().user, null);
});

test('restauración con error de identidad no publica usuario ni token', async () => {
  const { client } = backend({ '/api/auth/me/': () => json({}, 403) });
  await client.restore();
  assert.equal(client.getSnapshot().status, 'anonymous');
  assert.equal(client.getSnapshot().user, null);
  await assert.rejects(client.request('/api/obras/'), { status: 401 });
});

test('respuestas de autenticación malformadas terminan en error controlado', async () => {
  for (const data of [null, {}, { access: 'incompleto' }]) {
    const { client } = backend({ '/api/auth/login/': () => json(data) });
    await assert.rejects(client.login(credentials), { status: 502 });
    assert.equal(client.getSnapshot().user, null);
  }
});

test('correo propio confirmado invalida sesión local sin refresh y comunica nuevo login', async () => {
  const { client, calls } = backend();
  await client.login(credentials);
  assert.equal(client.sessionInvalidatedByEmailChange(), true);
  assert.equal(client.getSnapshot().status, 'anonymous');
  assert.equal(client.getSnapshot().user, null);
  assert.match(client.getSnapshot().notice, /nuevo correo electrónico/);
  const before = calls.length;
  await assert.rejects(client.request('/api/obras/'), { status: 401 });
  assert.equal(calls.length, before, 'no se utiliza access ni refresh revocados');
  assert.equal(client.sessionInvalidatedByEmailChange(), false);
});

test('aprobación comercial conserva errores públicos 400 y 409 solo en su ruta', async () => {
  const path = '/api/presupuestos/12/aprobar-finanzas/';
  let status = 400;
  const payload = () => status === 400
    ? {version_comercial_esperada:['Revise la versión comercial.'], monto_neto:['El monto neto debe ser positivo.'], interno:['No público']}
    : {code:'version_comercial_obsoleta', detail:'Los datos comerciales cambiaron.'};
  const {client,calls} = backend({
    [path]: () => json(payload(), status),
    '/api/presupuestos/12/': () => json(payload(), status),
  });
  await client.login(credentials);
  await assert.rejects(client.request(path,{method:'POST',body:{}}), error => {
    assert.equal(error.status,400);
    assert.deepEqual(error.fieldErrors,{version_comercial_esperada:['Revise la versión comercial.'],monto_neto:['El monto neto debe ser positivo.']});
    return true;
  });
  await assert.rejects(client.request('/api/presupuestos/12/'), error => {
    assert.deepEqual(error.fieldErrors,{}); return true;
  });
  status = 409;
  await assert.rejects(client.request(path,{method:'POST',body:{}}), error => {
    assert.equal(error.status,409); assert.equal(error.code,'version_comercial_obsoleta');
    assert.deepEqual(error.fieldErrors,{detail:['Los datos comerciales cambiaron.']}); return true;
  });
  await assert.rejects(client.request('/api/presupuestos/12/'), error => {
    assert.equal(error.code,null); return true;
  });
  assert.equal(calls.filter(c=>c.path===path).length,2);
});
