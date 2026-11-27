import test from 'node:test';
import assert from 'node:assert/strict';
import React from 'react';
import Renderer,{act} from 'react-test-renderer';
import {createServer} from 'vite';
let server,AuthProvider,Inventario;
test.before(async()=>{
 server=await createServer({configFile:false,esbuild:{jsx:'automatic'},server:{middlewareMode:true,ws:false,hmr:false},appType:'custom',optimizeDeps:{noDiscovery:true,include:[]}});
 ({AuthProvider}=await server.ssrLoadModule('/src/auth/AuthContext.jsx'));
 ({default:Inventario}=await server.ssrLoadModule('/src/pages/Inventario.jsx'));
});
test.after(async()=>{await server?.close();});
const flush=()=>new Promise(r=>setImmediate(r));
const text=n=>typeof n==='string'?n:(n?.children||[]).map(text).join('');
const ROOT='/api/inventario/disponibilidad/',identity={articulo:4,codigo:'lub-001',nombre:'Aceite para compresor',unidad:'litro'};
const stock={...identity,id:4,activo:true,descripcion:'Lubricante',saldo:'10.500'};
const event={...identity,id:8,tipo:'ENTREGA',obra:'OB-000003',cantidad:'2.500',referencia:'OT-5',motivo:'Despacho',creado_en:'2026-11-25T20:33:59-03:00',origen:'PRESUPUESTO'};
const pending={...event,id:9,tipo:'AUTORIZACION_ENTREGA',cantidad:'5.000',ejecutada:'2.500',pendiente:'2.500',saldo:'10.500',bloqueo:null};
const returning={...pending,id:10,tipo:'AUTORIZACION_DEVOLUCION',cantidad:'1.500',ejecutada:'0.000',pendiente:'1.500'};
const resumen={disponibles:24,sin_stock:3,despachos_pendientes:5};
async function mount(){
 const calls=[],session={status:'authenticated',user:{id:2,username:'supervisor',role:'SUPERVISOR_OBRAS'}};
 const client={getSnapshot:()=>session,subscribe:()=>()=>{},restore:async()=>{},request:async(path,opts={})=>{
  calls.push({path,method:opts.method||'GET'});const u=new URL(path,'http://localhost');assert.equal(u.pathname,ROOT);
  const q=u.searchParams,section=q.get('seccion'),vista=q.get('vista');
  const rows=section==='disponibilidad'?(q.get('stock')==='sin_stock'?[]:[stock]):section==='pendientes'?[pending]:vista==='por_recibir'?[returning]:[event];
  const results=q.get('buscar')==='Inexistente'?[]:rows;
  return {count:results.length,results,next:null,previous:null,resumen};
 }};
 let renderer;await act(async()=>{renderer=Renderer.create(React.createElement(AuthProvider,{client},React.createElement(Inventario)));await flush();});
 return {renderer,calls,close:()=>act(async()=>renderer.unmount())};
}
async function click(r,label){const b=r.root.findAllByType('button').find(b=>text(b).trim()===label);assert.ok(b,label);assert.ok(!b.props.disabled,label);await act(async()=>{b.props.onClick();await flush();});}
test('Supervisor: tres consultas, indicadores globales, remanentes y detalle de solo lectura',async()=>{
 const ui=await mount(),r=ui.renderer,body=()=>text(r.toJSON());
 try{
  assert.match(body(),/Disponibilidad de materiales/);assert.match(body(),/Aceite para compresor/);
  assert.match(body(),/Materiales disponibles24/);assert.match(body(),/Materiales sin stock3/);
  const query=r.root.findByType('form');assert.equal(query.findByType('select').props['aria-label'],'Disponibilidad');assert.equal(query.findByProps({'aria-label':'Buscar material'}).type,'input');
  assert.match(body(),/Despachos pendientes5/);
  assert.doesNotMatch(body(),/Autorizar entrega|Autorizar devolución|Registrar ingreso|Valorizar ingreso|Movimientos|Costo unitario/);
  await click(r,'Ver detalle');assert.match(body(),/Existencias físicas/);assert.match(body(),/10,5 litro/);
  await click(r,'Volver al listado');await click(r,'Pendientes de despacho');
  assert.match(body(),/Despacho parcial/);assert.match(body(),/2,5 litro/);
  await click(r,'Ver detalle');assert.match(body(),/Cantidad autorizada/);assert.match(body(),/Pendiente de despacho/);
  await click(r,'Volver al listado');await click(r,'Entregas y devoluciones');assert.match(body(),/Entregado/);
  assert.equal(r.root.findByType('form').findByType('select').props['aria-label'],'Tipo de registro');
  await act(async()=>{r.root.findByType('select').props.onChange({target:{value:'por_recibir'}});await flush();});
  assert.match(body(),/1,5 litro/);assert.ok(ui.calls.some(c=>c.path.includes('vista=por_recibir')));
  assert.ok(ui.calls.every(c=>c.method==='GET'&&c.path.startsWith(ROOT)));
 }finally{await ui.close();}
});
test('Supervisor: filtros y búsqueda de servidor no alteran indicadores globales',async()=>{
 const ui=await mount(),r=ui.renderer;
 try{
  await click(r,'Materiales sin stock3');
  assert.ok(ui.calls.some(c=>c.path.includes('stock=sin_stock')));
  assert.match(text(r.toJSON()),/No hay registros para mostrar/);
  assert.match(text(r.toJSON()),/Materiales disponibles24/);
  await click(r,'Limpiar filtros');
  await act(async()=>r.root.findByProps({'aria-label':'Buscar material'}).props.onChange({target:{value:'Inexistente'}}));
  const form=r.root.findByType('form');await act(async()=>{form.props.onSubmit({preventDefault(){}});await flush();});
  assert.ok(ui.calls.some(c=>c.path.includes('buscar=Inexistente')));
  assert.match(text(r.toJSON()),/No hay registros para mostrar/);
  await click(r,'Limpiar filtros');assert.match(text(r.toJSON()),/Aceite para compresor/);
 }finally{await ui.close();}
});
