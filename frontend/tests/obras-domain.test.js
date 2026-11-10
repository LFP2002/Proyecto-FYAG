import test from 'node:test';
import assert from 'node:assert/strict';
import { AF, canEditObra, canReadObras, canReadTeam, emptyObra, filterErrors, G, minimalFields, obraErrors, obraPayload, operationFor, projectObra, S, T, validDate } from '../src/obras/domain.js';
import { categoryPath, collectionPath, memberPath, obraPath, readPage } from '../src/obras/api.js';

test('Obras G/S/AF/T: capacidades y transiciones solo 005C-1', () => {
  for (const role of [G, S, AF, T]) {
    assert.ok(canReadObras(role)); assert.equal(canReadTeam(role), [G, S].includes(role));
    for (const state of ['PLANIFICADA', 'EN_PROCESO', 'SUSPENDIDA']) assert.equal(canEditObra(role, state), role === S);
    for (const state of ['FINALIZADA', 'CANCELADA']) { assert.equal(canEditObra(role, state), false); assert.equal(operationFor(role, { estado: state, tecnico_responsable: 7 }), null); }
  }
  assert.equal(canReadObras('supervisor'), false);
  assert.equal(operationFor(S, { estado: 'PLANIFICADA', tecnico_responsable: null }), null);
  assert.equal(operationFor(S, { estado: 'PLANIFICADA', tecnico_responsable: 7 }), 'iniciar');
  assert.equal(operationFor(S, { estado: 'EN_PROCESO' }), 'suspender');
  assert.equal(operationFor(S, { estado: 'SUSPENDIDA', tecnico_responsable: 7 }), 'reanudar');
});
test('filtros de servidor, IDs y fechas ISO sin parámetros vacíos, duplicados o inventados', () => {
  const url = new URL(collectionPath(obraPath(), 2, { estado: 'PLANIFICADA', cliente: '4', tecnico_responsable: '', fecha_programada_desde: '2026-11-08', ordering: '-creado_en' }), 'http://localhost');
  assert.equal(url.searchParams.get('cliente'), '4'); assert.equal(url.searchParams.get('page'), '2');
  assert.equal(url.searchParams.has('tecnico_responsable'), false); assert.equal(url.searchParams.getAll('page').length, 1);
  for (const filters of [{ rol: G }, { estado: 'CANCELAR' }, { cliente: '0' }, { ordering: 'monto_neto' }, { fecha_programada_desde: '2026-02-30' }]) assert.throws(() => collectionPath(obraPath(), 1, filters));
  assert.ok(filterErrors({ fecha_programada_desde: '2026-12-01', fecha_programada_hasta: '2026-11-01' }).fecha_programada_hasta);
  assert.ok(validDate('2028-02-29')); assert.equal(validDate('2026-02-29'), false); assert.equal(validDate('2026-11-08T12:00'), false);
  assert.equal(collectionPath('/api/obras/mis-obras/', 1, { estado: 'FINALIZADA' }), '/api/obras/mis-obras/?page=1&estado=FINALIZADA');
  assert.equal(collectionPath(categoryPath(), 1, { activo: 'false' }), '/api/categorias-servicio/?page=1&activo=false');
  assert.throws(() => collectionPath(categoryPath(), 1, { activo: 'True' }));
});
test('alta Obra usa solo campos permitidos, IDs JSON enteros, null explícito y descripción operativa propia', () => {
  const form = { ...emptyObra, presupuesto: '20', categoria_servicio: '2', descripcion: '  Operación nueva  ', estado: 'FINALIZADA', creado_por: 99, monto_neto: '100' };
  assert.deepEqual(obraErrors(form), {});
  assert.deepEqual(obraPayload(form), { presupuesto: 20, categoria_servicio: 2, descripcion: 'Operación nueva', tecnico_responsable: null, fecha_programada: null, motivo: '' });
  assert.ok(obraErrors({ ...form, tecnico_responsable: '7' }).motivo);
  assert.deepEqual(obraErrors({ ...form, tecnico_responsable: '7', motivo: 'Asignación' }), {});
});
test('PATCH acotado: no reenvía categoría histórica inactiva, ni presupuesto o responsable; fecha null', () => {
  const original = { presupuesto: 20, categoria_servicio: 1, tecnico_responsable: 7, descripcion: 'Anterior', fecha_programada: '2026-11-08' };
  const form = { ...emptyObra, ...original, categoria_servicio: '1', descripcion: 'Nueva', fecha_programada: '', motivo: 'Corrección' };
  assert.deepEqual(obraPayload(form, original), { descripcion: 'Nueva', fecha_programada: null, motivo: 'Corrección' });
  assert.ok(obraErrors({ ...form, motivo: '' }, original).motivo);
});
test('proyección AF exacta y ausencia de importes incluso ante campos adicionales inesperados', () => {
  const data = { ...Object.fromEntries(minimalFields.map((field) => [field, 1])), descripcion: 'Reservado', creado_por: 77, monto_neto: '999', costo_total: '777', secreto: 'oculto' };
  assert.deepEqual(Object.keys(projectObra(data, AF)).sort(), [...minimalFields].sort());
  for (const role of [G, S, T]) { assert.equal(projectObra(data, role).monto_neto, undefined); assert.equal(projectObra(data, role).descripcion, 'Reservado'); assert.equal(projectObra(data, role).secreto, undefined); }
});
test('rutas de miembro y Obra conservan PKs distintos; páginas DRF same-origin de 25', () => {
  assert.equal(memberPath(3, 102), '/api/obras/3/participantes/102/desasignar/');
  for (const id of ['3', 0, -1, 9007199254740992]) assert.throws(() => obraPath(id));
  const data = { count: 26, results: [], next: '/api/obras/?page=2&estado=PLANIFICADA', previous: null };
  assert.equal(readPage(data, obraPath()), data);
  assert.ok(readPage({ ...data, next: null, previous: '/api/obras/?estado=PLANIFICADA' }, obraPath()));
  assert.throws(() => readPage({ ...data, next: 'https://evil.test/api/obras/?page=2' }, obraPath()));
  assert.throws(() => readPage({ ...data, results: Array(26).fill({}) }, obraPath()));
});
