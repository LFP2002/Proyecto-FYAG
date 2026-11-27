import test, { before, after } from 'node:test';
import assert from 'node:assert/strict';
import React from 'react';
import Renderer, { act } from 'react-test-renderer';
import { createServer } from 'vite';
import {ApiError} from '../src/auth/client.js';
import { AF, G, S } from '../src/obras/domain.js';
import { obrasBackend } from './helpers/obras-backend.js';

let server, AuthProvider, Obras;
before(async () => {
  server = await createServer({ configFile: false, esbuild: { jsx: 'automatic' }, server: { middlewareMode: true, ws: false, hmr: false }, appType: 'custom', optimizeDeps: { noDiscovery: true, include: [] } });
  ({ AuthProvider } = await server.ssrLoadModule('/src/auth/AuthContext.jsx'));
  ({ default: Obras } = await server.ssrLoadModule('/src/pages/Obras.jsx'));
  globalThis.window = { confirm: () => true };
  globalThis.confirm = () => true;
});
after(async () => { delete globalThis.window; delete globalThis.confirm; await server.close(); });
const flush = () => new Promise((resolve) => setImmediate(resolve));
const text = (node) => typeof node === 'string' ? node : (node.children || []).map(text).join('');
async function mount(backend) {
  const session = { status: 'authenticated', user: { id: backend.role === 'TECNICO' ? 8 : 2, username: 'Cuenta de prueba', email: 'test@example.test', role: backend.role } };
  const client = { getSnapshot: () => session, subscribe: () => () => {}, restore: async () => {}, request: backend.request };
  let renderer;
  await act(async () => { renderer = Renderer.create(React.createElement(AuthProvider, { client }, React.createElement(Obras))); await flush(); });
  return renderer;
}
const buttons = (renderer, label) => renderer.root.findAllByType('button').filter((button) => text(button).trim() === label || button.props['aria-label'] === label);
async function click(renderer, label) {
  const button = buttons(renderer, label)[0]; assert.ok(button, `Falta el botón ${label}`); assert.ok(!button.props.disabled, `${label} deshabilitado`);
  await act(async () => { await button.props.onClick({ preventDefault() {} }); await flush(); });
}
async function input(renderer, id, value) { await act(async () => renderer.root.findByProps({ id }).props.onChange({ target: { value } })); }
async function openCosts(renderer) { await click(renderer, 'Ver obra'); await click(renderer, buttons(renderer,'Costos y cierre').length?'Costos y cierre':'Costos'); }
async function openExpenses(renderer) { await click(renderer, 'Ver obra'); await click(renderer, 'Materiales y gastos'); }
async function unmount(renderer) { await act(async () => renderer.unmount()); }

const gasto = { id: 4, obra: 1, tipo: 'MATERIAL', descripcion: 'Cable', unidad: 'metro', cantidad: '2.000', cantidad_devuelta: '0.000', costo_unitario_neto: '12.50', subtotal: '25.00', fecha_gasto: '2026-11-12', referencia_respaldo: '', observacion: '', vigente: true, anulado_por: null, anulado_en: null, motivo_anulacion: '', registrado_por: 2, creado_en: '2026-11-12T12:00:00Z', actualizado_en: '2026-11-12T12:00:00Z' };

