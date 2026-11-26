import test from 'node:test';
import assert from 'node:assert/strict';
import { createAuthClient, ApiError } from '../src/auth/client.js';
import { createServer } from 'vite';
import React from 'react';
import Renderer, { act } from 'react-test-renderer';

let server, AuthProvider, Alertas, Cobranzas, Dashboard, Reportes, validDashboardRange, todayInSantiago, safePage;
test.before(async () => {
  server = await createServer({ configFile: false, esbuild: { jsx: 'automatic' }, server: { middlewareMode: true, ws: false, hmr: false }, appType: 'custom', optimizeDeps: { noDiscovery: true, include: [] } });
  ({ AuthProvider } = await server.ssrLoadModule('/src/auth/AuthContext.jsx'));
  ({ safePage } = await server.ssrLoadModule('/src/integrations/useApi.js'));
  ({ default: Alertas } = await server.ssrLoadModule('/src/pages/Alertas.jsx'));
  ({ default: Cobranzas } = await server.ssrLoadModule('/src/pages/Cobranzas.jsx'));
  ({ default: Dashboard, validDashboardRange, todayInSantiago } = await server.ssrLoadModule('/src/pages/Dashboard.jsx'));
  ({ default: Reportes } = await server.ssrLoadModule('/src/pages/Reportes.jsx'));
  globalThis.window = { location: { origin: 'http://localhost' } };
  globalThis.document = { body: { appendChild() {} }, createElement: () => ({ click() {}, remove() {} }) };
});
test.after(async () => { delete globalThis.window; delete globalThis.document; await server.close(); });
const flush = () => new Promise((resolve) => setImmediate(resolve));
const text = (node) => typeof node === 'string' ? node : (node.children || []).map(text).join('');
const click = async (renderer,label)=>{const button=renderer.root.findAllByType('button').find((item)=>text(item)===label);assert.ok(button,`button ${label} missing`);await act(async()=>{button.props.onClick();await flush();});};

