import test from 'node:test';
import assert from 'node:assert/strict';
import { AF, G, actionsFor, canRead, clientPayload, emptyClient, emptyItem, itemPayload, money, needsReason, validDecimal, validRut, validateClient, validateItem } from '../src/comercial/domain.js';
import { budgetPath, clientPath, itemPath, pagePath, validatePage } from '../src/comercial/api.js';
import { createScope } from '../src/comercial/scope.js';
import { ApiError } from '../src/auth/client.js';
import { isCatalogUnit, OTHER_UNIT, UNIT_GROUPS } from '../src/comercial/units.js';

test('RUT módulo 11: formato común, K, DV inválido, nulo y cero', () => {
  assert.ok(validRut('12.345.678-5'));
  assert.ok(validRut('6-k'));
  for (const rut of ['12.345.678-9', '0-0', '', null, 'texto']) assert.equal(validRut(rut), false);
});
test('Cliente exige contacto y valida documento extranjero', () => {
  const form = { ...emptyClient, nombre_legal: 'Cliente', tipo_identificacion: 'DOCUMENTO_EXTRANJERO' };
  const errors = validateClient(form);
  for (const key of ['correo', 'numero_identificacion', 'pais_identificacion', 'tipo_documento_extranjero']) assert.ok(errors[key]);
  assert.deepEqual(validateClient({ ...form, telefono: '123', numero_identificacion: 'ABC', pais_identificacion: 'ar', tipo_documento_extranjero: 'Pasaporte' }), {});
});
test('SIN_IDENTIFICACION crea y transiciona con tres null explícitos; no manda activo ni ciudad', () => {
  const original = { ...emptyClient, nombre_legal: 'Cliente', correo: 'a@b.cl', numero_identificacion: '12345678-5', pais_identificacion: null, tipo_documento_extranjero: null };
  const form = { ...original, tipo_identificacion: 'SIN_IDENTIFICACION', activo: false, ciudad: 'no enviar' };
  const patch = clientPayload(form, original);
  assert.deepEqual(patch, { tipo_identificacion: 'SIN_IDENTIFICACION', numero_identificacion: null, pais_identificacion: null, tipo_documento_extranjero: null });
  const created = clientPayload(form);
  assert.equal(created.numero_identificacion, null);
  assert.equal(created.activo, undefined); assert.equal(created.ciudad, undefined);
});
test('PATCH cliente solo envía cambios, permite edición del inactivo', () => {
  const original = { ...emptyClient, tipo_identificacion: 'SIN_IDENTIFICACION', numero_identificacion: null, pais_identificacion: null, tipo_documento_extranjero: null, activo: false };
  assert.deepEqual(clientPayload({ ...original, nombre_legal: 'Nuevo' }, original), { nombre_legal: 'Nuevo' });
});
test('decimales exactos: escala, positivos, grandes y rechazo de floats/notación científica', () => {
  assert.ok(validDecimal('999999999.999', 9, 3, true));
  assert.ok(validDecimal('9999999999999.99', 13, 2));
  assert.ok(validDecimal('0.00', 13, 2));
  for (const value of ['0', '0.000', '1.0001', '1e3', '-1', '1,25', 1.5]) assert.equal(validDecimal(value, 9, 3, true), false);
  assert.equal(money('9999999999999999999999.99'), '$9.999.999.999.999.999.999.999,99 CLP');
});
test('ítems: payload estricto strings e int y PATCH sin campos calculados', () => {
  const original = { id: 4, descripcion: 'Línea', cantidad: '0.001', unidad: 'kg', precio_unitario: '9999999999999.99', orden: 1, subtotal: '10.00' };
  assert.deepEqual(validateItem(original), {});
  assert.deepEqual(itemPayload({ ...original, orden: '2' }, original), { orden: 2 });
  const created = itemPayload(original);
  assert.equal(typeof created.cantidad, 'string'); assert.equal(typeof created.precio_unitario, 'string'); assert.equal(typeof created.orden, 'number'); assert.equal(created.subtotal, undefined);
  assert.ok(validateItem({ ...original, orden: '2147483648' }).orden);
});
test('catálogo reutilizable de unidades: nombres, abreviaturas y valores únicos de hasta 30 caracteres', () => {
  const units = UNIT_GROUPS.flatMap((group) => group.options);
  assert.equal(new Set(units.map(([unit]) => unit)).size, units.length);
  for (const [unit, label] of units) {
    assert.ok(unit.length > 0 && unit.length <= 30);
    assert.ok(label.includes(`(${unit})`));
    assert.ok(isCatalogUnit(unit)); assert.notEqual(unit, OTHER_UNIT);
  }
  for (const unit of ['u', 'kg', 'm', 'm²', 'm³', 'L', 'h', 'punto', 'servicio']) assert.ok(isCatalogUnit(unit));
  assert.equal(isCatalogUnit('Unidad histórica'), false);
});
test('unidad obligatoria y máximo 30 caracteres; payload solo contiene el string recortado', () => {
  const form = { descripcion: 'Servicio', cantidad: '1', precio_unitario: '10', orden: '1', unidad: '' };
  for (const unidad of ['', '   ', 'x'.repeat(31)]) assert.ok(validateItem({ ...form, unidad }).unidad);
  for (const unidad of ['kg', 'Unidad histórica', 'x'.repeat(30)]) {
    assert.deepEqual(validateItem({ ...form, unidad }), {});
    assert.equal(itemPayload({ ...form, unidad: ` ${unidad} ` }).unidad, unidad);
  }
});
test('orden nuevo vacío: solo acepta un entero positivo explícito dentro del límite Django', () => {
  assert.equal(emptyItem.orden, '');
  const form = { ...emptyItem, descripcion: 'Línea', unidad: 'u', cantidad: '1', precio_unitario: '1' };
  for (const orden of ['', '0', '-1', '1.5', '2147483648']) assert.ok(validateItem({ ...form, orden }).orden);
  assert.equal(validateItem({ ...form, orden: '2147483647' }).orden, undefined);
});
test('roles G/AF/S/T, sin saltos de Gerencia ni excepción monetaria', () => {
  for (const role of ['TECNICO', 'SUPERVISOR_OBRAS']) { assert.equal(canRead(role), false); assert.deepEqual(actionsFor(role, 'BORRADOR'), []); }
  assert.ok(canRead(AF)); assert.ok(canRead(G));
  assert.deepEqual(actionsFor(AF, 'BORRADOR'), ['enviar-gerencia', 'anular']);
  assert.deepEqual(actionsFor(G, 'PENDIENTE_GERENCIA'), ['aprobar-gerencia', 'rechazar-gerencia']);
  assert.deepEqual(actionsFor(AF, 'PENDIENTE_GERENCIA'), ['anular']);
  assert.deepEqual(actionsFor(AF, 'RECHAZADO_GERENCIA'), ['crear-revision']);
  assert.deepEqual(actionsFor(AF, 'RECHAZADO_CLIENTE'), ['crear-revision']);
  assert.deepEqual(actionsFor(AF, 'ANULADO'), ['crear-revision']);
  assert.equal(actionsFor(AF, 'APROBADO_CLIENTE').includes('crear-revision'), false);
  for (const action of ['anular', 'rechazar-gerencia', 'registrar-rechazo-cliente']) assert.ok(needsReason(action));
});
test('rutas numéricas y paginación segura de listado e historial', () => {
  assert.equal(clientPath(4), '/api/clientes/4/'); assert.equal(itemPath(2, 3), '/api/presupuestos/2/items/3/');
  assert.equal(pagePath(budgetPath(), 2), '/api/presupuestos/?page=2');
  for (const value of ['Cliente', '2', -1, 0, 9007199254740992]) assert.throws(() => clientPath(value));
  const data = { count: 26, results: [], next: 'http://localhost/api/presupuestos/?page=2', previous: null };
  assert.equal(validatePage(data, budgetPath()), data);
  assert.ok(validatePage({ ...data, next: null, previous: 'http://localhost/api/presupuestos/' }, budgetPath()));
  for (const next of ['https://evil.test/api/presupuestos/?page=2', '/api/usuarios/?page=2', '/api/presupuestos/?page=-1']) assert.throws(() => validatePage({ ...data, next }, budgetPath()));
  assert.ok(validatePage({ ...data, next: '/api/presupuestos/2/historial/?page=2' }, `${budgetPath(2)}historial/`));
});
const deferred = () => { let resolve; const promise = new Promise((r) => { resolve = r; }); return { promise, resolve }; };
test('lecturas fuera de orden y desmontaje descartan respuestas y cancelan signal', async () => {
  const scope = createScope(), a = deferred(), b = deferred(), values = [];
  const first = scope.read('detail', () => a.promise, (v) => values.push(v));
  const second = scope.read('detail', () => b.promise, (v) => values.push(v));
  b.resolve('nuevo'); await second; a.resolve('viejo'); await first;
  assert.deepEqual(values, ['nuevo']);
  let signal; const gate = deferred();
  const pending = scope.read('detail', (s) => { signal = s; return gate.promise; }, (v) => values.push(v));
  scope.dispose(); assert.ok(signal.aborted); gate.resolve('tardío'); await pending;
  assert.deepEqual(values, ['nuevo']);
});
test('escritura evita doble envío, no aplica tras dispose', async () => {
  const scope = createScope(), gate = deferred(); let calls = 0, applied = 0;
  const first = scope.write(() => { calls++; return gate.promise; }, () => applied++);
  assert.equal(await scope.write(() => { calls++; }, () => applied++), false);
  scope.dispose(); gate.resolve({}); await first;
  assert.equal(calls, 1); assert.equal(applied, 0);
});
for (const status of [0, 409, 500, 502]) test(`resultado ${status}: no reenvía hasta relectura explícita`, async () => {
  const scope = createScope(); let calls = 0;
  await assert.rejects(scope.write(() => { calls++; throw new ApiError(status, 'Error'); }, () => {}));
  assert.ok(scope.locked);
  assert.equal(await scope.write(() => { calls++; }, () => {}), false); assert.equal(calls, 1);
  scope.reconciled(); await scope.write(() => { calls++; return {}; }, () => {}); assert.equal(calls, 2);
});
for (const status of [400, 401, 403, 404, 405, 429]) test(`error ${status}: libera envío sin reintentar escritura`, async () => {
  const scope = createScope(); let calls = 0;
  await assert.rejects(scope.write(() => { calls++; throw new ApiError(status, 'Error'); }, () => {}));
  assert.equal(calls, 1); assert.equal(scope.locked, false);
});
test('timeout de escritura acota incluso una operación que ignora abort y descarta éxito tardío', async () => {
  const scope = createScope({ timeoutMs: 5 }), gate = deferred(); let applied = 0, calls = 0;
  await assert.rejects(scope.write(() => { calls++; return gate.promise; }, () => applied++), { status: 0 });
  assert.ok(scope.locked); gate.resolve({}); await Promise.resolve();
  assert.equal(applied, 0); assert.equal(calls, 1);
});
test('timeout de lectura ofrece recuperación sin bloquear escrituras como inciertas', async () => {
  const scope = createScope({ timeoutMs: 5 }), gate = deferred();
  await assert.rejects(scope.read('list', () => gate.promise, () => assert.fail('No aplicar resultado tardío')), { status: 0 });
  gate.resolve([]); await Promise.resolve(); assert.equal(scope.locked, false);
});