test('Costos: POST confirmado y relectura de gastos fallida conserva formulario y bloquea reenvío', async () => {
  const backend = obrasBackend(S); backend.obras[0].estado = 'EN_PROCESO';
  backend.readFailure = (path) => backend.expenses.length > 0 && path === '/api/obras/1/gastos/?page=1';
  const renderer = await mount(backend);
  try {
    await openExpenses(renderer); await click(renderer,'Registrar gasto externo');
    for (const [field, value] of Object.entries({ descripcion: 'Cable', unidad: 'metro', cantidad: '2.000', costo_unitario_neto: '12.50', fecha_gasto: '2026-11-12' })) await input(renderer, `obras-gasto-${field}`, value);
    const form = renderer.root.findAllByType('form').find((node) => text(node).includes('Registrar gasto externo'));
    await act(async () => { await form.props.onSubmit({ preventDefault() {} }); await flush(); });
    assert.equal(backend.expenses.length, 1);
    assert.equal(renderer.root.findByProps({ id: 'obras-gasto-descripcion' }).props.value, 'Cable');
    assert.equal(buttons(renderer, 'Registrar gasto externo')[0].props.disabled, true);
    await act(async () => { await form.props.onSubmit({ preventDefault() {} }); await flush(); });
    assert.equal(backend.calls.filter((call) => call.method === 'POST').length, 1);
    assert.doesNotMatch(text(renderer.root), /Resumen económico|Control de rubros|Historial de costos/);
  } finally { await unmount(renderer); }
});

test('005C-3 Supervisor registra gasto con decimales string y actualiza datos remotos', async () => {
  const backend = obrasBackend(S); backend.obras[0].estado = 'EN_PROCESO';
  const renderer = await mount(backend);
  try {
    await openExpenses(renderer);
    const toolbar=renderer.root.findByProps({className:'so-actions so-expense-toolbar'});
    const actions=toolbar.findAllByType('button').map(button=>text(button).trim());
    assert.deepEqual(actions,['Actualizar','Autorizar material','Registrar gasto externo']); await click(renderer,'Registrar gasto externo');
    await input(renderer, 'obras-gasto-descripcion', 'Cable'); await input(renderer, 'obras-gasto-unidad', 'metro');
    await input(renderer, 'obras-gasto-cantidad', '2,000'); await input(renderer, 'obras-gasto-costo_unitario_neto', '12,50'); await input(renderer, 'obras-gasto-fecha_gasto', '2026-11-12');
    await act(async () => { await renderer.root.findAllByType('form').find((form) => text(form).includes('Registrar gasto externo'))?.props.onSubmit({ preventDefault() {} }); await flush(); });
    const call = backend.calls.find((entry) => entry.path === '/api/obras/1/gastos/' && entry.method === 'POST');
    assert.ok(call); assert.equal(call.body.cantidad, '2.000'); assert.equal(call.body.costo_unitario_neto, '12.50');
    assert.ok(backend.calls.filter((entry) => entry.path === '/api/obras/1/gastos/?page=1').length >= 2);
    assert.ok(!backend.calls.some((entry) => /costos\/(resumen|control)/.test(entry.path)));
    assert.equal(backend.expenses.length, 1);
  } finally { await unmount(renderer); }
});

test('Gerencia consulta resumen económico y actividad reciente sin acciones de escritura', async () => {
  const backend = obrasBackend(G); backend.obras[0].estado = 'EN_PROCESO'; backend.expenses = [gasto];
  backend.costTotals={materiales_total:'25.00',otros_total:'0.00',mano_obra_total:'0.00',costo_total:'25.00'};
  const renderer = await mount(backend);
  try {
    await click(renderer,'Ver obra');
    assert.ok(backend.calls.some(entry=>entry.path==='/api/obras/1/costos/resumen/'));
    await click(renderer,'Resumen económico');
    const summary=renderer.root.findByProps({'aria-label':'Resumen económico'});
    assert.match(text(summary),/Materiales/);
    assert.match(text(summary),/Mano de obra/);
    assert.match(text(summary),/\$25/);
    assert.doesNotMatch(text(summary),/Gastos de la obra|Cable/);
    await click(renderer,'Actividad reciente');
    assert.ok(backend.calls.some(entry=>entry.path.startsWith('/api/obras/1/historial/')));
    assert.match(text(renderer.root.findByProps({'aria-label':'Actividad reciente'})),/Obra creada/);
    for(const label of ['Registrar gasto externo','Validar costos','Finalizar obra'])assert.equal(buttons(renderer,label).length,0);
    assert.ok(backend.calls.every(entry=>entry.method==='GET'&&!/gastos|costos\/control|costos\/historial/.test(entry.path)));
  } finally { await unmount(renderer); }
});

