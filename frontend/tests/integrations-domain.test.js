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
  const alert = { id: 3, tipo: 'OBRA_SUSPENDIDA', estado: 'PENDIENTE', severidad: 'ALTA', rol_destinatario: role, recurso_tipo: 'OBRA', recurso_id: 4, recurso_codigo: 'OB-000004', obra: 4, titulo: 'Obra suspendida', descripcion: 'La obra se encuentra suspendida.', creado_en: '2026-11-14T10:00:00-03:00', atendida_por: null, atendida_en: null, motivo_atencion: null, resuelta_en: null, acciones_permitidas: ['ATENDER'] };
  const send = async (path, options = {}) => {
    calls.push({ path, options });
    if (path === '/api/alertas/resumen/') return { generado_en: '2026-11-14T10:00:00-03:00', zona_horaria: 'America/Santiago', por_estado: { PENDIENTE: 1, ATENDIDA: 0, RESUELTA: 0 }, activas: 1, por_tipo: { OBRA_SUSPENDIDA: { PENDIENTE: 1, ATENDIDA: 0, RESUELTA: 0 } }, sincronizacion: { ultima_correcta_en: null, desactualizada: false } };
    if (path === '/api/alertas/' || path === '/api/alertas/?page=1') return { count: 1, next: null, previous: null, results: [alert] };
    if (path === '/api/alertas/3/') return alert;
    if (path.startsWith('/api/alertas/3/historial/')) { const page = Number(new URL(path, 'http://localhost').searchParams.get('page') || 1); return { count: 26, next: page === 1 ? '/api/alertas/3/historial/?page=2' : null, previous: page === 2 ? '/api/alertas/3/historial/' : null, results: Array.from({length: page === 1 ? 25 : 1},(_,i)=>({id:(page-1)*25+i+1,alerta:3,tipo:'ATENCION',estado_anterior:'PENDIENTE',estado_nuevo:'ATENDIDA',actor:9,motivo:'Revisión',registrado_en:'2026-11-14T10:00:00-03:00'})) }; }
    if (path === '/api/finanzas/cobranzas/' || path === '/api/finanzas/cobranzas/?page=1') return { count: 0, next: null, previous: null, results: [] };
    if (path.startsWith('/api/finanzas/cobranzas/resumen/')) return { moneda: 'CLP', documentos: 0, conteos: { PENDIENTE: 0, PARCIAL: 0, PAGADA: 0, VENCIDA: 0 }, monto_documentado_total: '0.00', abonado_total: '0.00', saldo_total: '0.00', saldo_vencido: '0.00' };
    if (path === '/api/dashboard/resumen/') return { generado_en: '2026-11-14T10:00:00-03:00', zona_horaria: 'America/Santiago', moneda: 'CLP', periodo: { desde: '2026-06-01', hasta: '2026-11-14' }, operacion: { obras_por_estado_actual: { PLANIFICADA: 0, EN_PROCESO: 0, SUSPENDIDA: 0, FINALIZADA: 0, CANCELADA: 0 }, presupuestos_pendientes_gerencia_actual: 0, presupuestos_pendientes_finanzas_actual: 0, obras_finalizadas_periodo: 0 }, incidencias: { criticas_activas: 0, pendientes_por_area: { ADMINISTRATIVO_FINANZAS: 0, SUPERVISOR_OBRAS: 0 }, por_estado: { PENDIENTE: 0, ATENDIDA: 0, RESUELTA: 0 }, sincronizacion: { ultima_correcta_en: null, desactualizada: false } }, rentabilidad_cerrada_periodo: { obras_con_cierre: 0, presupuesto_neto: '0.00', costo_real_neto: '0.00', margen_real_neto: '0.00' }, cobranza_actual: { documentos_vigentes: 0, monto_documentado_bruto: '0.00', abonado: '0.00', saldo: '0.00', saldo_vencido: '0.00' } };
    if (path.startsWith('/api/dashboard/serie-obras/')) { const months = Number(new URL(path, 'http://localhost').searchParams.get('meses') || 6); return { metrica: 'OBRAS_FINALIZADAS', zona_horaria: 'America/Santiago', puntos: Array.from({ length: months }, (_, i) => ({ mes: `2026-${String(i + 1).padStart(2, '0')}`, cantidad: 0 })) }; }
    if (path.startsWith('/api/dashboard/obras-activas/')) return { count: 0, next: null, previous: null, results: [] };
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
  try{
    const typeSelect=()=>renderer.root.findAllByType('select').find((el)=>el.findAllByType('option').some((op)=>op.props.value==='rentabilidad'));
    const setDate=async(index,value)=>{const el=renderer.root.findAllByType('input').filter((item)=>item.props.type==='date')[index];assert.ok(el,`date input ${index} missing`);await act(async()=>{el.props.onChange({target:{value}});await flush();});};
    await setDate(0,'2026-11-01');await setDate(1,'2026-11-14');
    let selects=renderer.root.findAllByType('select');const base=selects.find((el)=>el.findAllByType('option').some((op)=>op.props.value==='FINALIZACION'));
    await act(async()=>{base.props.onChange({target:{value:'FINALIZACION'}});await flush();});
    selects=renderer.root.findAllByType('select');const state=selects.find((el)=>el.findAllByType('option').some((op)=>op.props.children==='FINALIZADA'));
    assert.ok(state,'Obras estado selector missing');
    await act(async()=>{state.props.onChange({target:{value:'FINALIZADA'}});await flush();});
    const cliente=renderer.root.findAllByType('input').find((el)=>el.props.inputMode==='numeric');await act(async()=>{cliente.props.onChange({target:{value:'15'}});await flush();});
    for(const format of ['CSV','XLSX','PDF']){await click(renderer,`Descargar ${format}`);const call=calls.filter((item)=>item.path.includes('/exportar/')).at(-1);const url=new URL(call.path,'http://localhost');assert.equal(url.pathname,'/api/reportes/obras/exportar/');assert.equal(url.searchParams.get('formato'),format.toLowerCase());assert.equal(url.searchParams.get('fecha_base'),'FINALIZACION');assert.equal(url.searchParams.get('estado'),'FINALIZADA');assert.equal(url.searchParams.get('cliente'),'15');assert.equal(url.searchParams.get('desde'),'2026-11-01');assert.equal(url.searchParams.has('page'),false);}
    await act(async()=>{typeSelect().props.onChange({target:{value:'rentabilidad'}});await flush();});
    const latestRent=calls.filter((item)=>item.path.startsWith('/api/reportes/rentabilidad/')&&!item.path.includes('/exportar/')).at(-1);
    assert.equal(latestRent.path,'/api/reportes/rentabilidad/?desde=2026-11-01&hasta=2026-11-14&cliente=15');
    await click(renderer,'Descargar XLSX');let call=calls.filter((item)=>item.path.includes('/exportar/')).at(-1);let url=new URL(call.path,'http://localhost');assert.equal(url.pathname,'/api/reportes/rentabilidad/exportar/');assert.equal(url.searchParams.get('cliente'),'15');assert.equal(url.searchParams.get('desde'),'2026-11-01');assert.equal(url.searchParams.has('fecha_base'),false);assert.equal(url.searchParams.has('estado'),false);
    await act(async()=>{typeSelect().props.onChange({target:{value:'cobranzas'}});await flush();});
    const cobranzasState=renderer.root.findAllByType('select').find((el)=>el.findAllByType('option').some((op)=>op.props.children==='PAGADA'));assert.ok(cobranzasState);
    await act(async()=>{cobranzasState.props.onChange({target:{value:'PAGADA'}});await flush();});
    await click(renderer,'Descargar PDF');call=calls.filter((item)=>item.path.includes('/exportar/')).at(-1);url=new URL(call.path,'http://localhost');assert.equal(url.pathname,'/api/reportes/cobranzas/exportar/');assert.equal(url.searchParams.get('cliente'),'15');assert.equal(url.searchParams.get('estado'),'PAGADA');assert.equal(url.searchParams.has('fecha_base'),false);
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
  try { assert.ok(calls.some((c) => c.path === '/api/dashboard/resumen/')); assert.ok(calls.some((c) => c.path === '/api/dashboard/serie-obras/?meses=6')); assert.ok(calls.some((c) => c.path === '/api/dashboard/obras-activas/')); assert.match(text(renderer.toJSON()), /Obras finalizadas por mes/); assert.doesNotMatch(text(renderer.toJSON()), /Margen proyectado|Exportación generada/); } finally { await act(async () => renderer.unmount()); }
});
test('Cobranzas oculta cifras previas cuando la consulta actual falla', { timeout: 15000 }, async () => {
  let fail=false;
  const calls=[],request=async(path,options)=>{calls.push({path,options});if(path==='/api/finanzas/cobranzas/'&&!fail)return {count:0,next:null,previous:null,results:[]};if(path.startsWith('/api/finanzas/cobranzas/resumen/')&&!fail)return {moneda:'CLP',documentos:3,conteos:{PENDIENTE:1,PARCIAL:1,PAGADA:0,VENCIDA:1},monto_documentado_total:'120.00',abonado_total:'20.00',saldo_total:'100.00',saldo_vencido:'50.00'};if(fail)throw new ApiError(500,'Fallo de lectura');throw new Error(`Unexpected ${path}`);};
  const session={status:'authenticated',user:{id:9,username:'ADMINISTRATIVO_FINANZAS',email:'account@example.test',role:'ADMINISTRATIVO_FINANZAS'}};const client={getSnapshot:()=>session,subscribe:()=>()=>{},restore:async()=>{},request};let renderer;
  await act(async()=>{renderer=Renderer.create(React.createElement(AuthProvider,{client},React.createElement(Cobranzas)));await flush();});
  try{
    assert.match(text(renderer.toJSON()),/120\.00/);fail=true;
    const refresh=renderer.root.findAllByType('button').find(b=>text(b)==='Actualizar');
    await act(async()=>{await refresh.props.onClick();await flush();});
    assert.doesNotMatch(text(renderer.toJSON()),/120\.00|50\.00/);
    assert.match(text(renderer.toJSON()),/Fallo de lectura/);
  }finally{await act(async()=>renderer.unmount());}
});

