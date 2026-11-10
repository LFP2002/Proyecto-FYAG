import test from 'node:test';
import assert from 'node:assert/strict';
import { createAuthClient } from '../src/auth/client.js';

test('Obras extiende errores públicos sin alterar Bearer, refresh ni saneamiento de datos sensibles', async () => {
  const calls = [];
  const json = (data, status = 200) => new Response(JSON.stringify(data), { status });
  let status = 400;
  const client = createAuthClient({ fetchImpl: async (path, options) => {
    calls.push({ path, options });
    if (path.endsWith('/csrf/')) return json({ csrfToken: 'csrf-test' });
    if (path.endsWith('/login/')) return json({ access: 'access-test', csrfToken: 'csrf-test' });
    if (path.endsWith('/me/')) return json({ id: 2, username: 'S', email: 's@example.test', role: 'SUPERVISOR_OBRAS' });
    return status === 400 ? json({ categoria_servicio: ['La categoría está inactiva.'], tecnico_responsable: ['Técnico no elegible.'], nombre: ['Ya existe.'], motivo: ['Ingrese un motivo.'], password: 'oculto', detail: '<script>no</script>' }, 400) : json({ detail: 'El participante ya está activo.', code: 'sin_cambios' }, 409);
  } });
  await client.login({ email: 's@example.test', password: 'test-only' });
  await assert.rejects(client.request('/api/obras/', { method: 'POST', body: {} }), (error) => {
    assert.deepEqual(error.fieldErrors, { categoria_servicio: ['La categoría está inactiva.'], tecnico_responsable: ['Técnico no elegible.'], nombre: ['Ya existe.'], motivo: ['Ingrese un motivo.'] }); return error.status === 400;
  });
  status = 409;
  await assert.rejects(client.request('/api/obras/1/participantes/', { method: 'POST', body: { tecnico: 7, motivo: 'Apoyo' } }), (error) => error.code === 'sin_cambios' && error.fieldErrors.detail[0] === 'El participante ya está activo.');
  assert.equal(calls.filter((call) => call.path.endsWith('/participantes/')).length, 1);
  assert.equal(calls.filter((call) => call.path.endsWith('/refresh/')).length, 0);
  assert.equal(calls.at(-1).options.headers.get('Authorization'), 'Bearer access-test');
});