function apiFor(role, calls) {
  const alert = { id: 3, rol_responsable:'SUPERVISOR_OBRAS', destinatarios:['SUPERVISOR_OBRAS','GERENCIA'], es_legada:false, generacion:1, tipo: 'OBRA_SUSPENDIDA', estado: 'PENDIENTE', severidad: 'ALTA', rol_destinatario: role, recurso_tipo: 'OBRA', recurso_id: 4, recurso_codigo: 'OB-000004', obra: 4, titulo: 'Obra suspendida', descripcion: 'La obra se encuentra suspendida.', creado_en: '2026-11-14T10:00:00-03:00', atendida_por: null, atendida_en: null, motivo_atencion: null, resuelta_en: null, acciones_permitidas: role==='GERENCIA'?[]:['ATENDER'] };
  if(role==='ADMINISTRATIVO_FINANZAS') Object.assign(alert,{tipo:'PRESUPUESTO_PENDIENTE_FINANZAS',rol_responsable:role,destinatarios:[role],severidad:'MEDIA',recurso_tipo:'PRESUPUESTO',recurso_codigo:'PRE-000004',obra:null,titulo:'Presupuesto pendiente de Finanzas',descripcion:'Requiere revisión de Finanzas.'});
  const send = async (path, options = {}) => {
    calls.push({ path, options });
    if (path === '/api/alertas/resumen/') return { generado_en: '2026-11-14T10:00:00-03:00', zona_horaria: 'America/Santiago', por_estado: { PENDIENTE: 1, ATENDIDA: 0, RESUELTA: 0 }, activas: 1, por_tipo: { [alert.tipo]: { PENDIENTE: 1, ATENDIDA: 0, RESUELTA: 0 } }, sincronizacion: { ultima_correcta_en: null, desactualizada: false } };
    if (new URL(path,'http://localhost').pathname === '/api/alertas/') {
      const q=new URL(path,'http://localhost').searchParams;
      const visible=(!q.get('estado')||q.get('estado')==='TODAS'||q.get('estado')===alert.estado)&&(!q.get('tipo')||q.get('tipo')===alert.tipo);
      return {count:visible?1:0,next:null,previous:null,results:visible?[alert]:[]};
    }
    if (path === '/api/alertas/3/') return alert;
    if (path.startsWith('/api/alertas/3/historial/')) { const page = Number(new URL(path, 'http://localhost').searchParams.get('page') || 1); return { count: 26, next: page === 1 ? '/api/alertas/3/historial/?page=2' : null, previous: page === 2 ? '/api/alertas/3/historial/' : null, results: Array.from({length: page === 1 ? 25 : 1},(_,i)=>({id:(page-1)*25+i+1,alerta:3,tipo:'ATENCION',estado_anterior:'PENDIENTE',estado_nuevo:'ATENDIDA',actor:9,motivo:'Revisión',registrado_en:'2026-11-14T10:00:00-03:00'})) }; }
    if (path === '/api/finanzas/cobranzas/' || path === '/api/finanzas/cobranzas/?page=1') return { count: 0, next: null, previous: null, results: [] };
    if (path.startsWith('/api/finanzas/cobranzas/resumen/')) return { moneda: 'CLP', documentos: 0, conteos: { PENDIENTE: 0, PARCIAL: 0, PAGADA: 0, VENCIDA: 0 }, monto_documentado_total: '0.00', abonado_total: '0.00', saldo_total: '0.00', saldo_vencido: '0.00' };
    if (path === '/api/dashboard/resumen/') return { generado_en: '2026-11-14T10:00:00-03:00', zona_horaria: 'America/Santiago', moneda: 'CLP', periodo: { desde: '2026-06-01', hasta: '2026-11-14' }, operacion: { obras_por_estado_actual: { PLANIFICADA: 0, EN_PROCESO: 0, SUSPENDIDA: 0, FINALIZADA: 0, CANCELADA: 0 }, presupuestos_pendientes_gerencia_actual: 0, presupuestos_pendientes_finanzas_actual: 0, obras_finalizadas_periodo: 0 }, incidencias: { criticas_activas: 0, pendientes_por_area: { ADMINISTRATIVO_FINANZAS: 0, SUPERVISOR_OBRAS: 0 }, por_estado: { PENDIENTE: 0, ATENDIDA: 0, RESUELTA: 0 }, sincronizacion: { ultima_correcta_en: null, desactualizada: false } }, rentabilidad_cerrada_periodo: { obras_con_cierre: 0, presupuesto_neto: '0.00', costo_real_neto: '0.00', margen_real_neto: '0.00' }, cobranza_actual: { documentos_vigentes: 0, monto_documentado_bruto: '0.00', abonado: '0.00', saldo: '0.00', saldo_vencido: '0.00' } };
    if (path.startsWith('/api/dashboard/serie-obras/')) { const months = Number(new URL(path, 'http://localhost').searchParams.get('meses') || 6); return { metrica: 'OBRAS_FINALIZADAS', zona_horaria: 'America/Santiago', puntos: Array.from({ length: months }, (_, i) => ({ mes: `2026-${String(i + 1).padStart(2, '0')}`, cantidad: 0 })) }; }
    if (path.startsWith('/api/dashboard/obras-activas/')) return { count: 0, next: null, previous: null, results: [] };
    if (path === '/api/clientes/') return [{id:15,nombre_legal:'Packing Valle de Coihue SpA'},{id:16,nombre_legal:'Viña Senderos del Itata SpA'}];
    if (path === '/api/reportes/catalogo/') return { moneda: 'CLP', zona_horaria: 'America/Santiago', formatos: ['csv', 'xlsx', 'pdf'], reportes: (role === 'GERENCIA' ? ['obras', 'rentabilidad', 'cobranzas'] : ['cobranzas']).map((tipo) => ({ tipo, titulo: tipo, filtros: ['desde', 'hasta', 'cliente', ...(tipo === 'obras' ? ['estado', 'fecha_base'] : tipo === 'cobranzas' ? ['estado'] : [])], formatos: ['csv', 'xlsx', 'pdf'] })) };
    if (path.startsWith('/api/reportes/') && path.includes('/exportar/')) { const type=path.split('/')[3],format=new URL(path,'http://localhost').searchParams.get('formato'),mime={csv:'text/csv',xlsx:'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',pdf:'application/pdf'}[format];return {blob:new Blob([`${type}-${format}`],{type:mime}),contentType:mime,contentDisposition:`attachment; filename="fyag-${type}-20261114-120000.${format}"`}; }
    if (path.startsWith('/api/reportes/')) { const tipo = path.split('/')[3]; return { count: 0, next: null, previous: null, results: [], totales: tipo === 'obras' ? { obras: 0, presupuesto_neto: '0.00' } : tipo === 'rentabilidad' ? { obras: 0, presupuesto_neto: '0.00', costo_real_neto: '0.00', margen_neto: '0.00' } : { documentos: 0, monto_documentado_bruto: '0.00', abonado: '0.00', saldo: '0.00', saldo_vencido: '0.00' }, periodo: { desde: '2026-11-01', hasta: '2026-11-14' }, moneda: 'CLP', fecha_corte: '2026-11-14T10:00:00-03:00' }; }
    throw new Error(`Unexpected API request ${path}`);
  };
  return send;
}
async function mount(Page, role) {
  const calls = [], request = apiFor(role, calls);
  const session = { status: 'authenticated', user: { id: 9, username: role, email: 'account@example.test', role } };
  const client = { getSnapshot: () => session, subscribe: () => () => {}, restore: async () => {}, request };
  let renderer;
  await act(async () => { renderer = Renderer.create(React.createElement(AuthProvider, { client }, React.createElement(Page))); await flush(); });
  return { renderer, calls };
}

