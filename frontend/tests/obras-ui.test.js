import test, { before, after } from 'node:test';
import assert from 'node:assert/strict';
import React from 'react';
import Renderer, { act } from 'react-test-renderer';
import { createServer } from 'vite';
import { ApiError } from '../src/auth/client.js';
import { AF, G, S, T } from '../src/obras/domain.js';
import { obrasBackend } from './helpers/obras-backend.js';
let server, AuthProvider, AppProvider, App, Obras;
before(async () => {
  server = await createServer({ configFile: false, esbuild: { jsx: 'automatic' }, server: { middlewareMode: true, ws: false, hmr: false }, appType: 'custom', optimizeDeps: { noDiscovery: true, include: [] } });
  ({ AuthProvider } = await server.ssrLoadModule('/src/auth/AuthContext.jsx'));
  ({ AppProvider } = await server.ssrLoadModule('/src/context/AppContext.jsx'));
  ({ default: App } = await server.ssrLoadModule('/src/app.jsx'));
  ({ default: Obras } = await server.ssrLoadModule('/src/pages/Obras.jsx'));
  globalThis.window = { confirm: () => true };
});
after(async () => { delete globalThis.window; await server.close(); });
const flush = () => new Promise((resolve) => setImmediate(resolve));
const text = (node) => typeof node === 'string' ? node : (node.children || []).map(text).join('');
async function mount(backend, role = backend.role) {
  const session = { status: 'authenticated', user: { id: role === T ? 8 : 2, username: 'Cuenta real', email: 'test@example.test', role } };
  const client = { getSnapshot: () => session, subscribe: () => () => {}, restore: async () => {}, request: backend.request };
  let renderer;
  await act(async () => { renderer = Renderer.create(React.createElement(AuthProvider, { client }, React.createElement(Obras))); await flush(); });
  return renderer;
}
const buttons = (renderer, label) => renderer.root.findAllByType('button').filter((b) => text(b) === label || b.props['aria-label'] === label);
async function click(renderer, label, index = 0) {
  const button = buttons(renderer, label)[index]; assert.ok(button, `Falta ${label}`); assert.ok(!button.props.disabled, `${label} deshabilitado`);
  await act(async () => { await button.props.onClick({ preventDefault() {} }); await flush(); });
}
async function input(renderer, name, value) { await act(async () => renderer.root.findByProps({ id: `obras-${name}` }).props.onChange({ target: { value } })); }
async function submit(renderer) { await act(async () => { await renderer.root.findByType('form').props.onSubmit({ preventDefault() {} }); await flush(); }); }
async function unmount(renderer) { await act(async () => renderer.unmount()); }

