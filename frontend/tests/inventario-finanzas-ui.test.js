import test from 'node:test';
import assert from 'node:assert/strict';
import {createServer} from 'vite';
import React from 'react';
import Renderer,{act} from 'react-test-renderer';

let server,AuthProvider,Inventario;
test.before(async()=>{
 server=await createServer({configFile:false,esbuild:{jsx:'automatic'},server:{middlewareMode:true,ws:false,hmr:false},appType:'custom',optimizeDeps:{noDiscovery:true,include:[]}});
 ({AuthProvider}=await server.ssrLoadModule('/src/auth/AuthContext.jsx'));
 ({default:Inventario}=await server.ssrLoadModule('/src/pages/Inventario.jsx'));
});
test.after(async()=>{await server?.close();});
const flush=()=>new Promise(r=>setImmediate(r));
const text=n=>typeof n==='string'?n:(n?.children||[]).map(text).join('');
const BASE='/api/inventario/finanzas/';
const material={id:1,nombre:'Tubería de cobre',codigo:'tub-001',unidad:'m'};
const movement={...material,id:6,tipo:'INGRESO',cantidad:'10.000',saldo_anterior:'0.000',saldo_posterior:'10.000',referencia:'Recepción',motivo:'',creado_en:'2026-11-25T20:33:59-03:00'};
const stock={...material,descripcion:'Cobre',activo:true,saldo:'10.000',pendiente:true,valor_neto:'0.00'};
const summary={materiales:12,sin_stock:1,pendientes:1,valor_neto:'12345.67'};
const page=results=>({count:results.length,next:null,previous:null,results});
async function mount({rows=[stock]}={}){
 const calls=[],session={status:'authenticated',user:{id:2,username:'finanzas',role:'ADMINISTRATIVO_FINANZAS'}};
 let saved=null;
 const client={getSnapshot:()=>session,subscribe:()=>()=>{},restore:async()=>{},request:async(path,opts={})=>{
  const method=opts.method||'GET';calls.push({path,method,body:opts.body});const url=new URL(path,'http://localhost');
  if(method==='POST'&&url.pathname==='/api/inventario/valorizaciones/'){
   saved={...movement,id:11,tipo:'VALORIZACION',costo_unitario_neto:'8900.00',saldo_valorado_anterior:'0.000',saldo_valorado_posterior:'10.000',promedio_anterior:null,promedio_posterior:'8900.00',referencia:opts.body.referencia,referencia_ingreso:'Recepción'};
   return {...saved,ingreso:6,clave_idempotencia:opts.body.clave_idempotencia};
  }
  if(url.pathname!==BASE)throw Error('Ruta no prevista: '+path);
  switch(url.searchParams.get('seccion')){
   case 'inventario':return {...page(url.searchParams.get('buscar')==='ausente'?[]:rows),resumen:summary};
   case 'movimientos':return page([movement]);
   case 'ingresos':return page(saved?[]:[movement]);
   case 'valoraciones':return page(saved?[saved]:[]);
   case 'regularizaciones':case 'historicos':return page([]);
   default:throw Error('Sección no prevista');
  }
 }};
 let renderer;await act(async()=>{renderer=Renderer.create(React.createElement(AuthProvider,{client},React.createElement(Inventario)));await flush();});
 return {renderer,calls,close:()=>act(async()=>renderer.unmount())};
}
const click=async(r,label)=>{const b=r.root.findAllByType('button').find(b=>text(b).trim()===label);assert.ok(b,label);await act(async()=>{b.props.onClick();await flush();});};
const change=async(r,label,value)=>{const l=r.root.findAllByType('label').find(l=>text(l).startsWith(label));assert.ok(l,label);const c=l.findAll(n=>['input','select','textarea'].includes(n.type))[0];await act(async()=>{c.props.onChange({target:{value}});await flush();});};
const submit=async(r,label)=>{const f=r.root.findByProps({'aria-label':label});await act(async()=>{await f.props.onSubmit({preventDefault(){}});await flush();});};
test('Inventario AF: catálogo unificado, indicadores globales, filtros y estados vacíos',async()=>{
 const ui=await mount(),r=ui.renderer,body=()=>text(r.toJSON());
 try{
  assert.match(body(),/Tubería de cobre/);assert.match(body(),/10 m/);assert.match(body(),/12\.345,67/);assert.match(body(),/Pendiente de valoración/);
  assert.doesNotMatch(body(),/Registrar ingreso físico|Despachar material|ID de artículo/);
  assert.equal(r.root.findAllByProps({'aria-label':'Paginación de inventario'}).length,0);
  await change(r,'Buscar material','ausente');await submit(r,'Buscar y filtrar inventario');
  assert.match(body(),/Sin resultados/);assert.match(body(),/12\.345,67/);
  await click(r,'Limpiar filtros');await click(r,'Ver detalle');assert.match(body(),/Descripción/);await click(r,'Volver al listado');
  await click(r,'Movimientos');assert.match(body(),/\+10 m/);
  await click(r,'Ver detalle');
  const movementSummary=r.root.findByProps({'aria-label':'Resumen del movimiento'});
  assert.match(text(movementSummary),/Cantidad del movimiento/);assert.match(text(movementSummary),/\+10 m/);assert.match(text(movementSummary),/Stock anterior/);assert.match(text(movementSummary),/Stock resultante/);
  assert.match(body(),/Información del registro/);assert.match(body(),/Sin motivo registrado/);
  await click(r,'Volver al listado');
  await click(r,'Saldo inicial');assert.match(body(),/No hay regularizaciones registradas/);
  await click(r,'Regularizar saldo histórico');assert.match(body(),/No hay saldos históricos por regularizar/);
  assert.ok(ui.calls.every(c=>c.method==='GET'));
 }finally{await ui.close();}
});
test('Inventario AF: selección de ingreso real y registro neto confirmado',async()=>{
 const ui=await mount(),r=ui.renderer,body=()=>text(r.toJSON());
 try{
  await click(r,'Valoración');await click(r,'Valorizar ingreso');await click(r,'Seleccionar');
  assert.match(body(),/Tubería de cobre/);
  await change(r,'Costo de adquisición unitario','8900,00');await change(r,'Referencia de respaldo','Factura 5300');await submit(r,'Registro de valoración');
  const writes=ui.calls.filter(c=>c.method==='POST');
  assert.equal(writes.length,1);assert.equal(writes[0].body.ingreso,6);assert.equal(writes[0].body.costo_unitario_neto,'8900.00');assert.ok(writes[0].body.clave_idempotencia);
  assert.match(body(),/Operación confirmada/);assert.match(body(),/8\.900/);
  await click(r,'Ver detalle');assert.match(body(),/Costo promedio anterior/);assert.match(body(),/Referencia del ingreso/);
  const valuationSummary=r.root.findByProps({'aria-label':'Resumen de la valoración'});
  assert.match(text(valuationSummary),/Costo unitario neto/);assert.match(text(valuationSummary),/Costo promedio resultante/);assert.match(text(valuationSummary),/Cantidad valorada/);
  assert.match(body(),/Sin costo promedio previo/);assert.match(body(),/Cantidad valorada resultante/);
 }finally{await ui.close();}
});