test('safePage acepta filtros paginados propios de cada endpoint y rechaza query manipulada', () => {
  assert.equal(safePage('/api/alertas/?page=2&estado=PENDIENTE&tipo=OBRA_SUSPENDIDA&recurso_tipo=OBRA&recurso_id=4&desde=2026-01-01&hasta=2026-02-01','/api/alertas/'),2);
  assert.equal(safePage('/api/reportes/rentabilidad/?desde=2026-01-01&hasta=2026-02-01&cliente=4&page=2','/api/reportes/rentabilidad/'),2);
  assert.equal(safePage('/api/reportes/obras/?estado=FINALIZADA&fecha_base=FINALIZACION&page=2','/api/reportes/obras/'),2);
  assert.equal(safePage('/api/finanzas/cobranzas/?estado=VENCIDA&obra=4&page=2','/api/finanzas/cobranzas/'),2);
  assert.throws(()=>safePage('https://evil.example/api/alertas/?page=2&tipo=OBRA_SUSPENDIDA','/api/alertas/'),(error)=>error.name==='ApiError');
  assert.throws(()=>safePage('/api/alertas/?page=2&tipo=OBRA_SUSPENDIDA&tipo=OBRA_SUSPENDIDA','/api/alertas/'),(error)=>error.name==='ApiError');
  assert.throws(()=>safePage('/api/reportes/rentabilidad/?fecha_base=FINALIZACION&page=2','/api/reportes/rentabilidad/'),(error)=>error.name==='ApiError');
  assert.throws(()=>safePage('/api/reportes/obras/?fecha_base=FINALIZACION&estado=EN_PROCESO&page=2','/api/reportes/obras/'),(error)=>error.name==='ApiError');
  assert.throws(()=>safePage('/api/alertas/?recurso_id=4&page=2','/api/alertas/'),(error)=>error.name==='ApiError');
});

