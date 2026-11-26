import test, { before, after } from 'node:test';
import assert from 'node:assert/strict';
import React from 'react';
import Renderer, { act } from 'react-test-renderer';
import { createServer } from 'vite';
import { ApiError } from '../src/auth/client.js';
import { AF, G, S, T } from '../src/obras/domain.js';
import { obrasBackend } from './helpers/obras-backend.js';
import {economicDifference} from '../src/obras/managerEconomy.js';
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
const buttons = (renderer, label) => renderer.root.findAllByType('button').filter((b) => text(b).trim() === label || b.props['aria-label'] === label);
async function click(renderer, label, index = 0) {
  const button = buttons(renderer, label)[index]; assert.ok(button, `Falta ${label}`); assert.ok(!button.props.disabled, `${label} deshabilitado`);
  await act(async () => { await button.props.onClick({ preventDefault() {} }); await flush(); });
}
async function input(renderer, name, value) { await act(async () => renderer.root.findByProps({ id: `obras-${name}` }).props.onChange({ target: { value } })); }
async function submit(renderer) { await act(async () => { await renderer.root.findByType('form').props.onSubmit({ preventDefault() {} }); await flush(); }); }
async function unmount(renderer) { await act(async () => renderer.unmount()); }

for (const role of [G, S, T]) test(`Obras ${role}: rutas autorizadas y proyección sin importes`, async () => {
  const b = obrasBackend(role);
  const renderer = await mount(b);
  try {
    assert.equal(b.calls[0].path, role === T ? '/api/obras/mis-obras/?page=1' : role===G?'/api/obras/supervision-gerencial/?page=1':'/api/obras/?page=1');
    assert.equal(buttons(renderer, 'Nueva obra').length, role === S ? 1 : 0);
    assert.equal(buttons(renderer, 'Categorías de servicio').length, role === S ? 1 : 0);
    await click(renderer, 'Ver obra');
    assert.ok(b.calls.some((c) => c.path === '/api/obras/1/'));
    assert.doesNotMatch(text(renderer.root), /999999|NO EXPONER|Usuario #999/);
    assert.equal(text(renderer.root).includes('Descripción operativa privada'), role !== AF);
    assert.equal(buttons(renderer, 'Editar obra').length, role === S ? 1 : 0);
    assert.equal(buttons(renderer, 'Equipo').length, role === S ? 1 : 0);
    assert.equal(buttons(renderer, 'Historial').length, role === S ? 1 : 0);
    if (role === AF || role === T) assert.ok(b.calls.every((c) => !/participantes|historial|categorias-servicio|disponibles/.test(c.path)));
    if (role === T) { assert.doesNotMatch(text(renderer.root), /Costos|Materiales y gastos/); assert.equal(b.obras[0].tecnico_responsable, 7); } // Miembro adicional, no filtrar por principal.
  } finally { await unmount(renderer); }
});
test('Obras Finanzas: resumen económico autorizado, búsqueda global y detalle sin datos privados', async()=>{
  const b=obrasBackend(AF),renderer=await mount(b);
  try{
    assert.equal(b.calls[0].path,'/api/finanzas/obras-resumen/?page=1');
    assert.match(text(renderer.root),/\$45\.300/);
    assert.match(text(renderer.root),/No habilitada/);
    const field=renderer.root.findByProps({placeholder:'Código, cliente o categoría'});
    await act(async()=>field.props.onChange({target:{value:'Cliente operativo'}}));
    await submit(renderer);
    assert.match(b.calls.at(-1).path,/buscar=Cliente\+operativo/);
    await click(renderer,'Ver obra');
    assert.ok(b.calls.some(c=>c.path==='/api/finanzas/obras-resumen/1/'));
    assert.ok(b.calls.some(c=>c.path==='/api/obras/1/costos/resumen/'));
    assert.match(text(renderer.root),/Importe provisional/);
    assert.match(text(renderer.root),/Pendiente de validación/);
    assert.doesNotMatch(text(renderer.root),/Descripción operativa privada|Editar obra|Turnos/);
    assert.ok(b.calls.every(c=>c.method==='GET'));
    await click(renderer,'Volver a obras');
    assert.match(b.calls.at(-1).path,/buscar=Cliente\+operativo/);
  }finally{await unmount(renderer);}
});
test('filtros reales y paginación de Obras conservan estado/página al actualizar', async () => {
  const b = obrasBackend(); b.obras = Array.from({ length: 26 }, (_, i) => ({ ...b.obras[0], id: i + 1, codigo: 'OB-'+(i+1) }));
  const renderer = await mount(b);
  try {
    await click(renderer,'Planificadas');
    await input(renderer,'buscar','Cliente operativo');
    await click(renderer,'Filtros');
    for (const [key,value] of Object.entries({fecha_programada_desde:'2026-11-01',fecha_programada_hasta:'2026-11-30',ordering:'-fecha_programada'})) await input(renderer,key,value);
    await submit(renderer);
    const url=new URL(b.calls.at(-1).path,'http://localhost');
    assert.equal(url.searchParams.get('estado'),'PLANIFICADA');assert.equal(url.searchParams.get('buscar'),'Cliente operativo');assert.equal(url.searchParams.get('ordering'),'-fecha_programada');assert.equal(url.searchParams.get('page'),'1');
    assert.match(text(renderer.root.findByProps({'aria-label':'Paginación de obras'})),/26 registros/);
    await click(renderer,'Siguiente');assert.match(b.calls.at(-1).path,/page=2/);
    const before=b.calls.at(-1).path;await click(renderer,'Actualizar datos');assert.equal(b.calls.at(-1).path,before);
    await click(renderer,'Anterior');await click(renderer,'Limpiar filtros');assert.equal(b.calls.at(-1).path,'/api/obras/?page=1&estado=PLANIFICADA');
    await click(renderer,'Todas');assert.equal(b.calls.at(-1).path,'/api/obras/?page=1');
    await click(renderer,'Filtros');await input(renderer,'fecha_programada_desde','2026-12-01');await input(renderer,'fecha_programada_hasta','2026-11-01');const count=b.calls.length;await submit(renderer);assert.equal(b.calls.length,count);assert.match(text(renderer.root),/Debe ser igual o posterior/);
  }finally{await unmount(renderer);}
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
    await click(renderer, 'Historial'); assert.match(text(renderer.root), /Cambio de estado/); assert.match(text(renderer.root), /Usuario #2/);
    assert.ok(b.calls.some((c) => c.path === '/api/obras/1/participantes/historial/?page=1'));
  } finally { await unmount(renderer); }
});
test('participantes: PK de miembro independiente, reactivación, baja y principal protegido', async () => {
  const b = obrasBackend(), renderer = await mount(b);
  try {
    await click(renderer, 'Ver obra'); await click(renderer, 'Equipo');
    assert.match(text(renderer.root), /Responsable principal/); assert.match(text(renderer.root), /Técnico adicional/); assert.match(text(renderer.root), /Registro histórico/);
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
test('catálogo S: alta, renombre, activación/desactivación con motivo e historial', async () => {
  const b = obrasBackend(S), renderer = await mount(b);
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
test('Gerencia tiene ficha propia, resume datos reales y carga información secundaria bajo demanda',async()=>{
  const b=obrasBackend(G),renderer=await mount(b);
  try{
    assert.equal(buttons(renderer,'Categorías de servicio').length,0);
    await click(renderer,'Ver obra');
    assert.match(text(renderer.root),/Presupuesto neto\$45\.300/);
    assert.match(text(renderer.root),/Técnicos activos1/);
    assert.ok(b.calls.some(c=>c.path==='/api/obras/1/participantes/?page=1&activo=true'));
    assert.ok(b.calls.every(c=>!c.path.includes('/historial/')&&!c.path.includes('/turnos/')));
    assert.equal(buttons(renderer,'Editar obra').length,0);
    await click(renderer,'Resumen económico');
    assert.match(text(renderer.root),/Costos pendientes de validación/);
    assert.match(text(renderer.root),/Composición de costos netos/);
    assert.match(text(renderer.root),/Desviación presupuestaria/);
    assert.equal(renderer.root.findAllByType('select').length,0);
    await click(renderer,'Actividad reciente');
    assert.match(text(renderer.root),/Obra creada/);
    await click(renderer,'Turnos');
    assert.match(text(renderer.root),/No hay turnos registrados/);
    assert.ok(b.calls.every(c=>c.method==='GET'));
    await click(renderer,'Volver al listado');
    assert.equal(buttons(renderer,'Ver obra').length,1);
  }finally{await unmount(renderer);}
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
  const b = obrasBackend(S);
  b.members.push(...Array.from({ length: 24 }, (_, i) => ({ ...b.members[1], id: 103 + i, tecnico: 30 + i })));
  b.events = Array.from({ length: 26 }, (_, i) => ({ ...b.events[0], id: i + 1 }));
  b.memberEvents = Array.from({ length: 26 }, (_, i) => ({ id: i + 1, participante: 102, tipo: 'ASIGNACION', registrado_por: 2, motivo: 'Apoyo', datos_anteriores: {}, datos_nuevos: { activo: true }, creado_en: '2026-11-08T12:00:00Z' }));
  const renderer = await mount(b);
  try {
    await click(renderer, 'Ver obra'); await click(renderer, 'Equipo'); await nextIn(renderer, 'Paginación de participantes');
    assert.ok(b.calls.some((c) => c.path === '/api/obras/1/participantes/?page=2'));
    await click(renderer, 'Historial'); await nextIn(renderer, 'Paginación del historial operativo'); await nextIn(renderer, 'Paginación del historial de participantes');
    assert.ok(b.calls.some((c) => c.path === '/api/obras/1/historial/?page=2'));
    assert.ok(b.calls.some((c) => c.path === '/api/obras/1/participantes/historial/?page=2'));
  } finally { await unmount(renderer); }
});
test('catálogo e historial de categoría paginados; filtro activo es del servidor', async () => {
  const b = obrasBackend(S);
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
test('T abre Mis turnos desde la Obra asignada y consulta su listado paginado', async () => {
  const b = obrasBackend(T); b.obras[0].estado = 'EN_PROCESO';
  const renderer = await mount(b, T);
  try {
    await click(renderer, 'Ver mis turnos');
    assert.match(text(renderer.root), /Mis turnos de esta obra/);
    assert.ok(b.calls.some((call) => call.path === '/api/obras/1/turnos/?page=1'));
    assert.equal(buttons(renderer, 'Iniciar turno').length, 1);
    assert.doesNotMatch(text(renderer.root), /pendiente de integración frontend en 005C-2/i);
  } finally { await unmount(renderer); }
});
test('T pierde acceso al revocarse membresía: 404 no conserva ficha anterior', async () => {
  const b = obrasBackend(T), renderer = await mount(b);
  try {
    await click(renderer, 'Ver obra'); assert.match(text(renderer.root), /Descripción operativa privada/);
    b.allowed.clear(); await click(renderer, 'Actualizar datos');
    assert.doesNotMatch(text(renderer.root), /Descripción operativa privada/); assert.match(text(renderer.root), /Recurso no disponible/);
    await click(renderer, 'Volver a mis obras'); assert.match(text(renderer.root), /No tienes obras asignadas/);
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
    await click(renderer, 'Ver obra'); await click(renderer, 'Actividad reciente');
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
      await click(renderer, 'Equipo'); assert.equal(buttons(renderer, 'Asignar participante').length, 0); assert.equal(buttons(renderer, 'Desasignar').length, 0);
    } finally { await unmount(renderer); }
  }
});
test('turnos: técnico inicia y cierra con multipart; revisión solo se ofrece a Supervisor', async () => {
  const b = obrasBackend(T); b.obras[0].estado = 'EN_PROCESO';
  const renderer = await mount(b, T);
  try {
    await click(renderer, 'Ver obra'); await click(renderer, 'Turnos');
    await click(renderer, 'Iniciar turno');
    assert.ok(b.calls.some((c) => c.path === '/api/obras/1/turnos/iniciar/' && c.method === 'POST' && Object.keys(c.body).length === 0));
    const turno = b.turnos[0]; assert.equal(turno.estado_revision, 'ABIERTO');
    await click(renderer, 'Cerrar mi turno'); await input(renderer, 'descripcion_trabajo', 'Reparación completada');
    await act(async () => {
      const file = new File(['png'], 'evidencia.png', { type: 'image/png' });
      renderer.root.findByProps({ id: 'turno-fotos' }).props.onChange({ target: { files: [file] } }); await flush();
    });
    await submit(renderer);
    const write = b.calls.find((c) => c.path === '/api/obras/1/turnos/1/finalizar/');
    assert.ok(write.body instanceof FormData); assert.equal(write.body.get('descripcion_trabajo'), 'Reparación completada'); assert.equal(write.body.getAll('fotos[]').length, 1);
    assert.equal(b.turnos[0].estado_revision, 'PENDIENTE_REVISION');
    assert.equal(buttons(renderer, 'Revisar turno').length, 0);
  } finally { await unmount(renderer); }
});
test('descarga de evidencia usa ruta autenticada same-origin y revoca el Blob URL', async () => {
  const b = obrasBackend(S); b.obras[0].estado = 'EN_PROCESO';
  b.turnos = [{ turno_id: 12, obra: 1, tecnico: 7, iniciado_en: '2026-11-12T12:00:00Z', terminado_en: '2026-11-12T13:00:00Z', descripcion_trabajo: 'Trabajo', estado_revision: 'PENDIENTE_REVISION', modo_cierre: 'TECNICO', fotos: [{ id: 91, tipo_mime: 'image/png', tamano: 25, descarga: 'https://external.invalid/private' }] }];
  const baseRequest = b.request;
  b.request = async (path, options) => path.endsWith('/fotos/91/') ? (b.calls.push({ path, method: options.method || 'GET', body: options.body }), new Blob(['foto'], { type: 'image/png' })) : baseRequest(path, options);
  const renderer = await mount(b, S);
  const originalCreate = URL.createObjectURL, originalRevoke = URL.revokeObjectURL, revoked = [];
  URL.createObjectURL = () => 'blob:test-evidencia'; URL.revokeObjectURL = (value) => revoked.push(value);
  globalThis.document = { body: { appendChild() {} }, createElement: () => ({ click() {}, remove() {}, set href(value) { this.url = value; }, set download(value) { this.filename = value; } }) };
  try {
    await click(renderer, 'Ver obra'); await click(renderer, 'Turnos');
    const button = buttons(renderer, 'Descargar evidencia privada')[0];
    assert.ok(button);
    await act(async () => { await button.props.onClick(); await flush(); });
    assert.match(b.calls.at(-1).path, /^\/api\/obras\/1\/turnos\/12\/fotos\/91\/$/);
    assert.equal(revoked.length, 0);
    await new Promise((resolve) => setTimeout(resolve, 1050));
    assert.deepEqual(revoked, ['blob:test-evidencia']);
  } finally {
    await unmount(renderer); delete globalThis.document;
    URL.createObjectURL = originalCreate; URL.revokeObjectURL = originalRevoke;
  }
});

test('Supervisor revisa con tarifa string decimal y reconsulta el turno', async () => {
  const b = obrasBackend(S); b.obras[0].estado = 'EN_PROCESO';
  b.turnos = [{ turno_id: 11, obra: 1, tecnico: 7, iniciado_en: '2026-11-12T12:00:00Z', terminado_en: '2026-11-12T13:00:00Z', descripcion_trabajo: 'Trabajo realizado', estado_revision: 'PENDIENTE_REVISION', modo_cierre: 'TECNICO', fotos: [], costo_hora_neto: null, costo_mano_obra: null }];
  const renderer = await mount(b, S);
  try {
    await click(renderer, 'Ver obra'); await click(renderer, 'Turnos'); await click(renderer, 'Revisar turno');
    assert.match(text(renderer.root), /Costo por hora de trabajo/); assert.doesNotMatch(text(renderer.root), /string decimal/);
    await input(renderer, 'motivo', 'Revisión completa'); await input(renderer, 'costo_hora_neto', '8000'); await submit(renderer);
    const call = b.calls.find((c) => c.path.endsWith('/11/revisar/'));
    assert.deepEqual(call.body, { decision: 'VALIDAR', motivo: 'Revisión completa', costo_hora_neto: '8000.00' });
    assert.equal(b.turnos[0].estado_revision, 'VALIDADO'); assert.equal(buttons(renderer, 'Revisar turno').length, 0);
  } finally { await unmount(renderer); }
});
test('roles de lectura y técnico no muestran acciones administrativas ni fotos no autorizadas', async () => {
  for (const role of [G, AF]) {
    const b = obrasBackend(role); b.obras[0].estado = 'EN_PROCESO';
    if (role === G) b.turnos = [{ turno_id: 3, obra: 1, tecnico: 7, iniciado_en: '2026-11-12T12:00:00Z', terminado_en: '2026-11-12T13:00:00Z', descripcion_trabajo: 'Trabajo', estado_revision: 'PENDIENTE_REVISION', modo_cierre: 'TECNICO', costo_hora_neto: '8000.00', costo_mano_obra: '10.00', fotos: [] }];
    const renderer = await mount(b, role);
    try {
      if (role === AF) continue;
      await click(renderer, 'Ver obra'); await click(renderer, 'Turnos');
      assert.equal(buttons(renderer, 'Iniciar turno').length, 0); assert.equal(buttons(renderer, 'Revisar turno').length, 0);
      assert.match(text(renderer.root), /Pendiente de revisión/);
    } finally { await unmount(renderer); }
  }
});

test('reconsulta tras conflicto de participante respeta el principal actual sin repetir escritura', async () => {
  const b = obrasBackend(), renderer = await mount(b);
  try {
    await click(renderer, 'Ver obra'); await click(renderer, 'Equipo'); await click(renderer, 'Reactivar'); await input(renderer, 'motivo', 'Apoyo');
    b.failure = new ApiError(409, 'La membresía cambió.'); await submit(renderer);
    b.obras[0].tecnico_responsable = 8; b.members[1].es_responsable = true; b.members[1].activo = true;
    const count = b.calls.filter((c) => c.method === 'POST').length;
    await click(renderer, 'Actualizar datos'); assert.equal(b.calls.filter((c) => c.method === 'POST').length, count);
    assert.ok(buttons(renderer, 'Guardar cambios')[0].props.disabled); assert.match(text(renderer.root), /ya no permiten esta acción/);
  } finally { await unmount(renderer); }
});

test('Panel gerencial: indicadores globales, prioridad y filtros remotos sin consultas por obra',async()=>{
  const b=obrasBackend(G);
  b.obras=Array.from({length:26},(_,i)=>({...b.obras[0],id:i+1,codigo:'OB-'+(i+1),estado:i===25?'EN_PROCESO':'PLANIFICADA',test_cost:i===25?'50000.00':'0.00'}));
  const renderer=await mount(b);
  try{
    assert.equal(b.calls.length,1);
    assert.match(text(renderer.root.findAllByType('article')[0]),/OB-26/);
    assert.match(text(renderer.root.findAllByType('article')[0]),/Sobrecosto/);
    assert.equal(renderer.root.findAllByProps({className:'portfolio-track'}).length,0);
    assert.equal(renderer.root.findByProps({id:'manager-obra-filters'}).props.hidden,true);
    await click(renderer,'Filtros');
    const before=b.calls.length;
    await act(async()=>{renderer.root.findByProps({id:'manager-obra-search'}).props.onChange({target:{value:'OB-26'}});await flush();});
    assert.equal(b.calls.length,before);
    await act(async()=>{renderer.root.findByProps({id:'manager-obra-filters'}).props.onSubmit({preventDefault(){}});await flush();});
    assert.match(b.calls.at(-1).path,/buscar=OB-26/);
    await click(renderer,'Limpiar filtros');
    assert.match(text(renderer.root),/26 obras/);
    await click(renderer,'Requieren atención');
    assert.match(b.calls.at(-1).path,/atencion=requiere/);
    assert.equal(renderer.root.findAllByType('article').length,1);
    assert.match(text(renderer.root),/26 obras/);
    await click(renderer,'Limpiar filtros');
    await click(renderer,'Siguiente');
    assert.match(b.calls.at(-1).path,/page=2/);
    assert.ok(b.calls.every(c=>c.path.startsWith('/api/obras/supervision-gerencial/')));
    b.readFailure=()=>true;
    await click(renderer,'Actualizar datos');
    assert.equal(renderer.root.findAllByType('article').length,0);
  }finally{await unmount(renderer);}
});

test('Diferencias económicas gerenciales exactas, sin porcentajes ficticios ni redondeo monetario',()=>{
  const over=economicDifference('600000.00','1023500.00');
  assert.equal(over.value,'+$423.500');assert.equal(over.detail,'70,6 % sobre presupuesto');assert.equal(over.tone,'red');
  assert.equal(economicDifference('580000.00','0.00').label,'Presupuesto restante');
  assert.equal(economicDifference('100.25','0.12',true).value,'$100,13');
  assert.equal(economicDifference('0.00','100.00').deviation,null);
  assert.equal(economicDifference(null,'100.00'),null);
  assert.equal(economicDifference('12345678901234567890.01','0.01').value,'$12.345.678.901.234.567.890');
});

test('T: navegación propia, consulta global y cierre desde turno actual',async()=>{
 const b=obrasBackend(T);
 b.obras[0].estado='EN_PROCESO';
 const session={status:'authenticated',user:{id:8,username:'tecnico',email:'tecnico@example.test',role:T}};
 const client={getSnapshot:()=>session,subscribe:()=>()=>{},restore:async()=>{},request:b.request};
 b.turnos=[{turno_id:1,obra:1,tecnico:8,iniciado_en:'2026-11-08T12:00:00Z',terminado_en:null,descripcion_trabajo:'',estado_revision:'ABIERTO',modo_cierre:null,duracion_segundos:null,duracion_ajustada_segundos:null,observacion:'',fotos:[]}];
 let renderer;
 try{
  await act(async()=>{renderer=Renderer.create(React.createElement(AuthProvider,{client},React.createElement(AppProvider,null,React.createElement(App))));await flush();});
  assert.deepEqual(renderer.root.findByProps({id:'fyag-modules-nav'}).findAllByType('button').map(text),['Mis obras','Mis turnos','Solicitudes','Mermas','Chat interno']);
  assert.equal(renderer.root.findAllByProps({className:'tec-work'}).length,1);
  assert.equal(renderer.root.findAllByType('table').length,0);
  await act(async()=>renderer.root.findByProps({'aria-label':'Buscar obra o cliente'}).props.onChange({target:{value:'Cliente operativo'}}));
  await submit(renderer);
  assert.equal(new URL(b.calls.at(-1).path,'http://localhost').searchParams.get('buscar'),'Cliente operativo');
  await click(renderer,'Mis turnos');
  assert.ok(b.calls.some(c=>c.path==='/api/obras/mis-turnos/?page=1'));
  assert.match(text(renderer.root),/Turno actual.*OB-000001/);
  assert.equal(buttons(renderer,'Finalizar turno').length,1);
  await click(renderer,'Finalizar turno');
  await input(renderer,'descripcion_trabajo','Reparación terminada');
  await submit(renderer);
  assert.equal(b.calls.filter(c=>c.method==='POST'&&c.path==='/api/obras/1/turnos/1/finalizar/').length,1);
  assert.equal(b.turnos[0].estado_revision,'PENDIENTE_REVISION');
  assert.match(text(renderer.root),/No tienes un turno en curso/);
  assert.doesNotMatch(text(renderer.root),/Costo mano de obra/);
 }finally{if(renderer)await unmount(renderer);}
});

test('Supervisor: suspender pide motivo y confirmación; cancelar no cambia estado', async()=>{
 const b=obrasBackend();b.obras[0].estado='EN_PROCESO';const renderer=await mount(b);
 const old=window.confirm;let message='';
 try{
  await click(renderer,'Ver obra');assert.match(buttons(renderer,'Suspender obra')[0].props.className,/so-danger-action/);
  await click(renderer,'Suspender obra');assert.equal(renderer.root.findByType('dialog').props['aria-labelledby'],'so-suspend-title');
  assert.equal(buttons(renderer,'Guardar cambios')[0].props.disabled,true);
  await input(renderer,'motivo','Pausa operativa');window.confirm=m=>{message=m;return false;};
  await submit(renderer);assert.match(message,/Podrás reanudar/);assert.equal(b.calls.filter(c=>c.method==='POST').length,0);
  assert.equal(b.obras[0].estado,'EN_PROCESO');
  window.confirm=()=>true;await submit(renderer);assert.equal(b.obras[0].estado,'SUSPENDIDA');
  assert.equal(renderer.root.findAllByType('dialog').length,0);assert.match(buttons(renderer,'Reanudar obra')[0].props.className,/so-positive-action/);
 }finally{window.confirm=old;await unmount(renderer);}
});

test('Supervisor: turnos destaca duración, costo y estado en una superficie única',async()=>{
 const b=obrasBackend(S);b.obras[0].estado='EN_PROCESO';
 b.turnos=[{turno_id:6,obra:1,tecnico:7,iniciado_en:'2026-11-12T12:00:00Z',terminado_en:'2026-11-12T21:00:00Z',duracion_segundos:32400,duracion_ajustada_segundos:null,descripcion_trabajo:'Inspección de componentes',observacion_revision:'Horas verificadas',estado_revision:'VALIDADO',modo_cierre:'TECNICO',costo_hora_neto:'18500.00',costo_mano_obra:'166500.00',fotos:[]}];
 const renderer=await mount(b);
 try{
  await click(renderer,'Ver obra');await click(renderer,'Turnos');
  const panel=renderer.root.findByProps({'aria-labelledby':'turnos-title'});
  assert.match(panel.props.className,/card-fyag so-panel so-turns/);
  const facts=renderer.root.findByProps({className:'so-turn-facts'});
  assert.match(text(facts),/Duración9 h/);assert.match(text(facts),/Costo mano de obra neto\$166\.500/);
  assert.equal(text(renderer.root.findByProps({className:'so-turn-status','data-state':'VALIDADO'})),'Validado');
  assert.match(text(panel),/Inspección de componentes/);assert.match(text(panel),/Horas verificadas/);
  assert.equal(buttons(renderer,'Corregir turno').length,1);
  assert.ok(b.calls.every(c=>c.method==='GET'));
 }finally{await unmount(renderer);}
});