test('Administrativo ve solo el resumen económico mínimo, sin consultas de gastos/control/historial', async () => {
  const backend = obrasBackend(AF); backend.obras[0].estado = 'EN_PROCESO';
  backend.costTotals={materiales_total:'25.00',otros_total:'0.00',mano_obra_total:'0.00',costo_total:'25.00'};
  const renderer = await mount(backend);
  try {
    await click(renderer,'Ver obra');
    assert.ok(backend.calls.some(entry=>entry.path==='/api/finanzas/obras-resumen/1/'));
    assert.ok(backend.calls.some(entry=>entry.path==='/api/obras/1/costos/resumen/'));
    assert.match(text(renderer.root),/Desglose de costos/);
    assert.match(text(renderer.root),/Costo real registrado/);
    assert.match(text(renderer.root),/\$25/);
    assert.ok(backend.calls.every(entry=>entry.method==='GET'&&!/gastos|costos\/control|costos\/historial/.test(entry.path)));
    assert.doesNotMatch(text(renderer.root), /Materiales y gastos|Control de rubros|Validar costos|Finalizar obra|Versión/);
  } finally { await unmount(renderer); }
});

test('Supervisor finaliza solo con validación remota, confirmación y motivo; refresca ficha', async () => {
  const backend = obrasBackend(S); backend.obras[0].estado = 'EN_PROCESO';
  backend.control.costos_validados = true; backend.control.version_validada = 0;
  const token='a'.repeat(64);
  backend.requirements={validacion:[],finalizacion:[],devoluciones:[],despachos:[{codigo:'CAB',nombre:'Cable',cantidad:'1.500',unidad:'m'}],confirmacion_remanente:token};
  const renderer = await mount(backend);
  try {
    await openCosts(renderer);
    await click(renderer,'Finalizar obra');
    await input(renderer, 'obras-finalizar-motivo', 'Trabajo terminado y revisado');
    await submitNamed(renderer,'Confirmar finalización');
    assert.ok(!backend.calls.some(entry=>entry.path==='/api/obras/1/finalizar/'));
    assert.match(text(renderer.root),/CAB · Cable: 1,500 m/);
    await act(async()=>renderer.root.findByProps({type:'checkbox'}).props.onChange({target:{checked:true}}));
    await act(async()=>{await renderer.root.findByProps({'aria-label':'Confirmar finalización'}).props.onSubmit({preventDefault(){}});await flush();});
    const call = backend.calls.find((entry) => entry.path === '/api/obras/1/finalizar/' && entry.method === 'POST');
    assert.deepEqual(call.body, { motivo: 'Trabajo terminado y revisado', confirmacion_remanente:token });
    assert.equal(backend.obras[0].estado, 'FINALIZADA');
    assert.ok(backend.calls.filter((entry) => entry.path === '/api/obras/1/').length >= 2);
    assert.equal(buttons(renderer, 'Finalizar obra').length, 0);
  } finally { await unmount(renderer); }
});

const submitNamed=async(renderer,label)=>act(async()=>{await renderer.root.findByProps({'aria-label':label}).props.onSubmit({preventDefault(){}});await flush();});