test('Reportes exporta los tres formatos con filtros permitidos por tipo solamente', { timeout: 15000 }, async () => {
  const {renderer,calls}=await mount(Reportes,'GERENCIA');
  const oldCreate=URL.createObjectURL,oldRevoke=URL.revokeObjectURL;URL.createObjectURL=()=> 'blob:reporte';URL.revokeObjectURL=()=>{};
  const field=async(id,value)=>{await act(async()=>{renderer.root.findByProps({id:'report-'+id}).props.onChange({target:{value}});await flush();});};
  const apply=async()=>{await act(async()=>{renderer.root.findByProps({id:'report-filters'}).props.onSubmit({preventDefault(){}});await flush();});};
  const exportAs=async format=>{await click(renderer,'Exportar reporte');await act(async()=>{renderer.root.findByProps({'aria-label':'Descargar '+format}).props.onClick();await flush();});return new URL(calls.filter(c=>c.path.includes('/exportar/')).at(-1).path,'http://localhost');};
  try{
    assert.equal(renderer.root.findByProps({id:'report-filters'}).props.hidden,true);
    assert.ok(!calls.some(c=>c.path==='/api/clientes/'));
    await click(renderer,'Filtros');
    assert.equal(renderer.root.findByProps({id:'report-filters'}).props.hidden,false);
    assert.ok(calls.some(c=>c.path==='/api/clientes/'));
    assert.ok(renderer.root.findByProps({id:'report-cliente'}).findAllByType('option').some(o=>o.props.children==='Packing Valle de Coihue SpA'));
    const before=calls.length;
    await field('desde','2026-11-01');await field('hasta','2026-11-14');await field('fecha_base','FINALIZACION');await field('estado','FINALIZADA');await field('cliente','15');
    assert.equal(calls.length,before);
    await apply();
    for(const format of ['CSV','XLSX','PDF']){const url=await exportAs(format);assert.equal(url.pathname,'/api/reportes/obras/exportar/');assert.equal(url.searchParams.get('formato'),format.toLowerCase());assert.equal(url.searchParams.get('fecha_base'),'FINALIZACION');assert.equal(url.searchParams.get('estado'),'FINALIZADA');assert.equal(url.searchParams.get('cliente'),'15');assert.equal(url.searchParams.get('desde'),'2026-11-01');assert.equal(url.searchParams.has('page'),false);}
    await click(renderer,'Rentabilidad');
    const latestRent=calls.filter(c=>c.path.startsWith('/api/reportes/rentabilidad/')&&!c.path.includes('/exportar/')).at(-1);
    assert.equal(latestRent.path,'/api/reportes/rentabilidad/?desde=2026-11-01&hasta=2026-11-14&cliente=15');
    let url=await exportAs('XLSX');assert.equal(url.pathname,'/api/reportes/rentabilidad/exportar/');assert.equal(url.searchParams.get('cliente'),'15');assert.equal(url.searchParams.get('desde'),'2026-11-01');assert.equal(url.searchParams.has('fecha_base'),false);assert.equal(url.searchParams.has('estado'),false);
    await click(renderer,'Cobranzas');await click(renderer,'Filtros');await field('estado','PAGADA');await apply();
    url=await exportAs('PDF');assert.equal(url.pathname,'/api/reportes/cobranzas/exportar/');assert.equal(url.searchParams.get('cliente'),'15');assert.equal(url.searchParams.get('estado'),'PAGADA');assert.equal(url.searchParams.has('fecha_base'),false);
  }finally{await act(async()=>renderer.unmount());URL.createObjectURL=oldCreate;URL.revokeObjectURL=oldRevoke;}
});

test('Dashboard acepta fechas ISO válidas y rechaza formato roto, calendario inválido y rango futuro', () => {
  assert.equal(todayInSantiago(new Date('2026-11-15T02:30:00Z')), '2026-11-14');
  assert.equal(validDashboardRange({desde:'2026-11-01',hasta:'2026-11-30'},'2026-11-30'),true);
  assert.equal(validDashboardRange({desde:'2026-2-01',hasta:'2026-11-30'},'2026-11-30'),false);
  assert.equal(validDashboardRange({desde:'2026-02-30',hasta:'2026-03-01'},'2026-11-30'),false);
  assert.equal(validDashboardRange({desde:'2026-12-01',hasta:'2026-12-02'},'2026-11-30'),false);
});

test('Dashboard descarta resumen tardío tras rango inválido y retira cifras ante error', async () => {
  const calls = [], base = apiFor('GERENCIA', calls);
  let resolveLate, fail = false, first = true;
  const late = new Promise((resolve) => { resolveLate = resolve; });
  const request = async (path, options) => {
    if (path.startsWith('/api/dashboard/resumen/')) {
      if (first) { first = false; return late; }
      if (fail) throw new ApiError(503, 'Resumen no disponible');
      const value = await base('/api/dashboard/resumen/', options);
      return { ...value, rentabilidad_cerrada_periodo: { ...value.rentabilidad_cerrada_periodo, presupuesto_neto: '98765.43' } };
    }
    return base(path, options);
  };
  const session = { status: 'authenticated', user: { id: 9, username: 'Gerencia', role: 'GERENCIA' } };
  const client = { getSnapshot: () => session, subscribe: () => () => {}, restore: async () => {}, request };
  let renderer;
  await act(async () => { renderer = Renderer.create(React.createElement(AuthProvider, { client }, React.createElement(Dashboard))); await flush(); });
  const date = async (value) => act(async () => { renderer.root.findAllByType('input')[0].props.onChange({ target: { value } }); await flush(); });
  try {
    await date('2026-02-30');
    await act(async () => { const value = await base('/api/dashboard/resumen/'); resolveLate({ ...value, rentabilidad_cerrada_periodo: { ...value.rentabilidad_cerrada_periodo, presupuesto_neto: '12345.67' } }); await flush(); });
    assert.doesNotMatch(text(renderer.toJSON()), /12\.345,67/);
    await date('');
    assert.match(text(renderer.toJSON()), /98\.765,43/);
    fail = true; await click(renderer, 'Actualizar');
    assert.doesNotMatch(text(renderer.toJSON()), /98\.765,43|12\.345,67/);
    assert.match(text(renderer.toJSON()), /Resumen no disponible/);
  } finally { await act(async () => renderer.unmount()); }
});