test('cobranzas consulta cartera y resumen sin exponer acciones de mutación', { timeout: 15000 }, async () => {
  const { renderer, calls } = await mount(Cobranzas, 'ADMINISTRATIVO_FINANZAS');
  try { assert.ok(calls.some((c) => c.path.startsWith('/api/finanzas/cobranzas/'))); assert.ok(calls.some((c) => c.path.startsWith('/api/finanzas/cobranzas/resumen/'))); assert.doesNotMatch(text(renderer.toJSON()), /Nuevo pago|Anular|Facturado/); } finally { await act(async () => renderer.unmount()); }
});
test('Reportes limita filtros al tipo, limpia filtros obsoletos y descarta respuesta tardía al cambiar tipo', { timeout: 15000 }, async () => {
  const { renderer, calls } = await mount(Reportes, 'GERENCIA');
  try {
    const selects=renderer.root.findAllByType('select');
    const typeSelect=selects.find((element)=>element.findAllByType('option').some((option)=>option.props.value==='rentabilidad'));
    const baseSelect=selects.find((element)=>element.findAllByType('option').some((option)=>option.props.value==='FINALIZACION'));
    assert.ok(typeSelect);assert.ok(baseSelect);
    await act(async()=>{baseSelect.props.onChange({target:{value:'FINALIZACION'}});await flush();});
    assert.equal(calls.some((c)=>c.path.includes('/api/reportes/obras/')&&c.path.includes('fecha_base=FINALIZACION')),false,'no enviar filtro de finalización incompatible');
    const stateSelect=renderer.root.findAllByType('select').find((element)=>element.findAllByType('option').some((option)=>option.children?.includes('FINALIZADA')));
    assert.ok(stateSelect,'estado de obra selector missing');
    await act(async()=>{stateSelect.props.onChange({target:{value:'FINALIZADA'}});await flush();});
    assert.ok(calls.some((c)=>c.path==='/api/reportes/obras/?estado=FINALIZADA&fecha_base=FINALIZACION'));
    await act(async()=>{typeSelect.props.onChange({target:{value:'rentabilidad'}});await flush();});
    const latest=calls.filter((c)=>c.path.startsWith('/api/reportes/rentabilidad/')).at(-1);
    assert.equal(latest.path,'/api/reportes/rentabilidad/');
    assert.doesNotMatch(latest.path,/estado|fecha_base/);
    assert.equal(renderer.root.findByProps({'aria-label':'Paginación del reporte rentabilidad'}).props['aria-label'],'Paginación del reporte rentabilidad');
  } finally { await act(async()=>renderer.unmount()); }
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
    assert.match(text(renderer.toJSON()),/ATENCION/);
  }finally{await act(async()=>renderer.unmount());}
});