for (const role of [G, S, AF, T]) test(`Obras ${role}: rutas autorizadas y proyección sin importes`, async () => {
  const b = obrasBackend(role);
  if (role === AF) {
    const request = b.request;
    b.request = async (...args) => { const result = await request(...args); if (result.results) result.results.forEach((row) => Object.assign(row, { descripcion: 'NO EXPONER', creado_por: 999, costo_total: '999999.99' })); else Object.assign(result, { descripcion: 'NO EXPONER', creado_por: 999, costo_total: '999999.99' }); return result; };
  }
  const renderer = await mount(b);
  try {
    assert.equal(b.calls[0].path, role === T ? '/api/obras/mis-obras/?page=1' : '/api/obras/?page=1');
    assert.equal(buttons(renderer, 'Nueva obra').length, role === S ? 1 : 0);
    assert.equal(buttons(renderer, 'Categorías de servicio').length, [G, S].includes(role) ? 1 : 0);
    await click(renderer, 'Ver obra');
    assert.ok(b.calls.some((c) => c.path === '/api/obras/1/'));
    assert.doesNotMatch(text(renderer.root), /999999|NO EXPONER|Usuario #999/);
    assert.equal(text(renderer.root).includes('Descripción operativa privada'), role !== AF);
    assert.equal(buttons(renderer, 'Editar obra').length, role === S ? 1 : 0);
    assert.equal(buttons(renderer, 'Técnicos').length, [G, S].includes(role) ? 1 : 0);
    assert.equal(buttons(renderer, 'Historial').length, [G, S].includes(role) ? 1 : 0);
    if (role === AF || role === T) assert.ok(b.calls.every((c) => !/participantes|historial|categorias-servicio|disponibles/.test(c.path)));
    if (role === T) { assert.doesNotMatch(text(renderer.root), /Costos|Materiales y gastos/); assert.equal(b.obras[0].tecnico_responsable, 7); } // Miembro adicional, no filtrar por principal.
  } finally { await unmount(renderer); }
});
test('filtros reales y paginación de Obras conservan estado/página al actualizar', async () => {
  const b = obrasBackend(); b.obras = Array.from({ length: 26 }, (_, i) => ({ ...b.obras[0], id: i + 1, codigo: `OB-${i + 1}` }));
  const renderer = await mount(b);
  try {
    await click(renderer, 'Filtros');
    for (const [key, value] of Object.entries({ estado: 'PLANIFICADA', cliente: '4', tecnico_responsable: '7', categoria_servicio: '1', fecha_programada_desde: '2026-11-01', fecha_programada_hasta: '2026-11-30', ordering: '-fecha_programada' })) await input(renderer, key, value);
    await submit(renderer);
    const url = new URL(b.calls.at(-1).path, 'http://localhost');
    assert.equal(url.searchParams.get('estado'), 'PLANIFICADA'); assert.equal(url.searchParams.get('ordering'), '-fecha_programada'); assert.equal(url.searchParams.get('page'), '1');
    assert.equal(url.searchParams.getAll('cliente').length, 1); assert.equal(url.searchParams.get('fecha_programada_desde'), '2026-11-01');
    const pager = renderer.root.findByProps({ 'aria-label': 'Paginación de obras' }); assert.match(text(pager), /26 registros/);
    await click(renderer, 'Siguiente'); assert.match(b.calls.at(-1).path, /page=2/);
    const before = b.calls.at(-1).path; await click(renderer, 'Actualizar datos'); assert.equal(b.calls.at(-1).path, before);
    assert.equal(renderer.root.findByProps({ id: 'obras-estado' }).props.value, 'PLANIFICADA');
    await click(renderer, 'Anterior'); assert.match(b.calls.at(-1).path, /page=1/);
    await click(renderer, 'Limpiar filtros'); assert.equal(b.calls.at(-1).path, '/api/obras/?page=1');
    await input(renderer, 'cliente', '0'); const count = b.calls.length; await submit(renderer); assert.equal(b.calls.length, count); assert.match(text(renderer.root), /ID positivo/);
  } finally { await unmount(renderer); }
});
test('S crea desde presupuesto elegible y categoría activa con ID real y motivo de asignación', async () => {
  const b = obrasBackend(), renderer = await mount(b);
  try {
    await click(renderer, 'Nueva obra');
    assert.ok(b.calls.some((c) => c.path === '/api/obras/presupuestos-disponibles/?page=1'));
    assert.ok(b.calls.some((c) => c.path === '/api/obras/tecnicos-disponibles/?page=1'));
    assert.ok(b.calls.some((c) => c.path === '/api/categorias-servicio/?page=1&activo=true'));
    assert.equal(renderer.root.findByProps({ id: 'obras-categoria_servicio' }).findAllByType('option').some((o) => o.props.value === '1'), false);
    assert.equal(renderer.root.findByProps({ id: 'obras-descripcion' }).props.value, '');
    await input(renderer, 'presupuesto', '20'); await input(renderer, 'categoria_servicio', '2'); await input(renderer, 'tecnico_responsable', '8'); await input(renderer, 'descripcion', 'Trabajo operativo nuevo'); await input(renderer, 'fecha_programada', '2026-12-01');
    await submit(renderer); assert.equal(b.calls.filter((c) => c.method === 'POST').length, 0); assert.match(text(renderer.root), /Campo obligatorio/);
    await input(renderer, 'motivo', 'Asignación inicial'); await submit(renderer);
    assert.deepEqual(b.calls.find((c) => c.method === 'POST').body, { presupuesto: 20, categoria_servicio: 2, tecnico_responsable: 8, descripcion: 'Trabajo operativo nuevo', fecha_programada: '2026-12-01', motivo: 'Asignación inicial' });
    assert.match(text(renderer.root), /Trabajo operativo nuevo/); assert.equal(b.obras.length, 2);
    assert.ok(b.calls.filter((c) => c.path === '/api/obras/2/').length >= 2);
    assert.ok(b.calls.every((c) => !c.path.startsWith('/api/presupuestos/') && !c.path.startsWith('/api/clientes/')));
  } finally { await unmount(renderer); }
});
test('S edita sin reenviar categoría histórica inactiva, presupuesto ni responsable', async () => {
  const b = obrasBackend(), renderer = await mount(b);
  try {
    await click(renderer, 'Ver obra'); await click(renderer, 'Editar obra');
    assert.equal(renderer.root.findAllByProps({ id: 'obras-presupuesto' }).length, 0);
    assert.equal(renderer.root.findAllByProps({ id: 'obras-tecnico_responsable' }).length, 0);
    await input(renderer, 'descripcion', 'Nueva descripción operativa'); await input(renderer, 'fecha_programada', ''); await input(renderer, 'motivo', 'Corrección'); await submit(renderer);
    assert.deepEqual(b.calls.find((c) => c.method === 'PATCH').body, { descripcion: 'Nueva descripción operativa', fecha_programada: null, motivo: 'Corrección' });
    assert.match(text(renderer.root), /Nueva descripción operativa/);
  } finally { await unmount(renderer); }
});
test('S cambia responsable por acción dedicada, inicia, suspende y reanuda con historial remoto', async () => {
  const b = obrasBackend(), renderer = await mount(b);
  try {
    await click(renderer, 'Ver obra'); await click(renderer, 'Cambiar responsable'); await input(renderer, 'tecnico_responsable', '8'); await input(renderer, 'motivo', 'Relevo'); await submit(renderer);
    const change = b.calls.find((c) => c.method === 'POST'); assert.equal(change.path, '/api/obras/1/cambiar-tecnico/'); assert.deepEqual(change.body, { tecnico_responsable: 8, motivo: 'Relevo' });
    for (const [label, expected] of [['Iniciar obra', 'EN_PROCESO'], ['Suspender obra', 'SUSPENDIDA'], ['Reanudar obra', 'EN_PROCESO']]) {
      await click(renderer, label); await input(renderer, 'motivo', label); await submit(renderer); assert.equal(b.obras[0].estado, expected);
    }
    assert.equal(b.obras[0].iniciado_en, '2026-11-08T12:00:00Z');
    assert.equal(buttons(renderer, 'Finalizar obra').length, 0); assert.equal(buttons(renderer, 'Cancelar obra').length, 0);
    await click(renderer, 'Historial'); assert.match(text(renderer.root), /CAMBIO ESTADO/); assert.match(text(renderer.root), /Usuario #2/);
    assert.ok(b.calls.some((c) => c.path === '/api/obras/1/participantes/historial/?page=1'));
  } finally { await unmount(renderer); }
});
test('participantes: PK de miembro independiente, reactivación, baja y principal protegido', async () => {
  const b = obrasBackend(), renderer = await mount(b);
  try {
    await click(renderer, 'Ver obra'); await click(renderer, 'Técnicos');
    assert.match(text(renderer.root), /Miembro #101/); assert.match(text(renderer.root), /Técnico #8/); assert.match(text(renderer.root), /MIGRACION_004B/);
    assert.equal(buttons(renderer, 'Desasignar').length, 0);
    await click(renderer, 'Reactivar'); await input(renderer, 'motivo', 'Retomar apoyo'); await submit(renderer);
    assert.equal(b.members[1].id, 102); assert.ok(b.members[1].activo);
    assert.deepEqual(b.calls.find((c) => c.method === 'POST').body, { tecnico: 8, motivo: 'Retomar apoyo' });
    await click(renderer, 'Desasignar'); await input(renderer, 'motivo', 'Otra tarea'); await submit(renderer);
    assert.equal(b.calls.filter((c) => c.method === 'POST').at(-1).path, '/api/obras/1/participantes/102/desasignar/');
    assert.equal(b.members[1].activo, false); assert.match(text(renderer.root), /Histórico \/ inactivo/);
    await input(renderer, 'miembros_activo', 'true'); assert.ok(b.calls.some((c) => c.path === '/api/obras/1/participantes/?page=1&activo=true'));
  } finally { await unmount(renderer); }
});
test('catálogo G: alta, renombre, activación/desactivación con motivo e historial', async () => {
  const b = obrasBackend(G), renderer = await mount(b);
  try {
    await click(renderer, 'Categorías de servicio'); await click(renderer, 'Nueva categoría'); await input(renderer, 'nombre', 'Servicio nuevo'); await submit(renderer);
    assert.deepEqual(b.calls.find((c) => c.method === 'POST').body, { nombre: 'Servicio nuevo' });
    await click(renderer, 'Renombrar categoría'); await input(renderer, 'nombre', 'Nombre preciso'); await submit(renderer);
    assert.equal(b.calls.filter((c) => c.method === 'PATCH').length, 0);
    await input(renderer, 'motivo', 'Corregir etiqueta'); await submit(renderer);
    assert.deepEqual(b.calls.find((c) => c.method === 'PATCH').body, { nombre: 'Nombre preciso', motivo: 'Corregir etiqueta' });
    await click(renderer, 'Desactivar categoría'); await input(renderer, 'motivo', 'Retirar oferta'); await submit(renderer);
    assert.equal(b.categories.at(-1).activo, false);
    await click(renderer, 'Activar categoría'); await input(renderer, 'motivo', 'Nueva oferta'); await submit(renderer); assert.ok(b.categories.at(-1).activo);
    assert.match(text(renderer.root), /Corregir etiqueta/); assert.match(text(renderer.root), /Historial de categoría/);
    await click(renderer, 'Volver a categorías'); await input(renderer, 'categorias_activo', 'false'); assert.equal(b.calls.at(-1).path, '/api/categorias-servicio/?page=1&activo=false');
  } finally { await unmount(renderer); }
});
test('S consulta categorías sin escrituras ni historial de catálogo; G lee participantes sin operar', async () => {
  for (const role of [G, S]) {
    const b = obrasBackend(role), renderer = await mount(b);
    try {
      if (role === S) {
        await click(renderer, 'Categorías de servicio'); assert.equal(buttons(renderer, 'Nueva categoría').length, 0); await click(renderer, 'Ver categoría');
        assert.equal(buttons(renderer, 'Renombrar categoría').length, 0); assert.ok(b.calls.every((c) => !c.path.includes('/historial/')));
      } else {
        await click(renderer, 'Ver obra'); await click(renderer, 'Técnicos');
        assert.equal(buttons(renderer, 'Asignar participante').length, 0); assert.equal(buttons(renderer, 'Reactivar').length, 0);
        await click(renderer, 'Historial'); assert.ok(b.calls.some((c) => c.path.includes('/participantes/historial/')));
      }
    } finally { await unmount(renderer); }
  }
});
async function nextIn(renderer, label) {
  await act(async () => { const nav = renderer.root.findByProps({ 'aria-label': label }); const next = nav.findAllByType('button').find((b) => text(b) === 'Siguiente'); assert.ok(!next.props.disabled); next.props.onClick(); await flush(); });
}
test('selecciones de presupuestos/técnicos/categorías respetan páginas y conservan IDs elegidos', async () => {
  const b = obrasBackend();
  b.budgets = Array.from({ length: 26 }, (_, i) => ({ ...b.budgets[0], id: 20 + i, codigo: `PRE-${20 + i}` }));
  b.technicians = Array.from({ length: 26 }, (_, i) => ({ id: 7 + i, nombre: `Técnico ${7 + i}` }));
  b.categories = Array.from({ length: 26 }, (_, i) => ({ id: 2 + i, nombre: `Categoría ${2 + i}`, activo: true }));
  const renderer = await mount(b);
  try {
    await click(renderer, 'Nueva obra');
    await nextIn(renderer, 'Páginas de presupuesto disponible'); await input(renderer, 'presupuesto', '45');
    await nextIn(renderer, 'Páginas de técnico responsable (opcional)'); await input(renderer, 'tecnico_responsable', '32');
    await nextIn(renderer, 'Páginas de categoría de servicio'); await input(renderer, 'categoria_servicio', '27');
    assert.ok(b.calls.some((c) => c.path === '/api/obras/presupuestos-disponibles/?page=2'));
    assert.ok(b.calls.some((c) => c.path === '/api/obras/tecnicos-disponibles/?page=2'));
    assert.ok(b.calls.some((c) => c.path === '/api/categorias-servicio/?page=2&activo=true'));
    await input(renderer, 'descripcion', 'Operación paginada'); await input(renderer, 'motivo', 'Asignación'); await submit(renderer);
    const body = b.calls.find((c) => c.method === 'POST').body;
    assert.equal(body.presupuesto, 45); assert.equal(body.tecnico_responsable, 32); assert.equal(body.categoria_servicio, 27);
  } finally { await unmount(renderer); }
});
test('participantes, historial operativo e historial de membresías tienen paginaciones independientes', async () => {
  const b = obrasBackend(G);
  b.members.push(...Array.from({ length: 24 }, (_, i) => ({ ...b.members[1], id: 103 + i, tecnico: 30 + i })));
  b.events = Array.from({ length: 26 }, (_, i) => ({ ...b.events[0], id: i + 1 }));
  b.memberEvents = Array.from({ length: 26 }, (_, i) => ({ id: i + 1, participante: 102, tipo: 'ASIGNACION', registrado_por: 2, motivo: 'Apoyo', datos_anteriores: {}, datos_nuevos: { activo: true }, creado_en: '2026-11-08T12:00:00Z' }));
  const renderer = await mount(b);
  try {
    await click(renderer, 'Ver obra'); await click(renderer, 'Técnicos'); await nextIn(renderer, 'Paginación de participantes');
    assert.ok(b.calls.some((c) => c.path === '/api/obras/1/participantes/?page=2'));
    await click(renderer, 'Historial'); await nextIn(renderer, 'Paginación del historial operativo'); await nextIn(renderer, 'Paginación del historial de participantes');
    assert.ok(b.calls.some((c) => c.path === '/api/obras/1/historial/?page=2'));
    assert.ok(b.calls.some((c) => c.path === '/api/obras/1/participantes/historial/?page=2'));
  } finally { await unmount(renderer); }
});
test('catálogo e historial de categoría paginados; filtro activo es del servidor', async () => {
  const b = obrasBackend(G);
  b.categories.push(...Array.from({ length: 24 }, (_, i) => ({ id: 3 + i, nombre: `Servicio ${i}`, activo: true })));
  b.categoryEvents = Array.from({ length: 26 }, (_, i) => ({ id: i + 1, tipo: 'EDICION', registrado_por: 1, motivo: 'Ajuste', datos_anteriores: { nombre: 'Antes' }, datos_nuevos: { nombre: 'Después' }, creado_en: '2026-11-08T12:00:00Z' }));
  const renderer = await mount(b);
  try {
    await click(renderer, 'Categorías de servicio'); await nextIn(renderer, 'Paginación de categorías');
    assert.equal(b.calls.at(-1).path, '/api/categorias-servicio/?page=2');
    await input(renderer, 'categorias_activo', 'false'); assert.equal(b.calls.at(-1).path, '/api/categorias-servicio/?page=1&activo=false');
    await click(renderer, 'Ver categoría'); await nextIn(renderer, 'Paginación del historial de categoría');
    assert.ok(b.calls.some((c) => c.path === '/api/categorias-servicio/1/historial/?page=2'));
  } finally { await unmount(renderer); }
});
for (const status of [400, 403, 404, 409, 0, 500]) test(`alta Obra con error ${status}: conserva formulario, no simula éxito ni repite escritura`, async () => {
  const b = obrasBackend(), renderer = await mount(b);
  try {
    await click(renderer, 'Nueva obra'); await input(renderer, 'presupuesto', '20'); await input(renderer, 'categoria_servicio', '2'); await input(renderer, 'descripcion', 'Texto conservado');
    b.failure = new ApiError(status, `Error público ${status}`, null, { fieldErrors: status === 400 ? { presupuesto: ['Presupuesto inválido.'] } : {}, code: status === 409 ? 'presupuesto_utilizado' : null });
    await submit(renderer);
    assert.equal(renderer.root.findByProps({ id: 'obras-descripcion' }).props.value, 'Texto conservado');
    assert.match(text(renderer.root), new RegExp(`Error público ${status}`)); assert.equal(b.obras.length, 1);
    assert.equal(b.calls.filter((c) => c.method === 'POST').length, 1);
    if ([0, 409, 500].includes(status)) {
      assert.ok(buttons(renderer, 'Crear obra')[0].props.disabled);
      await click(renderer, 'Reconsultar opciones'); assert.equal(b.calls.filter((c) => c.method === 'POST').length, 1);
    }
    b.failure = null; await submit(renderer); assert.equal(b.obras.length, 2);
  } finally { await unmount(renderer); }
});
test('escritura confirmada con relectura fallida no aparenta sincronización ni permite reenvío ciego', async () => {
  const b = obrasBackend(), renderer = await mount(b);
  try {
    await click(renderer, 'Ver obra'); await click(renderer, 'Editar obra'); await input(renderer, 'descripcion', 'Cambio persistido'); await input(renderer, 'motivo', 'Corrección');
    b.readFailure = (path) => path.includes('/participantes/?'); await submit(renderer);
    assert.equal(b.obras[0].descripcion, 'Cambio persistido'); assert.match(text(renderer.root), /Falta confirmar el resultado/);
    assert.equal(renderer.root.findByProps({ id: 'obras-descripcion' }).props.value, 'Cambio persistido');
    assert.ok(buttons(renderer, 'Guardar cambios')[0].props.disabled);
    b.readFailure = null; await click(renderer, 'Actualizar datos'); await click(renderer, 'Cancelar');
    assert.equal(b.calls.filter((c) => c.method === 'PATCH').length, 1); assert.match(text(renderer.root), /Cambio persistido/);
  } finally { await unmount(renderer); }
});
test('T pierde acceso al revocarse membresía: 404 no conserva ficha anterior', async () => {
  const b = obrasBackend(T), renderer = await mount(b);
  try {
    await click(renderer, 'Ver obra'); assert.match(text(renderer.root), /Descripción operativa privada/);
    b.allowed.clear(); await click(renderer, 'Actualizar datos');
    assert.doesNotMatch(text(renderer.root), /Descripción operativa privada/); assert.match(text(renderer.root), /Recurso no disponible/);
    await click(renderer, 'Volver al listado'); assert.match(text(renderer.root), /No hay obras/);
  } finally { await unmount(renderer); }
});
test('historial tardío de otra Obra queda abortado y no se mezcla al navegar', async () => {
  const b = obrasBackend(G); b.obras.push({ ...b.obras[0], id: 2, codigo: 'OB-000002', descripcion: 'Segunda obra' });
  let release, signal;
  const gate = new Promise((resolve) => { release = resolve; }), request = b.request;
  b.request = async (path, options) => {
    if (path === '/api/obras/1/historial/?page=1') { signal = options.signal; await gate; }
    return request(path, options);
  };
  const renderer = await mount(b);
  try {
    await click(renderer, 'Ver obra'); await click(renderer, 'Historial');
    await click(renderer, 'Volver al listado'); assert.ok(signal.aborted);
    await click(renderer, 'Ver obra', 1); release(); await act(async () => { await flush(); });
    assert.match(text(renderer.root), /Segunda obra/); assert.doesNotMatch(text(renderer.root), /Descripción operativa privada/);
  } finally { release(); await unmount(renderer); }
});
test('logout durante escritura aborta el scope y descarta una respuesta tardía de Obras', async () => {
  const b = obrasBackend(), listeners = new Set();
  let session = { status: 'authenticated', user: { id: 2, username: 'Supervisor', role: S } }, release, signal;
  const gate = new Promise((resolve) => { release = resolve; });
  const request = async (path, options) => {
    if (options?.method === 'POST') { signal = options.signal; await gate; return { ...b.obras[0], descripcion: 'Respuesta de sesión cerrada' }; }
    return b.request(path, options);
  };
  const client = { getSnapshot: () => session, subscribe: (fn) => { listeners.add(fn); return () => listeners.delete(fn); }, restore: async () => {}, request };
  let renderer;
  await act(async () => { renderer = Renderer.create(React.createElement(AuthProvider, { client }, React.createElement(AppProvider, null, React.createElement(App)))); await flush(); });
  try {
    await click(renderer, 'Ver obra'); await click(renderer, 'Cambiar responsable'); await input(renderer, 'tecnico_responsable', '8'); await input(renderer, 'motivo', 'Relevo');
    let pending;
    await act(async () => { pending = renderer.root.findByType('form').props.onSubmit({ preventDefault() {} }); await flush(); });
    await act(async () => { session = { status: 'anonymous', user: null }; listeners.forEach((fn) => fn()); await flush(); });
    assert.ok(signal.aborted); assert.match(text(renderer.root), /Correo electrónico/);
    await act(async () => { release(); await pending; await flush(); });
    assert.doesNotMatch(text(renderer.root), /Respuesta de sesión cerrada|Descripción operativa privada|Cambiar responsable/);
  } finally { release(); await unmount(renderer); }
});
test('doble alta de Obra comparte el bloqueo de escritura y no duplica el POST', async () => {
  const b = obrasBackend(); let release, attempts = 0;
  const gate = new Promise((resolve) => { release = resolve; }), request = b.request;
  b.request = async (path, options) => { if (options?.method === 'POST') { attempts++; await gate; } return request(path, options); };
  const renderer = await mount(b);
  try {
    await click(renderer, 'Nueva obra'); await input(renderer, 'presupuesto', '20'); await input(renderer, 'categoria_servicio', '2'); await input(renderer, 'descripcion', 'Obra única');
    let first, second;
    await act(async () => { const handler = renderer.root.findByType('form').props.onSubmit; first = handler({ preventDefault() {} }); second = handler({ preventDefault() {} }); await flush(); });
    assert.equal(attempts, 1); assert.match(text(renderer.root), /Guardando…/);
    await act(async () => { release(); await Promise.all([first, second]); await flush(); });
    assert.equal(b.obras.length, 2); assert.equal(b.calls.filter((c) => c.method === 'POST').length, 1);
  } finally { release(); await unmount(renderer); }
});
test('responsable null solo en PLANIFICADA; Obras terminales no habilitan mutaciones', async () => {
  const b = obrasBackend(); b.obras[0].estado = 'EN_PROCESO';
  let renderer = await mount(b);
  try {
    await click(renderer, 'Ver obra'); await click(renderer, 'Cambiar responsable'); await input(renderer, 'motivo', 'Reasignar'); await submit(renderer);
    assert.equal(b.calls.filter((c) => c.method === 'POST').length, 0); assert.match(text(renderer.root), /técnico elegible/);
    await input(renderer, 'tecnico_responsable', '8'); await submit(renderer); assert.equal(b.obras[0].tecnico_responsable, 8);
  } finally { await unmount(renderer); }
  for (const state of ['FINALIZADA', 'CANCELADA']) {
    b.obras[0].estado = state; renderer = await mount(b);
    try {
      await click(renderer, 'Ver obra');
      for (const label of ['Editar obra', 'Cambiar responsable', 'Iniciar obra', 'Suspender obra', 'Reanudar obra', 'Finalizar obra', 'Cancelar obra']) assert.equal(buttons(renderer, label).length, 0);
      await click(renderer, 'Técnicos'); assert.equal(buttons(renderer, 'Asignar participante').length, 0); assert.equal(buttons(renderer, 'Desasignar').length, 0);
    } finally { await unmount(renderer); }
  }
});
test('reconsulta tras conflicto de participante respeta el principal actual sin repetir escritura', async () => {
  const b = obrasBackend(), renderer = await mount(b);
  try {
    await click(renderer, 'Ver obra'); await click(renderer, 'Técnicos'); await click(renderer, 'Reactivar'); await input(renderer, 'motivo', 'Apoyo');
    b.failure = new ApiError(409, 'La membresía cambió.'); await submit(renderer);
    b.obras[0].tecnico_responsable = 8; b.members[1].es_responsable = true; b.members[1].activo = true;
    const count = b.calls.filter((c) => c.method === 'POST').length;
    await click(renderer, 'Actualizar datos'); assert.equal(b.calls.filter((c) => c.method === 'POST').length, count);
    assert.ok(buttons(renderer, 'Guardar cambios')[0].props.disabled); assert.match(text(renderer.root), /ya no permiten esta acción/);
  } finally { await unmount(renderer); }
});