test('dashboard consulta los tres endpoints y despliega respuestas reales, sin mock', { timeout: 15000 }, async () => {
  const { renderer, calls } = await mount(Dashboard, 'GERENCIA');
  try { assert.ok(calls.some((c) => c.path === '/api/dashboard/resumen/')); assert.ok(calls.some((c) => c.path === '/api/dashboard/serie-obras/?meses=6')); assert.ok(calls.some((c) => c.path === '/api/dashboard/obras-activas/')); assert.match(text(renderer.toJSON()), /Obras finalizadas por mes/); assert.doesNotMatch(text(renderer.toJSON()), /Margen proyectado|Exportación generada|Datos del servidor|America\/Santiago/); assert.match(text(renderer.toJSON()), /Cobranza actual/); assert.equal(renderer.root.findAllByProps({'aria-label':'Paginación de Obras en proceso'}).length,0); } finally { await act(async () => renderer.unmount()); }
});
test('Cobranzas oculta cifras previas cuando la consulta actual falla', { timeout: 15000 }, async () => {
  let fail=false;
  const calls=[],request=async(path,options)=>{calls.push({path,options});if(path==='/api/finanzas/cobranzas/'&&!fail)return {count:0,next:null,previous:null,results:[]};if(path.startsWith('/api/finanzas/cobranzas/resumen/')&&!fail)return {moneda:'CLP',documentos:3,conteos:{PENDIENTE:1,PARCIAL:1,PAGADA:0,VENCIDA:1},monto_documentado_total:'120.00',abonado_total:'20.00',saldo_total:'100.00',saldo_vencido:'50.00'};if(fail)throw new ApiError(500,'Fallo de lectura');throw new Error(`Unexpected ${path}`);};
  const session={status:'authenticated',user:{id:9,username:'ADMINISTRATIVO_FINANZAS',email:'account@example.test',role:'ADMINISTRATIVO_FINANZAS'}};const client={getSnapshot:()=>session,subscribe:()=>()=>{},restore:async()=>{},request};let renderer;
  await act(async()=>{renderer=Renderer.create(React.createElement(AuthProvider,{client},React.createElement(Cobranzas)));await flush();});
  try{
    assert.match(text(renderer.toJSON()),/\$120/);fail=true;
    const refresh=renderer.root.findAllByType('button').find(b=>text(b)==='Actualizar');
    await act(async()=>{await refresh.props.onClick();await flush();});
    assert.doesNotMatch(text(renderer.toJSON()),/\$120|\$50/);
    assert.match(text(renderer.toJSON()),/Fallo de lectura/);
  }finally{await act(async()=>renderer.unmount());}
});