test('019F: la obra planificada muestra líneas vinculadas y distingue adicionales',async()=>{
 const backend=obrasBackend(S),request=backend.request;
 backend.request=(path,opts)=>path.includes('conciliacion-materiales/')?Promise.resolve({count:1,next:null,previous:null,results:[{
  id:1, codigo:'CAB', nombre:path.includes('ADICIONAL')?'Cable adicional':'Cable previsto', unidad:'metro',
  origen:path.includes('ADICIONAL')?'SOLICITUD':'PRESUPUESTO', presupuestado:'2.500', autorizado:'0.000', despachado:'0.000', devuelto:'0.000', neto_imputado:'0.000', pendiente_despacho:'0.000',estado:'SIN_AUTORIZACION',
 }]}):request(path,opts);
 const renderer=await mount(backend);
 try{
  await click(renderer,'Ver obra');
  assert.match(text(renderer.root),/Cable previsto.*Presupuestado2,5 m/);
  assert.match(text(renderer.root),/no acredita consumo físico/);
  await click(renderer,'Adicionales y sin vínculo histórico');
  assert.match(text(renderer.root),/Cable adicional.*Solicitud aprobada/);
  assert.doesNotMatch(text(renderer.root),/Cable previsto/);
 }finally{await unmount(renderer);}
});

test('019F: cierre obsoleto relee pendientes y exige confirmar otra vez',async()=>{
 const backend=obrasBackend(S),request=backend.request;
 backend.obras[0].estado='EN_PROCESO';backend.control.costos_validados=true;backend.control.version_validada=0;
 const nuevo='b'.repeat(64), anterior='a'.repeat(64), enviados=[];
 const despacho={codigo:'CAB',nombre:'Cable',cantidad:'5.000',unidad:'m'};
 backend.requirements={validacion:[],finalizacion:[],devoluciones:[],despachos:[despacho],confirmacion_remanente:anterior};
 backend.request=async(path,opts)=>{
  if(path.endsWith('/finalizar/')&&opts?.method==='POST'){
   enviados.push(opts.body.confirmacion_remanente);
   if(enviados.length===1){
    backend.requirements={...backend.requirements,despachos:[{...despacho,cantidad:'4.000'}],confirmacion_remanente:nuevo};
    throw new ApiError(409,'Confirma las cantidades actuales.',null,{code:'confirmacion_remanente_requerida'});
   }
  }
  return request(path,opts);
 };
 const renderer=await mount(backend);
 try{
  await openCosts(renderer);await click(renderer,'Finalizar obra');
  await input(renderer,'obras-finalizar-motivo','Trabajo terminado');
  const marcar=()=>act(async()=>renderer.root.findByProps({type:'checkbox'}).props.onChange({target:{checked:true}}));
  await marcar();await submitNamed(renderer,'Confirmar finalización');
  assert.deepEqual(enviados,[anterior]);assert.match(text(renderer.root),/4,000 m/);
  await click(renderer,'Reconsultar resultado');await click(renderer,'Finalizar obra');
  await input(renderer,'obras-finalizar-motivo','Trabajo terminado');
  assert.equal(renderer.root.findByProps({type:'checkbox'}).props.checked,false);
  await marcar();await submitNamed(renderer,'Confirmar finalización');
  assert.deepEqual(enviados,[anterior,nuevo]);
 }finally{await unmount(renderer);}
});

