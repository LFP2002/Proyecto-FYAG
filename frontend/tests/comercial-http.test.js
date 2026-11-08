import test from 'node:test';
import assert from 'node:assert/strict';
import { createAuthClient } from '../src/auth/client.js';
const response = (data, status = 200) => new Response(JSON.stringify(data), { status, headers: { 'Content-Type': 'application/json' } });
async function authenticated(result) {
  const calls = [];
  const client = createAuthClient({ fetchImpl: async (path, options) => {
    calls.push({ path, options });
    if (path.endsWith('/csrf/')) return response({ csrfToken: 'csrf' });
    if (path.endsWith('/login/')) return response({ access: 'access', csrfToken: 'csrf' });
    if (path.endsWith('/me/')) return response({ id: 1, username: 'AF', email: 'af@example.test', role: 'ADMINISTRATIVO_FINANZAS' });
    if (path.endsWith('/refresh/')) return response({ access: 'new' });
    return result(path, options);
  } });
  await client.login({ email: 'af@example.test', password: 'test-only' });
  return { client, calls };
}
test('400 comercial conserva solo errores públicos permitidos; sanea HTML/trazas/secretos', async () => {
  const { client } = await authenticated(() => response({ nombre_legal: ['Nombre requerido.'], correo: ['Ya existe.'], detail: '<script>no</script>', password: 'secreto', non_field_errors: ['Traceback token SQL'], desconocido: 'no mostrar' }, 400));
  await assert.rejects(client.request('/api/clientes/', { method: 'POST', body: {} }), (e) => {
    assert.deepEqual(e.fieldErrors, { nombre_legal: ['Nombre requerido.'], correo: ['Ya existe.'] }); return e.status === 400;
  });
});
test('409 utilizado expone código público y detalle sin refrescar ni repetir POST', async () => {
  const { client, calls } = await authenticated(() => response({ code: 'presupuesto_utilizado', detail: 'El presupuesto está utilizado por una obra.' }, 409));
  await assert.rejects(client.request('/api/presupuestos/1/anular/', { method: 'POST', body: { motivo: 'Motivo' } }), (e) => e.code === 'presupuesto_utilizado' && e.fieldErrors.detail[0].includes('utilizado'));
  assert.equal(calls.filter((c) => c.path.endsWith('/anular/')).length, 1);
  assert.equal(calls.filter((c) => c.path.endsWith('/refresh/')).length, 0);
});
test('red de escritura no reintenta; 5xx HTML no se expone', async () => {
  for (const network of [true, false]) {
    const { client, calls } = await authenticated(() => { if (network) throw new Error('secreto'); return new Response('<html>Traceback</html>', { status: 500 }); });
    await assert.rejects(client.request('/api/clientes/', { method: 'POST', body: {} }), (e) => e.status === (network ? 0 : 500) && !e.message.includes('secreto') && Object.keys(e.fieldErrors).length === 0);
    assert.equal(calls.filter((c) => c.path === '/api/clientes/').length, 1);
  }
});
test('401 de escritura renueva y reintenta solo una vez conservando payload decimal', async () => {
  let attempts = 0;
  const { client, calls } = await authenticated(() => ++attempts === 1 ? response({}, 401) : response({ id: 2 }, 201));
  const body = { cantidad: '0.001', precio_unitario: '9999999999999.99', descripcion: 'Línea', unidad: 'u', orden: 1 };
  assert.deepEqual(await client.request('/api/presupuestos/1/items/', { method: 'POST', body }), { id: 2 });
  assert.equal(attempts, 2);
  for (const call of calls.filter((c) => c.path.endsWith('/items/'))) assert.deepEqual(JSON.parse(call.options.body), body);
  assert.equal(calls.filter((c) => c.path.endsWith('/refresh/')).length, 1);
});