test('cobranzas consulta cartera y resumen sin exponer acciones de mutación', { timeout: 15000 }, async () => {
  const { renderer, calls } = await mount(Cobranzas, 'ADMINISTRATIVO_FINANZAS');
  try { assert.ok(calls.some((c) => c.path.startsWith('/api/finanzas/cobranzas/'))); assert.ok(calls.some((c) => c.path.startsWith('/api/finanzas/cobranzas/resumen/'))); assert.doesNotMatch(text(renderer.toJSON()), /Nuevo pago|Anular|Facturado/); } finally { await act(async () => renderer.unmount()); }
});
test('Reportes limita filtros al tipo, valida antes de consultar y oculta paginación innecesaria', { timeout: 15000 }, async () => {
  const { renderer, calls } = await mount(Reportes, 'GERENCIA');
  try {
    await click(renderer,'Filtros');
    const field=async(id,value)=>await act(async()=>{renderer.root.findByProps({id:'report-'+id}).props.onChange({target:{value}});await flush();});
    const apply=async()=>await act(async()=>{renderer.root.findByProps({id:'report-filters'}).props.onSubmit({preventDefault(){}});await flush();});
    await field('fecha_base','FINALIZACION');await apply();
    assert.equal(calls.some(c=>c.path.includes('/api/reportes/obras/')&&c.path.includes('fecha_base=FINALIZACION')),false);
    assert.match(text(renderer.toJSON()),/Selecciona el estado Finalizada/);
    await field('estado','FINALIZADA');await apply();
    assert.ok(calls.some(c=>c.path==='/api/reportes/obras/?estado=FINALIZADA&fecha_base=FINALIZACION'));
    await click(renderer,'Rentabilidad');
    const latest=calls.filter(c=>c.path.startsWith('/api/reportes/rentabilidad/')).at(-1);
    assert.equal(latest.path,'/api/reportes/rentabilidad/');
    assert.equal(renderer.root.findAllByProps({'aria-label':'Paginación del reporte rentabilidad'}).length,0);
    assert.match(text(renderer.toJSON()),/Sin importes para representar/);
    assert.match(text(renderer.toJSON()),/Margen porcentual/);
    await click(renderer,'Filtros');
    assert.equal(renderer.root.findAllByProps({id:'report-estado'}).length,0);
    assert.equal(renderer.root.findAllByProps({id:'report-fecha_base'}).length,0);
  } finally { await act(async()=>renderer.unmount()); }
});

test('Reportes gerenciales: filas legibles y cascada con margen negativo real',async()=>{
  const calls=[],base=apiFor('GERENCIA',calls);
  const session={status:'authenticated',user:{id:9,username:'gerencia',role:'GERENCIA'}};
  const client={getSnapshot:()=>session,subscribe:()=>()=>{},restore:async()=>{},request:async(path,opts)=>{
    const value=await base(path,opts);
    if(!path.startsWith('/api/reportes/rentabilidad/'))return value;
    return {...value,count:1,results:[{obra:8,codigo_obra:'OB-000008',cliente:15,cliente_nombre:'Packing Valle de Coihue SpA',finalizado_en:'2026-11-14T10:00:00-03:00',moneda:'CLP',presupuesto_neto:'1000.25',costo_real_neto:'1200.30',margen_neto:'-200.05',tiene_cortesia_sin_cobro:false}],totales:{obras:1,presupuesto_neto:'1000.25',costo_real_neto:'1200.30',margen_neto:'-200.05'}};
  }};
  let renderer;
  try{
    await act(async()=>{renderer=Renderer.create(React.createElement(AuthProvider,{client},React.createElement(Reportes)));await flush();});
    await click(renderer,'Rentabilidad');
    const body=text(renderer.toJSON());
    assert.match(body,/OB-000008/);assert.match(body,/Packing Valle de Coihue/);
    assert.match(body,/-\$200,05/);assert.match(body,/-20%/);assert.match(body,/14\/11\/2026/);
    assert.doesNotMatch(body,/cliente_nombre|presupuesto_neto|2026-11-14T/);
    assert.equal(renderer.root.findAllByProps({'aria-label':'Cascada: presupuesto neto menos costos reales igual a margen neto'}).length,1);
    assert.ok(renderer.root.findAllByType('rect').some(r=>r.props.fill==='#E34D59'&&r.props.height>0));
    assert.equal(renderer.root.findAllByProps({'aria-label':'Paginación del reporte rentabilidad'}).length,0);
  }finally{if(renderer)await act(async()=>renderer.unmount());}
});