test('Supervisor: obra planificada muestra costos de solo lectura y estados vacíos',async()=>{
 const backend=obrasBackend(S),renderer=await mount(backend);
 try{
  await openCosts(renderer);
  assert.match(text(renderer.root),/Inicia la obra/);
   assert.match(text(renderer.root),/Por validar/);
  assert.equal(buttons(renderer,'Revisar materiales').length,0);
  assert.equal(buttons(renderer,'Validar costos').length,0);
  assert.equal(buttons(renderer,'Finalizar obra').length,0);
  assert.equal(buttons(renderer,'Registrar sin cobro').length,0);
  assert.ok(backend.calls.every(c=>c.method==='GET'));
 }finally{await unmount(renderer);}
});
test('Supervisor: sin declaraciones individuales, cortesía separada y validación vigente',async()=>{
 const backend=obrasBackend(S);backend.obras[0].estado='EN_PROCESO';
 backend.costTotals={materiales_total:'420000.00',otros_total:'0.00',mano_obra_total:'350000.00',costo_total:'770000.00'};
 const renderer=await mount(backend);
 try{
  await openCosts(renderer);
  assert.match(text(renderer.root),/\$770\.000/);
   assert.equal(buttons(renderer,'Validar costos')[0].props.disabled,false);
   assert.equal(buttons(renderer,'Revisar materiales').length,0);
   assert.equal(buttons(renderer,'Revisar otros gastos').length,0);
  await click(renderer,'Registrar sin cobro');
  await input(renderer,'obras-cortesia-justificacion','Garantía excepcional');
  await submitNamed(renderer,'Registrar servicio sin cobro');
  assert.equal(backend.courtesy.justificacion,'Garantía excepcional');
  assert.match(text(renderer.root),/\$770\.000/);
  await click(renderer,'Validar costos');
  await input(renderer,'obras-costos-motivo','Revisión completa');
  await submitNamed(renderer,'Confirmar validación');
   assert.equal(backend.control.costos_validados,true);
   assert.equal(backend.calls.filter(c=>c.method==='PATCH').length,0);
  assert.equal(buttons(renderer,'Finalizar obra').length,1);
 }finally{await unmount(renderer);}
});
test('Supervisor: rechazo de validación presenta pendientes y no reenvía automáticamente',async()=>{
 const backend=obrasBackend(S);backend.obras[0].estado='EN_PROCESO';
 backend.costTotals={materiales_total:'1.00',otros_total:'0.00',mano_obra_total:'0.00',costo_total:'1.00'};
 backend.control.materiales_estado='CON_REGISTROS';backend.control.otros_estado='NO_APLICA';
 const request=backend.request;let attempted=0;
 backend.request=async(path,opts)=>{if(path==='/api/obras/1/costos/validar/'&&opts?.method==='POST'){attempted++;throw new ApiError(409,'Costos incompletos',null,{code:'costos_incompletos',fieldErrors:{pendientes:['turnos_abiertos']}});}return request(path,opts);};
 const renderer=await mount(backend);
 try{
  await openCosts(renderer);await click(renderer,'Validar costos');await input(renderer,'obras-costos-motivo','Revisión');
  await submitNamed(renderer,'Confirmar validación');
  assert.match(text(renderer.root),/Hay turnos abiertos/);
  assert.equal(buttons(renderer,'Confirmar validación')[0].props.disabled,true);
  await submitNamed(renderer,'Confirmar validación');assert.equal(attempted,1);
  await click(renderer,'Reconsultar resultado');assert.equal(attempted,1);
  assert.equal(buttons(renderer,'Finalizar obra').length,0);
 }finally{await unmount(renderer);}
});

test('Supervisor: sin rectificación de rubros y con confirmación de servicio sin cobro',async()=>{
 const backend=obrasBackend(S);backend.obras[0].estado='EN_PROCESO';backend.control.materiales_estado='CON_REGISTROS';backend.control.otros_estado='NO_APLICA';
 backend.costTotals={materiales_total:'420000.00',otros_total:'0.00',mano_obra_total:'350000.00',costo_total:'770000.00'};
 const renderer=await mount(backend),old=window.confirm;
 try{
  await openCosts(renderer);
  assert.equal(buttons(renderer,'Actualizar').length,1);
  assert.equal(buttons(renderer,'Actualizar datos').length,0);
   assert.equal(buttons(renderer,'Rectificar materiales').length,0);
  assert.match(buttons(renderer,'Registrar sin cobro')[0].props.className,/so-danger-action/);
  await click(renderer,'Registrar sin cobro');await input(renderer,'obras-cortesia-justificacion','Garantía');
  let confirmation='';window.confirm=m=>{confirmation=m;return false;};
  await submitNamed(renderer,'Registrar servicio sin cobro');assert.match(confirmation,/no puede retirarse/);assert.equal(backend.calls.filter(c=>c.method==='POST').length,0);
  window.confirm=()=>true;await submitNamed(renderer,'Registrar servicio sin cobro');assert.equal(backend.courtesy.justificacion,'Garantía');
 }finally{window.confirm=old;await unmount(renderer);}
});