test('Inventario AF: estados separados, prioridad de indicadores y accesos desde la ficha',async()=>{
 const empty={...stock,id:2,nombre:'Compresor',codigo:'com-001',unidad:'unidad',saldo:'0.000',pendiente:false,descripcion:'',valor_neto:'0.00'};
 const ui=await mount({rows:[empty,stock]}),r=ui.renderer;
 try{
  const root=r.root;
  assert.equal(root.findAllByProps({'data-tone':'danger'}).length>=1,true);
  assert.equal(root.findAllByProps({'data-tone':'warning'}).length>=1,true);
  const row=root.findAllByType('tr').find(n=>text(n).includes('Compresor'));
  const cells=row.findAllByType('td');
  assert.match(text(cells[1]),/0 unidades/);assert.match(text(cells[1]),/Sin stock/);
  assert.equal(text(cells[3]),'Valorizado');assert.doesNotMatch(text(cells[3]),/Sin stock/);
  await click(r,'Ver detalle');
  assert.match(text(r.toJSON()),/Sin descripción registrada/);
  assert.match(text(r.toJSON()),/Existencias actuales/);
  await click(r,'Ver movimientos');
  assert.ok(ui.calls.some(c=>c.path.includes('seccion=movimientos')&&c.path.includes('buscar=com-001')));
  assert.ok(ui.calls.every(c=>c.method==='GET'));
 }finally{await ui.close();}
});