test('reportes consulta catálogo autorizado y primer listado JSON', { timeout: 15000 }, async () => {
  const { renderer, calls } = await mount(Reportes, 'ADMINISTRATIVO_FINANZAS');
  try { assert.ok(calls.some((c) => c.path === '/api/reportes/catalogo/')); assert.ok(calls.some((c) => c.path.startsWith('/api/reportes/cobranzas/'))); assert.doesNotMatch(text(renderer.toJSON()), /Reporte de obras|Rentabilidad/); } finally { await act(async () => renderer.unmount()); }
});
test('Alertas carga la página seleccionada del historial y habilita paginación real', { timeout: 15000 }, async () => {
  const { renderer,calls }=await mount(Alertas,'GERENCIA');
  try{
    await click(renderer,'Obra suspendida');
    assert.ok(calls.some(c=>c.path==='/api/alertas/3/historial/'));
    const nav=renderer.root.findByProps({'aria-label':'Paginación del historial'});const next=nav.findAllByType('button').find(b=>text(b)==='Siguiente');
    await act(async()=>{next.props.onClick();await flush();});
    assert.ok(calls.some(c=>c.path==='/api/alertas/3/historial/?page=2'));
    assert.match(text(renderer.toJSON()),/Alerta atendida/);
    assert.match(text(renderer.toJSON()),/Usuario #9/);
    assert.doesNotMatch(text(renderer.toJSON()),/ATENCION/);
  }finally{await act(async()=>renderer.unmount());}
});

test('Alertas gerenciales: filtros confirmados, bandeja, retorno y consulta sin mutaciones',async()=>{
  const {renderer,calls}=await mount(Alertas,'GERENCIA');
  try{
    const root=renderer.root,body=()=>text(renderer.toJSON());
    assert.equal(root.findByProps({id:'alert-filters'}).props.hidden,true);
    assert.equal(root.findAllByProps({'aria-label':'Paginación de alertas'}).length,0);
    assert.match(body(),/Prioridad alta/);
    assert.match(body(),/Responsable: Supervisión/);
    assert.doesNotMatch(body(),/OBRA_SUSPENDIDA|ID recurso|Atender alerta/);
    await click(renderer,'Filtros');
    assert.equal(root.findByProps({id:'alert-filters'}).props.hidden,false);
    const before=calls.length;
    await act(async()=>{root.findByProps({id:'alert-type'}).props.onChange({target:{value:'OBRA_SUSPENDIDA'}});await flush();});
    assert.equal(calls.length,before);
    await act(async()=>{root.findByProps({id:'alert-filters'}).props.onSubmit({preventDefault(){}});await flush();});
    assert.match(calls.at(-1).path,/tipo=OBRA_SUSPENDIDA/);
    await click(renderer,'Obra suspendida');
    assert.equal(root.findAllByProps({'data-alerta':3}).length,0);
    assert.match(body(),/Historial de la alerta/);
    assert.match(body(),/Usuario #9/);
    await click(renderer,'Volver al listado');
    assert.equal(root.findByProps({id:'alert-type'}).props.value,'OBRA_SUSPENDIDA');
    assert.equal(root.findAllByProps({'data-alerta':3}).length,1);
    await click(renderer,'Resueltas');
    assert.match(calls.at(-1).path,/estado=RESUELTA/);
    assert.match(body(),/Sin alertas para estos filtros/);
    await click(renderer,'Limpiar filtros');
    assert.match(body(),/Sin alertas resueltas/);
    const metric=root.findAllByType('button').find(b=>text(b).startsWith('Alertas activas'));
    assert.ok(metric);
    await act(async()=>{metric.props.onClick();await flush();});
    assert.equal(calls.at(-1).path,'/api/alertas/');
    assert.equal(root.findAllByProps({'data-alerta':3}).length,1);
    assert.ok(calls.every(c=>!c.options.method||c.options.method==='GET'));
  }finally{await act(async()=>renderer.unmount());}
});

test('alertas solicita resumen/lista e impone matriz por rol', { timeout: 15000 }, async () => {
  for (const role of ['GERENCIA', 'SUPERVISOR_OBRAS','ADMINISTRATIVO_FINANZAS']) {
    const { renderer, calls } = await mount(Alertas, role);
    try { assert.ok(calls.some((c) => c.path === '/api/alertas/resumen/')); assert.ok(calls.some((c) => c.path === '/api/alertas/')); assert.match(text(renderer.toJSON()), role==='ADMINISTRATIVO_FINANZAS'?/Presupuesto pendiente de Finanzas/:/Obra suspendida/); await click(renderer,role==='ADMINISTRATIVO_FINANZAS'?'Presupuesto pendiente de Finanzas':'Obra suspendida'); assert.equal(renderer.root.findAllByType('button').some(b=>text(b)==='Atender alerta'),role!=='GERENCIA'); if (role === 'SUPERVISOR_OBRAS') assert.ok(calls.every((c) => !c.path.includes('COBRANZA_VENCIDA'))); } finally { await act(async () => renderer.unmount()); }
  }
});
test('AuthClient mantiene metadata de descarga y códigos públicos de conflicto de alerta', async () => {
  const calls = []; const json = (data, status = 200, headers = {}) => new Response(JSON.stringify(data), { status, headers });
  const client = createAuthClient({ fetchImpl: async (path, options) => { calls.push({ path, options }); if (path.endsWith('/csrf/')) return json({ csrfToken: 'csrf' }); if (path.endsWith('/login/')) return json({ access: 'token', csrfToken: 'csrf' }); if (path.endsWith('/me/')) return json({ id: 9, username: 'G', email: 'g@example.test', role: 'GERENCIA' }); if (path.endsWith('/exportar/?formato=pdf')) return new Response('%PDF-test', { status: 200, headers: { 'Content-Type': 'application/pdf', 'Content-Disposition': 'attachment; filename="fyag-obras-20261114-120000.pdf"' } }); return json({ motivo: ['Revisa el motivo.'], code: 'alerta_ya_atendida', password: 'hidden' }, 409, { 'Content-Type': 'application/json' }); } });
  await client.login({ email: 'g@example.test', password: 'dummy' }); const result = await client.request('/api/reportes/obras/exportar/?formato=pdf', { responseType: 'blob-response' }); assert.equal(result.contentType, 'application/pdf'); assert.match(result.contentDisposition, /filename="fyag-obras-/); assert.equal(await result.blob.text(), '%PDF-test');
  await assert.rejects(client.request('/api/alertas/3/atender/', { method: 'POST', body: { motivo: 'Revisar' } }), (error) => error instanceof ApiError && error.code === 'alerta_ya_atendida' && !Object.hasOwn(error.fieldErrors, 'password'));
});

test('Dashboard dona muestra proporciones reales, total y cinco estados incluso sin obras', async()=>{
  const calls=[],base=apiFor('GERENCIA',calls);
  let counts={PLANIFICADA:10,EN_PROCESO:15,SUSPENDIDA:0,FINALIZADA:1,CANCELADA:0};
  const request=async(path,options)=>{
    const value=await base(path,options);
    if(path==='/api/dashboard/resumen/')value.operacion.obras_por_estado_actual=counts;
    return value;
  };
  const session={status:'authenticated',user:{id:9,username:'Gerencia',role:'GERENCIA'}};
  const client={getSnapshot:()=>session,subscribe:()=>()=>{},restore:async()=>{},request};
  let renderer;
  await act(async()=>{renderer=Renderer.create(React.createElement(AuthProvider,{client},React.createElement(Dashboard)));await flush();});
  try{
    const root=renderer.root;
    assert.equal(text(root.findByProps({className:'dash-donut-center'})),'26obras');
    const segments=root.findAllByType('circle').filter(node=>node.props.className?.split(' ').includes('dash-donut-segment'));
    assert.equal(segments.length,3);
    assert.ok(segments.every(node=>Number(node.props.pathLength)===100));
    assert.ok(Math.abs(segments.reduce((sum,node)=>sum+Number(node.props.strokeDasharray.split(' ')[0]),0)-100)<1e-9);
    assert.ok(Math.abs(Number(segments[0].props.strokeDasharray.split(' ')[0])-10/26*100)<1e-9);
    assert.equal(root.findByProps({className:'dash-donut-legend'}).findAllByType('li').length,5);
    assert.deepEqual(root.findAllByProps({className:'dash-donut-percent'}).map(text),['38,5%','57,7%','0,0%','3,8%','0,0%']);
    counts={PLANIFICADA:0,EN_PROCESO:0,SUSPENDIDA:0,FINALIZADA:0,CANCELADA:0};
    await click(renderer,'Actualizar');
    assert.equal(text(root.findByProps({className:'dash-donut-center'})),'0obras');
    assert.ok(root.findAllByProps({className:'dash-donut-percent'}).every(node=>text(node)==='0,0%'));
    assert.equal(root.findAllByType('circle').filter(node=>node.props.className?.split(' ').includes('dash-donut-segment')).length,0);
  }finally{await act(async()=>renderer.unmount());}
});