test('Supervisor: importes identificados y actividad económica con comparación comprensible',async()=>{
 const backend=obrasBackend(S);backend.obras[0].estado='EN_PROCESO';
 backend.costTotals={materiales_total:'420000.00',otros_total:'0.00',mano_obra_total:'350000.00',costo_total:'770000.00'};
 backend.costEvents=[
 {id:1,obra:1,gasto:null,control:1,cortesia:null,tipo:'DECLARACION',registrado_por:2,motivo:'Materiales revisados',datos_anteriores:{materiales_estado:'PENDIENTE',otros_estado:'NO_APLICA',version_actual:1},datos_nuevos:{materiales_estado:'CON_REGISTROS',otros_estado:'NO_APLICA',version_actual:2},creado_en:'2026-11-12T12:00:00Z'},
 {id:2,obra:1,gasto:4,control:null,cortesia:null,tipo:'CORRECCION',registrado_por:2,motivo:'Corrección de precio',datos_anteriores:{descripcion:'Cable',cantidad:'2.000',costo_unitario_neto:'12.50',subtotal:'25.00'},datos_nuevos:{descripcion:'Cable',cantidad:'2.000',costo_unitario_neto:'15.50',subtotal:'31.00',version_costos:3},creado_en:'2026-11-13T12:00:00Z'}
 ];
 const renderer=await mount(backend);
 try{
  await openCosts(renderer);
   const amounts=renderer.root.findByProps({className:'so-cost-values'});
   assert.match(text(amounts),/Materiales\$420\.000/);
   assert.equal(amounts.findAllByType('button').length,0);
  const history=renderer.root.findByProps({'aria-label':'Actividad de costos'});
  assert.match(text(history),/Declaración de rubros actualizada/);
  assert.match(text(history),/Gasto corregido/);
  assert.match(text(history),/Cable/);
  assert.match(text(history),/Con registros/);
  assert.match(text(history),/Materiales revisados/);
  assert.doesNotMatch(text(history),/CON_REGISTROS|costo_unitario_neto|materiales_estado/);
  const details=history.findAllByType('details');
  assert.equal(details.length,2);assert.ok(details.every(d=>!d.props.open));
  assert.match(text(details[0]),/Declaración de materiales/);
  assert.doesNotMatch(text(details[0]),/Declaración de otros gastos/);
  assert.match(text(details[1]),/\$12,50 CLP/);
  assert.match(text(details[1]),/\$15,50 CLP/);
  assert.ok(backend.calls.every(c=>c.method==='GET'));
 }finally{await unmount(renderer);}
});


