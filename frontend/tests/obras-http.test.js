import test from 'node:test';
import assert from 'node:assert/strict';
import { createAuthClient } from '../src/auth/client.js';

test('Obras extiende errores públicos sin alterar Bearer, refresh ni saneamiento de datos sensibles', async () => {
  const calls = [];
  const json = (data, status = 200) => new Response(JSON.stringify(data), { status });
  let status = 400, pending=false;
  const client = createAuthClient({ fetchImpl: async (path, options) => {
    calls.push({ path, options });
    if (path.endsWith('/csrf/')) return json({ csrfToken: 'csrf-test' });
    if (path.endsWith('/login/')) return json({ access: 'access-test', csrfToken: 'csrf-test' });
    if (path.endsWith('/me/')) return json({ id: 2, username: 'S', email: 's@example.test', role: 'SUPERVISOR_OBRAS' });
    if(pending)return json({detail:'Costos incompletos',code:'costos_incompletos',pendientes:['turnos_abiertos','password','turnos_abiertos']},409);
    return status === 400 ? json({ categoria_servicio: ['La categoría está inactiva.'], tecnico_responsable: ['Técnico no elegible.'], nombre: ['Ya existe.'], motivo: ['Ingrese un motivo.'], password: 'oculto', detail: '<script>no</script>' }, 400) : json({ detail: 'El participante ya está activo.', code: 'sin_cambios' }, 409);
  } });
  await client.login({ email: 's@example.test', password: 'test-only' });
  await assert.rejects(client.request('/api/obras/', { method: 'POST', body: {} }), (error) => {
    assert.deepEqual(error.fieldErrors, { categoria_servicio: ['La categoría está inactiva.'], tecnico_responsable: ['Técnico no elegible.'], nombre: ['Ya existe.'], motivo: ['Ingrese un motivo.'] }); return error.status === 400;
  });
  status = 409;
  await assert.rejects(client.request('/api/obras/1/participantes/', { method: 'POST', body: { tecnico: 7, motivo: 'Apoyo' } }), (error) => error.code === 'sin_cambios' && error.fieldErrors.detail[0] === 'El participante ya está activo.');
  pending=true;
  await assert.rejects(client.request('/api/obras/1/costos/validar/',{method:'POST',body:{motivo:'QA'}}),error=>error.status===409&&error.code==='costos_incompletos'&&error.fieldErrors.pendientes.join(',')==='turnos_abiertos');
  assert.equal(calls.filter((call) => call.path.endsWith('/participantes/')).length, 1);
  assert.equal(calls.filter((call) => call.path.endsWith('/refresh/')).length, 0);
  assert.equal(calls.at(-1).options.headers.get('Authorization'), 'Bearer access-test');
});

test('019F admite mensajes públicos solo en las rutas pertinentes y sanea materiales', async () => {
  const json = (data, status = 200) => new Response(JSON.stringify(data), {status});
  let body, status;
  const client = createAuthClient({fetchImpl: async path => {
    if (path.endsWith('/csrf/')) return json({csrfToken:'csrf-test'});
    if (path.endsWith('/login/')) return json({access:'access-test',csrfToken:'csrf-test'});
    if (path.endsWith('/me/')) return json({id:2,username:'S',email:'s@example.test',role:'SUPERVISOR_OBRAS'});
    return json(body,status);
  }});
  await client.login({email:'s@example.test',password:'test-only'});
  const post = path => client.request(`/api/obras/1/${path}/`,{method:'POST',body:{}});
  status=400; body={materiales:['MAT-1: material inactivo. Solicite a Bodega regularizar el catálogo.']};
  await assert.rejects(post('iniciar'), e=>e.fieldErrors.materiales?.[0]===body.materiales[0]);
  await assert.rejects(post('suspender'), e=>!e.fieldErrors.materiales);
  body={materiales:['<script>contenido</script>','Bearer privado']};
  await assert.rejects(post('iniciar'), e=>!e.fieldErrors.materiales);
  status=409;
  for (const code of ['devolucion_pendiente','confirmacion_remanente_requerida','version_costos_obsoleta']) {
    body={code,detail:'password confidencial'};
    await assert.rejects(post('finalizar'), e=>e.code===code&&!e.fieldErrors.detail);
    await assert.rejects(post('suspender'), e=>e.code===null);
  }
  await assert.rejects(post('costos/validar'), e=>e.code==='version_costos_obsoleta');
});
