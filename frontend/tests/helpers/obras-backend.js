import { ApiError } from '../../src/auth/client.js';
import { AF, G, minimalFields, S, T } from '../../src/obras/domain.js';

// Contratos controlados exclusivamente para pruebas de componentes, no servidor productivo.
export function obrasBackend(role = S) {
  const clone = (value) => structuredClone(value);
  const time = '2026-11-08T12:00:00Z';
  const backend = {
    role, calls: [], failure: null, readFailure: null,
    categories: [{ id: 1, nombre: 'Categoría histórica', activo: false }, { id: 2, nombre: 'Mantención', activo: true }],
    budgets: [{ id: 20, codigo: 'PRE-000020', cliente: 4, cliente_nombre: 'Cliente operativo' }, { id: 21, codigo: 'PRE-000021', cliente: 4, cliente_nombre: 'Cliente operativo' }],
    technicians: [{ id: 7, nombre: 'Técnico principal' }, { id: 8, nombre: 'Técnico adicional' }],
    obras: [{ id: 1, codigo: 'OB-000001', presupuesto: 10, presupuesto_codigo: 'PRE-000010', cliente: 4, cliente_nombre: 'Cliente operativo', categoria_servicio: 1, categoria_nombre: 'Categoría histórica', descripcion: 'Descripción operativa privada', tecnico_responsable: 7, tecnico_nombre: 'Técnico principal', fecha_programada: '2026-11-20', iniciado_en: null, estado: 'PLANIFICADA', finalizado_en: null, cancelado_en: null, creado_por: 2, creado_en: time, actualizado_en: time }],
    members: [{ id: 101, obra: 1, tecnico: 7, tecnico_nombre: 'Técnico principal', activo: true, es_responsable: true, origen_registro: 'OPERACION', asignado_por: 2, asignado_en: time, motivo_asignacion: 'Inicial', desasignado_por: null, desasignado_en: null, motivo_desasignacion: '' }, { id: 102, obra: 1, tecnico: 8, tecnico_nombre: 'Técnico adicional', activo: false, es_responsable: false, origen_registro: 'MIGRACION_004B', asignado_por: null, asignado_en: null, motivo_asignacion: '', desasignado_por: 2, desasignado_en: time, motivo_desasignacion: 'Retirado' }],
    events: [{ id: 1, obra: 1, tipo: 'CREACION', estado_anterior: null, estado_nuevo: 'PLANIFICADA', datos_anteriores: {}, datos_nuevos: { descripcion: 'Descripción operativa privada' }, registrado_por: 2, motivo: 'Inicial', creado_en: time }],
    memberEvents: [], categoryEvents: [], allowed: new Set([1]),
  };
  function paginate(rows, url) {
    const page = Number(url.searchParams.get('page') || 1);
    if (page > Math.max(1, Math.ceil(rows.length / 25))) throw new ApiError(404, 'Página no disponible.');
    const link = (p) => { const copy = new URL(url); if (p === 1) copy.searchParams.delete('page'); else copy.searchParams.set('page', p); return copy.pathname + copy.search; };
    return { count: rows.length, next: page * 25 < rows.length ? link(page + 1) : null, previous: page > 1 ? link(page - 1) : null, results: clone(rows.slice((page - 1) * 25, page * 25)) };
  }
  const project = (obra) => backend.role === AF ? Object.fromEntries(minimalFields.map((key) => [key, obra[key]])) : clone(obra);
  const assertRole = (roles) => { if (!roles.includes(backend.role)) throw new ApiError(403, 'Acceso denegado.'); };
  backend.request = async (path, options = {}) => {
    const method = options.method || 'GET', body = options.body;
    backend.calls.push({ path, method, body: clone(body), signal: options.signal });
    if (method !== 'GET' && backend.failure) throw backend.failure;
    if (method === 'GET' && backend.readFailure?.(path)) throw new ApiError(500, 'Relectura fallida.');
    if (/\/(turnos|gastos|costos|finalizar|cancelar)(\/|\?)/.test(path)) throw new Error(`Fuera de 005C-1: ${path}`);
    const url = new URL(path, 'http://localhost'), route = url.pathname;
    if (route === '/api/obras/presupuestos-disponibles/') { assertRole([S]); return paginate(backend.budgets, url); }
    if (route === '/api/obras/tecnicos-disponibles/') { assertRole([S]); return paginate(backend.technicians, url); }
    if (route === '/api/obras/' || route === '/api/obras/mis-obras/') {
      if (method === 'POST') {
        assertRole([S]);
        if (!backend.budgets.some((p) => p.id === body.presupuesto)) throw new ApiError(409, 'Presupuesto utilizado.', null, { code: 'presupuesto_utilizado' });
        const id = Math.max(...backend.obras.map((o) => o.id)) + 1;
        const obra = { ...clone(backend.obras[0]), ...body, id, codigo: `OB-${id}`, presupuesto_codigo: `PRE-${body.presupuesto}`, categoria_nombre: backend.categories.find((c) => c.id === body.categoria_servicio)?.nombre, tecnico_nombre: backend.technicians.find((t) => t.id === body.tecnico_responsable)?.nombre || null, estado: 'PLANIFICADA', iniciado_en: null };
        delete obra.motivo; backend.obras.push(obra); backend.budgets = backend.budgets.filter((p) => p.id !== body.presupuesto); return project(obra);
      }
      if (route.endsWith('/mis-obras/')) assertRole([T]);
      let rows = backend.obras.filter((o) => backend.role !== T || backend.allowed.has(o.id));
      for (const key of ['estado', 'cliente', 'tecnico_responsable', 'categoria_servicio']) if (url.searchParams.has(key)) rows = rows.filter((o) => String(o[key]) === url.searchParams.get(key));
      for (const [key, comparison] of [['fecha_programada_desde', (a, b) => a >= b], ['fecha_programada_hasta', (a, b) => a <= b]]) if (url.searchParams.has(key)) rows = rows.filter((o) => o.fecha_programada && comparison(o.fecha_programada, url.searchParams.get(key)));
      return paginate(rows.map(project), url);
    }
    const match = route.match(/^\/api\/obras\/(\d+)\/(.*)$/);
    if (match) {
      const obra = backend.obras.find((o) => o.id === Number(match[1])), suffix = match[2];
      if (!obra || (backend.role === T && !backend.allowed.has(obra.id))) throw new ApiError(404, 'Recurso no disponible.');
      if (!suffix && method === 'GET') return project(obra);
      if (method === 'GET') {
        assertRole([G, S]);
        if (suffix === 'historial/') return paginate(backend.events.filter((e) => e.obra === obra.id), url);
        if (suffix === 'participantes/historial/') return paginate(backend.memberEvents, url);
        if (suffix === 'participantes/') return paginate(backend.members.filter((m) => m.obra === obra.id && (!url.searchParams.has('activo') || String(m.activo) === url.searchParams.get('activo'))), url);
      }
      assertRole([S]);
      if (method === 'PATCH') { Object.assign(obra, body); delete obra.motivo; return project(obra); }
      if (suffix === 'cambiar-tecnico/') {
        const previous = obra.tecnico_responsable; obra.tecnico_responsable = body.tecnico_responsable; obra.tecnico_nombre = backend.technicians.find((t) => t.id === body.tecnico_responsable)?.nombre || null;
        backend.members.forEach((m) => { if (m.tecnico === previous) m.activo = false; if (m.tecnico === body.tecnico_responsable) m.activo = true; m.es_responsable = m.tecnico === body.tecnico_responsable; });
        return project(obra);
      }
      if (suffix === 'participantes/') {
        let member = backend.members.find((m) => m.obra === obra.id && m.tecnico === body.tecnico);
        if (member?.activo) throw new ApiError(409, 'Participante ya activo.', null, { code: 'sin_cambios' });
        if (!member) { member = { ...clone(backend.members[0]), id: 100 + backend.members.length + 1, obra: obra.id, tecnico: body.tecnico, tecnico_nombre: backend.technicians.find((t) => t.id === body.tecnico)?.nombre, es_responsable: false }; backend.members.push(member); }
        Object.assign(member, { activo: true, asignado_por: 2, asignado_en: time, motivo_asignacion: body.motivo, desasignado_por: null, desasignado_en: null, motivo_desasignacion: '' });
        backend.memberEvents.push({ id: backend.memberEvents.length + 1, participante: member.id, tipo: 'REACTIVACION', registrado_por: 2, motivo: body.motivo, datos_anteriores: { activo: false }, datos_nuevos: { activo: true }, creado_en: time }); return clone(member);
      }
      if (suffix.match(/^participantes\/\d+\/desasignar\/$/)) {
        const member = backend.members.find((m) => m.id === Number(suffix.split('/')[1]) && m.obra === obra.id);
        if (!member) throw new ApiError(404, 'Miembro no disponible.');
        if (member.es_responsable) throw new ApiError(409, 'Cambie al responsable.');
        Object.assign(member, { activo: false, desasignado_por: 2, desasignado_en: time, motivo_desasignacion: body.motivo }); return clone(member);
      }
      const states = { 'iniciar/': ['PLANIFICADA', 'EN_PROCESO'], 'suspender/': ['EN_PROCESO', 'SUSPENDIDA'], 'reanudar/': ['SUSPENDIDA', 'EN_PROCESO'] };
      if (states[suffix]) {
        const [before, after] = states[suffix]; if (obra.estado !== before) throw new ApiError(409, 'Estado incompatible.');
        obra.estado = after; if (suffix === 'iniciar/') obra.iniciado_en = time;
        backend.events.push({ ...clone(backend.events[0]), id: backend.events.length + 1, obra: obra.id, tipo: 'CAMBIO_ESTADO', estado_anterior: before, estado_nuevo: after, motivo: body.motivo, datos_anteriores: {}, datos_nuevos: {} }); return project(obra);
      }
    }
    if (route.startsWith('/api/categorias-servicio/')) {
      assertRole([G, S]);
      const match = route.match(/^\/api\/categorias-servicio\/(\d+)\/(.*)$/);
      if (!match) {
        if (method === 'GET') return paginate(backend.categories.filter((c) => !url.searchParams.has('activo') || String(c.activo) === url.searchParams.get('activo')), url);
        assertRole([G]); const category = { id: Math.max(...backend.categories.map((c) => c.id)) + 1, nombre: body.nombre, activo: true }; backend.categories.push(category); return clone(category);
      }
      const category = backend.categories.find((c) => c.id === Number(match[1]));
      if (!category) throw new ApiError(404, 'Categoría no disponible.');
      if (method === 'GET' && !match[2]) return clone(category);
      assertRole([G]);
      if (match[2] === 'historial/') return paginate(backend.categoryEvents, url);
      if (method === 'PATCH') category.nombre = body.nombre;
      if (match[2] === 'activar/') category.activo = true;
      if (match[2] === 'desactivar/') category.activo = false;
      backend.categoryEvents.push({ id: backend.categoryEvents.length + 1, tipo: 'EDICION', registrado_por: 1, motivo: body.motivo, datos_anteriores: {}, datos_nuevos: { nombre: category.nombre, activo: category.activo }, creado_en: time }); return clone(category);
    }
    throw new Error(`Endpoint inesperado ${method} ${path}`);
  };
  return backend;
}