test('Supervisor: autorizar material desde obra conserva UUID y no registra gasto manual',async()=>{
 const backend=obrasBackend(S);backend.obras[0].estado='EN_PROCESO';
 const original=backend.request;let lost=true;let saved;
 backend.request=async(path,opts={})=>{
  if(path.startsWith('/api/inventario/articulos/')){
   backend.calls.push({path,method:'GET'});
   return {count:1,next:null,previous:null,results:[{id:9,nombre:'Tubería de cobre',codigo:'TUB-01',unidad:'metro',activo:true}]};
  }
  if(path==='/api/inventario/autorizaciones-entrega/'&&opts.method==='POST'){
   backend.calls.push({path,method:'POST',body:structuredClone(opts.body)});
   saved??={id:15,tipo:'AUTORIZACION_ENTREGA',...opts.body,cantidad:'2.500'};
   if(lost){lost=false;throw new ApiError(503,'Respuesta incierta');}
   return saved;
  }
  return original(path,opts);
 };
 const renderer=await mount(backend);
 try{
  await openExpenses(renderer);await click(renderer,'Autorizar material');
  const form=()=>renderer.root.findByProps({'aria-label':'Autorizar material de Bodega'});
  const select=form().findByType('select');
  assert.ok(select.findAllByType('option').some(o=>text(o).includes('Tubería de cobre')));
  assert.equal(form().findAllByProps({'aria-label':'Páginas de material a entregar'}).length,0);
  assert.equal(buttons(renderer,'Autorizar entrega')[0].props.disabled,true);
  await act(async()=>select.props.onChange({target:{value:'9'}}));
  assert.match(text(form().findByProps({className:'so-warehouse-unit'})),/metro/);
  assert.match(text(form().findByType('details')),/Número o código de documento de respaldo/);
  assert.equal(buttons(renderer,'Autorizar entrega')[0].props.disabled,true);
  const quantity=form().findAllByType('input').find(n=>n.props.inputMode==='decimal');
  await act(async()=>quantity.props.onChange({target:{value:'2,5'}}));
  assert.equal(buttons(renderer,'Autorizar entrega')[0].props.disabled,false);
  assert.doesNotMatch(text(form()),/Costo unitario neto \(CLP\)/);
  await act(async()=>{await form().props.onSubmit({preventDefault(){}});await flush();});
  assert.equal(buttons(renderer,'Reintentar misma autorización').length,1);
  assert.ok(form().findByType('select').props.disabled);
  await click(renderer,'Reintentar misma autorización');
  const writes=backend.calls.filter(c=>c.method==='POST');
  assert.equal(writes.length,2);assert.deepEqual(writes[0].body,writes[1].body);
  assert.equal(writes[0].body.obra,1);assert.equal(writes[0].body.articulo,9);assert.equal(writes[0].body.cantidad,'2.5');
  assert.ok(writes[0].body.clave_idempotencia);
  assert.ok(writes.every(c=>c.path==='/api/inventario/autorizaciones-entrega/'));
  assert.equal(backend.expenses.length,0);assert.match(text(renderer.root),/Entrega autorizada/);
 }finally{await unmount(renderer);}
});

test('Supervisor: origen Bodega impide edición manual y autoriza devolución de la entrega real',async()=>{
 const backend=obrasBackend(S);backend.obras[0].estado='EN_PROCESO';
 backend.expenses=[{...gasto,origen:'BODEGA_019B',entrega_bodega:55},{...gasto,id:5,descripcion:'Compra directa',origen:'MANUAL',entrega_bodega:null}];
 const original=backend.request;
 backend.request=async(path,opts={})=>{
  if(path==='/api/inventario/autorizaciones-devolucion/'&&opts.method==='POST'){
   backend.calls.push({path,method:'POST',body:structuredClone(opts.body)});
   return {id:56,tipo:'AUTORIZACION_DEVOLUCION',obra:1,...opts.body,cantidad:'1.000'};
  }
  return original(path,opts);
 };
 const renderer=await mount(backend);
 try{
  await openExpenses(renderer);
  const rows=renderer.root.findAllByType('tr');
  const warehouse=rows.find(row=>text(row).includes('Cable'));
  const external=rows.find(row=>text(row).includes('Compra directa'));
  assert.match(text(warehouse),/Bodega/);assert.match(text(warehouse),/Autorizar devolución/);
  assert.doesNotMatch(text(warehouse),/Corregir|Anular|Devolver cantidad/);
  assert.match(text(external),/Corregir|Anular/);
  await click(renderer,'Autorizar devolución');
  const form=renderer.root.findByProps({'aria-label':'Autorizar devolución de Bodega'});
  await act(async()=>form.findAllByType('input').find(n=>n.props.inputMode==='decimal').props.onChange({target:{value:'1'}}));
  await act(async()=>{await form.props.onSubmit({preventDefault(){}});await flush();});
  const writes=backend.calls.filter(c=>c.method==='POST');
  assert.equal(writes.length,1);assert.equal(writes[0].body.entrega,55);assert.equal(writes[0].body.cantidad,'1');
  assert.equal(backend.expenses[0].cantidad_devuelta,'0.000');
  assert.match(text(renderer.root),/Devolución autorizada/);
 }finally{await unmount(renderer);}
});
