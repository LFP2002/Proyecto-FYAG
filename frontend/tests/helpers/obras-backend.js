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
    turnos: [], expenses: [], costEvents: [], control: { id: 1, obra: 1, materiales_estado: 'PENDIENTE', materiales_justificacion: '', otros_estado: 'PENDIENTE', otros_justificacion: '', version_actual: 0, version_validada: null, validado_por: null, validado_en: null, costos_validados: false, creado_en: time, actualizado_en: time }, courtesy: null,
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
    backend.calls.push({ path, method, body: typeof FormData !== 'undefined' && body instanceof FormData ? body : clone(body), signal: options.signal });
    if (method !== 'GET' && backend.failure) throw backend.failure;
    if (method === 'GET' && backend.readFailure?.(path)) throw new ApiError(500, 'Relectura fallida.');

    const url = new URL(path, 'http://localhost'), route = url.pathname;
    if (/^\/api\/presupuestos\/\d+\/$/.test(route) && method==='GET') { assertRole([G,AF]); const id=Number(route.split('/')[3]); return {id,monto_neto:'45300.00'}; }
    if (route.startsWith('/api/finanzas/obras-resumen/')) {
      assertRole([AF]);
      const rows=backend.obras.map(o=>({...project(o),monto_neto_aprobado:'45300.00',situacion_financiera:o.estado==='FINALIZADA'?'PENDIENTE_FACTURACION':'NO_HABILITADA'}));
      if(route!=='/api/finanzas/obras-resumen/'){
        const id=Number(route.split('/')[4]), row=rows.find(o=>o.id===id);
        if(!row)throw new ApiError(404,'Obra no encontrada');
        return {...row,documento:null};
      }
      return paginate(rows.filter(o=>(!url.searchParams.has('estado')||o.estado===url.searchParams.get('estado'))&&(!url.searchParams.has('situacion_financiera')||o.situacion_financiera===url.searchParams.get('situacion_financiera'))&&(!url.searchParams.has('buscar')||[o.codigo,o.cliente_nombre,o.categoria_nombre].some(v=>v.toLowerCase().includes(url.searchParams.get('buscar').toLowerCase())))),url);
    }
    if (route === '/api/obras/supervision-gerencial/') {
      assertRole([G]);
      const rows=backend.obras.map(o=>{const cost=o.test_cost||'0.00',budget='45300.00',alerts=[];
        if(Number(cost)>Number(budget))alerts.push('PRESUPUESTO_SUPERADO');
        if(o.estado==='SUSPENDIDA')alerts.push('SUSPENDIDA');
        if(o.estado==='PLANIFICADA'&&!o.fecha_programada)alerts.push('SIN_PROGRAMAR');
        return {...o,presupuesto_neto:budget,costo_total:cost,diferencia_neta:(Number(budget)-Number(cost)).toFixed(2),porcentaje_utilizado:(Number(cost)/Number(budget)*100).toFixed(1),costos_provisionales:true,sin_cobro:false,alertas:alerts,nivel:alerts.includes('PRESUPUESTO_SUPERADO')?'critica':alerts.length?'atencion':'normal'};
      }).sort((a,b)=>['critica','atencion','normal'].indexOf(a.nivel)-['critica','atencion','normal'].indexOf(b.nivel));
      const resumen={total:rows.length,en_ejecucion:rows.filter(o=>o.estado==='EN_PROCESO').length,sin_programar:rows.filter(o=>o.alertas.includes('SIN_PROGRAMAR')).length,presupuesto_superado:rows.filter(o=>o.alertas.includes('PRESUPUESTO_SUPERADO')).length,suspendidas:rows.filter(o=>o.estado==='SUSPENDIDA').length,requieren_atencion:rows.filter(o=>o.alertas.length).length};
      const filtered=rows.filter(o=>(!url.searchParams.has('estado')||o.estado===url.searchParams.get('estado'))&&(url.searchParams.get('atencion')!=='requiere'||o.alertas.length)&&(url.searchParams.get('atencion')!=='sin_alertas'||!o.alertas.length)&&(!url.searchParams.has('buscar')||o.codigo.includes(url.searchParams.get('buscar')))&&(!url.searchParams.has('prioridad')||o.alertas.includes(({sin_programar:'SIN_PROGRAMAR',presupuesto_superado:'PRESUPUESTO_SUPERADO',suspendidas:'SUSPENDIDA'})[url.searchParams.get('prioridad')])));
      return {...paginate(filtered,url),resumen};
    }
    if (route === '/api/obras/mis-turnos/') {
      assertRole([T]);
      const rows=backend.turnos.filter(t=>t.tecnico===8&&backend.allowed.has(t.obra)).map(t=>({...t,obra_codigo:backend.obras.find(o=>o.id===t.obra).codigo,categoria_nombre:backend.obras.find(o=>o.id===t.obra).categoria_nombre,obra_estado:backend.obras.find(o=>o.id===t.obra).estado}));
      const history=rows.filter(t=>t.terminado_en&&(!url.searchParams.has('estado')||t.estado_revision===url.searchParams.get('estado')));
      return {...paginate(history,url),activo:clone(rows.find(t=>t.estado_revision==='ABIERTO')||null),hora_servidor:'2026-11-08T13:00:00Z'};
    }
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
      if((route.endsWith('/mis-obras/')||backend.role===S)&&url.searchParams.has('buscar')){const term=url.searchParams.get('buscar').toLowerCase();rows=rows.filter(o=>[o.codigo,o.cliente_nombre,o.categoria_nombre,...(backend.role===S?[o.tecnico_nombre]:[])].some(v=>String(v||'').toLowerCase().includes(term)));}
      for (const key of ['estado', 'cliente', 'tecnico_responsable', 'categoria_servicio']) if (url.searchParams.has(key)) rows = rows.filter((o) => String(o[key]) === url.searchParams.get(key));
      for (const [key, comparison] of [['fecha_programada_desde', (a, b) => a >= b], ['fecha_programada_hasta', (a, b) => a <= b]]) if (url.searchParams.has(key)) rows = rows.filter((o) => o.fecha_programada && comparison(o.fecha_programada, url.searchParams.get(key)));
      return paginate(rows.map(project), url);
    }
    const match = route.match(/^\/api\/obras\/(\d+)\/(.*)$/);
    if (match) {
      const obra = backend.obras.find((o) => o.id === Number(match[1])), suffix = match[2];
      if (!obra || (backend.role === T && !backend.allowed.has(obra.id))) throw new ApiError(404, 'Recurso no disponible.');
      if (!suffix && method === 'GET') return project(obra);
      if (suffix === 'costos/resumen/' && method === 'GET') {
        assertRole([G, S, AF]);
        const summary = { obra: obra.id, materiales_total: '0.00', otros_total: '0.00', mano_obra_total: '0.00', costo_total: '0.00', ...backend.costTotals, costos_validados: backend.control.costos_validados, cortesia_sin_cobro: !!backend.courtesy };
        if (backend.role !== AF) Object.assign(summary, { materiales_estado: backend.control.materiales_estado, otros_estado: backend.control.otros_estado, materiales_justificacion: backend.control.materiales_justificacion, otros_justificacion: backend.control.otros_justificacion, version_actual: backend.control.version_actual, version_validada: backend.control.version_validada, validado_por: backend.control.validado_por, validado_en: backend.control.validado_en, cortesia_justificacion: backend.courtesy?.justificacion ?? null, provisional: !backend.control.costos_validados || obra.estado === 'SUSPENDIDA' });
        return summary;
      }
      if (suffix === 'costos/control/' && method === 'GET') { assertRole([G, S]); return clone(backend.control); }
      if (suffix === 'conciliacion-materiales/' && method === 'GET') { assertRole([G, S]); return {count:0,next:null,previous:null,results:[]}; }
      if (suffix === 'requisitos-cierre/' && method === 'GET') { assertRole([S]); return clone(backend.requirements||{validacion:[],finalizacion:[],devoluciones:[],despachos:[],confirmacion_remanente:null}); }
      if (suffix === 'costos/control/' && method === 'PATCH') { assertRole([S]); Object.assign(backend.control, body, { version_actual: backend.control.version_actual + 1, version_validada: null, costos_validados: false }); backend.costEvents.push({ id: backend.costEvents.length + 1, obra: obra.id, gasto: null, control: 1, cortesia: null, tipo: 'DECLARACION', registrado_por: 2, motivo: body.motivo, datos_anteriores: {}, datos_nuevos: clone(backend.control), creado_en: time }); return clone(backend.control); }
      if (suffix === 'costos/validar/' && method === 'POST') { assertRole([S]); if (!body.motivo?.trim()) throw new ApiError(400, 'Motivo obligatorio.'); backend.control.costos_validados = true; backend.control.version_validada = backend.control.version_actual; backend.control.validado_por = 2; backend.control.validado_en = time; backend.costEvents.push({ id: backend.costEvents.length + 1, obra: obra.id, gasto: null, control: 1, cortesia: null, tipo: 'VALIDACION', registrado_por: 2, motivo: body.motivo, datos_anteriores: {}, datos_nuevos: clone(backend.control), creado_en: time }); return clone(backend.control); }
      if (suffix === 'cortesia-sin-cobro/' && method === 'POST') { assertRole([S]); if (backend.courtesy && !body.motivo) throw new ApiError(400, 'Motivo obligatorio.'); backend.courtesy = { justificacion: body.justificacion }; backend.control.version_actual++; backend.control.costos_validados = false; backend.costEvents.push({ id: backend.costEvents.length + 1, obra: obra.id, gasto: null, control: null, cortesia: 1, tipo: 'CORTESIA', registrado_por: 2, motivo: body.motivo || body.justificacion, datos_anteriores: {}, datos_nuevos: { justificacion: body.justificacion }, creado_en: time }); return clone(backend.courtesy); }
      if (suffix.startsWith('costos/historial/') && method === 'GET') { assertRole([G, S]); return paginate(backend.costEvents, url); }
      if (suffix === 'gastos/' && method === 'GET') { assertRole([G, S]); return paginate(backend.expenses.map(item=>({origen:'MANUAL',entrega_bodega:null,...item})), url); }
      if (suffix === 'gastos/' && method === 'POST') { assertRole([S]); const item = { id: backend.expenses.length + 1, obra: obra.id, ...clone(body), cantidad_devuelta: '0.000', subtotal: '25.00', vigente: true, anulado_por: null, anulado_en: null, motivo_anulacion: '', registrado_por: 2, creado_en: time, actualizado_en: time }; backend.expenses.unshift(item); backend.control.version_actual++; backend.control.costos_validados = false; return clone(item); }
      const expenseMatch = suffix.match(/^gastos\/(\d+)(?:\/(devolver|anular))?\/$/);
      if (expenseMatch && method !== 'GET') { assertRole([S]); const item = backend.expenses.find((entry) => entry.id === Number(expenseMatch[1])); if (!item) throw new ApiError(404, 'No disponible.'); if (method === 'PATCH') Object.assign(item, body); else if (expenseMatch[2] === 'devolver') item.cantidad_devuelta = body.cantidad; else if (expenseMatch[2] === 'anular') { item.vigente = false; item.motivo_anulacion = body.motivo; } backend.control.version_actual++; backend.control.costos_validados = false; return clone(item); }
      if (suffix === 'finalizar/' && method === 'POST') { assertRole([S]); if (!backend.control.costos_validados || obra.estado !== 'EN_PROCESO') throw new ApiError(409, 'Costos incompletos.'); obra.estado = 'FINALIZADA'; obra.finalizado_en = time; return project(obra); }
      if (suffix === 'turnos/' && method === 'GET') {
        assertRole([G, S, T]);
        return paginate(backend.turnos.filter((turno) => turno.obra === obra.id && (backend.role !== T || turno.tecnico === 8)), url);
      }
      if (suffix === 'turnos/iniciar/' && method === 'POST') {
        assertRole([T]);
        if (obra.estado !== 'EN_PROCESO') throw new ApiError(409, 'Estado incompatible.');
        const turno = { turno_id: backend.turnos.length + 1, obra: obra.id, tecnico: 8, iniciado_en: '2026-11-12T12:00:00Z', terminado_en: null, duracion_segundos: null, duracion_ajustada_segundos: null, descripcion_trabajo: '', estado_revision: 'ABIERTO', modo_cierre: null, cerrado_por: null, observacion: '', fotos: [] };
        backend.turnos.push(turno); return clone(turno);
      }
      const turnoMatch = suffix.match(/^turnos\/(\d+)\/(finalizar|subsanar|revisar|corregir|cerrar-administrativamente)\/$/);
      if (turnoMatch && method === 'POST') {
        const turno = backend.turnos.find((entry) => entry.turno_id === Number(turnoMatch[1]) && entry.obra === obra.id);
        if (!turno) throw new ApiError(404, 'Turno no disponible.');
        const action = turnoMatch[2]; assertRole(action === 'finalizar' || action === 'subsanar' ? [T] : [S]);
        if (action === 'finalizar' || action === 'subsanar' || action === 'cerrar-administrativamente') {
          const description = body instanceof FormData ? body.get('descripcion_trabajo') : body.descripcion_trabajo;
          if (description) turno.descripcion_trabajo = description;
          turno.estado_revision = 'PENDIENTE_REVISION'; turno.terminado_en = '2026-11-12T13:00:00Z';
          turno.modo_cierre = action === 'cerrar-administrativamente' ? 'SUPERVISOR' : 'TECNICO';
        } else if (action === 'revisar') {
          turno.estado_revision = body.decision === 'VALIDAR' ? 'VALIDADO' : 'OBSERVADO';
          turno.observacion = body.decision === 'OBSERVAR' ? body.motivo : '';
          turno.observacion_revision = body.motivo; turno.costo_hora_neto = body.costo_hora_neto || null; turno.costo_mano_obra = '10.00';
        }
        return clone(turno);
      }      if (method === 'GET') {
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
        assertRole([S]); const category = { id: Math.max(...backend.categories.map((c) => c.id)) + 1, nombre: body.nombre, activo: true }; backend.categories.push(category); return clone(category);
      }
      const category = backend.categories.find((c) => c.id === Number(match[1]));
      if (!category) throw new ApiError(404, 'Categoría no disponible.');
      if (method === 'GET' && !match[2]) return clone(category);
      if (match[2] === 'historial/' && method === 'GET') return paginate(backend.categoryEvents, url);
      assertRole([S]);
      if (method === 'PATCH') category.nombre = body.nombre;
      if (match[2] === 'activar/') category.activo = true;
      if (match[2] === 'desactivar/') category.activo = false;
      backend.categoryEvents.push({ id: backend.categoryEvents.length + 1, tipo: 'EDICION', registrado_por: 1, motivo: body.motivo, datos_anteriores: {}, datos_nuevos: { nombre: category.nombre, activo: category.activo }, creado_en: time }); return clone(category);
    }
    throw new Error(`Endpoint inesperado ${method} ${path}`);
  };
  return backend;
}