test('alertas solicita resumen/lista e impone matriz por rol', { timeout: 15000 }, async () => {
  for (const role of ['GERENCIA', 'SUPERVISOR_OBRAS']) {
    const { renderer, calls } = await mount(Alertas, role);
    try { assert.ok(calls.some((c) => c.path === '/api/alertas/resumen/')); assert.ok(calls.some((c) => c.path === '/api/alertas/')); assert.match(text(renderer.toJSON()), /Obra suspendida/); if (role === 'SUPERVISOR_OBRAS') assert.ok(calls.every((c) => !c.path.includes('COBRANZA_VENCIDA'))); } finally { await act(async () => renderer.unmount()); }
  }
});
test('AuthClient mantiene metadata de descarga y códigos públicos de conflicto de alerta', async () => {
  const calls = []; const json = (data, status = 200, headers = {}) => new Response(JSON.stringify(data), { status, headers });
  const client = createAuthClient({ fetchImpl: async (path, options) => { calls.push({ path, options }); if (path.endsWith('/csrf/')) return json({ csrfToken: 'csrf' }); if (path.endsWith('/login/')) return json({ access: 'token', csrfToken: 'csrf' }); if (path.endsWith('/me/')) return json({ id: 9, username: 'G', email: 'g@example.test', role: 'GERENCIA' }); if (path.endsWith('/exportar/?formato=pdf')) return new Response('%PDF-test', { status: 200, headers: { 'Content-Type': 'application/pdf', 'Content-Disposition': 'attachment; filename="fyag-obras-20261114-120000.pdf"' } }); return json({ motivo: ['Revisa el motivo.'], code: 'alerta_ya_atendida', password: 'hidden' }, 409, { 'Content-Type': 'application/json' }); } });
  await client.login({ email: 'g@example.test', password: 'dummy' }); const result = await client.request('/api/reportes/obras/exportar/?formato=pdf', { responseType: 'blob-response' }); assert.equal(result.contentType, 'application/pdf'); assert.match(result.contentDisposition, /filename="fyag-obras-/); assert.equal(await result.blob.text(), '%PDF-test');
  await assert.rejects(client.request('/api/alertas/3/atender/', { method: 'POST', body: { motivo: 'Revisar' } }), (error) => error instanceof ApiError && error.code === 'alerta_ya_atendida' && !Object.hasOwn(error.fieldErrors, 'password'));
});
